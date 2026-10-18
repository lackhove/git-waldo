# Remote-helper protocol surface: what the helper implements, what git may do

Type: grilling
Status: open
Blocked by: 01

## Question

Design the helper's protocol behaviour against git's actual expectations (ticket 01 supplies the facts):

- **Exposure**: which refs `list` reports (`refs/heads/main` only?), what happens for `list for-push`, and whether tags or extra branches are rejected or ignored.
- **Snapshot construction**: the helper builds a commit from the target tree locally (`hash-object -w`, temporary index, `write-tree`, `commit-tree`), including deletions, author/committer ident and message for a commit no human authored, and the parent chain. The objects must be written **during `list`**, since `?` does not advertise objects; `list` advertises the real oid and `fetch` acks with a blank line. Decide the ident/message convention (tool version? target host? timestamp?).
- **`list for-push` and clone**: whether the tool supports `git clone` (requires the `fetch` ack and `@refs/heads/main HEAD`), and what `list for-push` advertises before the clean check runs.
- **Pull**: which behaviour is `git fetch <remote>` vs a convenience `pull`, and what `git fetch --prune` should mean when the target is empty or unreadable.
- **Push**: what the helper receives, and what it validates that git cannot pre-check (fast-forward under `+`/`--force`, unknown old oids, races, clean target). Use `error <dst> non-fast forward` for `[rejected]`. `--dry-run` requires advertising `option` and answering `ok` to `option dry-run true`, then simulating the push.
- **Rejections**: exact behaviour for force pushes, deletion refspecs, pushing a ref other than `main`, and pushing when the target has drifted.
- **Stop conditions**: which protocol gaps we accept (no `option progress`, no `export`, no marks) and what git does when those are absent.
