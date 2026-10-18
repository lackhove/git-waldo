# 03: Fetch a real target through the fence, refusing what cannot be represented

**What to build:** Real snapshots. The helper reads the target's regular files and symlinks through the fence, writes their content without applying local git filters, assembles a tree, parents the snapshot on the current remote branch, and skips the commit when the tree is unchanged. The fence is the union of the `.gitignore` at the remote branch and at `HEAD`: a path ignored by either is invisible. Paths the target cannot represent faithfully are fatal errors naming the path rather than silent drops.

**Blocked by:** 02 — Walking skeleton: clone an empty target

**Status:** resolved

- [x] A target with regular files and symlinks produces a snapshot whose tree equals the target's non-ignored paths, byte for byte.
- [x] Regular modes 0644 and 0755 and symlink mode 120000 are preserved; symlinks are stored as links and never followed.
- [x] The target's `.gitignore` is read with a single-file tar; candidate names come from `find` and are filtered through git's own ignore semantics against the union of the remote-branch fence and the `HEAD` fence.
- [x] Blobs are written without clean filters or `core.autocrlf`; the tree is assembled against a temporary index, never via `git add`.
- [x] The snapshot is parented on the current `refs/remotes/<remote>/main` when it exists, and is a root commit otherwise.
- [x] If the built tree equals the parent's tree, no commit is emitted and the parent oid is advertised unchanged; a clean repeated fetch does not move the remote branch or create an empty commit.
- [x] FIFOs, sockets, device nodes, unreadable files, and non-UTF-8 names fail with a non-zero protocol-level error naming the path.
- [x] Empty directories are ignored rather than refused.
- [x] Ignored target files never enter the snapshot and never count as target drift.
- [x] Tests cover both union directions (ignored at the remote branch but not at `HEAD`, and the reverse) and every refused path type.

## Comments

The device-node test needs `CAP_MKNOD` and skips when the host cannot create
one; FIFO, socket, unreadable file and non-UTF-8 name run everywhere.

`Target` now owns the read seam (`find_files`, `find_special`, `archive`), so
ticket 04 can add write operations without changing callers. `snapshot.py`
parses the tar stream in `snapshot.py`; the target module only transports bytes.

## Answer

Resolved 2026-10-18. Commit `40b9594` (merged `4d05333`) built real snapshots through the union fence. Verified by `tests/test_snapshot.py` and `tests/test_snapshot_contents.py`, including both union directions and every refused path type. The live cutover exposed one fence edge — a negation re-including a file under an ignored directory — fixed with a regression test in ticket 08.
