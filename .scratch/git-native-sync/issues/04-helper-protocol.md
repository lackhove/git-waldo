# Remote-helper protocol surface: what the helper implements, what git may do

Type: grilling
Status: open
Blocked by: 01

## Question

Design the helper's protocol behaviour against git's actual expectations (ticket 01 supplies the facts):

- **Exposure**: which refs `list` reports (`refs/heads/main` only?), what happens for `list for-push`, and whether tags or extra branches are rejected or ignored.
- **Snapshot construction**: the helper builds a commit from the target tree locally (`hash-object -w`, temporary index, `write-tree`, `commit-tree`), including deletions, author/committer ident and message for a commit no human authored, and the parent chain. Then it advertises the commit with `? <oid>` so git never transfers a pack.
- **Pull**: which behaviour is `git fetch <remote>` vs a convenience `pull`, and what `git fetch --prune` should mean when the target is empty or unreadable.
- **Push**: what the helper receives, what it validates (fast-forward against the remote branch, clean target), which per-ref status strings it returns, and how `--dry-run` avoids touching the target.
- **Rejections**: exact behaviour for force pushes, deletion refspecs, pushing a ref other than `main`, and pushing when the target has drifted.
- **Stop conditions**: which protocol gaps we accept (no `option progress`, no `export`, no marks) and what git does when those are absent.
