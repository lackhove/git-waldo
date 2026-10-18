"""Local git subprocesses and the object store a snapshot is written into.

Inside a repository the helper writes into that repository's object database,
which is what makes git's ``check_exist_and_connected()`` skip the transport
fetch. Outside one (``git ls-remote``) it writes into a temporary bare repo
that lives for the length of the helper process.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from collections.abc import Iterable, Mapping
from pathlib import Path

from tarssh.errors import ProtocolError

EMPTY_TREE = "4b825dc642cb6eb9a060e54bf8d69288fbee4904"
IDENT = {
    "GIT_AUTHOR_NAME": "tarssh",
    "GIT_AUTHOR_EMAIL": "tarssh@localhost",
    "GIT_COMMITTER_NAME": "tarssh",
    "GIT_COMMITTER_EMAIL": "tarssh@localhost",
}


def _git(args: list[str], cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=cwd,
        text=True,
        capture_output=True,
        check=False,
    )


class GitStore:
    """The object database and ref lookups used while building snapshots."""

    def __init__(self, git_dir: Path, *, temporary: bool = False) -> None:
        self.git_dir = git_dir
        self.temporary = temporary

    @classmethod
    def discover(cls, cwd: Path | None = None) -> GitStore:
        """Use the current repository, or a temporary bare one outside a repo."""
        probe = _git(["rev-parse", "--absolute-git-dir"], cwd)
        if probe.returncode == 0:
            git_dir = Path(probe.stdout.strip())
            object_format = _git(["rev-parse", "--show-object-format"], cwd)
            if object_format.returncode != 0:
                raise ProtocolError(
                    f"cannot determine the repository object format: "
                    f"{object_format.stderr.strip()}"
                )
            found = object_format.stdout.strip()
            if found != "sha1":
                raise ProtocolError(
                    f"unsupported repository object format {found}: "
                    f"tarssh requires sha1, not sha256"
                )
            return cls(git_dir)

        directory = Path(tempfile.mkdtemp(prefix="tarssh-objects-"))
        init = _git(
            ["init", "--quiet", "--bare", "--object-format=sha1", str(directory)],
            cwd=cwd,
        )
        if init.returncode != 0:
            shutil.rmtree(directory, ignore_errors=True)
            raise ProtocolError(
                f"cannot create a temporary object store: {init.stderr.strip()}"
            )
        return cls(directory, temporary=True)

    def close(self) -> None:
        if self.temporary:
            shutil.rmtree(self.git_dir, ignore_errors=True)

    def _environment(self, extra: Mapping[str, str] | None = None) -> dict[str, str]:
        environment = os.environ.copy()
        environment["GIT_DIR"] = str(self.git_dir)
        environment.pop("GIT_WORK_TREE", None)
        environment.pop("GIT_INDEX_FILE", None)
        if extra:
            environment.update(extra)
        return environment

    def run(
        self,
        *args: str,
        input: str | bytes | None = None,
        env: Mapping[str, str] | None = None,
        check: bool = True,
    ) -> subprocess.CompletedProcess[str]:
        completed = subprocess.run(
            ["git", *args],
            input=input,
            text=isinstance(input, str) or input is None,
            capture_output=True,
            env=self._environment(env),
            check=False,
        )
        if check and completed.returncode != 0:
            detail = (completed.stderr or completed.stdout).strip()
            raise ProtocolError(f"git {' '.join(args)} failed: {detail}")
        return completed

    def out(self, *args: str, env: Mapping[str, str] | None = None) -> str:
        return self.run(*args, env=env).stdout.strip()

    def ref(self, name: str) -> str | None:
        completed = self.run("rev-parse", "--verify", "--quiet", name, check=False)
        oid = completed.stdout.strip()
        return oid if completed.returncode == 0 and oid else None

    def tree_of(self, rev: str) -> str:
        return self.out("rev-parse", f"{rev}^{{tree}}")

    def read_at(self, rev: str, path: str) -> bytes | None:
        """The raw blob at ``rev:path``, or ``None`` when it does not exist.

        ``None`` also covers an unborn ref: neither a first fetch nor a repo
        without a ``.gitignore`` at ``HEAD`` has a local fence.
        """
        completed = subprocess.run(
            ["git", "cat-file", "blob", f"{rev}:{path}"],
            capture_output=True,
            env=self._environment(),
            check=False,
        )
        if completed.returncode != 0:
            return None
        return completed.stdout

    def has_commit(self, oid: str) -> bool:
        completed = self.run(
            "rev-parse", "--verify", "--quiet", f"{oid}^{{commit}}", check=False
        )
        return completed.returncode == 0

    def write_tree(self, entries: Iterable[tuple[str, str, str]] = ()) -> str:
        """Assemble a tree through a temporary index, never ``git add``."""
        index_dir = Path(tempfile.mkdtemp(prefix="tarssh-index-"))
        try:
            env = {"GIT_INDEX_FILE": str(index_dir / "index")}
            for mode, oid, path in entries:
                self.run(
                    "update-index",
                    "--add",
                    "--cacheinfo",
                    f"{mode},{oid},{path}",
                    env=env,
                )
            return self.out("write-tree", env=env)
        finally:
            shutil.rmtree(index_dir, ignore_errors=True)

    def hash_blob(self, data: bytes) -> str:
        completed = subprocess.run(
            ["git", "hash-object", "-w", "--no-filters", "--stdin"],
            input=data,
            capture_output=True,
            env=self._environment(),
            check=False,
        )
        if completed.returncode != 0:
            detail = completed.stderr.decode("utf-8", "replace").strip()
            raise ProtocolError(f"git hash-object failed: {detail}")
        return completed.stdout.decode("utf-8", "replace").strip()

    def archive(self, rev: str) -> bytes:
        """The commit as a tar stream, ready to pipe into the target's tar."""
        completed = subprocess.run(
            ["git", "archive", "--format=tar", rev],
            capture_output=True,
            env=self._environment(),
            check=False,
        )
        if completed.returncode != 0:
            detail = completed.stderr.decode("utf-8", "replace").strip()
            raise ProtocolError(f"git archive {rev} failed: {detail}")
        return completed.stdout

    def commit(self, tree: str, parents: Iterable[str], message: str) -> str:
        args = ["commit-tree", tree]
        for parent in parents:
            args.extend(["-p", parent])
        args.extend(["-m", message])
        return self.out(*args, env=IDENT)
