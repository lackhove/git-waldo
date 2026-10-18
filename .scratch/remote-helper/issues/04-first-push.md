# 04: First push creates the target and deploys the commit

**What to build:** The push side's first-use path. With no remote branch yet, `git push -u target main` creates a missing target directory, treats the push as a branch creation, and deploys the full commit. Files are extracted with numeric ownership preserved, under a lock outside the target. The operator sees deploy counts on stderr; `--dry-run` reports the same without writing. Until delta pushes land, a push when the remote branch already exists is refused with a clear temporary error rather than deploying unsafely.

**Blocked by:** 02 — Walking skeleton: clone an empty target

**Status:** resolved

- [x] The helper advertises `push` and implements `list for-push` with the real oid.
- [x] `git push -u target main` against a missing or empty target creates the directory with `mkdir -p` and deploys the full commit; the target tree equals `HEAD` for non-ignored paths.
- [x] Deployed files keep target-side ownership, not the client's uid.
- [x] A lock named from the target path is taken on the target under `/tmp` before deployment and released on every exit path; failure to take it is a protocol-level error.
- [x] `git push --dry-run` reports the would-be deploy on stderr and writes nothing.
- [x] Per-ref statuses are printed; git updates the remote branch itself.
- [x] A push when the remote branch already exists is refused with a clear temporary error saying delta pushes are not yet implemented.
- [x] Operator output goes to stderr; stdout remains protocol-only.
- [x] Tests verify the resulting target filesystem directly and never contact a live target.

## Answer

Resolved 2026-10-18. Commit `4c66446` (merged `424fa24`) implemented the first-use push, the target-side lock, the full deploy, dry-run and per-ref statuses. Verified by `tests/test_first_push.py`; the live cutover's push exercised the installed helper against the live target without deploying because the trees were already equal.
