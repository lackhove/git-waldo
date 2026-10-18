# 04: First push creates the target and deploys the commit

**What to build:** The push side's first-use path. With no remote branch yet, `git push -u target main` creates a missing target directory, treats the push as a branch creation, and deploys the full commit. Files are extracted with numeric ownership preserved, under a lock outside the target. The operator sees deploy counts on stderr; `--dry-run` reports the same without writing. Until delta pushes land, a push when the remote branch already exists is refused with a clear temporary error rather than deploying unsafely.

**Blocked by:** 02 — Walking skeleton: clone an empty target

**Status:** ready-for-agent

- [ ] The helper advertises `push` and implements `list for-push` with the real oid.
- [ ] `git push -u target main` against a missing or empty target creates the directory with `mkdir -p` and deploys the full commit; the target tree equals `HEAD` for non-ignored paths.
- [ ] Deployed files keep target-side ownership, not the client's uid.
- [ ] A lock named from the target path is taken on the target under `/tmp` before deployment and released on every exit path; failure to take it is a protocol-level error.
- [ ] `git push --dry-run` reports the would-be deploy on stderr and writes nothing.
- [ ] Per-ref statuses are printed; git updates the remote branch itself.
- [ ] A push when the remote branch already exists is refused with a clear temporary error saying delta pushes are not yet implemented.
- [ ] Operator output goes to stderr; stdout remains protocol-only.
- [ ] Tests verify the resulting target filesystem directly and never contact a live target.
