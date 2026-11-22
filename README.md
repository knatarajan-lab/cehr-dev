# cehr-dev

A Claude Code plugin marketplace (`cehr-plugins`) with one plugin, `cehr-dev`, that
carries a set of skills for day-to-day development.

## Skills

| Skill | What it does |
|---|---|
| `audit-branches` | Read-only audit of local branches, worktrees and stashes. Reports what is merged into main, what is only in a development branch, what is unmerged but not needed locally, and what still holds unmerged or unpushed work. Never deletes anything: it proposes local deletions only and hands you the commands. |
| `implement-feature` | Implements a feature as the smallest diff a human can review, in four stages: confirms the requirement, reads the code, agrees a plan with you, and only then edits. Follows the repository's own patterns, keeps comments to a line or two, writes no tests by default, and stops to propose a split when the change gets large. Reads a `CONVENTIONS.md` in the repository if there is one. |
| `tester` | Independent tester for a change someone else wrote. Runs the existing tests, adds a few targeted tests only where the change leaves new behaviour uncovered, and removes or merges duplicate tests in the files involved. Changes no source files. |
| `reviewer` | Reviews a pull request, branch or diff against the standards the two skills above set: is it correct, is every line needed, does it follow the repository's patterns, and are its tests necessary and sufficient. Read-only; posts to the pull request only when asked. |

## Install

From GitHub:

```
/plugin marketplace add knatarajan-lab/cehr-dev
/plugin install cehr-dev@cehr-plugins
```

From a local clone:

```
/plugin marketplace add /path/to/cehr-dev
/plugin install cehr-dev@cehr-plugins
```

The same commands work from a terminal as `claude plugin marketplace add ...` and
`claude plugin install ...`. Restart Claude Code after installing. One install brings
every skill.

## Use

Ask in plain words and the matching skill is picked up, or invoke one directly.

**Branches**: "which of my branches are safe to delete?", "summarize the branches I'm
working on".

```
/cehr-dev:audit-branches
```

Main is treated as the gold standard. The skill asks whether a development branch
should also count before it classifies anything.

**Features**: "add an option to ...", "implement ...".

```
/cehr-dev:implement-feature
```

To give it your repository's own rules, copy
`plugins/cehr-dev/skills/implement-feature/references/conventions-template.md`
to `CONVENTIONS.md` at the root of your repository and fill it in.

**Testing**: "test this branch", "is this change tested?", "clean up the tests for this change".

```
/cehr-dev:tester the new --foo option should ..., branch my-feature against main
```

It runs in its own context (`context: fork`) and does not see the conversation that
invoked it, so say what the change should do and which change to test. It leaves its
edits uncommitted for you to read as a diff. `audit-branches` and `implement-feature`
run in the conversation; start a new session or `/clear` first if you want them to
start clean.

**Review**: "review PR 215", "is this branch ok to merge?".

```
/cehr-dev:reviewer 215
```

It also runs in its own context and returns findings with file and line. It changes
nothing. Add `post` to have it post the review as a comment on the pull request; it
never approves, requests changes or merges.

## Requirements

For `audit-branches`:

- git 2.38 or newer (for the trial merge check)
- Python 3.8 or newer
- `gh`, authenticated, for pull-request state (optional; without it the audit falls back
  to ancestry and content checks)

## Layout

```
.claude-plugin/marketplace.json
CONVENTIONS.md
CLAUDE.md
plugins/
  cehr-dev/
    .claude-plugin/plugin.json
    skills/
      audit-branches/
        SKILL.md
        scripts/audit_branches.py
        references/recovery.md
      implement-feature/
        SKILL.md
        references/conventions-template.md
      tester/
        SKILL.md
      reviewer/
        SKILL.md
```

To add a skill, create `plugins/cehr-dev/skills/<name>/SKILL.md` and add a row to the
table above. [CONVENTIONS.md](CONVENTIONS.md) has the rules: one job per skill,
`SKILL.md` under 200 lines, detail moved into `references/` and `scripts/`.
