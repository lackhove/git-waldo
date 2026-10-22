"""Push preparation and delta deployment.

``list for-push`` is where the push session starts: it takes the target lock,
builds a fresh snapshot for the clean check, and remembers the oid git was
told the remote branch has. The ``push`` batch then either rejects the ref
(drift, non-fast-forward, unsupported refspec) or streams exactly the delta
between the remote branch and the pushed commit into the target.

Ref-level refusals use git's exact status vocabulary: force pushes, branch
deletions, and every destination other than ``refs/heads/main``. They are
results, not transport errors, so the helper still exits zero.
"""

from __future__ import annotations

import re
import sys
from dataclasses import dataclass
from typing import TYPE_CHECKING

from waldo.errors import ProtocolError
from waldo.snapshot import MAIN_REF, remote_ref, snapshot

if TYPE_CHECKING:
    from waldo.descriptor import Descriptor
    from waldo.gitcmd import GitStore
    from waldo.target import Target

#: Keep every remote command comfortably below ARG_MAX.
CHUNK = 500
DRIFT_LIMIT = 10


def _err(message: str) -> None:
    sys.stderr.write(f"git-remote-waldo: {message}\n")
    sys.stderr.flush()


@dataclass(frozen=True)
class Refspec:
    """One parsed ``push`` line, including the facts its rejection reports on."""

    src: str
    dst: str
    force: bool = False
    deletion: bool = False

    @property
    def problem(self) -> str | None:
        """The rejection for a refspec this build must not act on.

        Precedence is part of the outcome: a forced deletion of another
        branch reports force first, then deletion, then the destination.
        """
        if self.force:
            return "force pushes are not supported"
        if self.deletion:
            return "deleting branches is not supported"
        if self.dst != MAIN_REF:
            return "only refs/heads/main is deployed"
        return None


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
    else:
        dst = dst or src
    if not src and not dst:
        raise ProtocolError(f"malformed push line: {line!r}")
    deletion = not src
    return Refspec(src=src, dst=dst, force=force, deletion=deletion)


def _diff_entries(store: GitStore, old: str, new: str) -> list[tuple[str, str]]:
    """``(status, path)`` pairs from ``git diff-tree``, in diff order."""
    raw = store.run("diff-tree", "-r", "--name-status", "-z", old, new).stdout
    fields = raw.split("\0")
    entries: list[tuple[str, str]] = []
    index = 0
    while index + 1 < len(fields) and fields[index]:
        entries.append((fields[index], fields[index + 1]))
        index += 2
    return entries


def _changed_paths(store: GitStore, old: str, new: str) -> list[str]:
    """Paths whose type or content differs, from ``git diff-tree``."""
    return [path for _, path in _diff_entries(store, old, new)]


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
    written: list[str] = []
    deleted: list[str] = []
    for status, path in _diff_entries(store, old, new):
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
            _err(str(error))


def _is_ancestor(store: GitStore, old: str, new: str) -> bool:
    completed = store.run("merge-base", "--is-ancestor", old, new, check=False)
    return completed.returncode == 0


def _names_path(message: str, path: str) -> bool:
    """Whether the target's stderr names exactly this ``./``-relative path."""
    token = re.escape(f"./{path}")
    return re.search(rf"(?<![\w./-]){token}(?![\w./-])", message) is not None


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
        paths = delta.deleted[start : start + CHUNK]
        try:
            target.remove(f"./{path}" for path in paths)
        except ProtocolError as error:
            # busybox rm names the paths it could not remove in stderr. Report
            # only those; without per-path detail, the chunk is all we know.
            message = str(error)
            failed = [path for path in paths if _names_path(message, path)] or paths
            for path in failed:
                _err(f"cannot delete {path} from target")
            raise


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
            message = "a prepared session has either created or expected"
            raise AssertionError(message)
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
    label = session.descriptor.label()

    session.prepare()
    for line in lines:
        refspec = parse_refspec(line)
        problem = refspec.problem
        if problem is not None:
            statuses.append(RefStatus(refspec.dst, problem))
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

        delta = _deploy(store, session.target, session, refspec.src, dry_run=dry_run)
        if delta.count:
            messages.append(
                f"deploying {delta.count} changes to {label}: "
                f"{len(delta.written)} written, {len(delta.deleted)} deleted"
            )
        else:
            messages.append(f"already up to date with {label}")
        statuses.append(RefStatus(refspec.dst))

    return PushResult(tuple(statuses), tuple(messages))
