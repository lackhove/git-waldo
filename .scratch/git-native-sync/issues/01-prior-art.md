# Prior art: a git remote over busybox-only SSH

Type: research
Status: open
Blocked by: —

## Question

Does this already exist? Specifically: is there an existing git remote helper or transport that makes an SSH target with only busybox `find` and `tar` — **no git, no rsync, no SFTP** — a first-class git remote (fetch, push, remote-tracking refs), rather than a one-way file copier?

If a tool does this, name it, its licence, and its operational requirements on the target. Adopting it would close tickets 04 and 05 as out of scope, so that answer matters more than the rest.

If nothing does, establish the minimum surface we must implement, from primary sources:

- `gitremote-helpers(7)`: which commands a helper must handle for `fetch`, for `push`, and for `list`; what `list for-push` is for; what `option` calls git will send; how `? <oid>` advertises an object already present in the local object database so no pack is transferred (this is how the snapshot commit can be built locally and handed straight to git).
- What git does with the helper's `refs/heads/*` in `list` (does it create `refs/remotes/<name>/*` itself, and under what fetch refspec?).
- What a helper is expected to do on push: refspec parsing, reporting per-ref status (`ok`, `error`, `non-fast-forward`), and whether git or the helper is responsible for the fast-forward decision.
- Behaviour of `git fetch --prune` and `git push --dry-run` against a helper.
- Prior art to read for shape, not to copy: `git-remote-hg`, `git-remote-dropbox`, `git-lfs`, `git-remote-gcrypt`, and any helper that materialises a working tree rather than a bare repository.
- Whether `git-remote-ext` or another built-in transport removes the need for a custom helper given the target lacks git (state plainly why it does or does not).
