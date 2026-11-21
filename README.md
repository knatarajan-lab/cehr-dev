# cehr-dev

A Claude Code plugin marketplace (`cehr-plugins`) with one plugin, `cehr-dev`, that
carries a set of skills for day-to-day development.

## Skills

| Skill | What it does |
|---|---|
| `audit-branches` | Read-only audit of local branches, worktrees and stashes. Reports what is merged into main, what is only in a development branch, and what still holds unmerged or unpushed work. Never deletes anything; it hands you the commands. |
| `implement-feature` | Implements a feature as the smallest diff a human can review: follows the repository's own patterns, keeps comments to a line or two, writes no tests by default, and stops to propose a split when the change gets large. Reads a `CONVENTIONS.md` in the repository if there is one. |

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

## Requirements

For `audit-branches`:

- git 2.38 or newer (for the trial merge check)
- Python 3.8 or newer
- `gh`, authenticated, for pull-request state (optional; without it the audit falls back
  to ancestry and content checks)

## Layout

```
.claude-plugin/marketplace.json
plugins/
  cehr-dev/
    .claude-plugin/plugin.json
    skills/
      audit-branches/
        SKILL.md
        scripts/audit_branches.py
      implement-feature/
        SKILL.md
        references/conventions-template.md
```

To add a skill, create `plugins/cehr-dev/skills/<name>/SKILL.md` and add a row to the
table above.
