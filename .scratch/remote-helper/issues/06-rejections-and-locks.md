# 06: Rejections, stale locks, and interrupted deploys

**What to build:** The remaining refusal and failure surface. Force pushes, branch deletions, and pushes to any ref other than `refs/heads/main` are rejected with git's exact tokens. A stale lock is reported by its target path and never auto-broken. An interrupted deploy leaves target drift that the next push refuses until the operator fetches and reconciles it. Ref rejections exit zero after printing statuses; transport-level failures exit non-zero.

**Blocked by:** 05 — Delta pushes with clean check and fast-forward

**Status:** resolved

- [x] A `+`/force push sends `error <dst> force pushes are not supported`, which git shows as `[remote rejected]`.
- [x] A `:<dst>` deletion sends `error <dst> deleting branches is not supported`.
- [x] Any destination other than `refs/heads/main` sends `error <dst> only refs/heads/main is deployed`.
- [x] A stale lock is reported by its target path and is never auto-broken.
- [x] An interrupted or failed deploy leaves target drift; the next push refuses until a fetch and merge resolve it.
- [x] When a deletion is refused, per-file lines identify the affected paths.
- [x] Ref rejections exit 0 after printing statuses; SSH failure, unreadable target, and failed extraction go to stderr with a non-zero exit.
- [x] Tests cover every rejection and failure case and never contact a live target.

## Answer

Resolved 2026-10-18. Commit `4394576` (merged `4cfed56`) implemented force/delete/wrong-ref rejections, stale-lock reporting, interrupted-deploy drift and the exit-code rules. Verified by `tests/test_rejections.py`.
