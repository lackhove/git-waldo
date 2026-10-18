# 08: Cut over the config repo and retire the bridge

**What to build:** The end-to-end cutover that makes the helper the config repo's real workflow. Install the tool so git finds `git-remote-tarssh`, configure the `target` remote, fetch the live target, reconcile the unrelated root snapshot with an ordinary merge, push the config repo, and verify the target tree equals the repository's `HEAD`. Then delete the temporary bridge and remove bridge references from the tool's documentation. This is the one explicit end-to-end check against the live target.

**Blocked by:** 03 — Fetch a real target through the fence, refusing what cannot be represented; 06 — Rejections, stale locks, and interrupted deploys; 07 — Tool mode: `--config` and `--version`

**Status:** ready-for-agent

- [ ] The installed tool is discovered by git as `git-remote-tarssh`.
- [ ] `git-remote-tarssh --config` works in the config repo, or its behavior is verified against the existing target descriptor; the `target` remote is `tarssh::`.
- [ ] `git fetch target` records the live target as a root snapshot, and the unrelated histories are reconciled with `git merge -s ours --allow-unrelated-histories target/main`.
- [ ] `git push target main` succeeds; the target tree equals the config repo's `HEAD` for non-ignored paths, verified by a path-sorted `sha1sum` comparison on both sides.
- [ ] The temporary bridge is deleted and no stale bridge references remain in the tool's docs or layout docs.
- [ ] The fake-target test suite still passes and no test contacts the live target.
- [ ] The execution date and results are recorded in this ticket, as the earlier split ticket did.
