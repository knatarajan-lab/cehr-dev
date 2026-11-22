# Setting up run-on-server

The user does this once. Copy `servers-template.json` to `~/.config/cehr-dev/servers.json`
and fill it in. The file stays on your machine; it is not part of any repository.

## The fields

| Field | Meaning |
|---|---|
| `read_names` | File names that may be read, as patterns. Anything else is refused. |
| server key | The ssh alias from `~/.ssh/config`. Only listed servers can be reached. |
| `repos` | The repositories on the server, each under a name you choose. Add one entry per repository. With more than one, `start` and `git` take `--repo <name>`. |
| `path` | The repository folder. Its jobs start there; `git` runs there. |
| `setup` | Run before every job of that repository, for example to activate its environment. |
| `run` | A job's command in that repository must start with one of these. |
| `log_dir` | Where a started job writes `<name>.log`. Must be inside a `read_roots` folder. |
| `read_roots` | Folders whose logs and metrics may be read. Absolute paths. |
| `deny_parts` | Names of folders that hold nothing but data and are never entered for reading. Keep it short: a results folder that also holds a metrics file should stay readable, since data files in it are refused by type anyway. It does not limit which folders a job may work on. |
| `env` | Variables that `start --env` may set. |
| `also_block` | Other names for the server (host name, address) that direct ssh may not use. |

Data formats (parquet, arrow, pickle, numpy, model weights, jsonl) are never readable,
whatever `read_names` says. A csv is readable only if you list a pattern for it; do not
list one that could match per-patient output.

## The audit file

`~/.config/cehr-dev/audit.jsonl` gets one line for every ssh call the script makes
(the exact remote command, then its exit code and how many characters came back), every
request it refused with the reason, and every direct ssh or edit the hook blocked. Each
line has the time and the folder the agent was working in. The output itself is not
stored. The file is yours: the hook stops the agent from editing it, and nothing ever
trims it.

## What this does and does not guarantee

- The script checks every command and path against this file, and follows symlinks
  before reading.
- The plugin's hook blocks direct `ssh`, `scp`, `sftp` and `rsync` to a listed server,
  and blocks edits to this file. It takes effect once this file exists.
- Both run on your machine and match text, so they stop mistakes, not a determined
  bypass. Two stronger layers are yours to add:
  - Permission rules in `~/.claude/settings.json`, which Claude Code enforces itself:
    `"permissions": {"deny": ["Bash(ssh <alias>:*)", "Bash(scp:*)", "Bash(rsync:*)"]}`
  - An account on the server that cannot read the patient data folders. This is the
    only layer that holds whatever happens on your machine.
- A job you allow can write anything to its log. Keep `run` to commands whose logs you
  would be comfortable reading aloud.
