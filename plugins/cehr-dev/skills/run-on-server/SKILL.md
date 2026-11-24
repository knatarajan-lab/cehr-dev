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
user's list, a hook blocks every direct ssh, and a job's output goes to a log file on
the server instead of coming back to you. Nothing is allowed until a server is listed.

## The commands

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/skills/run-on-server/scripts/remote.py <action> <server> ...
```

| Action | What it does |
|---|---|
| `status <server>` | GPUs, memory, disk, load and the largest processes |
| `jobs <server>` | The tmux sessions |
| `start <server> <name> [--repo NAME] [--env KEY=VALUE] -- <command>` | Start a listed command in tmux session `cc-<name>`; its output goes to `<log_dir>/<name>.log` |
| `stop <server> <name>` | Stop `cc-<name>` |
| `git <server> status\|fetch\|pull` and `git <server> checkout <branch>` | In a repository folder on the server |
| `tail <server> <path> [-n N]` | The last lines, 300 at most, of a log or metrics file |
| `du <server> <folder>` | The total size of each `*features_with_label` and `*dataset_prepared*` folder at, or up to four levels under, a folder |
| `propose <server>`, `accept <server>` | Show, then write, the default entry for a server that is not listed; `--read-root <folder>` adds a folder of logs and metrics |

A listed `python -m` command may also start through `torchrun`, as in `torchrun
--nproc_per_node=2 -m cehrgpt.runners.hf_cehrgpt_pretrain_runner`; only
`--nproc_per_node`, `--nnodes`, `--master_port` and `--standalone` may come before `-m`,
written with `=`. A refusal says what is listed. A server can list several repositories, each with its
own commands; name one with `--repo` on `start` and `git`. To follow a run, `tail` its
log or its `trainer_state.json`.

## Rules

**Changing the server needs the user's word.** `start`, `stop`, `git pull` and
`git checkout` change a shared machine. Run them only when the user asked for that
action, and say the exact command first. The other actions only look and need no asking.

**Take the command from the repository's list.** A repository has dozens of runnable
modules with similar names, and the wrong one can run for hours before anyone notices.
Before `start`, read the "Server jobs" section of the conventions file (`CONVENTIONS.md`,
then `CLAUDE.md`) in the local checkout of that repository, and follow its notes. If the
job is not listed there, or there is no such section, ask the user which command to run.

**When something is refused, stop.** Do not look for another way in: no plain ssh, no
copying files off the server, and no job whose purpose is to print data into a log.
Tell the user what was refused and why, then ask them to run it themselves and paste the
result, or to add it to their list.

**The list is the user's.** `~/.config/cehr-dev/servers.json` says what may run and be
read. For a server that is not listed, offer the default: `propose <server>` shows an
entry that allows every cehrgpt and cehrgpt-turbo command there, and `accept <server>`
writes it. Show the user the proposal and run `accept` only after they say yes. You
never write or change the file any other way, and anything beyond the default is the
user's own edit (`references/setup.md`).

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
