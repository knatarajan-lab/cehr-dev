---
name: audit-branches
description: Read-only audit of a git repository's local branches, worktrees and stashes that reports which ones are already merged and safe to clean up and which still hold unmerged or unpushed work. Use this whenever the user asks what branches they are working on, which branches or worktrees are stale, merged, or safe to delete, whether a branch's commits already landed in main or another branch, or wants to tidy up a repository with many branches or worktrees, even if they do not say "audit". It also flags unmerged branches that are not needed locally. It never deletes anything; it proposes local deletions only, never anything on the remote, and hands the user the commands to run.
---

# Audit branches and worktrees

Work out, with evidence, what each local branch and worktree still holds, so the user can
clean up without losing work. The main branch is the gold standard: a branch is "merged"
when its work is in main. A development branch the user names counts as a second, weaker
tier, reported separately.

## This skill is read-only

Other people install this skill and trust it not to touch their work, and a deleted
branch is much harder to get back than it looks (`references/recovery.md`, which you
should read if the user asks whether deleted branches can be recovered). So
while this skill is active, do not run anything that removes or rewrites git state:

- no `git branch -d/-D`, `git worktree remove`, `git worktree prune`, `git stash drop/clear`
- no `git checkout/switch/reset/restore/clean/rebase/merge/commit/gc`
- no `git push` of any kind (including `--delete`), no `git remote prune`
- no `git fetch --prune`: pruning deletes remote-tracking refs, which can be the last
  local pointer to commits whose remote branch was deleted
- no `gh pr close/merge`, no `rm` on a worktree folder

The deliverable is a report plus commands the user can run themselves. If the user asks
you to do the cleanup, give them the commands and say this skill does not run them.

The only state-changing command allowed is `git fetch --no-prune <remote>`, which only
adds. Everything else comes from the bundled script, which refuses any git subcommand
that is not on its read-only allowlist.

## Step 1: Refresh, then take a first pass

The script lives at `scripts/audit_branches.py` in this skill's base directory (shown when
the skill loads; inside a plugin that is `${CLAUDE_PLUGIN_ROOT}/skills/audit-branches`).

```bash
git fetch --no-prune origin
python3 <skill-dir>/scripts/audit_branches.py --repo <repo> --no-lines
```

Fetch first because stale remote-tracking refs give wrong answers (a merged pull request
looks unmerged until its merge commit is fetched). If the fetch fails, carry on and say
in the report how old the remote state is; the script prints the last fetch time.

The first pass finds the gold standard (the remote's default branch, usually
`origin/main`; override with `--gold`) and prints **candidate development branches**:
branches that pull requests target instead of main.

## Step 2: Ask about a development branch

Many teams merge feature branches into an integration branch long before main. Under a
main-only rule all of that work looks unmerged, so ask the user before classifying. Use
the question tool if there is one:

> Main (`origin/main`) is the gold standard for "merged". Is there a development branch
> whose contents should also count?

Offer the candidates the script printed, plus "No, main only". More than one is fine.
Do not assume a development branch from its name or from the candidates list; a branch
that many pull requests target may itself be abandoned.

## Step 3: Full audit

```bash
python3 <skill-dir>/scripts/audit_branches.py --repo <repo> --dev <branch> --json <scratch>/audit.json
```

Repeat `--dev` for each development branch. Write the JSON somewhere temporary, not in
the repository. Take every count from the script's SUMMARY rather than counting rows
yourself; hand counts drift when the list is long.

Categories the script assigns:

| Category | Meaning | Safe to delete? |
|---|---|---|
| `in-main` | Tip is on main, its pull request's merge commit is on main, or a trial merge into main changes nothing | Yes, unless flagged |
| `in-dev` | Same test, against a development branch | Only if the user accepts that tier |
| `open-pr` | Has an open pull request | No, in progress |
| `in-another-branch` | The commits live on in some other branch that is not in main or dev | Not yet |
| `not-covered` | Nothing proves the work is anywhere else | No, needs a look |
| `reference` | The gold or a development branch itself | No |

An unmerged branch can still be stale. The script marks one `NOT NEEDED LOCALLY` when
deleting the local branch loses nothing, for one of three reasons:

- its pull request was closed without merging, and the remote branch still holds its tip
- it has had no commits for 90 days (`--stale-days N` to change), and the remote branch
  still holds its tip
- its remote branch was deleted, and every commit is also on a branch that is kept

These are safe only because another copy exists, usually the remote branch. That is one
reason this skill never proposes deleting anything on the remote. A branch whose commits
are on no remote and in no other branch is never marked, however old it is.

Do not fall back on `git branch --merged`: squash merges and rebases give merged work
new commit hashes, so ancestry reports most merged branches as unmerged. The script
checks merged pull requests, stacked chains and a trial merge instead.

A flag on a branch overrides its category. In particular `UNCOMMITTED WORK in its
worktree` means the branch name may be redundant but the folder is not, and `N commit(s)
on no remote` means deleting it leaves no copy anywhere.

## Step 4: Look at the uncertain ones

`not-covered` and `in-another-branch` are where judgment is needed, and where a wrong
"it's merged" costs the user real work. For each, read before concluding:

1. Start from the script's evidence against the closest target: trial merge result,
   equivalent patches, how many added lines exist there, which files are absent.
2. Read the branch's own commits: `git log --oneline <branch> --not <target>` and
   `git show <commit>`.
3. Look for the same change in the target. Code moves, so search for the distinctive
   symbols and strings anywhere in the target (`git grep <symbol> <target>`), not only
   in the same file.
4. A closed pull request with the note "same title as merged PR #N" usually means the
   work landed through #N; confirm by reading, do not assume.

Then say which of these it is, and keep them apart in the report:

- **Present**: the same change is there (name the file or commit).
- **Rewritten**: the behaviour is there in a different form (say what differs).
- **Partly present**: name what is missing.
- **Absent**: not there.
- **Superseded or rejected**: the target does something different on purpose.

A high "added lines found" number is a hint, not proof: common lines match by accident.
Say what you did not check; you compared code, you did not run tests.

When you write shell loops here, write `"${ref}:${path}"` rather than `$ref:path`
(zsh treats `:t`, `:h` and friends as modifiers), and use Python rather than `jq`, which
is often not installed.

## Step 5: Worktrees and stashes

A worktree is only safe to remove when all of these hold, and the script's WORKTREES
section reports each:

- no modified and no untracked files
- no ignored files that matter (`git worktree remove` deletes ignored files without
  asking; the script lists ignored paths that are not caches)
- its HEAD is on a branch or a remote (a detached HEAD on no branch is lost with the folder)
- its branch is `in-main`, or `in-dev` if the user accepts that tier

Also check that nothing is using the folder: another agent session whose working
directory is that worktree, or a running process (`lsof -a -d cwd` on macOS/Linux). If
your environment can list sessions, use that. When a session still points at a worktree,
report it as in use rather than safe.

A worktree whose folder is missing is a stale entry; it holds nothing.

List stashes too; they survive deleting the branch they were made on.

## Step 6: Report

Lead with the answer, then the detail. Use this shape:

```markdown
N of M local branches are in main[, K more are only in <dev branch>], and J hold work that is nowhere else.

## Safe to delete (in main)            <- names, in a code block
## Only in <dev branch>                 <- separate tier, say it is not in main
## Not merged, but not needed locally   <- name, reason, and where the copy lives
## Open pull requests                   <- branch, PR, state
## Needs your decision                  <- one line each: what is there, where it lives, what is missing
## Worktrees                            <- table: path, branch, state, verdict
## Stashes
## If you want to clean up              <- commands, see below
```

Put the highest-risk items where they cannot be missed: branches with commits on no
remote, and worktrees with uncommitted work.

### Commands for the user

Keep each command on a single line so it can be copied whole.

- Branches merged by ancestry: `git branch -d <names>`.
- Branches merged by squash or rebase: `git branch -D <names>`. Say why `-D` is needed:
  git cannot see a squash merge, so `-d` refuses; the evidence is the merged pull request.
- Branches not needed locally: `git branch -D <names>`, as a separate command, saying
  the work is unmerged and stays on the remote.
- Worktrees: `git worktree remove <path>` with no `--force`, so git refuses if anything
  is unsaved. Stale entries: `git worktree prune`.
- Before deleting anything that is local only: `git push -u origin <branch>`.

Every proposed deletion is local. Never include a remote deletion (`git push --delete`,
`git branch -d -r`), even if the user asks: say this skill only proposes local ones.
