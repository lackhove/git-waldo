"""Push preparation and delta deployment.

``list for-push`` is where the push session starts: it takes the target lock,
builds a fresh snapshot for the clean check, and remembers the oid git was
told the remote branch has. The ``push`` batch then either rejects the ref
(drift, non-fast-forward, unsupported refspec) or streams exactly the delta
between the remote branch and the pushed commit into the target.

Ticket 06 owns the remaining rejection vocabulary (force, deletion, other
destinations, stale-lock detail); :func:`parse_refspec` keeps that information
so it can be filled in there.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass

from tarssh.descriptor import Descriptor
from tarssh.errors import ProtocolError
from tarssh.gitcmd import GitStore
from tarssh.snapshot import MAIN_REF, remote_ref, snapshot
from tarssh.target import Target

#: Keep every remote command comfortably below ARG_MAX.
CHUNK = 500
DRIFT_LIMIT = 10

OTHER_REFSPEC_NOT_IMPLEMENTED = "only first pushes of refs/heads/main are implemented"


@dataclass(frozen=True)
class Refspec:
    """One parsed ``push`` line, including the facts ticket 06 will report on."""

    src: str
    dst: str
    force: bool = False
    deletion: bool = False

    @property
    def problem(self) -> str:
        """The rejection for a refspec this build must not act on."""
        if self.force or self.deletion or not self.src or self.dst != MAIN_REF:
            return OTHER_REFSPEC_NOT_IMPLEMENTED
        return ""


def parse_refspec(line: str) -> Refspec:
    command, _, spec = line.partition(" ")
    if command != "push" or not spec.strip():
        raise ProtocolError(f"malformed push line: {line!r}")
    spec = spec.strip()
    force = spec.startswith("+")
    if force:
        spec = spec[1:]
    src, separator, dst = spec.partition(":")
    if not separator:
        src = dst = spec
    deletion = not src
    return Refspec(src=src, dst=dst or src, force=force, deletion=deletion)


def _changed_paths(store: GitStore, old: str, new: str) -> list[str]:
    """Paths whose type or content differs, from ``git diff-tree``."""
    raw = store.run("diff-tree", "-r", "--name-status", "-z", old, new).stdout
    fields = raw.split("\0")
    paths: list[str] = []
    index = 0
    while index + 1 < len(fields) and fields[index]:
        paths.append(fields[index + 1])
        index += 2
    return paths


@dataclass(frozen=True)
class Drift:
    """The paths that make the target differ from the remote branch."""

    paths: tuple[str, ...]

    @property
    def detail(self) -> str:
        shown = ", ".join(self.paths[:DRIFT_LIMIT])
        hidden = len(self.paths) - DRIFT_LIMIT
        if hidden > 0:
            return f"{shown} and {hidden} more ({len(self.paths)} paths)"
        return shown


@dataclass(frozen=True)
class Delta:
    written: tuple[str, ...]
    deleted: tuple[str, ...]

    @property
    def count(self) -> int:
        return len(self.written) + len(self.deleted)


def _full_delta(store: GitStore, commit: str) -> Delta:
    raw = store.run("ls-tree", "-r", "--name-only", "-z", commit).stdout
    return Delta(tuple(path for path in raw.split("\0") if path), ())


def _delta(store: GitStore, old: str, new: str) -> Delta:
    raw = store.run("diff-tree", "-r", "--name-status", "-z", old, new).stdout
    fields = raw.split("\0")
    written: list[str] = []
    deleted: list[str] = []
    index = 0
    while index + 1 < len(fields) and fields[index]:
        status, path = fields[index], fields[index + 1]
        index += 2
        if status.startswith("D"):
            deleted.append(path)
        else:
            # Added, modified, and type changes all need the new blob.
            written.append(path)
    return Delta(tuple(written), tuple(deleted))


@dataclass
class PushSession:
    """Everything push preparation learns during ``list for-push``.

    The lock belongs to the session and is held until :meth:`close`, so a
    target cannot be changed between the clean check and the deploy. Git may
    never send a ``push`` line (an up-to-date push); the caller still closes
    the session on every exit path.
    """

    store: GitStore
    target: Target
    descriptor: Descriptor
    remote: str
    expected: str | None = None
    drift: Drift | None = None
    created: bool = False
    prepared: bool = False
    _lock: str | None = None

    def prepare(self) -> None:
        """Take the lock, then build the snapshot and run the clean check.

        A missing remote branch means branch creation: no snapshot and no
        clean check. An existing branch always advertises its own oid, even
        when the target has drifted, so the push line arrives here and gets
        the drift rejection instead of git inventing an error.
        """
        if self.prepared:
            return

        lock = self.target.acquire_lock()
        try:
            expected = self.store.ref(remote_ref(self.remote))
            if expected is None:
                self.created = True
            else:
                fresh = snapshot(self.store, self.target, self.descriptor, self.remote)
                if self.store.tree_of(fresh) != self.store.tree_of(expected):
                    self.drift = Drift(tuple(_changed_paths(self.store, expected, fresh)))
                self.expected = expected
            self._lock = lock
            self.prepared = True
        except BaseException:
            self._release(lock)
            raise

    def close(self) -> None:
        if self._lock is not None:
            lock, self._lock = self._lock, None
            self._release(lock)

    def _release(self, lock: str) -> None:
        try:
            self.target.release_lock(lock)
        except ProtocolError as error:
            print(f"git-remote-tarssh: {error}", file=sys.stderr, flush=True)


def _is_ancestor(store: GitStore, old: str, new: str) -> bool:
    completed = store.run("merge-base", "--is-ancestor", old, new, check=False)
    return completed.returncode == 0


def _apply(
    store: GitStore,
    target: Target,
    commit: str,
    delta: Delta,
    *,
    created: bool,
) -> None:
    if created or delta.count:
        target.create()
    for start in range(0, len(delta.written), CHUNK):
        paths = delta.written[start : start + CHUNK]
        completed = target.extract(store.archive(commit, paths))
        if completed.returncode != 0:
            raise target.failure(completed, "deploy to")
    for start in range(0, len(delta.deleted), CHUNK):
        target.remove(f"./{path}" for path in delta.deleted[start : start + CHUNK])


@dataclass(frozen=True)
class RefStatus:
    """One line of the push result journal, before the closing blank line."""

    dst: str
    error: str | None = None

    def line(self) -> str:
        if self.error is None:
            return f"ok {self.dst}"
        return f"error {self.dst} {self.error}"


@dataclass(frozen=True)
class PushResult:
    statuses: tuple[RefStatus, ...]
    messages: tuple[str, ...] = ()


def _deploy(
    store: GitStore,
    target: Target,
    session: PushSession,
    commit: str,
    *,
    dry_run: bool,
) -> Delta:
    if session.created:
        delta = _full_delta(store, commit)
    else:
        expected = session.expected
        if expected is None:
            raise AssertionError("a prepared session has either created or expected")
        delta = _delta(store, expected, commit)
    if not dry_run:
        _apply(store, target, commit, delta, created=session.created)
    return delta


def push_refs(
    session: PushSession,
    lines: list[str],
    *,
    dry_run: bool,
) -> PushResult:
    """Answer a whole push batch; git applies the ref updates itself."""
    statuses: list[RefStatus] = []
    messages: list[str] = []
    store = session.store

    session.prepare()
    for line in lines:
        refspec = parse_refspec(line)
        if refspec.problem:
            statuses.append(RefStatus(refspec.dst, refspec.problem))
            continue
        if not store.has_commit(refspec.src):
            raise ProtocolError(
                f"push: object {refspec.src} is not a commit in the local repository"
            )

        if not session.created and session.drift is not None:
            statuses.append(
                RefStatus(
                    refspec.dst,
                    f"target has local changes: {session.drift.detail}",
                )
            )
            continue
        if (
            not session.created
            and session.expected is not None
            and not _is_ancestor(store, session.expected, refspec.src)
        ):
            statuses.append(RefStatus(refspec.dst, "non-fast forward"))
            continue

        delta = _deploy(
            store, session.target, session, refspec.src, dry_run=dry_run
        )
        if delta.count:
            messages.append(
                f"deploying {delta.count} changes: "
                f"{len(delta.written)} written, {len(delta.deleted)} deleted"
            )
        else:
            messages.append("already up to date")
        statuses.append(RefStatus(refspec.dst))

    return PushResult(tuple(statuses), tuple(messages))
