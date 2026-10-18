# 01: Fake target and protocol test harness

**What to build:** A pytest foundation that makes the helper testable end to end without a live host. It provides a fake target reached over a localhost-only SSH seam, restricts that target to the busybox command set (`find`, `tar`, `rm`, `mkdir`, `xargs`, `sha1sum`), and drives `git-remote-tarssh` exactly as git does: git's command lines on stdin, protocol output on stdout, operator output on stderr, and an exit code. Tests can populate or empty the target, remove it, make paths unreadable, break SSH, and force an extraction failure.

**Blocked by:** None (can start immediately)

**Status:** ready-for-agent

- [ ] `uv run pytest` runs the harness.
- [ ] A target directory can be created, populated, emptied, removed, and made unreadable per test.
- [ ] The helper reaches the fake target without a real network SSH connection or a live instance.
- [ ] Any attempt to use git, rsync, SFTP, or a command or flag outside the busybox set fails the test and names the offending command.
- [ ] The protocol driver feeds `list`, `list for-push`, `fetch`, `push`, and `option` batches, and asserts stdout lines, stderr lines, and exit codes independently.
- [ ] SSH failure, unreadable target, missing target, and failed extraction are simulatable.
