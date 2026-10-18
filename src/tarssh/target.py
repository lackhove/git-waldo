"""The SSH seam and the busybox commands the target may run.

Only ``find``, ``tar``, ``rm``, ``mkdir`` and shell builtins are available on
the far side. This module owns invocation, not policy: callers decide what a
failed command means.
"""

from __future__ import annotations

import contextlib
import hashlib
import shlex
import subprocess
import sys
from dataclasses import dataclass

from tarssh.descriptor import Descriptor
from tarssh.errors import ProtocolError


def _last_line(text: str | bytes) -> str:
    if isinstance(text, bytes):
        text = text.decode("utf-8", "replace")
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    return lines[-1] if lines else ""


@dataclass(frozen=True)
class Target:
    """One resolved target, reached over SSH."""

    descriptor: Descriptor
    ssh_command: str = "ssh"

    def ssh(
        self,
        command: str,
        *,
        input: str | bytes | None = None,
    ) -> subprocess.CompletedProcess[str]:
        argv = [
            self.ssh_command,
            "-o",
            "BatchMode=yes",
            "-p",
            str(self.descriptor.port),
            "-l",
            self.descriptor.user,
            self.descriptor.host,
            command,
        ]
        return subprocess.run(
            argv,
            input=input,
            text=isinstance(input, str) or input is None,
            capture_output=True,
            check=False,
        )

    def failure(self, completed: subprocess.CompletedProcess, action: str) -> ProtocolError:
        detail = _last_line(completed.stderr) or f"ssh exited {completed.returncode}"
        return ProtocolError(
            f"cannot {action} target {self.descriptor.path} "
            f"at {self.descriptor.url}: {detail}"
        )

    def check(self) -> None:
        """Fail loudly if the target is missing, unreadable or not a directory."""
        command = f"cd {shlex.quote(self.descriptor.path)} && find . -maxdepth 0 -print"
        completed = self.ssh(command)
        if completed.returncode != 0:
            raise self.failure(completed, "read")

    def create(self) -> None:
        """Create a missing target directory; an existing one is left alone."""
        completed = self.ssh(f"mkdir -p {shlex.quote(self.descriptor.path)}")
        if completed.returncode != 0:
            raise self.failure(completed, "create")

    def extract(self, archive: bytes) -> subprocess.CompletedProcess:
        """Unpack a tar stream into the target.

        ``-o`` keeps ownership with the target-side user instead of restoring
        the client's numeric uid, which would be meaningless on the far side.
        """
        command = f"tar -o -xf - -C {shlex.quote(self.descriptor.path)}"
        return self.ssh(command, input=archive)

    def lock_path(self) -> str:
        """The lock lives outside the target so it can never become drift."""
        digest = hashlib.sha256(self.descriptor.path.encode()).hexdigest()[:16]
        return f"/tmp/tarssh-{digest}.lock"

    def acquire_lock(self) -> str:
        path = self.lock_path()
        completed = self.ssh(f"mkdir {shlex.quote(path)}")
        if completed.returncode != 0:
            detail = _last_line(completed.stderr) or f"ssh exited {completed.returncode}"
            raise ProtocolError(
                f"cannot take lock {path} on target {self.descriptor.path} "
                f"at {self.descriptor.url}: {detail}"
            )
        return path

    def release_lock(self, path: str) -> None:
        completed = self.ssh(f"rm -rf {shlex.quote(path)}")
        if completed.returncode != 0:
            detail = _last_line(completed.stderr) or f"ssh exited {completed.returncode}"
            raise ProtocolError(f"cannot release lock {path}: {detail}")

    @contextlib.contextmanager
    def locked(self):
        """Hold the target lock for one deployment; always release it.

        A lock that was already there belongs to someone else (or a previous
        interrupted run) and is reported, never removed.
        """
        path = self.acquire_lock()
        try:
            yield path
        finally:
            try:
                self.release_lock(path)
            except ProtocolError as error:
                print(f"git-remote-tarssh: {error}", file=sys.stderr, flush=True)
