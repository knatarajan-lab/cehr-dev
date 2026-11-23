#!/usr/bin/env python3
"""PreToolUse guard: remote servers are reached only through the run-on-server script.

Blocks a shell command that runs ssh, scp, sftp, or rsync to a host, and any change to
~/.config/cehr-dev, which is the user's. A command that only mentions ssh is left alone.
It blocks by default; the user turns it off by creating ~/.config/cehr-dev/declined
while no server is listed.
"""
import datetime
import json
import os
import re
import shlex
import sys

FOLDER = os.path.expanduser("~/.config/cehr-dev")
REMOTE = {"ssh", "scp", "sftp", "mosh", "autossh", "sshpass"}
WRAPPERS = {"sudo", "command", "exec", "time", "nohup", "env", "xargs", "timeout", "watch",
            "bash", "sh", "zsh", "eval"}
ASSIGNMENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")
OWN_PATH = re.compile(r"^(~|/|\$HOME|\$\{HOME\}).*\.config/cehr-dev")


def blocked(line):
    """Whether a shell line runs a remote program or touches the user's folder. Best effort."""
    for part in line.splitlines():
        lexer = shlex.shlex(part, posix=True, punctuation_chars=True)
        lexer.whitespace_split = True
        try:
            tokens = list(lexer)
        except ValueError:  # unbalanced quotes
            tokens = part.split()
        at_program = True  # the next word names the program that runs
        rsync = False
        for token in tokens:
            if set(token) <= set(";&|()"):
                at_program = True
                continue
            name = os.path.basename(token)
            if OWN_PATH.match(token) or any(blocked(inner) for inner in re.split(r"\$\(|`", token)[1:]):
                return True
            if not at_program:
                if rsync and re.match(r"^[\w.@-]+:", token):  # host:path
                    return True
                continue
            if name in REMOTE or (" " in token and blocked(token)):  # the second: bash -c '...'
                return True
            # options, numbers, VAR=value and wrappers such as sudo come before the program
            at_program = token.startswith("-") or token.isdigit() or bool(ASSIGNMENT.match(token)) or name in WRAPPERS
            rsync = name == "rsync"
    return False


def main():
    if not os.path.exists(os.path.join(FOLDER, "servers.json")) and os.path.exists(os.path.join(FOLDER, "declined")):
        return
    # stdin from Claude Code: {"session_id", "transcript_path", "cwd", "hook_event_name": "PreToolUse",
    #   "tool_name", "tool_input"}; tool_input is the tool call's own arguments, e.g. Bash
    #   {"command", "description"}, Edit/Write/MultiEdit {"file_path", ...}, NotebookEdit {"notebook_path", ...}
    try:
        tool_input = json.load(sys.stdin).get("tool_input") or {}
    except ValueError:
        return
    path = str(tool_input.get("file_path") or tool_input.get("notebook_path") or "")
    command = str(tool_input.get("command") or "")
    edits_folder = path and os.path.realpath(os.path.expanduser(path)).startswith(os.path.realpath(FOLDER) + os.sep)
    if not edits_folder and not blocked(command):
        return
    entry = {"time": datetime.datetime.now().astimezone().isoformat(timespec="seconds"),
             "cwd": os.getcwd(), "outcome": "blocked by hook", "attempted": (command or f"edit {path}")[:500]}
    try:
        with open(os.path.join(FOLDER, "audit.jsonl"), "a") as f:
            f.write(json.dumps(entry) + "\n")
    except OSError:
        pass
    print("Blocked: a server may hold patient data, so direct ssh is not allowed, and ~/.config/cehr-dev "
          "is the user's to edit. Use the run-on-server skill's remote.py; for a server that is not listed, "
          "offer the user `remote.py propose <server>`. If it cannot do what is needed, ask the user to "
          "run it themselves.", file=sys.stderr)
    sys.exit(2)


if __name__ == "__main__":
    main()
