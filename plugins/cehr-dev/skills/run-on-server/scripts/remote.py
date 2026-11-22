#!/usr/bin/env python3
"""Run whitelisted commands on a listed server over ssh, and read only logs and metrics.

This is the only way the plugin reaches a server. A job's output goes to a log file on
the server and is never returned, and a file can be read only when its folder and its
name are both listed in ~/.config/cehr-dev/servers.json, which the user writes.
Every ssh call and every refusal is appended to ~/.config/cehr-dev/audit.jsonl.
Python 3.8+, standard library only.
"""
import argparse
import datetime
import fnmatch
import json
import os
import posixpath
import re
import shlex
import subprocess
import sys

CONFIG = os.path.expanduser("~/.config/cehr-dev/servers.json")
AUDIT = os.path.expanduser("~/.config/cehr-dev/audit.jsonl")
MAX_CHARS, MAX_LINES, LINE_WIDTH = 20000, 300, 400
# never readable, whatever the config says
DATA_SUFFIXES = (".parquet", ".arrow", ".feather", ".pkl", ".pickle", ".npy", ".npz", ".pt",
                 ".pth", ".bin", ".safetensors", ".h5", ".hdf5", ".db", ".sqlite", ".jsonl")
NAME = re.compile(r"^[A-Za-z0-9_-]{1,40}$")
BRANCH = re.compile(r"^[A-Za-z0-9._/-]{1,100}$")
SAFE_ARG = re.compile(r"^[A-Za-z0-9_./:,=@%+-]+$")
STATUS = ("nvidia-smi --query-gpu=index,name,utilization.gpu,memory.used,memory.total --format=csv; "
          "free -g; df -h; uptime; "
          "ps -eo user,pid,etime,pcpu,rss,args --sort=-rss | head -25 | cut -c1-200")


def audit(**fields):
    """Append one line to the user's audit file, which only they should edit."""
    entry = {"time": datetime.datetime.now().astimezone().isoformat(timespec="seconds"),
             "cwd": os.getcwd(), "argv": sys.argv[1:], **fields}
    fd = os.open(AUDIT, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o600)
    with os.fdopen(fd, "a") as f:
        f.write(json.dumps(entry) + "\n")


def fail(message):
    try:
        audit(outcome="refused", reason=message)
    except OSError:
        pass  # no config folder yet, so nothing has been set up to audit
    sys.exit(f"refused: {message}")


def load(name):
    if not os.path.exists(CONFIG):
        fail(f"no server list at {CONFIG}. The user writes it (see references/servers-template.json); "
             "do not create or edit it yourself.")
    with open(CONFIG) as f:
        cfg = json.load(f)
    if name not in cfg.get("servers", {}):
        fail(f"'{name}' is not a listed server. Listed: {', '.join(cfg.get('servers', {})) or 'none'}")
    return cfg, cfg["servers"][name]


def ssh(host, remote, dry_run=False):
    if dry_run:
        audit(outcome="dry run", host=host, remote=remote)
        return 0, f"[dry run] ssh {host} {remote}"
    audit(outcome="sent", host=host, remote=remote)  # before it runs: no record, no command
    try:
        r = subprocess.run(["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=10", host, remote],
                           capture_output=True, text=True, errors="replace", timeout=120)
    except subprocess.TimeoutExpired:
        fail(f"ssh to {host} timed out")
    out = (r.stdout + r.stderr)[:MAX_CHARS]
    audit(outcome="finished", host=host, exit=r.returncode, output_chars=len(out))
    return r.returncode, out


def check_path(cfg, server, path, is_file):
    """Refuse unless the path is inside a listed folder and, for a file, has a listed name."""
    if not path.startswith("/"):
        fail(f"{path}: give an absolute path")
    path = posixpath.normpath(path)
    if not any(path == root or path.startswith(root.rstrip("/") + "/") for root in server.get("read_roots", [])):
        fail(f"{path} is not inside a readable folder: {server.get('read_roots', [])}")
    for part in path.split("/"):
        if any(fnmatch.fnmatch(part, pattern) for pattern in server.get("deny_parts", [])):
            fail(f"{path}: '{part}' is on the deny list")
    if is_file:
        name = posixpath.basename(path)
        if name.lower().endswith(DATA_SUFFIXES):
            fail(f"{name} is a data file; data files are never read")
        if not any(fnmatch.fnmatch(name, pattern) for pattern in cfg.get("read_names", [])):
            fail(f"{name} is not a readable file name: {cfg.get('read_names', [])}")
    return path


def readable(cfg, server, host, path, is_file, dry_run):
    """Check the path, then check where it really points: a symlink must not lead to data."""
    path = check_path(cfg, server, path, is_file)
    if dry_run:
        return path
    rc, real = ssh(host, f"realpath -e -- {shlex.quote(path)}")
    if rc:
        fail(f"{path} does not exist on {host}")
    return check_path(cfg, server, real.strip(), is_file)


def job_command(server, env, words):
    """The shell line of a job: only listed commands, plain arguments, listed variables."""
    line = " ".join(words)
    if not any(line.startswith(prefix) for prefix in server.get("run", [])):
        fail(f"'{line}' does not start with a listed command: {server.get('run', [])}")
    for word in words:
        if not SAFE_ARG.match(word) or ".." in word:
            fail(f"argument '{word}' is not allowed (quotes, spaces, shell syntax, or '..')")
    assigns = []
    for item in env:
        key, _, value = item.partition("=")
        if key not in server.get("env", []) or not SAFE_ARG.match(value or "x"):
            fail(f"variable '{item}' is not allowed; listed variables: {server.get('env', [])}")
        assigns.append(f"{key}={value}")
    return " ".join(assigns + [shlex.quote(w) for w in words])


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dry-run", action="store_true", help="print the ssh command instead of running it")
    sub = ap.add_subparsers(dest="action", required=True)
    for action in ("status", "jobs", "rules"):
        sub.add_parser(action).add_argument("server")
    sub.add_parser("audit", help="show the last lines of the audit file").add_argument("-n", type=int, default=20)
    p = sub.add_parser("start", help="start a listed command in tmux; its output goes to a log file")
    p.add_argument("server")
    p.add_argument("name")
    p.add_argument("--env", action="append", default=[], metavar="KEY=VALUE")
    p.add_argument("command", nargs=argparse.REMAINDER, help="after --")
    p = sub.add_parser("stop")
    p.add_argument("server")
    p.add_argument("name")
    p = sub.add_parser("git")
    p.add_argument("server")
    p.add_argument("what", choices=["status", "fetch", "pull", "log", "checkout"])
    p.add_argument("branch", nargs="?")
    p = sub.add_parser("ls")
    p.add_argument("server")
    p.add_argument("folder")
    p = sub.add_parser("tail")
    p.add_argument("server")
    p.add_argument("path")
    p.add_argument("-n", type=int, default=50)
    p = sub.add_parser("grep", help="fixed-string search in one log or metrics file")
    p.add_argument("server")
    p.add_argument("pattern")
    p.add_argument("path")
    args = ap.parse_args()

    if args.action == "audit":
        if os.path.exists(AUDIT):
            with open(AUDIT) as f:
                print("".join(f.readlines()[-max(1, args.n):]).rstrip())
        return
    cfg, server = load(args.server)
    host, dry = args.server, args.dry_run
    if args.action == "rules":
        print(json.dumps({"read_names": cfg.get("read_names", []), **server}, indent=2))
        return
    if args.action == "status":
        remote = STATUS
    elif args.action == "jobs":
        remote = "tmux ls 2>/dev/null || echo 'no tmux sessions'"
    elif args.action == "start":
        if not NAME.match(args.name):
            fail("job name: letters, digits, _ and - only")
        words = list(args.command)  # argparse may or may not keep the "--"
        while words[:1] == ["--env"] and len(words) > 1:
            args.env.append(words[1])
            words = words[2:]
        if words[:1] == ["--"]:
            words = words[1:]
        if not words or words[0].startswith("-"):
            fail("usage: start <server> <name> [--env KEY=VALUE ...] -- <command>")
        log = posixpath.join(server["log_dir"], f"{args.name}.log")
        check_path(cfg, server, log, is_file=True)
        inner = f"{server.get('setup', 'true')}; {job_command(server, args.env, words)} > {shlex.quote(log)} 2>&1; echo exit=$? >> {shlex.quote(log)}"
        remote = (f"[ ! -e {shlex.quote(log)} ] || {{ echo 'log exists, pick another name'; exit 3; }}; "
                  f"mkdir -p {shlex.quote(server['log_dir'])} && cd {shlex.quote(server['repo'])} && "
                  f"tmux new-session -d -s cc-{args.name} {shlex.quote(inner)} && echo started cc-{args.name}, log {shlex.quote(log)}")
    elif args.action == "stop":
        if not NAME.match(args.name):
            fail("job name: letters, digits, _ and - only")
        remote = f"tmux kill-session -t cc-{args.name} && echo stopped cc-{args.name}"
    elif args.action == "git":
        git = f"git -C {shlex.quote(server['repo'])} "
        if args.what == "checkout":
            if not args.branch or not BRANCH.match(args.branch) or args.branch.startswith("-"):
                fail("checkout needs a plain branch name")
            remote = git + f"checkout {shlex.quote(args.branch)}"
        else:
            remote = git + {"status": "status --short --branch", "fetch": "fetch", "pull": "pull --ff-only",
                            "log": "log -n 15 --oneline"}[args.what]
    elif args.action == "ls":
        folder = readable(cfg, server, host, args.folder, False, dry)
        remote = f"ls -lAh -- {shlex.quote(folder)} | head -200"
    elif args.action == "tail":
        path = readable(cfg, server, host, args.path, True, dry)
        remote = f"tail -n {max(1, min(args.n, MAX_LINES))} -- {shlex.quote(path)} | cut -c1-{LINE_WIDTH}"
    else:
        path = readable(cfg, server, host, args.path, True, dry)
        remote = f"grep -n -F -m 100 -e {shlex.quote(args.pattern)} -- {shlex.quote(path)} | cut -c1-{LINE_WIDTH}"
    rc, out = ssh(host, remote, dry)
    print(out.rstrip())
    sys.exit(rc)


if __name__ == "__main__":
    main()
