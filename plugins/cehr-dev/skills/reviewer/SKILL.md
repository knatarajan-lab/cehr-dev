---
name: reviewer
description: Review a pull request, branch or diff the way a careful maintainer would, against the same standards the implement-feature and tester skills set - is it correct, is every line needed, does it follow the repository's patterns, and are its tests necessary and sufficient. Returns findings with file and line. Changes nothing, and posts nothing unless asked. Use this whenever the user asks to review, check or give feedback on a pull request, branch or diff, or asks "is this PR ok to merge?", even if they do not say "reviewer". Not for writing the change (implement-feature) or adding tests to it (tester).
argument-hint: "[PR number or URL, or branch] [post]"
context: fork
background: false
---

# Review a change someone else wrote

A review is worth reading only if the author acts on it. Report what is wrong or not
needed, where it is, and why. Leave out what is merely different from how you would have
written it.

The standard is the one the author was asked to meet. Before reading the change, read:

- the repository's conventions file (`CONVENTIONS.md`, `docs/CONVENTIONS.md`,
  `.claude/CONVENTIONS.md`, then `CLAUDE.md`, `AGENTS.md`, `CONTRIBUTING.md`); its
  rules override the two below
- `${CLAUDE_PLUGIN_ROOT}/skills/implement-feature/SKILL.md`, stage 4: what belongs in a
  change, comments, and the author's test policy
- `${CLAUDE_PLUGIN_ROOT}/skills/tester/SKILL.md`, steps 3 and 4: which tests a change
  needs and which are duplicates

## Ground rules

- **Read only.** Do not edit files, commit, push, approve, request changes or merge.
  Do not check out or switch branches in the user's checkout: read code at the change's
  head with `git show <sha>:<path>` and `git grep <pattern> <sha>`.
- **Post nothing unless the arguments say `post`.** Then post the review once, as a
  comment (`gh pr review <n> --comment --body-file <file>`), never as an approval or a
  request for changes. Those are the user's to give.
- **Stay independent.** Take the description and the diff. If you can see the change
  being written earlier in this conversation, say so on the first line.

## 1. Get the change

What the user passed in: $ARGUMENTS

For a pull request: `gh pr view <n> --json title,body,baseRefName,headRefOid,files`,
`gh pr diff <n>`, `gh pr checks <n>` for CI, and `git fetch --no-prune origin
pull/<n>/head` so its files can be read. With nothing named, use the pull request of the
current branch, or else the current branch against the base the conventions file names.
You cannot ask questions from here, so put what you assumed on the first line.

Count the size with `git diff --numstat <base>...<head>`: source lines and files
separately from test lines.

## 2. Read it in this order

1. **Does it do what it says?** From the description alone, write down what should be
   true with the feature on, with it off, and what must not change. Then check that the
   diff delivers that and nothing else. Note anything the diff does that the description
   does not mention.
2. **Is it correct?** Look for what the change disturbs, using the list in tester's
   step 3. Check a suspicion before reporting it: read the callers, and where it is
   cheap, try it in a clone in a scratch directory. A suspicion you could not check is
   a question, not a defect.
3. **Is every line needed?** Put each hunk to implement-feature's test: would the
   feature work without it? Flag edits to code the feature does not need, guards for
   things that cannot fail, compatibility scaffolding, options nobody asked for, side
   scripts and documents, formatting churn, and comments that restate the code or tell
   its history.
4. **Does it follow the repository?** It should take the same route as the closest
   existing feature. Flag a helper that already exists and was written again.
5. **Are the tests right?** By tester's criteria: new behaviour that could break
   silently with no test is a missing test; tests of defaults, parsing, wording or mock
   calls, and duplicates, are not needed; a test that would still pass with the
   behaviour broken is not testing it.
6. **Is it reviewable?** If it is over the size budget, say where it could be split
   into changes that each stand on their own.

## 3. Write the review

Each finding gives `path:line`, what is wrong, why (the failing case or the rule), and
the smallest fix. Group them by what the author has to do:

- **Must fix**: a wrong result, a crash on a path people use, a change in behaviour
  with the feature off.
- **Should fix**: lines that are not needed, a pattern not followed, a missing or
  unnecessary test, a change over the budget.
- **Question**: what you could not verify.

No praise, no summary of the diff, and no style preference the conventions do not
state. Leave out an empty group. Give at most about ten findings; past that, keep the
most important and say how many of which kind you left out.

The report:

- **First line**: the verdict (ready to merge, ready once the must-fix items are done,
  or needs rework or a split), what you reviewed, what you assumed, and the CI state.
- **Size**: source lines and files, and test lines, against the budget.
- **Findings**, grouped as above.
- **Not checked**: what you did not run or could not see.
