#!/usr/bin/env python3
"""Run whitelisted commands on a listed server over ssh, and read only logs and metrics.

The only way the plugin reaches a server. A job's output goes to a log file on the server
and is never returned, and a file is read only when its folder and its name are both
listed in ~/.config/cehr-dev/servers.json. Every ssh call and every refusal is appended
to ~/.config/cehr-dev/audit.jsonl. Python 3.8+, standard library only.
"""
import argparse
import datetime
import fnmatch
import json
import os
import posixpath
import re
import subprocess
import sys
from shlex import quote

FOLDER = os.path.expanduser("~/.config/cehr-dev")
CONFIG, AUDIT = os.path.join(FOLDER, "servers.json"), os.path.join(FOLDER, "audit.jsonl")
# what `accept` writes for a new server: every command of these repositories, nothing else
PACKAGES = {"cehrgpt": "cehrgpt", "cehrgpt-turbo": "cehrgpt_turbo"}
READ_NAMES = ["*.log", "trainer_state.json", "metrics.json", "*_metrics.json", "all_results.json",
              "train_results.json", "eval_results.json"]
PROBE = ('printf "home=%s\\n" "$HOME"; for d in ' + " ".join(PACKAGES) + '; do [ -d "$HOME/$d/.git" ] && '
         'printf "repo=%s venv=%s\\n" "$d" "$([ -f "$HOME/$d/.venv/bin/activate" ] && echo yes || echo no)"; done')
# never readable, whatever the list says
DATA_SUFFIXES = (".parquet", ".arrow", ".feather", ".pkl", ".pickle", ".npy", ".npz", ".pt",
                 ".pth", ".bin", ".safetensors", ".h5", ".hdf5", ".db", ".sqlite", ".jsonl")
NAME = re.compile(r"^[A-Za-z0-9_-]{1,40}$")
BRANCH = re.compile(r"^[A-Za-z0-9._/][A-Za-z0-9._/-]{0,99}$")
SAFE_ARG = re.compile(r"^[A-Za-z0-9_./:,=@%+-]+$")
STATUS = ("nvidia-smi --query-gpu=index,name,utilization.gpu,memory.used,memory.total --format=csv; "
          "free -g; df -h; uptime; ps -eo user,pid,etime,pcpu,rss,args --sort=-rss | head -25 | cut -c1-200")
GIT = {"status": "status --short --branch", "fetch": "fetch", "pull": "pull --ff-only"}


def audit(**fields):
    """Append one line to the user's audit file."""
    os.makedirs(FOLDER, exist_ok=True)
    entry = {"time": datetime.datetime.now().astimezone().isoformat(timespec="seconds"),
             "cwd": os.getcwd(), "argv": sys.argv[1:], **fields}
    with os.fdopen(os.open(AUDIT, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o600), "a") as f:
        f.write(json.dumps(entry) + "\n")


def fail(message):
    audit(outcome="refused", reason=message)
    sys.exit(f"refused: {message}")


def ssh(host, remote):
    audit(outcome="sent", host=host, remote=remote)  # before it runs: no record, no command
    r = subprocess.run(["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=10", host, remote],
                       capture_output=True, text=True, errors="replace")
    out = (r.stdout + r.stderr)[:20000]
    audit(outcome="finished", host=host, exit=r.returncode, output_chars=len(out))
    return r.returncode, out


def proposal(host, read_roots):
    """The default entry for a new server, from where the known repositories are on it."""
    rc, out = ssh(host, PROBE)
    home = next((line[5:] for line in out.splitlines() if line.startswith("home=")), "")
    if rc or not home.startswith("/"):
        fail(f"cannot reach {host} or read its home folder: {out.strip()[:200]}")
    repos = {}
    for line in out.splitlines():
        name = line.split()[0][5:] if line.startswith("repo=") else None
        if name in PACKAGES:
            repos[name] = {"path": f"{home}/{name}",
                           "setup": "source .venv/bin/activate" if "venv=yes" in line else "true",
                           "run": [f"python -m {PACKAGES[name]}.", f"python -u -m {PACKAGES[name]}.", "bash scripts/"]}
    if not repos:
        fail(f"none of {list(PACKAGES)} found in {home} on {host}; the user writes this entry by hand")
    if any(not root.startswith("/") or ".." in root for root in read_roots):
        fail("--read-root takes absolute folders")
    return {"repos": repos, "log_dir": f"{home}/cc_logs", "read_roots": [f"{home}/cc_logs"] + read_roots,
            "deny_parts": ["dataset_prepared", "patient_sequence"],
            "env": ["CUDA_VISIBLE_DEVICES", "HF_HOME", "PYTHONPATH"]}


def check_path(cfg, server, path):
    """Refuse unless the file is inside a listed folder and has a listed name."""
    path = posixpath.normpath(path)
    if not any(path.startswith(root.rstrip("/") + "/") for root in server.get("read_roots", [])):
        fail(f"{path} is not inside a readable folder: {server.get('read_roots', [])}")
    for part in path.split("/"):
        if any(fnmatch.fnmatch(part, pattern) for pattern in server.get("deny_parts", [])):
            fail(f"{path}: '{part}' is on the deny list")
    name = posixpath.basename(path)
    if name.lower().endswith(DATA_SUFFIXES):
        fail(f"{name} is a data file; data files are never read")
    if not any(fnmatch.fnmatch(name, pattern) for pattern in cfg.get("read_names", [])):
        fail(f"{name} is not a readable file name: {cfg.get('read_names', [])}")
    return path


def repository(server, name):
    """The repository a job or git command works in; a server may list several."""
    repos = server.get("repos", {})
    if name is None and len(repos) == 1:
        name = next(iter(repos))
    if name not in repos:
        fail(f"choose a listed repository with --repo: {', '.join(repos) or 'none listed'}")
    return repos[name]


def job_command(server, repo, env, words):
    """The shell line of a job: only listed commands, plain arguments, listed variables."""
    line = " ".join(words)
    if not any(line.startswith(prefix) for prefix in repo.get("run", [])):
        fail(f"'{line}' does not start with a listed command: {repo.get('run', [])}")
    for word in words:
        if not SAFE_ARG.match(word) or ".." in word:
            fail(f"argument '{word}' is not allowed (quotes, spaces, shell syntax, or '..')")
    for item in env:
        if "=" not in item or item.split("=")[0] not in server.get("env", []) or not SAFE_ARG.match(item):
            fail(f"variable '{item}' is not allowed; listed variables: {server.get('env', [])}")
    return " ".join(env + words)


def parse_args():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="action", required=True)
    p = {name: sub.add_parser(name) for name in ("status", "jobs", "start", "stop", "git", "tail", "propose", "accept")}
    for parser in p.values():
        parser.add_argument("server")
    for name in ("start", "stop"):
        p[name].add_argument("name")
    for name in ("start", "git"):
        p[name].add_argument("--repo")
    p["start"].add_argument("--env", action="append", default=[], metavar="KEY=VALUE")
    p["start"].add_argument("command", nargs="+", help="after --")
    p["git"].add_argument("what", choices=[*GIT, "checkout"])
    p["git"].add_argument("branch", nargs="?")
    p["tail"].add_argument("path")
    p["tail"].add_argument("-n", type=int, default=50)
    for name in ("propose", "accept"):
        p[name].add_argument("--read-root", action="append", default=[], help="another folder of logs and metrics")
    return ap.parse_args()


def add_server(args, cfg, host):
    """`propose` shows the default entry for a new server; `accept` also writes it."""
    entry = proposal(host, args.read_root)
    if args.action == "accept":
        cfg["servers"][host] = entry
        with os.fdopen(os.open(CONFIG, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600), "w") as f:
            json.dump(cfg, f, indent=2)
        audit(outcome="server added", host=host, entry=entry)
    print(json.dumps({host: entry}, indent=2))


def remote_command(args, cfg, server, host):
    """The shell line a request runs on the server, after every check."""
    if args.action in ("start", "stop") and not NAME.match(args.name):
        fail("job name: letters, digits, _ and - only")
    if args.action == "status":
        return STATUS
    if args.action == "jobs":
        return "tmux ls 2>/dev/null || echo 'no tmux sessions'"
    if args.action == "stop":
        return f"tmux kill-session -t cc-{args.name} && echo stopped cc-{args.name}"
    if args.action == "start":
        repo = repository(server, args.repo)
        log = quote(check_path(cfg, server, posixpath.join(server["log_dir"], f"{args.name}.log")))
        job = f"{repo.get('setup', 'true')}; {job_command(server, repo, args.env, args.command)} > {log} 2>&1; echo exit=$? >> {log}"
        return (f"[ ! -e {log} ] || {{ echo 'log exists, pick another name'; exit 3; }}; "
                f"mkdir -p {quote(server['log_dir'])} && cd {quote(repo['path'])} && "
                f"tmux new-session -d -s cc-{args.name} {quote(job)} && echo started cc-{args.name}, log {log}")
    if args.action == "git":
        if args.what == "checkout" and not (args.branch and BRANCH.match(args.branch)):
            fail("checkout needs a plain branch name")
        return f"git -C {quote(repository(server, args.repo)['path'])} " + (
            f"checkout {quote(args.branch)}" if args.what == "checkout" else GIT[args.what])
    rc, real = ssh(host, f"realpath -e -- {quote(check_path(cfg, server, args.path))}")
    if rc:
        fail(f"{args.path} does not exist on {host}")
    # checked again where it really points: a symlink must not lead to data
    return f"tail -n {max(1, min(args.n, 300))} -- {quote(check_path(cfg, server, real.strip()))} | cut -c1-400"


def main():
    args = parse_args()
    host, cfg = args.server, {"read_names": READ_NAMES, "servers": {}}
    if os.path.exists(CONFIG):
        with open(CONFIG) as f:
            cfg = json.load(f)
    server = cfg["servers"].get(host)
    if args.action in ("propose", "accept"):
        if server:
            fail(f"'{host}' is already listed; only the user changes an existing entry")
        return add_server(args, cfg, host)
    if not server:
        fail(f"'{host}' is not a listed server (listed: {', '.join(cfg['servers']) or 'none'}). "
             f"Offer the user `propose {host}`; see references/setup.md")
    rc, out = ssh(host, remote_command(args, cfg, server, host))
    print(out.rstrip())
    sys.exit(rc)


if __name__ == "__main__":
    main()
