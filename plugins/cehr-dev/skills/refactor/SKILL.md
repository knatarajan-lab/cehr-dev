---
name: refactor
description: Restructure existing code without changing what it does, as a change a reviewer can verify. Covers two kinds of refactor - one well-scoped area such as the batch assembly of a collator or the helpers that launch a tool on several GPUs, or one pattern refactored out across the codebase - and merges similar functions, removes duplicates and splits monolithic ones. Works in four stages - agree the goal, read the code, agree a plan with the user, then change it in small steps and show the outputs are the same, on a test dataset on a server when needed. Use this whenever the user asks to refactor, clean up, simplify, reorganise, deduplicate, harmonise, split, rename or move code, even if they do not say "refactor". Not for adding behaviour (implement-feature) or fixing a bug.
---

# Refactor without changing behaviour

A refactor is harder to review than a feature. Every line moved, and the reviewer has to
convince themselves that nothing changed. So the job is to make "nothing changed"
checkable: a narrow scope, one kind of change at a time, and evidence that the outputs
are the same.

The principles are those of `implement-feature`. Read first:

- the repository's conventions file (`CONVENTIONS.md`, `docs/CONVENTIONS.md`,
  `.claude/CONVENTIONS.md`, then `CLAUDE.md`, `AGENTS.md`, `CONTRIBUTING.md`); its rules
  override the ones below
- `${CLAUDE_PLUGIN_ROOT}/skills/implement-feature/SKILL.md`, stage 4: change only what
  is needed, follow the existing plumbing, short functions, comments, formatting, and
  the test policy all apply here
- `${CLAUDE_PLUGIN_ROOT}/skills/implement-feature/references/data-changes.md`, when the
  code touches datasets, tokenization or caches: a rename can change a hash

Work through four stages in order. Do not edit any file until the user has approved the
plan in stage 3.

## Two kinds of refactor

Pick one per change and say which. Mixing them makes the diff unreadable.

- **One area**: a well-scoped part of the code, such as the batch assembly of one
  collator, or the helpers that launch a tool on several GPUs. The area is the boundary.
  Inside it code may be restructured; what the rest of the code sees of it stays the
  same. An area is well scoped when it sits behind one interface, has an output that can
  be compared exactly, and fits a few pull requests. A whole subsystem such as "data
  loading" is not: narrow it first.
- **One pattern**: the same construct wherever it occurs, such as a repeated guard or a
  helper copied into several files. The pattern is the boundary. Every occurrence is
  changed the same way, and nothing else in those files is touched.

## What to aim for

- **One function for one job.** Merge functions that do the same thing, and harmonise
  those that differ only in a detail into one that takes that detail as an argument.
  Search for an existing helper before writing one.
- **No monolithic functions.** Split a long function at its seams, as implement-feature
  describes. A merge must not create one either: if joining two functions needs several
  flags to switch between behaviours, give them a shared helper and keep them apart.
- **Imports that flow one way.** A lower-level module does not import a higher-level
  one, and a refactor adds no import cycle. Put a shared helper in the lowest module
  that both callers can already import. Remove a cycle inside the boundary when moving a
  function is enough, and do not hide one with an import inside a function. Drop imports
  the change leaves unused.
- **Short comments.** One or two lines saying why, or none. A refactor does not narrate
  what moved or what the code used to be.

## Stage 1: Agree the goal

State in a sentence what is wrong with the code as it is, which of the two kinds this
is, what done looks like, and where the boundary lies. A refactor with no stated problem
is not worth a reviewer's time; say so if you cannot find one.

Confirm the base branch unless the user already said.

## Stage 2: Read the code

- **Everything that uses what will change.** `git grep` each name, and look beyond
  calls: names inside strings, `getattr`, config keys, command-line options, and tests
  that patch or mock them. For a pattern, list every occurrence and the variants.
- **Which way the imports run.** For the modules in scope, list what each imports from
  the rest of the package and what imports it, and note every cycle.
- **What must stay as it is from outside**: command-line options, config and checkpoint
  keys, file names and formats, log lines something parses, the hash that identifies
  stored data.
- **What would show a change**: the tests that exercise this code, and a command whose
  real output can be compared. Note where there is neither.

## Stage 3: Agree the plan

Give the user a plan they can read in a minute:

- the steps in order, each one kind of change: move, rename, extract, merge, inline, or
  delete dead code
- for each step, how sameness will be shown: which tests, and which output is compared
  before and after
- the rough size of each step. Over the size budget, propose separate pull requests that
  each stand on their own, for example the pure moves first, then the merges
- the imports between modules that will be added or removed, and any cycle that goes
- what you are leaving alone, and anything that cannot be verified

**Ask for a test dataset when tests are not enough.** For data loading, tokenization or
model code, unit tests rarely show that a real run is unchanged. Ask the user for a
small dataset to run on, such as MIMIC-IV, and where it is on the server.

Then stop and wait for the user's answer. Start only after they approve.

## Stage 4: Change it in small steps

**Capture the baseline first.** Run the tests. For a run on a server, use the
`run-on-server` skill: run the agreed command on the base branch with a fixed seed, and
keep its summary output, such as the loss, the metrics file and the counts in the log.

**One step at a time, then check.** After each step run the tests. When the steps are
done, repeat the server run on the refactored branch and compare the summaries. The
second run must reuse the dataset the first one prepared: a rebuild means a hash changed.
If anything differs, stop: either a step changed behaviour and is undone, or the
difference is intended and this is not a refactor, which the user needs to know.

**Never mix in a behaviour change.** A bug you find goes on the "noticed, not changed"
list, even when the fix is one line. Mixed in, it hides among the moved lines.

**Move first, edit later.** Move code unchanged in one step and alter it in the next, so
the move shows as a move in the diff. Do not rename or reformat while moving.

**Leave the outside as it is.** Do not rename anything stored or parsed elsewhere: a
config key, a command-line option, a class or field that is pickled or hashed. Inside
the code, change every caller in the same step; no aliases or shims for the old name.

**Do not pad it.** A refactor that adds many lines needs a reason. If the code has
neither a test nor an output to compare, say that the refactor cannot be verified and
let the user decide; the `tester` skill can pin the behaviour first.

Do not commit or push unless the user asked.

## Report

- the problem, the kind of refactor, and the steps done against the plan
- lines added and removed per step, and the net change
- functions merged or split, with their length before and after
- imports between modules added and removed, and the cycles before and after
- the evidence: tests run, and which outputs were compared and whether they are identical
- what could not be verified
- "noticed, not changed": bugs and other problems you saw and left alone
