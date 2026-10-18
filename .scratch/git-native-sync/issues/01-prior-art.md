# Prior art: a git remote over busybox-only SSH

Type: research
Status: resolved
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

## Answer

**Nothing existing does this.** No helper or transport treats a busybox-only SSH working tree (`find`/`tar`, no git) as a first-class git remote. Closest, all falling short: `git-remote-gcrypt` (needs rsync/SFTP/git), `git-remote-rclone` (bare repo archive via rclone), `git-remote-dropbox` (Dropbox API), `git-remote-hg` (needs Mercurial), `git-lfs` (not a helper), `git-remote-deploy` (needs git on target), `git-remote-ext` (needs `git-upload-pack`/`git-receive-pack` on target). So tickets 04 and 05 stand, and no scope shrinks.

**Protocol facts that change our design:**

- **`?` does not advertise objects.** In `gitremote-helpers(7)` it means "could not get the value of the ref"; under `fetch` git then fails with `bad object`. Our plan must instead *build the snapshot objects during `list`*, advertise the **real oid**, and answer the resulting `fetch <oid> <name>` with a **blank line** (one per batch). Normal `git fetch` then skips the transport fetch via `check_exist_and_connected()`.
- **`git clone` always calls `transport_fetch_refs`**, so `fetch` must exist as an ack even when `list` already wrote the objects. `list` must include `@refs/heads/main HEAD`, or clone loses `origin/HEAD` and an anonymous `git fetch <url>` fails with "couldn't find remote ref HEAD".
- **`list for-push` must advertise the real current target oid.** If it advertises an unknown value, git treats the ref as new, skips its fast-forward pre-check, and pushes blind. The clean-target check belongs here (and again in `push`).
- **Push enforcement is layered:** git pre-rejects non-fast-forward pushes it can see and never sends them to the helper, but the helper must still enforce fast-forward for `+`/`--force`, unknown old oids, and races. It must also reject when the target is dirty.
- **Status spelling:** `error <dst> non-fast forward` (spaces) yields git's `[rejected] (non-fast-forward)`; the hyphenated form yields `[remote rejected]`.
- **`git push --dry-run` is not free:** advertise `option` and answer `ok` to `option dry-run true`, else git exits 128 with "helper does not support dry-run". The `push` lines still arrive and must be simulated.
- **`git fetch --prune` is free** (pruned locally from `list`), and the helper **must not write `refs/remotes/*`** — git owns those under the fetch refspec.

Findings: `docs/research/git-remote-helper-prior-art.md` on branch `research/prior-art` (commit `919ecdc`), with per-claim citations to `gitremote-helpers.adoc`, git's C sources, and a prototype helper used to verify each row.
