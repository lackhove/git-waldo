"""First-use push: deploy a complete commit into a target that has no branch yet.

Delta pushes, clean checks and fast-forward enforcement arrive in later
tickets. Until then any push whose remote branch already exists is refused as
a temporary, per-ref protocol result so git never sees a half-applied update.
"""

from __future__ import annotations

from dataclasses import dataclass

from tarssh.errors import ProtocolError
from tarssh.gitcmd import GitStore
from tarssh.snapshot import MAIN_REF, remote_ref
from tarssh.target import Target

DELTA_NOT_IMPLEMENTED = "delta pushes are not yet implemented"
OTHER_REFSPEC_NOT_IMPLEMENTED = "only first pushes of refs/heads/main are implemented"


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


def parse_refspec(line: str) -> tuple[str, str, str]:
    """Return ``(src, dst, problem)`` for one ``push`` line.

    ``problem`` is non-empty when this build must not act on the refspec. The
    rejection vocabulary grows in the delta-push ticket; first use only knows
    how to create ``refs/heads/main``.
    """
    command, _, spec = line.partition(" ")
    if command != "push" or not spec.strip():
        raise ProtocolError(f"malformed push line: {line!r}")
    spec = spec.strip()
    forced = spec.startswith("+")
    if forced:
        spec = spec[1:]
    src, separator, dst = spec.partition(":")
    if not separator:
        src = dst = spec
    if forced or not src or not dst or dst != MAIN_REF:
        return src, dst or src, OTHER_REFSPEC_NOT_IMPLEMENTED
    return src, dst, ""


def _count_written(store: GitStore, commit: str) -> int:
    listing = store.out("ls-tree", "-r", "--name-only", "-z", commit)
    return len([path for path in listing.split("\0") if path])


def _deploy(store: GitStore, target: Target, commit: str, *, dry_run: bool) -> int:
    written = _count_written(store, commit)

    with target.locked():
        if dry_run:
            return written
        target.create()
        archive = store.archive(commit)
        completed = target.extract(archive)
        if completed.returncode != 0:
            raise target.failure(completed, "deploy to")
    return written


def push_refs(
    store: GitStore,
    target: Target,
    remote: str,
    lines: list[str],
    *,
    dry_run: bool,
) -> PushResult:
    """Answer a whole push batch; git applies the ref updates itself."""
    statuses: list[RefStatus] = []
    messages: list[str] = []
    existing = store.ref(remote_ref(remote))

    for line in lines:
        src, dst, problem = parse_refspec(line)
        if problem:
            statuses.append(RefStatus(dst or src, problem))
            continue
        if existing is not None:
            statuses.append(RefStatus(dst, DELTA_NOT_IMPLEMENTED))
            continue
        if not store.has_commit(src):
            raise ProtocolError(f"push: object {src} is not a commit in the local repository")
        written = _deploy(store, target, src, dry_run=dry_run)
        if written:
            messages.append(f"deploying {written} changes: {written} written, 0 deleted")
        else:
            messages.append("already up to date")
        statuses.append(RefStatus(dst))

    return PushResult(tuple(statuses), tuple(messages))
