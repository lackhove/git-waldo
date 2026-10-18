"""The SSH seam and the busybox commands the target may run.

Only ``find``, ``tar``, ``rm``, ``mkdir`` and shell builtins are available on
the far side. This module owns invocation, not policy: callers decide what a
failed command means.
"""

from __future__ import annotations

import shlex
import subprocess
from collections.abc import Iterable
from dataclasses import dataclass

from tarssh.descriptor import Descriptor
from tarssh.errors import ProtocolError


def _detail(text: str | bytes) -> str:
    """Keep every diagnostic line, so tar's failing path is not lost."""
    if isinstance(text, bytes):
        text = text.decode("utf-8", "replace")
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    return "; ".join(lines)


def _shell_path(path: str) -> str:
    return shlex.quote(path)


@dataclass(frozen=True)
class Target:
    """One resolved target, reached over SSH.

    Every remote operation lives here so the snapshot and push paths share one
    seam and ticket 04 can add writes beside :meth:`archive` and
    :meth:`find_files`.
    """

    descriptor: Descriptor
    ssh_command: str = "ssh"

    def run(
        self,
        command: str,
        *,
        input: str | bytes | None = None,
    ) -> subprocess.CompletedProcess[bytes]:
        """Run one remote shell command and keep its streams as bytes.

        Byte streams matter: ``find -print0`` and ``tar`` carry file names and
        file content, neither of which is guaranteed to be UTF-8.
        """
        data = input.encode() if isinstance(input, str) else input
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
            input=data,
            capture_output=True,
            check=False,
        )

    def ssh(
        self,
        command: str,
        *,
        input: str | bytes | None = None,
    ) -> subprocess.CompletedProcess[str]:
        """Same as :meth:`run`, decoded for commands that only print text."""
        completed = self.run(command, input=input)
        return subprocess.CompletedProcess(
            completed.args,
            completed.returncode,
            completed.stdout.decode("utf-8", "replace"),
            completed.stderr.decode("utf-8", "replace"),
        )

    def failure(self, completed: subprocess.CompletedProcess, action: str) -> ProtocolError:
        detail = _detail(completed.stderr) or f"ssh exited {completed.returncode}"
        return ProtocolError(
            f"cannot {action} target {self.descriptor.path} "
            f"at {self.descriptor.url}: {detail}"
        )

    def check(self) -> None:
        """Fail loudly if the target is missing, unreadable or not a directory."""
        command = f"cd {_shell_path(self.descriptor.path)} && find . -maxdepth 0 -print"
        completed = self.ssh(command)
        if completed.returncode != 0:
            raise self.failure(completed, "read")

    def _find(self, expression: str, action: str) -> list[bytes]:
        command = (
            f"cd {_shell_path(self.descriptor.path)} && "
            f"find . {expression} -print0"
        )
        completed = self.run(command)
        if completed.returncode != 0:
            raise self.failure(completed, action)
        return [name for name in completed.stdout.split(b"\0") if name]

    def find_files(self) -> list[bytes]:
        """Regular files and symlinks; directories are implied by their paths."""
        return self._find(r"\( -type f -o -type l \)", "read")

    def find_special(self) -> list[bytes]:
        """Path types a git tree cannot represent faithfully."""
        return self._find(r"\( -type p -o -type s -o -type b -o -type c \)", "read")

    def archive(self, names: Iterable[bytes | str]) -> bytes:
        """Tar the named ``./``-relative paths to stdout, without recursion."""
        payload = b"\n".join(
            name.encode() if isinstance(name, str) else name for name in names
        )
        if not payload:
            return b""
        command = (
            f"cd {_shell_path(self.descriptor.path)} && tar -cf - -T -"
        )
        completed = self.run(command, input=payload + b"\n")
        if completed.returncode != 0:
            raise self.failure(completed, "read")
        return completed.stdout
