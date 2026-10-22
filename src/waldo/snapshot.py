"""Build the snapshot commit that records the target's state."""

from __future__ import annotations

import io
import os
import tarfile
from dataclasses import dataclass
from typing import TYPE_CHECKING

from pathspec import GitIgnoreSpec

from waldo.errors import ProtocolError

if TYPE_CHECKING:
    from collections.abc import Iterable, Sequence

    from waldo.descriptor import Descriptor
    from waldo.gitcmd import GitStore
    from waldo.target import Target

MAIN_REF = "refs/heads/main"
GITIGNORE = ".gitignore"


def remote_ref(remote: str) -> str:
    return f"refs/remotes/{remote}/main"


@dataclass(frozen=True)
class _Archived:
    """One entry from the target's tar stream."""

    kind: str  # "file" or "symlink"
    executable: bool
    content: bytes


def _name_of(raw: bytes, *, role: str = "target path") -> str:
    """Decode and normalise one ``./``-relative name from find or tar.

    Git paths are UTF-8 in this tool's protocol; a name git cannot carry is
    refused by name rather than silently rewritten.
    """
    try:
        name = raw.decode("utf-8")
    except UnicodeDecodeError as error:
        shown = raw.decode("utf-8", "backslashreplace")
        raise ProtocolError(f"{role} is not valid UTF-8: {shown}") from error
    name = name.removeprefix("./")
    if not name or name == "." or name.startswith("/") or "\0" in name or "\n" in name:
        raise ProtocolError(f"cannot represent {role}: {name!r}")
    return name


def _ignore_spec(content: bytes) -> GitIgnoreSpec:
    text = content.decode("utf-8", "surrogateescape")
    return GitIgnoreSpec.from_lines(text.splitlines())


def _parse_archive(data: bytes, expected: set[str]) -> dict[str, _Archived]:
    """Turn the target's tar stream into the entries a git tree can hold."""
    entries: dict[str, _Archived] = {}
    try:
        with tarfile.open(fileobj=io.BytesIO(data), mode="r:") as archive:
            for member in archive:
                if member.isdir():
                    # Directories are implied by the paths below them; empty
                    # ones are deliberately not representable.
                    continue
                try:
                    raw_name = member.name.encode("utf-8")
                except UnicodeEncodeError:
                    raw_name = member.name.encode("utf-8", "surrogateescape")
                name = _name_of(raw_name, role=f"target path {raw_name!r}")
                if name not in expected:
                    raise ProtocolError(f"tar returned an unexpected target path: {name!r}")

                if member.issym():
                    entries[name] = _Archived(
                        kind="symlink",
                        executable=False,
                        # The link target is the blob content; never resolve it.
                        content=os.fsencode(member.linkname),
                    )
                elif member.isfile():
                    handle = archive.extractfile(member)
                    if handle is None:
                        raise ProtocolError(f"cannot read target path: {name}")
                    try:
                        content = handle.read()
                    except OSError as error:
                        raise ProtocolError(f"cannot read target path {name}: {error}") from error
                    entries[name] = _Archived(
                        kind="file",
                        executable=bool(member.mode & 0o111),
                        content=content,
                    )
                else:
                    raise ProtocolError(
                        f"cannot represent target path {name}: not a regular file or symlink"
                    )
    except tarfile.TarError as error:
        raise ProtocolError(f"cannot parse the target's tar stream: {error}") from error
    return entries


def _local_fence(store: GitStore, rev: str) -> bytes | None:
    return store.read_at(rev, GITIGNORE)


def _target_fence(target: Target, candidates: Sequence[tuple[bytes, str]]) -> bytes | None:
    """The target's own ``.gitignore``, the fallback when no local fence exists."""
    raw = next((raw for raw, name in candidates if name == GITIGNORE), None)
    if raw is None:
        return None
    archived = _parse_archive(target.archive([raw]), {GITIGNORE})
    entry = archived.get(GITIGNORE)
    if entry is None or entry.kind != "file":
        return None
    return entry.content


def _fence_specs(
    store: GitStore,
    target: Target,
    remote: str,
    candidates: Sequence[tuple[bytes, str]],
) -> list[GitIgnoreSpec]:
    specs: list[GitIgnoreSpec] = []
    for rev in (remote_ref(remote), "HEAD"):
        content = _local_fence(store, rev)
        if content is not None:
            specs.append(_ignore_spec(content))
    if specs:
        # Either local fence exists, so normal fetches use only their union.
        # The target's own file is just another tracked target file here.
        return specs
    # No local fence exists: cloning a non-empty target (or a repository with
    # no HEAD yet) cannot see a tracked .gitignore. The target's own file is
    # the only safe fallback, keeping runtime state out of the first snapshot.
    content = _target_fence(target, candidates)
    return [_ignore_spec(content)] if content is not None else []


def _is_ignored(name: str, specs: Iterable[GitIgnoreSpec]) -> bool:
    parts = name.split("/")
    # Git cannot re-include a file whose parent directory is excluded, but a
    # bare ``GitIgnoreSpec.match_file`` applies the last matching pattern to the
    # file's own name, so ``!.gitignore`` would resurrect
    # ``runtime/.gitignore`` inside an ignored ``runtime/``. Check every parent
    # directory as a directory first, then the path itself.
    candidates = ["/".join(parts[:depth]) + "/" for depth in range(1, len(parts))]
    candidates.append(name)
    return any(spec.match_file(path) for spec in specs for path in candidates)


def _tree_entries(store: GitStore, archived: dict[str, _Archived]) -> list[tuple[str, str, str]]:
    entries: list[tuple[str, str, str]] = []
    for name in sorted(archived):
        entry = archived[name]
        mode = "120000" if entry.kind == "symlink" else "100755" if entry.executable else "100644"
        entries.append((mode, store.hash_blob(entry.content), name))
    return entries


def snapshot(
    store: GitStore,
    target: Target,
    descriptor: Descriptor,
    remote: str,
) -> str:
    """Return the oid to advertise for ``refs/heads/main``.

    The target is read through the fence, its blobs and tree are written into
    the local object database, and the snapshot is parented on the current
    remote branch. An unchanged tree emits no commit at all.
    """
    target.check()

    special = target.find_special()
    if special:
        name = _name_of(special[0], role="target path")
        raise ProtocolError(
            f"cannot represent target path {name}: only regular files and symlinks are supported"
        )

    candidates: list[tuple[bytes, str]] = [(raw, _name_of(raw)) for raw in target.find_files()]

    specs = _fence_specs(store, target, remote, candidates)
    survivors = [(raw, name) for raw, name in candidates if not _is_ignored(name, specs)]

    archive = target.archive(raw for raw, _ in survivors)
    archived = _parse_archive(archive, {name for _, name in survivors}) if archive else {}
    tree = store.write_tree(_tree_entries(store, archived))

    parent = store.ref(remote_ref(remote))
    if parent is not None and store.tree_of(parent) == tree:
        return parent
    parents = [parent] if parent is not None else []
    subject = f"snapshot of {descriptor.host}:{descriptor.path}"
    return store.commit(tree, parents, subject)
