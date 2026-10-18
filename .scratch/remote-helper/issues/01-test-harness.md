# 01: Fake target and protocol test harness

**What to build:** A pytest foundation that makes the helper testable end to end without a live host. It provides a fake target reached over a localhost-only SSH seam, restricts that target to the busybox command set (`find`, `tar`, `rm`, `mkdir`, `xargs`, `sha1sum`), and drives `git-remote-tarssh` exactly as git does: git's command lines on stdin, protocol output on stdout, operator output on stderr, and an exit code. Tests can populate or empty the target, remove it, make paths unreadable, break SSH, and force an extraction failure.

**Blocked by:** None (can start immediately)

**Status:** resolved

- [x] `uv run pytest` runs the harness.
- [x] A target directory can be created, populated, emptied, removed, and made unreadable per test.
- [x] The helper reaches the fake target without a real network SSH connection or a live instance.
- [x] Any attempt to use git, rsync, SFTP, or a command or flag outside the busybox set fails the test and names the offending command.
- [x] The protocol driver feeds `list`, `list for-push`, `fetch`, `push`, and `option` batches, and asserts stdout lines, stderr lines, and exit codes independently.
- [x] SSH failure, unreadable target, missing target, and failed extraction are simulatable.

## Answer

Resolved 2026-10-18. Commit `6b6e6d5` (merged `58ab1c4`) added `tests/conftest.py`, `fake_ssh.py`, `harness.py`, the protocol driver, the busybox guard and the git shim. Verified by the full `uv run pytest` suite (141 passed, 1 skipped for `CAP_MKNOD`); the tests never contact the live target.
