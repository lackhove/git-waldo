"""The SSH seam and the busybox commands the target may run.

Only ``find``, ``tar``, ``rm``, ``mkdir`` and shell builtins are available on
the far side. This module owns invocation, not policy: callers decide what a
failed command means.
"""

from __future__ import annotations

import shlex
import subprocess
from dataclasses import dataclass

from tarssh.descriptor import Descriptor
from tarssh.errors import ProtocolError


def _last_line(text: str) -> str:
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
