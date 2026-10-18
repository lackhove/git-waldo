# 05: Delta pushes with clean check and fast-forward

**What to build:** Subsequent pushes deploy exactly the delta between the remote branch and the pushed commit. Added and modified paths are streamed from git and extracted on the target; deleted paths are removed in `./`-relative chunks. The target must be clean relative to the remote branch, and the push must be a fast-forward against the oid advertised for the push. Drift and non-fast-forward pushes are rejected with git's status tokens. Untracked and ignored files on the target survive, and directories emptied by a deletion are left in place.

**Blocked by:** 03 — Fetch a real target through the fence, refusing what cannot be represented; 04 — First push creates the target and deploys the commit

**Status:** ready-for-agent

- [ ] Added and modified paths are written via a git archive piped into a target-side tar extraction; deletions use `rm -f` with `./`-relative paths in chunks of about 500 per SSH call.
- [ ] The lock is taken before the clean check, so two concurrent pushes cannot both pass it, and is released on every exit path.
- [ ] The clean check compares the freshly built snapshot tree with the remote branch tree; drift rejection sends `error <dst> target has local changes: <paths>` with the first ten paths and a count.
- [ ] Fast-forward is verified against the oid advertised by `list for-push`, remembered in-process, unless the ref is being created; a non-fast-forward push sends `error <dst> non-fast forward`.
- [ ] Paths outside the delta are untouched; untracked and ignored target files survive; directories emptied by deletion remain.
- [ ] `git push --dry-run` simulates the delta and writes nothing.
- [ ] A no-op push reports `already up to date` on stderr.
- [ ] The helper never writes the remote branch; git updates it.
- [ ] Tests cover add, modify, delete, no-op, drift, non-fast-forward, dry-run, and target-side survival.
