#!/usr/bin/env python3
"""PreToolUse guard for the servers listed in ~/.config/cehr-dev/servers.json.

Blocks a direct ssh, scp, sftp or rsync to a listed server, so the run-on-server script
and its whitelist are the only way in, and blocks changes to the list and the audit file,
which are the user's. Records what it blocks. Does nothing when the list does not exist.
"""
import datetime
import json
import os
import re
import sys

FOLDER = os.path.expanduser("~/.config/cehr-dev")
CONFIG = os.path.join(FOLDER, "servers.json")
REMOTE = re.compile(r"(^|[\s;&|(`'\"/=])(ssh|scp|sftp|rsync|mosh|autossh|sshpass)(?=\s|$)")


def block(message, attempted):
    entry = {"time": datetime.datetime.now().astimezone().isoformat(timespec="seconds"),
             "cwd": os.getcwd(), "outcome": "blocked by hook", "attempted": attempted[:500]}
    try:
        with open(os.path.join(FOLDER, "audit.jsonl"), "a") as f:
            f.write(json.dumps(entry) + "\n")
    except OSError:
        pass
    print(message, file=sys.stderr)
    sys.exit(2)


def main():
    if not os.path.exists(CONFIG):
        return
    try:
        event = json.load(sys.stdin)
    except ValueError:
        return
    tool_input = event.get("tool_input") or {}
    path = str(tool_input.get("file_path") or tool_input.get("notebook_path") or "")
    if path and os.path.realpath(os.path.expanduser(path)).startswith(os.path.realpath(FOLDER) + os.sep):
        block("The server list and the audit file belong to the user. Ask the user to change "
              "them; do not edit them.", f"edit {path}")
    command = str(tool_input.get("command") or "")
    if not command:
        return
    if ".config/cehr-dev" in command:
        block("Do not touch the server list or the audit file from the shell. `remote.py rules "
              "<server>` and `remote.py audit` show them; the user edits them.", command)
    if not REMOTE.search(command):
        return
    try:
        with open(CONFIG) as f:
            servers = json.load(f)["servers"]
        names = set(servers)
        for server in servers.values():
            names.update(server.get("also_block", []))
    except (OSError, ValueError, KeyError, AttributeError, TypeError):
        block("servers.json cannot be read, so direct ssh is blocked. Ask the user to fix the file.", command)
    for name in names:
        if re.search(r"(?<![\w.-])" + re.escape(name) + r"(?![\w-])", command):
            block(f"Direct ssh to '{name}' is blocked: the server holds patient data. Use the "
                  "run-on-server skill's remote.py, which runs only whitelisted commands and reads "
                  "only logs and metrics. If it cannot do what is needed, ask the user to run it.", command)


if __name__ == "__main__":
    main()
