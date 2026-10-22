# Cutover checklist: a config repo against a live target

Use for first use or retargeting. This is the one place a test may touch a live
host.

1. Install and verify: `uv tool install --force .`, then
   `command -v git-remote-waldo` and `git-remote-waldo --version`.
2. Descriptor: verify `.waldo.toml` (or `WALDO_*`); ensure
   `git remote get-url target` exists or `git remote add target waldo::`.
3. Fetch: `git fetch target`. Confirm `target/main` is a snapshot commit.
4. Drift gate: `git diff --stat HEAD target/main`. A non-empty diff means the
   target changed since the last snapshot. **Stop**: fetch and merge it
   normally, or get the operator's decision. `-s ours` reconciles unrelated
   roots only; it must never discard real drift.
5. Reconcile roots only when the trees match:
   `git merge -s ours --allow-unrelated-histories target/main`.
6. Push: `git push target main` (never force). Expect
   `already up to date` when the trees already match.
7. Verify: path-sorted `sha1sum` for every tracked path on both sides
   (`git ls-files` is the list); confirm ignored files survived and no
   `/tmp/waldo-*.lock` remains.
8. On failure: do not force. Fetch the half state, reconcile, then push.
