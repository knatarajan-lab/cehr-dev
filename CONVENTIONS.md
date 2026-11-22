# Conventions for skills in cehr-dev

Rules for anyone, human or coding agent, adding or changing a skill in this repository.
A skill is read in full every time it runs, and by a person every time it is reviewed,
so its length is a cost paid on every use.

## One skill, one job

A skill does one thing. The check: say what it is for in one sentence without "and".
If a user would ask for two parts of it separately, they are two skills.

Several steps toward one result are still one job (`tester` runs, adds and prunes
tests, all for one change). Two results that only share a topic are not (auditing
branches and deleting them).

Before adding a skill, check that an existing one does not already cover the request.
Extend that one only if the new behaviour is the same job.

## Keep `SKILL.md` short

`SKILL.md` stays under 200 lines. It holds what every run needs: when to use the skill,
the steps, and the rules that must not be broken.

200 is a ceiling, not a target. Write the shortest skill that does the job: a line
stays only if an agent would act differently without it. Do not restate a rule in a
second place, add an example where the rule is already clear, or cover a case that has
not come up. The same holds for reference files and scripts.

When it grows past that, go in this order, and do not squeeze the wording of what is
left to make it fit:

1. Delete what the agent would act the same without. A reference file is not a place to
   keep text that did not earn a line.
2. Move a rule about one repository to that repository's `CONVENTIONS.md`.
3. Move out what is needed, but only in some runs:

- **`references/<topic>.md`** for material only some runs need: long examples, lookup
  tables, edge cases, templates, variants for different tools. `SKILL.md` names each
  file and says when to read it. A reference file over 300 lines starts with a table of
  contents.
- **`scripts/<name>`** for steps that are deterministic, repeated on every run, or have
  to be safe by construction. A script is run, not read, so it costs no context.
  `audit-branches/scripts/audit_branches.py` is the model: it allows only read-only
  git commands, so the skill cannot delete anything by mistake.

If it is still over 200 lines after that, the skill is probably doing two jobs.

## Writing a skill

- The `description` in the frontmatter says what the skill does and when to use it,
  including the words a user would actually type. It is the only part that decides
  whether the skill is picked up.
- Give the reason for a rule, not only the rule. An agent that knows why can handle a
  case the skill did not list.
- A skill that deletes, pushes or publishes anything says so at the top and asks first.
- Use `context: fork` only for a skill that must not see the conversation and never
  needs to ask a question (`tester`). A forked skill gets the skill text and its
  arguments, nothing else.
- In a script, a function over about 40 lines needs a reason. Split it at a natural seam,
  a step with its own inputs and outputs, not to meet the number.
- No per-skill README or changelog. The skill folder holds `SKILL.md`, `references/`
  and `scripts/`.

## Checklist for a change

1. `plugins/cehr-dev/skills/<name>/SKILL.md`, with `name` equal to the folder name.
2. A row in the Skills table in `README.md`, and the folder in its Layout section.
3. `claude plugin validate .` and `claude plugin validate plugins/cehr-dev` both pass.
4. Bump `version` in `plugins/cehr-dev/.claude-plugin/plugin.json` when a skill is
   added, removed or renamed.
5. Run the skill once on a real task before publishing, and say in the pull request
   what it was run on.
