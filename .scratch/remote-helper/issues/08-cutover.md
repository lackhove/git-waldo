# 08: Cut over the config repo and retire the bridge

**What to build:** The end-to-end cutover that makes the helper the config repo's real workflow. Install the tool so git finds `git-remote-tarssh`, configure the `target` remote, fetch the live target, reconcile the unrelated root snapshot with an ordinary merge, push the config repo, and verify the target tree equals the repository's `HEAD`. Then delete the temporary bridge and remove bridge references from the tool's documentation. This is the one explicit end-to-end check against the live target.

**Blocked by:** 03 — Fetch a real target through the fence, refusing what cannot be represented; 06 — Rejections, stale locks, and interrupted deploys; 07 — Tool mode: `--config` and `--version`

**Status:** resolved

- [ ] The installed tool is discovered by git as `git-remote-tarssh`.
- [ ] `git-remote-tarssh --config` works in the config repo, or its behavior is verified against the existing target descriptor; the `target` remote is `tarssh::`.
- [ ] `git fetch target` records the live target as a root snapshot, and the unrelated histories are reconciled with `git merge -s ours --allow-unrelated-histories target/main`.
- [ ] `git push target main` succeeds; the target tree equals the config repo's `HEAD` for non-ignored paths, verified by a path-sorted `sha1sum` comparison on both sides.
- [ ] The temporary bridge is deleted and no stale bridge references remain in the tool's docs or layout docs.
- [ ] The fake-target test suite still passes and no test contacts the live target.
- [ ] The execution date and results are recorded in this ticket, as the earlier split ticket did.

## Answer

Resolved 2026-10-18. Installed `tarssh 0.1.0` from this worktree with `uv tool install --force`; `command -v git-remote-tarssh` and `git-remote-tarssh --version` both answered from `~/.local/bin`. The config repo's `.tarssh.toml` already matched the live descriptor (`user@host.example:22222`, `/srv/config`); no `target` remote existed, so it was added as `tarssh::`.

`git fetch target` produced root snapshot `bbbbbbbf8cabafbb8bace2103a8b16f8fe1890fc`, ident `tarssh <tarssh@localhost>`, subject `snapshot of host.example:/srv/config`. The safety diff against config `HEAD` (`aaaaaaa`) was first non-empty: the fence leaked `extensions/example_component/.idea/.gitignore` because `pathspec` let `!.gitignore` re-include a file inside an ignored directory. Git forbids that re-inclusion; `snapshot._is_ignored` now checks each parent directory with trailing-slash semantics before the file itself, with regression test `test_a_negation_cannot_reinclude_a_file_under_an_ignored_directory`. After reinstalling and re-fetching from a deleted local remote-tracking ref, `git diff --stat HEAD target/main` was empty, so the target had not drifted.

Reconciled with `git merge -s ours --allow-unrelated-histories target/main`: merge commit `167bdad6b47c732716bc7ce1aa777e045465b211`, parents `aaaaaaa` and `bbbbbbb`. `git push target main` exited 0 and reported `already up to date` / `bbbbbbb..167bdad main -> main` (no files deployed because the trees were equal). A second `git fetch target` left `refs/remotes/target/main` at `167bdad`.

Path-sorted `sha1sum` of all 18 tracked paths was identical locally and on the target (`diff` empty). Ignored target files were not deployed, `.tarssh.toml` is absent from the target, and no `tarssh-*.lock` remained. `the bridge` was deleted and bridge/layout references removed from `AGENTS.md`, `docs/agents/domain.md`, and `docs/design/spec.md` §10/Traceability. `uv run pytest` and `uv run ruff check .` pass; no test contacts the live target.
