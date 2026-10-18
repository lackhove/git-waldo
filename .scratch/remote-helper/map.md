# Map: the remote-helper implementation

## Destination

`git-remote-tarssh` installed and used as the live `config-repo` repo's `target` remote: fetch records the target tree as a snapshot, merge reconciles it, push deploys the delta to the busybox-only host, and the temporary bridge is gone. Reached 2026-10-18 (ticket 08).

## Decisions so far

- [01 — Fake target and protocol test harness](issues/01-test-harness.md): `tests/conftest.py` with a localhost SSH seam, a busybox-command whitelist and a protocol driver; every test runs without a live host.
- [02 — Empty-target walking skeleton](issues/02-empty-target-clone.md): installable helper, `tarssh://` and `tarssh::`, descriptor precedence, real oids, root snapshot on clone/fetch.
- [03 — Fetch through the fence](issues/03-fetch-through-fence.md): snapshot tree built from the target through the union of the remote-branch and `HEAD` fences; `--no-filters`; unrepresentable paths refuse loudly. A negation must not re-include a file under an ignored directory.
- [04 — First push](issues/04-first-push.md): missing target created, full deploy under a target-side lock, dry-run, per-ref statuses.
- [05 — Delta push](issues/05-delta-push.md): clean check before fast-forward, archive writes plus `./`-relative deletion chunks, ignored files survive, no-op reports `already up to date`.
- [06 — Rejections and locks](issues/06-rejections-and-locks.md): force/delete/wrong-ref rejected with git's tokens, stale locks reported, interrupted deploys become drift, ref rejections exit 0.
- [07 — Tool mode](issues/07-tool-mode.md): `--version` and the `--config` writer; a leading `-` is always a verb.
- [08 — Cutover](issues/08-cutover.md): live fetch/merge/push with a path-sorted `sha1sum` verification, bridge deleted, docs rewritten for the helper. The fence ancestor fix landed here.
