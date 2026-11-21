# CONVENTIONS.md template

Copy this to `CONVENTIONS.md` at the root of a repository and fill it in. The
`implement-feature` skill reads it before making changes; anything here overrides the
skill's defaults. Keep it short: rules an agent can check, each tied to an example a
reviewer can open.

The best source for these rules is the repository's own history. Look at the last 30 or
so merged changes: which ones were easy to review and why, which grew large and where the
lines went (`git log --first-parent --numstat`), and which helpers keep getting copied.

```markdown
# Conventions for changes to <repository>

## Base branch
<Which branch new work starts from, or "ask">

## Size budget
<e.g. 150 changed source lines or 6 files; above that, propose a split>

## How a new option or feature is wired
<The layers it passes through, in order, with the file for each.>
Template to copy: <commit hash or PR that did it cleanly>

## Follow
- <rule> (example: <file or commit>)

## Avoid
- <rule> (example: <file or commit>)

## Helpers that already exist
- <what it does>: <function> in <file>

## Tests
<When a test is wanted, what kind, and what never to test.>
<How to run the existing ones.>

## Comments
<Length and content expected.>

## Formatting
<Which formatters exist and whether to run them.>
```
