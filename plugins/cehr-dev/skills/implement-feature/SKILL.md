---
name: implement-feature
description: Implement a new feature, option, flag or behaviour in an existing codebase as the smallest diff a human can review, following the repository's own patterns, with short comments and no inflated tests. Use this whenever the user asks to add, implement, build, support or extend something in existing code, or to wire a new option through it, even if they do not mention diff size or review. Not for greenfield projects, pure refactors or bug hunts.
---

# Implement a feature as a small, reviewable change

A person has to read every line of this change. Their attention is the scarce resource,
so each added line has to earn its place: lines that are not needed for the feature to
work make the real change harder to see and slower to trust. Aim for the diff an
experienced maintainer of this repository would have written by hand.

## Before editing

### 1. Read the repository's conventions

Look for a conventions file, in this order: `CONVENTIONS.md`, `docs/CONVENTIONS.md`,
`.claude/CONVENTIONS.md`, then `CLAUDE.md`, `AGENTS.md`, `CONTRIBUTING.md`. Its rules
override the defaults in this skill, including the size budget and the test policy.

If there is none, learn the conventions from the code: find two or three recent commits
that added something similar (`git log --oneline -- <likely files>`, then `git show`)
and treat them as the template. Say in your plan that you inferred the conventions, and
mention that `references/conventions-template.md` in this skill is a starting point if
the user wants to write them down.

### 2. Confirm the base branch

Ask which branch to build on unless the user already said. The default branch is often
far behind where work actually happens, and code written against it re-implements
things that already exist on the active branch. If there is a question tool, use it and
offer the current branch, the default branch, and any branch that recent pull requests
target.

### 3. Find the closest existing feature and copy its shape

Most features have a precedent: an option that is already plumbed through the same
layers, a command that already does something similar. Find it and follow the same path
through the same files. A new option that travels the same route as an old one is a
change reviewers can check by comparison.

Before writing any helper, search for one that already does the job (by name and by
what it does: `git grep` the verbs and nouns you would use). A second copy of an
existing helper is the most common avoidable addition.

### 4. State the plan and its size

Before the first edit, tell the user in a few lines:

- the files you will touch and roughly how many lines in each
- the existing feature you are using as the template
- anything the request could be read to include that you are leaving out

**Size budget**: 150 changed source lines or 6 files, unless the conventions file sets
another number. The budget counts source files and lines; tests are limited separately,
below. If your estimate is over, stop and propose how to split the work into
changes that each stand on their own, and let the user choose. A reviewer handles two
small changes far better than one large one.

## While editing

**Change only what the feature needs.** For every hunk, the test is: would the feature
work without it? If yes, leave it out. That rules out renames, reordering, added type
hints, reformatting, import sorting, and fixing things you noticed nearby. Collect those
in a short "noticed, not changed" list for the user instead; they are real, but they
belong in their own change.

One thing is not a drive-by: a code path that worked before and breaks once your feature
is switched on. Your change created that failure, so its fix is part of the feature,
even when it is a one-line guard in a function you were not otherwise touching. Before
you finish, look for the places that use whatever your feature removes or makes
optional. A defect that was already there with the feature off stays on the list.

**Follow the plumbing that exists.** Do not introduce a new abstraction, base class,
registry or config mechanism for a single use.

**Trust the code's own guarantees.** If the dataclass, parser or config defines a field,
read it directly. `getattr(obj, "field", default)`, `hasattr`, and `try/except` around
things that cannot fail add lines and hide real errors. Validate at the boundary only:
user input, files, external services.

**No compatibility scaffolding unless asked.** No shims, re-exports, deprecated aliases,
or branches for "the old behaviour". Change the callers instead.

**Nothing speculative.** No options nobody asked for, no flags that only a test sets, no
hooks for future use.

**No side artifacts.** No benchmark or validation scripts, no new documentation files,
no README sections, unless the user asks. If you need a throwaway script to check your
work, keep it out of the repository, and delete it afterwards or say where it is.

**Leave formatting alone.** Format the lines you wrote to match their neighbours. Do not
run a formatter or pre-commit over whole files: it rewrites lines the reviewer then has
to read. If a hook reformats untouched lines anyway, undo those hunks or tell the user.

### Comments

Default to none. Add one when a reader would otherwise have to work out *why* the code
is the way it is, and keep it to one or two lines.

Do not write comments that restate the code, narrate history ("previously", "no longer",
"renamed from"), record benchmark numbers, describe who calls the function, or explain
your reasoning to the reviewer. That material belongs in the commit message or nowhere.

Docstrings on new functions: match the neighbours, three lines at most. Error messages:
one short sentence.

```python
# Right size: says why, in two lines
# Above this value the term grows linearly instead of exponentially,
# so one outlier cannot blow up the loss; None disables it
```

## Tests

**Write no new tests by default.** Tests written by the same agent that wrote the code
share its understanding of the code, so they pass by construction and tell the reviewer
little, while often doubling the size of the change.

**The exception** is logic where a wrong answer is silent: numerical formulas, indexing,
offsets, masking, ordering. There, write one test, about 30 lines, that compares the
result with a value worked out by hand or produced by an independent reference (a
library function, a slow obvious implementation that already exists). Do not derive the
expected value with the same formula as the code. Reuse existing fixtures and helpers.

Wiring is not in that category. A change that only passes an existing value to an
existing function (a new option reaching the model, a different input reaching an
existing loss) needs no test: there is no independent value to compare against, and
running the feature once shows whether it is connected.

Never write tests for: default values, argument parsing, help text, error message
wording, that a removed argument stays removed, that a mock received certain keyword
arguments, or a re-implementation of the code under test.

If the user asks for tests, write what they ask for.

**Do run the existing tests** that cover the files you touched (find them by the modules
they import). They were written before your change, so they are an independent check
that you broke nothing. Report the result as it is. If one fails because the behaviour
intentionally changed, say so and show the smallest edit to it; do not rewrite or delete
a test to make it pass.

Where it is cheap, exercise the new behaviour once for real (run the command, call the
function) and say what you saw. Say plainly what you could not verify.

## Before handing over

Read your own diff as the reviewer will:

1. `git diff --stat`: compare with the plan. If it grew past the budget, say so first.
2. Go through every hunk with the "would the feature work without it?" test and remove
   what fails.
3. Check that no untouched line changed (whitespace, quotes, wrapping, import order).
4. Re-read each comment and docstring; cut any that the code already says.

Do not commit or push unless the user asked.

## Report

Keep it short:

- what the feature does and how to use it (one or two lines, with the option or command)
- files changed with line counts, and the total against your estimate
- what you ran and what happened; what you did not verify
- "noticed, not changed": problems you saw and deliberately left alone
