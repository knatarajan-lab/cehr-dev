---
name: run-on-server
description: Run whitelisted commands on the user's remote servers over ssh - check GPUs and memory, start and stop training jobs, sync code, and read training logs and metrics - without ever reading patient-level data. Use this whenever the user asks to run, start, stop, check or monitor something on a server or GPU machine, to look at a training run, its loss or its logs, or names one of their servers, even if they do not say "ssh". Never use plain ssh, scp or rsync for these servers.
---

# Run commands on a server that holds patient data

The servers hold patient-level records. You may run approved commands there and read
training logs and metrics. You may never read the data yourself: not a row, not a
sample. A listed script may compute on it and write summary metrics, and those you may
read.

This text is not what enforces that. `scripts/remote.py` refuses anything outside the
user's list, a hook blocks direct ssh to a listed server, and a job's output goes to a
log file on the server instead of coming back to you.

## The commands

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/skills/run-on-server/scripts/remote.py <action> <server> ...
```

| Action | What it does |
|---|---|
| `rules <server>` | Show what may be run and read on that server |
| `status <server>` | GPUs, memory, disk, load and the largest processes |
| `jobs <server>` | The tmux sessions |
| `start <server> <name> [--env KEY=VALUE] -- <command>` | Start a listed command in tmux session `cc-<name>`; its output goes to `<log_dir>/<name>.log` |
| `stop <server> <name>` | Stop `cc-<name>` |
| `git <server> status\|fetch\|pull\|log` and `git <server> checkout <branch>` | In the repository folder on the server |
| `ls <server> <folder>` | File names in a readable folder |
| `tail <server> <path> [-n N]` | The last lines, 300 at most, of a log or metrics file |
| `grep <server> <text> <path>` | Fixed-text search in one such file |
| `audit [-n N]` | The last lines of the audit file |

Start with `rules` when you do not know what is listed. Add `--dry-run` before the
action to see the ssh command without running it.

To follow a run, `tail` its log, or `grep eval_loss` in its `trainer_state.json`.

## Rules

**Changing the server needs the user's word.** `start`, `stop`, `git pull` and
`git checkout` change a shared machine. Run them only when the user asked for that
action, and say the exact command first. The other actions only look and need no asking.

**When something is refused, stop.** Do not look for another way in: no plain ssh, no
copying files off the server, and no job whose purpose is to print data into a log.
Tell the user what was refused and why, then ask them to run it themselves and paste the
result, or to add it to their list.

**The list is the user's.** They write and edit `~/.config/cehr-dev/servers.json`. You
do not create it, change it, or suggest wider rules to get a task done. If it does not
exist, point the user to `references/setup.md`.

**Everything is recorded.** Each ssh call, refusal and blocked attempt is appended to
the user's audit file, `~/.config/cehr-dev/audit.jsonl`. Do not edit or remove it.

**A log can still contain data.** If a log, a file name or a process list shows what
looks like patient records or identifiers, stop reading, do not quote it, and tell the
user which file.

**Compute through listed scripts only.** A listed script may work on a data folder and
write summary metrics such as a loss or an AUC, which you may read. What no listed
script produces, such as an ad hoc count or anything per patient, is the user's to run:
say which number you need.

**Keep server details out of repositories.** Host names, addresses and server paths do
not go into commits, pull requests or tracked files.
