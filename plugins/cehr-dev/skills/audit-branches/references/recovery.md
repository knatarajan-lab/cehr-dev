# Why a deleted branch is hard to recover

- Deleting a branch deletes its own reflog. Only `HEAD`'s reflog can still reach it.
- Each worktree has its own `HEAD` reflog, which goes when the worktree is removed, so a
  branch worked on in a removed worktree may have no reflog entry at all.
- Unreachable commits are garbage-collected: by default about 30 days with a reflog
  entry, about 2 weeks without one.

What actually protects a deleted branch is a copy elsewhere: the branch still on the
remote, or a merged pull request, whose head commit the host keeps.
