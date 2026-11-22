#!/usr/bin/env python3
"""Read-only audit of a git repository's local branches, worktrees and stashes.

For every local branch: is its work already in the gold-standard branch (by default the
remote's default branch), only in a named development branch, or nowhere else?

It never changes the repository: every git call goes through an allowlist of read-only
subcommands (see _check). Python 3.8+, standard library only; `gh` is optional.
"""
import argparse
import collections
import datetime
import json
import os
import subprocess
import sys
import time

REPO = "."

READ_ONLY = {
    "rev-parse", "for-each-ref", "rev-list", "merge-base", "cherry", "merge-tree",
    "status", "cat-file", "symbolic-ref", "ls-remote",
}
READ_ONLY_FORMS = {("worktree", "list"), ("stash", "list")}

# ignored files that are not worth mentioning when a worktree is otherwise clean
CACHE_MARKERS = (
    "__pycache__", ".egg-info", ".pytest_cache", ".mypy_cache", ".ruff_cache", ".venv",
    "venv/", "node_modules", ".DS_Store", ".tox", ".ipynb_checkpoints", "build/", "dist/",
    ".idea", ".vscode", ".cache", "target/", ".gradle",
)


def _check(args):
    """Refuse anything that is not on the read-only allowlist."""
    if args[0] in READ_ONLY:
        if args[0] == "symbolic-ref" and sum(not a.startswith("-") for a in args[1:]) != 1:
            raise RuntimeError("symbolic-ref may only be used to read a ref")
        return
    if tuple(args[:2]) in READ_ONLY_FORMS:
        return
    raise RuntimeError(f"refusing to run a git command that is not read-only: git {' '.join(args)}")


def git(*args, cwd=None):
    _check(args)
    r = subprocess.run(
        ["git", "--no-optional-locks", "-C", cwd or REPO, *args],
        capture_output=True, text=True, errors="replace",
    )
    return r.returncode, r.stdout


def exists(ref):
    return git("rev-parse", "--verify", "-q", f"{ref}^{{commit}}")[0] == 0


def is_ancestor(a, b):
    return git("merge-base", "--is-ancestor", a, b)[0] == 0


def have_object(oid):
    return bool(oid) and git("cat-file", "-e", f"{oid}^{{commit}}")[0] == 0


def count(*rev_list_args):
    rc, out = git("rev-list", "--count", *rev_list_args)
    return int(out.strip()) if rc == 0 and out.strip().isdigit() else 0


def resolve_ref(name, remote):
    """Prefer the remote copy of a branch: the local copy is often behind it."""
    for candidate in (f"{remote}/{name}", name):
        if exists(candidate):
            return candidate
    return None


def resolve_gold(remote, given):
    if given:
        ref = resolve_ref(given, remote)
        if not ref:
            sys.exit(f"gold branch '{given}' not found")
        return ref
    rc, out = git("symbolic-ref", "-q", f"refs/remotes/{remote}/HEAD")
    if rc == 0 and out.strip():
        return out.strip().replace("refs/remotes/", "", 1)
    for candidate in (f"{remote}/main", f"{remote}/master", "main", "master"):
        if exists(candidate):
            return candidate
    sys.exit("cannot work out the main branch; pass --gold")


def short(ref, remote):
    return ref[len(remote) + 1:] if ref.startswith(remote + "/") else ref


def load_prs():
    """All pull requests of the repository, or None when gh cannot provide them."""
    fields = "number,state,title,headRefName,headRefOid,baseRefName,mergeCommit,mergedAt,isCrossRepository"
    try:
        r = subprocess.run(
            ["gh", "pr", "list", "--state", "all", "--limit", "2000", "--json", fields],
            cwd=REPO, capture_output=True, text=True, timeout=180,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None
    if r.returncode:
        return None
    try:
        return json.loads(r.stdout)
    except ValueError:
        return None


def remote_heads(remote):
    """Branches that exist on the remote right now, name -> sha (a read-only network call)."""
    rc, out = git("ls-remote", "--heads", remote)
    if rc:
        return None
    return {line.split("refs/heads/", 1)[1]: line.split()[0] for line in out.splitlines() if "refs/heads/" in line}


def worktrees():
    rc, out = git("worktree", "list", "--porcelain")
    items, cur = [], None
    for line in out.splitlines():
        if line.startswith("worktree "):
            cur = {"path": line[9:], "branch": None, "detached": False, "locked": False}
            items.append(cur)
        elif cur is None:
            continue
        elif line.startswith("HEAD "):
            cur["head"] = line[5:]
        elif line.startswith("branch "):
            cur["branch"] = line[7:].replace("refs/heads/", "", 1)
        elif line == "detached":
            cur["detached"] = True
        elif line.startswith("locked"):
            cur["locked"] = True
    for i, w in enumerate(items):
        w["primary"] = i == 0
        w["exists"] = os.path.isdir(w["path"])
        w["modified"] = w["untracked"] = 0
        w["ignored"] = []
        if not w["exists"]:
            continue
        rc, out = git("status", "--porcelain", "--ignored", cwd=w["path"])
        for line in out.splitlines():
            code, path = line[:2], line[3:]
            if code == "??":
                w["untracked"] += 1
            elif code == "!!":
                if not any(m in path for m in CACHE_MARKERS):
                    w["ignored"].append(path)
            else:
                w["modified"] += 1
        head = w.get("head")
        w["head_only_local"] = count(head, "--not", "--remotes") if head else 0
        w["head_on_branch"] = bool(head) and count(head, "--not", "--branches", "--remotes") == 0
    return items


class Target:
    """A ref to compare against."""

    def __init__(self, ref):
        self.ref = ref
        self.tree = git("rev-parse", f"{ref}^{{tree}}")[1].strip()


def trial_merge(target, sha):
    """
    Would merging the branch change the target?

    'no-op' means every change the branch made is already in the target, whatever the
    commit hashes are (squash merges, rebases, cherry-picks). 'conflicts' is inconclusive.
    """
    rc, out = git("merge-tree", "--write-tree", "--no-messages", target.ref, sha)
    if rc == 1:
        return "conflicts"
    if rc != 0 or not out.strip():
        return "unavailable"
    return "no-op" if out.split()[0] == target.tree else "changes"


def follow_chain(pr, gold, devs, merged_by_head, depth=0):
    """
    A pull request merged into branch X is covered when X itself was merged afterwards.

    Returns (ref the chain ends on, [PR numbers along the way]) or None. Only later merges
    count: a parent that merged before the child cannot have carried the child's work.
    """
    if depth > 6:
        return None
    for parent in merged_by_head.get(pr["baseRefName"], []):
        if (parent.get("mergedAt") or "") < (pr.get("mergedAt") or ""):
            continue
        merge = (parent.get("mergeCommit") or {}).get("oid")
        if have_object(merge):
            for t in [gold] + devs:
                if is_ancestor(merge, t.ref):
                    return t.ref, [parent["number"]]
        up = follow_chain(parent, gold, devs, merged_by_head, depth + 1)
        if up:
            return up[0], [parent["number"]] + up[1]
    return None


def contained_in(name, sha, remote):
    """Other branches, local or remote, that already contain this branch's tip."""
    _, out = git("for-each-ref", "--contains", sha, "--format=%(refname:short)", "refs/heads", "refs/remotes")
    own = {name, f"{remote}/{name}", remote, f"{remote}/HEAD"}
    return [r for r in out.split() if r not in own][:4]


def by_history(b, gold, devs, raw_prs, merged_by_head):
    """Category from ancestry and pull-request state: (category, reason, covered by), or None."""
    sha = b["sha"]
    merged = [p for p in b["prs"] if p["state"] == "MERGED"]
    open_prs = [p for p in b["prs"] if p["state"] == "OPEN"]
    if b["is_reference"]:
        return "reference", "the gold or a development branch itself", None
    if is_ancestor(sha, gold.ref):
        return "in-main", f"tip is already on {gold.ref} (no commits of its own)", gold.ref
    for p in merged:
        if p["tip_in_head"] and p["merge_in_gold"]:
            return "in-main", f"PR #{p['number']} merged; its merge commit is on {gold.ref}", gold.ref
    if open_prs:
        return "open-pr", f"PR #{open_prs[0]['number']} is open against {open_prs[0]['base']}", None
    for d in devs:
        if is_ancestor(sha, d.ref):
            return "in-dev", f"tip is already on {d.ref}", d.ref
    for p in merged:
        for d in devs:
            if p["tip_in_head"] and d.ref in p["merge_in_dev"]:
                return "in-dev", f"PR #{p['number']} merged; its merge commit is on {d.ref}", d.ref
    for p in merged:
        hit = p["tip_in_head"] and follow_chain(raw_prs[p["number"]], gold, devs, merged_by_head)
        if hit:
            via = " -> ".join(f"#{n}" for n in hit[1])
            return ("in-main" if hit[0] == gold.ref else "in-dev",
                    f"PR #{p['number']} merged into {p['base']}, which was merged later via {via} "
                    f"and reached {hit[0]} (inferred from the chain of pull requests)", hit[0])
    return None


def by_content(b, gold, devs, prs_known, remote):
    """Category from what the branch holds, for one that history did not settle."""
    sha = b["sha"]
    merged = [p for p in b["prs"] if p["state"] == "MERGED"]
    notes = []
    for p in merged:
        if p["tip_in_head"] is False:
            notes.append(f"has commits made after PR #{p['number']} merged")
        elif p["tip_in_head"] is None:
            notes.append(f"PR #{p['number']} merged but its head commit is not fetched")
    for p in b["prs"]:
        if p["state"] == "CLOSED":
            twin = p.get("twin")
            notes.append(f"PR #{p['number']} was closed without merging"
                         + (f" (same title as merged PR #{twin})" if twin else ""))
    noted = "; " + "; ".join(notes) if notes else ""
    b["content"] = {}
    for t in [gold] + devs:
        _, cherry = git("cherry", t.ref, sha)
        marks = [line[0] for line in cherry.splitlines() if line]
        e = {"trial_merge": trial_merge(t, sha), "patch_equivalent": f"{marks.count('-')}/{len(marks)}"}
        b["content"][t.ref] = e
        if e["trial_merge"] == "no-op" or (marks and marks.count("-") == len(marks)):
            how = "a trial merge changes nothing" if e["trial_merge"] == "no-op" else "every commit has an equivalent patch"
            return "in-main" if t is gold else "in-dev", f"content is in {t.ref}: {how}" + noted, t.ref
    targets = gold.ref + (" or a development branch" if devs else "")
    for p in merged:
        if p["tip_in_head"]:
            return ("in-another-branch", f"PR #{p['number']} merged into {p['base']}, but that merge is not on {targets} "
                    f"({p['base']} is not merged yet, or its history was rewritten)", None)
    others = contained_in(b["name"], sha, remote)
    if others:
        b["contained_in"] = others
        return "in-another-branch", f"every commit is also on {', '.join(others)}, which is not on {targets}" + noted, None
    where = "local only: these commits are on no remote" if b["local_only"] else "pushed"
    if not prs_known:
        notes.append("pull-request state unknown (gh unavailable)")
    return "not-covered", where + ("; " + "; ".join(notes) if notes else ""), None


def classify(b, gold, devs, prs_known, remote, raw_prs, merged_by_head):
    """Decide the category of one branch and say why. Mutates and returns b."""
    category, reason, covered_by = (by_history(b, gold, devs, raw_prs, merged_by_head)
                                    or by_content(b, gold, devs, prs_known, remote))
    b.update(category=category, reason=reason, covered_by=covered_by)
    return b


def stale_reason(b, heads, remote, stale_days, proposed):
    """
    Why an unmerged branch is not needed locally, or None.

    Only when deleting the local branch loses nothing: the live remote branch holds its
    tip, or another branch that is being kept does. `proposed` is the names flagged so far.
    """
    if heads is None or b["category"] not in ("in-another-branch", "not-covered"):
        return None
    tip = heads.get(b["name"])
    if tip:
        if not (have_object(tip) and is_ancestor(b["sha"], tip)):
            return None
        if any(p["state"] == "CLOSED" for p in b["prs"]):
            return f"pull request closed without merging; {remote}/{b['name']} still holds it"
        age = (datetime.date.today() - datetime.date.fromisoformat(b["date"])).days
        if age >= stale_days:
            return f"no commits for {age} days; {remote}/{b['name']} still holds it"
        return None
    if not (b["upstream"] or exists(f"{remote}/{b['name']}")):
        return None
    # a holder counts only if it is a live remote branch or a local branch that is kept
    for ref in b.get("contained_in", []):
        live = ref.startswith(remote + "/") and short(ref, remote) in heads
        if live or (exists(f"refs/heads/{ref}") and ref not in proposed):
            return f"its remote branch was deleted; every commit is also on {ref}"
    return None


ORDER = ["in-main", "in-dev", "open-pr", "in-another-branch", "not-covered", "reference"]
TITLES = {
    "in-main": "IN MAIN: work is in {gold}",
    "in-dev": "IN A DEVELOPMENT BRANCH ONLY: not in main yet",
    "open-pr": "OPEN PULL REQUEST: still in progress",
    "in-another-branch": "IN ANOTHER BRANCH ONLY: the work lives on in a branch that is not in main or a development branch",
    "not-covered": "NOT COVERED: work that is in neither main nor a development branch",
    "reference": "REFERENCE BRANCHES",
}


def parse_args():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--repo", default=".", help="path inside the repository (default: current directory)")
    ap.add_argument("--remote", default="origin")
    ap.add_argument("--gold", help="gold-standard branch (default: the remote's default branch)")
    ap.add_argument("--dev", action="append", default=[],
                    help="a development/integration branch that also counts; repeatable")
    ap.add_argument("--json", dest="json_path", help="also write the full result as JSON to this file")
    ap.add_argument("--stale-days", type=int, default=90,
                    help="an unmerged branch this old whose tip is on the remote is not needed locally")
    return ap.parse_args()


def targets(args):
    """The gold and development refs to compare against, and warnings about them."""
    remote = args.remote
    gold = Target(resolve_gold(remote, args.gold))
    devs, warnings = [], []
    for name in args.dev:
        ref = resolve_ref(name, remote)
        if not ref:
            warnings.append(f"development branch '{name}' not found; ignored")
        elif ref != gold.ref and ref not in [d.ref for d in devs]:
            devs.append(Target(ref))
    for t in [gold] + devs:
        local = short(t.ref, remote)
        if t.ref != local and exists(local):
            ahead = count(local, "--not", t.ref)
            if ahead:
                warnings.append(f"local {local} has {ahead} commit(s) that {t.ref} does not; they are not counted as covered")
    return gold, devs, warnings


def pr_entries(name, sha, prs, gold, devs, merged_titles):
    """The pull requests whose head is this branch, with where each one ended up."""
    entries = []
    for p in prs or []:
        if p["headRefName"] != name or p.get("isCrossRepository"):
            continue
        head, merge = p.get("headRefOid"), (p.get("mergeCommit") or {}).get("oid")
        entry = {"number": p["number"], "state": p["state"], "base": p["baseRefName"],
                 "tip_in_head": is_ancestor(sha, head) if have_object(head) else None,
                 "merge_in_gold": have_object(merge) and is_ancestor(merge, gold.ref),
                 "merge_in_dev": [d.ref for d in devs if have_object(merge) and is_ancestor(merge, d.ref)]}
        if p["state"] == "CLOSED":
            entry["twin"] = merged_titles.get(p["title"].strip().lower())
        entries.append(entry)
    return entries


def read_branches(gold, devs, prs, heads, trees, reference_names, remote):
    """Every local branch with its pull requests, flags and category."""
    merged_titles, raw_prs, merged_by_head = {}, {}, collections.defaultdict(list)
    for p in prs or []:
        raw_prs[p["number"]] = p
        if p["state"] == "MERGED":
            merged_titles.setdefault(p["title"].strip().lower(), p["number"])
            if not p.get("isCrossRepository"):
                merged_by_head[p["headRefName"]].append(p)
    tree_of_branch = {w["branch"]: w for w in trees if w["branch"]}
    fmt = "%(refname:short)%09%(objectname)%09%(committerdate:short)%09%(upstream:short)%09%(contents:subject)"
    _, rows = git("for-each-ref", "--sort=-committerdate", "refs/heads", f"--format={fmt}")
    branches = []
    for row in rows.splitlines():
        name, sha, date, upstream, subject = (row.split("\t", 4) + [""] * 5)[:5]
        b = {"name": name, "sha": sha, "date": date, "upstream": upstream or None, "subject": subject,
             "is_reference": name in reference_names, "prs": [], "flags": []}
        b["local_only"] = count(sha, "--not", "--remotes")
        b["on_remote"] = None if heads is None else name in heads
        b["own_commits_vs_gold"] = count("--no-merges", sha, "--not", gold.ref)
        b["prs"] = pr_entries(name, sha, prs, gold, devs, merged_titles)
        w = tree_of_branch.get(name)
        if w:
            b["worktree"] = w["path"]
            if w["primary"]:
                b["flags"].append("checked out in the main working folder")
            if not w["exists"]:
                b["flags"].append("worktree folder is missing")
            if w["modified"] or w["untracked"]:
                b["flags"].append(f"UNCOMMITTED WORK in its worktree ({w['modified']} modified, {w['untracked']} untracked)")
        if b["local_only"]:
            b["flags"].append(f"{b['local_only']} commit(s) on no remote")
        branches.append(classify(b, gold, devs, prs is not None, remote, raw_prs, merged_by_head))
    return branches


def candidate_dev_branches(prs, reference_names, remote):
    """Branches that pull requests target instead of main, most used first."""
    candidates = collections.Counter()
    for p in prs or []:
        if p["baseRefName"] not in reference_names and not p.get("isCrossRepository"):
            candidates[p["baseRefName"]] += 1
    rows = []
    for name, n in candidates.most_common(6):
        open_to_gold = [q["number"] for q in prs if q["headRefName"] == name and q["state"] == "OPEN"]
        rows.append({"branch": name, "prs_targeting_it": n, "exists": bool(resolve_ref(name, remote)),
                     "its_own_open_pr": open_to_gold[0] if open_to_gold else None})
    return rows


def last_fetch_time():
    fetch_head = os.path.join(git("rev-parse", "--git-common-dir")[1].strip() or ".git", "FETCH_HEAD")
    if not os.path.isabs(fetch_head):
        fetch_head = os.path.join(REPO, fetch_head)
    if not os.path.exists(fetch_head):
        return "never"
    return time.strftime("%Y-%m-%d %H:%M", time.localtime(os.path.getmtime(fetch_head)))


def print_branches(result, pr_count):
    """The header, the summary counts, and every branch under its category."""
    summary, branches = result["summary"], result["branches"]
    print(f"BRANCH AUDIT  {result['repo']}")
    print(f"gold standard: {result['gold']}   development: {', '.join(result['dev']) or '(none given)'}")
    print(f"pull-request data: {'yes, ' + str(pr_count) + ' PRs' if result['pr_data'] else 'NO (gh unavailable)'}"
          f"   remote branch list: {'checked' if result['remote_checked'] else 'not checked'}   last fetch: {result['last_fetch']}")
    for w in result["warnings"]:
        print(f"WARNING: {w}")
    print("\nSUMMARY (use these counts; do not recount by hand)")
    print(f"  local branches: {summary['total']}")
    for k in ORDER:
        extra = f" (of which local only: {summary['not_covered_local_only']})" if k == "not-covered" else ""
        print(f"  {k}: {summary[k]}{extra}")
    print(f"  branches with uncommitted work in a worktree: {summary['with_uncommitted_work']}")
    print(f"  not merged but not needed locally: {summary['not_merged_but_not_needed_locally']}")
    for k in ORDER:
        group = [b for b in branches if b["category"] == k]
        if not group:
            continue
        print(f"\n== {TITLES[k].format(gold=result['gold'])} ({len(group)})")
        for b in group:
            print(f"  {b['name']}  [{b['date']}]  {b['reason']}")
            for f in b["flags"]:
                print(f"      ! {f}")
            if b["stale"]:
                print(f"      NOT NEEDED LOCALLY: {b['stale']}")
            if b.get("worktree") and not any("main working folder" in f for f in b["flags"]):
                print(f"      worktree: {b['worktree']}")
            if k == "not-covered":
                print(f"      own commits vs {result['gold']}: {b['own_commits_vs_gold']}; "
                      f"still on remote: {b['on_remote'] if b['on_remote'] is not None else 'unknown'}")
                for ref, e in b.get("content", {}).items():
                    print(f"      vs {ref}: trial merge {e['trial_merge']}; equivalent patches {e['patch_equivalent']}")


def print_worktrees(result):
    """The worktrees, the stashes and the candidate development branches."""
    trees, stashes = result["worktrees"], result["stashes"]
    print(f"\n== WORKTREES ({len(trees)})")
    for w in trees:
        what = w["branch"] or ("detached at " + w.get("head", "?")[:8])
        if w["primary"]:
            state = "main working folder"
        elif not w["exists"]:
            state = "FOLDER MISSING (stale entry)"
        elif w["modified"] or w["untracked"]:
            state = f"UNCOMMITTED WORK ({w['modified']} modified, {w['untracked']} untracked)"
        else:
            state = "clean"
        extra = []
        if w["exists"] and w["ignored"] and not w["primary"]:
            extra.append(f"{len(w['ignored'])} ignored non-cache path(s), e.g. {w['ignored'][0]}")
        if w["exists"] and w["detached"] and not w["head_on_branch"]:
            extra.append("detached HEAD is on no branch")
        if w["exists"] and w.get("head_only_local"):
            extra.append(f"{w['head_only_local']} commit(s) on no remote")
        if w["locked"]:
            extra.append("locked")
        cat = next((b["category"] for b in result["branches"] if b["name"] == w["branch"]), None)
        print(f"  {w['path']}\n      {what}  |  {state}" + (f"  |  branch is {cat}" if cat else "")
              + ("  |  " + "; ".join(extra) if extra else ""))
    print(f"\n== STASHES ({len(stashes)})")
    for s in stashes:
        print(f"  {s[0]}  {s[1] if len(s) > 1 else ''}")
    if result["candidate_dev_branches"]:
        print("\n== CANDIDATE DEVELOPMENT BRANCHES (pull requests target these instead of main)")
        for c in result["candidate_dev_branches"]:
            pr = f"; its own open PR: #{c['its_own_open_pr']}" if c["its_own_open_pr"] else ""
            print(f"  {c['branch']}: {c['prs_targeting_it']} PR(s) target it"
                  f"{'' if c['exists'] else '; branch no longer exists'}{pr}")


def main():
    global REPO
    args = parse_args()
    top = subprocess.run(["git", "-C", args.repo, "rev-parse", "--show-toplevel"],
                         capture_output=True, text=True)
    if top.returncode:
        sys.exit(f"{args.repo} is not inside a git repository")
    REPO = top.stdout.strip()
    remote = args.remote

    gold, devs, warnings = targets(args)
    reference_names = {short(t.ref, remote) for t in [gold] + devs}
    prs, heads, trees = load_prs(), remote_heads(remote), worktrees()
    branches = read_branches(gold, devs, prs, heads, trees, reference_names, remote)
    proposed = {b["name"] for b in branches if b["category"] in ("in-main", "in-dev")}
    for b in branches:
        b["stale"] = stale_reason(b, heads, remote, args.stale_days, proposed)
        if b["stale"]:
            proposed.add(b["name"])
    _, stash_out = git("stash", "list", "--format=%gd%x09%gs")

    summary = {k: sum(1 for b in branches if b["category"] == k) for k in ORDER}
    summary["total"] = len(branches)
    summary["not_covered_local_only"] = sum(1 for b in branches if b["category"] == "not-covered" and b["local_only"])
    summary["with_uncommitted_work"] = sum(1 for b in branches if any("UNCOMMITTED" in f for f in b["flags"]))
    summary["not_merged_but_not_needed_locally"] = sum(1 for b in branches if b["stale"])
    result = {"repo": REPO, "gold": gold.ref, "dev": [d.ref for d in devs], "pr_data": prs is not None,
              "remote_checked": heads is not None, "last_fetch": last_fetch_time(), "warnings": warnings,
              "summary": summary, "branches": branches, "worktrees": trees,
              "stashes": [line.split("\t", 1) for line in stash_out.splitlines() if line],
              "candidate_dev_branches": candidate_dev_branches(prs, reference_names, remote)}
    if args.json_path:
        with open(args.json_path, "w") as f:
            json.dump(result, f, indent=1)
    print_branches(result, len(prs or []))
    print_worktrees(result)
    if args.json_path:
        print(f"\nfull result written to {args.json_path}")


if __name__ == "__main__":
    main()
