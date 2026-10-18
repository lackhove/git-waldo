"""Reusable test infrastructure for the tarssh remote helper.

The public seam is a fake target reached through an SSH shim whose remote
PATH contains only the commands a busybox host has. Nothing here imports the
helper: tests drive an executable over the helper protocol.
"""

from __future__ import annotations

import contextlib
import json
import os
import shlex
import shutil
import stat
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Iterable, Mapping

#: Commands the target host may run. Shell builtins are provided by its shell.
BUSYBOX_COMMANDS = ("find", "tar", "rm", "mkdir", "xargs", "sha1sum")


class Target:
    """A directory tree standing in for the remote target.

    Every mutation is local and per-test. ``restore`` must be called before
    deleting a target whose permissions were changed; the fixture does that.
    """

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self._saved_modes: dict[Path, int] = {}

    def create(self) -> Target:
        self.path.mkdir(parents=True, exist_ok=True)
        return self

    def remove(self) -> None:
        self.restore()
        if self.path.exists():
            shutil.rmtree(self.path)

    def empty(self) -> None:
        self.restore()
        for child in self.path.iterdir():
            self.restore(child)
            if child.is_dir() and not child.is_symlink():
                shutil.rmtree(child)
            else:
                child.unlink()

    def populate(self, files: Mapping[str, str | bytes]) -> Target:
        for name, content in files.items():
            self.write(name, content)
        return self

    def write(self, name: str, content: str | bytes, mode: int = 0o644) -> Path:
        path = self.path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        data = content.encode() if isinstance(content, str) else content
        path.write_bytes(data)
        path.chmod(mode)
        return path

    def symlink(self, name: str, destination: str) -> Path:
        path = self.path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.symlink_to(destination)
        return path

    def mkdir(self, name: str, mode: int = 0o755) -> Path:
        path = self.path / name
        path.mkdir(parents=True, exist_ok=True)
        path.chmod(mode)
        return path

    def read(self, name: str) -> bytes:
        return (self.path / name).read_bytes()

    def read_text(self, name: str, encoding: str = "utf-8") -> str:
        return (self.path / name).read_text(encoding=encoding)

    def exists(self, name: str = "") -> bool:
        return (self.path / name).exists() if name else self.path.exists()

    def chmod(self, name: str, mode: int) -> Path:
        path = self.path / name if name else self.path
        path.chmod(mode)
        return path

    def make_unreadable(self, name: str = "") -> Path:
        """Remove all permission bits from a path, remembering its old mode."""
        path = self.path / name if name else self.path
        self._saved_modes.setdefault(path, stat.S_IMODE(path.stat().st_mode))
        path.chmod(0)
        return path

    def restore(self, path: str | Path | None = None) -> None:
        """Restore modes changed by :meth:`make_unreadable`.

        With no argument every saved mode is restored; with a path only that
        subtree is restored.
        """
        if path is None:
            for saved, mode in reversed(list(self._saved_modes.items())):
                with contextlib.suppress(FileNotFoundError):
                    saved.chmod(mode)
            self._saved_modes.clear()
            return

        root = self.path / path if not isinstance(path, Path) else path
        for saved, mode in reversed(list(self._saved_modes.items())):
            if saved == root or root in saved.parents:
                with contextlib.suppress(FileNotFoundError):
                    saved.chmod(mode)
                del self._saved_modes[saved]

    def url(self, host: str = "fake-target") -> str:
        """A helper URL addressing this target over the fake SSH seam."""
        return f"tarssh://{host}{self.path}"


@dataclass(frozen=True)
class SSHCall:
    host: str
    port: int
    user: str | None
    command: str
    returncode: int


@dataclass(frozen=True)
class HarnessEvent:
    kind: str
    reason: str


class FakeSSH:
    """A localhost-only SSH stand-in wired into a restricted target PATH.

    ``client_bin`` holds ``ssh``, traps for ``scp``/``sftp``/``rsync`` and the
    ``git-remote-tarssh`` shim. Add it to a helper's ``PATH`` with :meth:`env`.
    The target itself can run only :data:`BUSYBOX_COMMANDS`.
    """

    def __init__(self, target: Target, root: str | Path) -> None:
        self.target = target
        self.root = Path(root)
        self.host = "fake-target"
        self.workdir = self.root / "work"
        self.target_bin = self.root / "target-bin"
        self.client_bin = self.root / "client-bin"
        self.state_path = self.root / "state.json"
        self.log_path = self.root / "fake-ssh.log"
        for directory in (self.workdir, self.target_bin, self.client_bin):
            directory.mkdir(parents=True, exist_ok=True)

        real: dict[str, str] = {}
        for name in BUSYBOX_COMMANDS:
            resolved = shutil.which(name)
            if resolved is None:
                raise RuntimeError(f"the test host is missing required command: {name}")
            real[name] = resolved

        self._state: dict = {
            "target": str(target.path),
            "workdir": str(self.workdir),
            "target_bin": str(self.target_bin),
            "log": str(self.log_path),
            "real": real,
            "shell": shutil.which("bash") or "/bin/sh",
            "connection_failure": None,
            "extraction_failure": None,
            "removal_failure": None,
        }
        self._write_state()
        self._install_target_commands()
        self._install_client_commands()
        self._write_remote_shell()

    @property
    def url(self) -> str:
        return self.target.url(self.host)

    def _write_state(self) -> None:
        temporary = self.state_path.with_suffix(".tmp")
        temporary.write_text(json.dumps(self._state), encoding="utf-8")
        temporary.replace(self.state_path)

    def _update_state(self, **changes) -> None:
        self._state.update(changes)
        self._write_state()

    def _write_script(self, path: Path, body: str) -> None:
        path.write_text(body, encoding="utf-8")
        path.chmod(0o755)

    def _install_target_commands(self) -> None:
        guard = Path(__file__).with_name("busybox_guard.py")
        for name in BUSYBOX_COMMANDS:
            body = (
                "#!/bin/sh\n"
                f"exec {shlex.quote(sys.executable)} {shlex.quote(str(guard))} "
                f'{name} "$@"\n'
            )
            self._write_script(self.target_bin / name, body)

    def _install_client_commands(self) -> None:
        fake = Path(__file__).with_name("fake_ssh.py")
        launcher = f"exec {shlex.quote(sys.executable)} {shlex.quote(str(fake))}"
        self._write_script(self.client_bin / "ssh", f'#!/bin/sh\n{launcher} "$@"\n')
        for tool in ("scp", "sftp", "rsync"):
            self._write_script(
                self.client_bin / tool,
                f'#!/bin/sh\n{launcher} --fake-tool {tool} "$@"\n',
            )
        remote_shim = Path(__file__).with_name("remote_shim.py")
        self._write_script(
            self.client_bin / "git-remote-tarssh",
            f'#!/bin/sh\nexec {shlex.quote(sys.executable)} {shlex.quote(str(remote_shim))} "$@"\n',
        )

    def _write_remote_shell(self) -> None:
        guard = Path(__file__).with_name("busybox_guard.py")
        shell = self._state["shell"]
        hook = ""
        if Path(shell).name == "bash":
            hook = (
                "command_not_found_handle() {\n"
                f"  {shlex.quote(sys.executable)} {shlex.quote(str(guard))} "
                '--forbidden "$1"\n'
                "  return 127\n"
                "}\n"
            )
        body = f'#!{shell}\n{hook}readonly PATH\neval "$FAKE_SSH_COMMAND"\n'
        self._write_script(self.workdir / "remote-shell.sh", body)

    def env(self, extra: Mapping[str, str] | None = None) -> dict[str, str]:
        """A copy of the environment with the shim directory first on PATH."""
        environment = os.environ.copy()
        environment["PATH"] = str(self.client_bin) + os.pathsep + environment.get("PATH", "")
        environment["FAKE_SSH_STATE"] = str(self.state_path)
        environment.setdefault("GIT_CONFIG_NOSYSTEM", "1")
        environment.setdefault("GIT_CONFIG_GLOBAL", os.devnull)
        environment.setdefault("GIT_TERMINAL_PROMPT", "0")
        if extra:
            environment.update(extra)
        return environment

    def run_ssh(
        self, *args: str, data: str | bytes | None = None
    ) -> subprocess.CompletedProcess[str]:
        payload = data.encode() if isinstance(data, str) else data
        completed = subprocess.run(
            [str(self.client_bin / "ssh"), *args],
            input=payload,
            capture_output=True,
            env=self.env(),
            check=False,
        )
        return subprocess.CompletedProcess(
            completed.args,
            completed.returncode,
            completed.stdout.decode("utf-8", "replace"),
            completed.stderr.decode("utf-8", "replace"),
        )

    def run_remote(
        self, command: str, data: str | bytes | None = None
    ) -> subprocess.CompletedProcess[str]:
        return self.run_ssh(self.host, command, data=data)

    def run_client(self, tool: str, *args: str) -> subprocess.CompletedProcess[str]:
        completed = subprocess.run(
            [str(self.client_bin / tool), *args],
            capture_output=True,
            env=self.env(),
            check=False,
        )
        return subprocess.CompletedProcess(
            completed.args,
            completed.returncode,
            completed.stdout.decode("utf-8", "replace"),
            completed.stderr.decode("utf-8", "replace"),
        )

    def fail_connection(self, message: str = "Connection refused") -> None:
        self._update_state(connection_failure=message)

    def fail_extraction(self, message: str = "tar: corrupted archive: short read") -> None:
        self._update_state(extraction_failure=message)

    def fail_removal(self, message: str = "rm: Permission denied") -> None:
        """Refuse non-recursive ``rm``; the lock's ``rm -rf`` still succeeds."""
        self._update_state(removal_failure=message)

    def restore(self) -> None:
        self._update_state(
            connection_failure=None,
            extraction_failure=None,
            removal_failure=None,
        )

    def _events(self) -> list[dict]:
        if not self.log_path.exists():
            return []
        return [
            json.loads(line)
            for line in self.log_path.read_text(encoding="utf-8").splitlines()
            if line
        ]

    @property
    def calls(self) -> list[SSHCall]:
        events = (event for event in self._events() if event["kind"] == "ssh")
        return [
            SSHCall(
                host=event["host"],
                port=event["port"],
                user=event.get("user"),
                command=event["command"],
                returncode=event["returncode"],
            )
            for event in events
        ]

    @property
    def forbidden(self) -> list[HarnessEvent]:
        return [
            HarnessEvent(kind=event["kind"], reason=event["reason"])
            for event in self._events()
            if event["kind"] == "forbidden"
        ]

    @property
    def failures(self) -> list[HarnessEvent]:
        return [
            HarnessEvent(kind=event["kind"], reason=event["reason"])
            for event in self._events()
            if event["kind"] in ("extraction", "removal", "ssh-failure")
        ]


DEFAULT_STUB_OID = "a" * 40


@dataclass(frozen=True)
class ProtocolResult:
    """Everything a helper process produced, with the streams kept apart."""

    stdin: str
    stdout: str
    stderr: str
    exit_code: int
    argv: tuple[str, ...]

    @property
    def stdout_lines(self) -> list[str]:
        return self.stdout.splitlines()

    @property
    def stderr_lines(self) -> list[str]:
        return self.stderr.splitlines()

    def assert_exit(self, expected: int = 0) -> None:
        assert self.exit_code == expected, (
            f"expected exit {expected}, got {self.exit_code}; "
            f"stderr={self.stderr!r}; stdout={self.stdout!r}"
        )

    def assert_stdout_lines(self, *expected: str) -> None:
        assert self.stdout_lines == list(expected), (
            f"stdout lines differ:\n  expected {list(expected)!r}\n  got      {self.stdout_lines!r}"
        )

    def assert_stderr_lines(self, *expected: str) -> None:
        assert self.stderr_lines == list(expected), (
            f"stderr lines differ:\n  expected {list(expected)!r}\n  got      {self.stderr_lines!r}"
        )

    def assert_stdout_empty(self) -> None:
        assert self.stdout == "", f"expected empty stdout, got {self.stdout!r}"

    def assert_stderr_empty(self) -> None:
        assert self.stderr == "", f"expected empty stderr, got {self.stderr!r}"


class ProtocolDriver:
    """Runs an executable the way git runs a remote helper.

    git invokes ``git-remote-<scheme> <remote> <url>`` and speaks a newline
    protocol on stdin/stdout. The driver appends those arguments, feeds command
    lines, and captures stdout, stderr and the exit code independently.
    """

    def __init__(
        self,
        command: Iterable[str],
        *,
        remote: str = "origin",
        url: str = "tarssh://fake-target/target",
        env: Mapping[str, str] | None = None,
        cwd: str | Path | None = None,
        timeout: float = 30.0,
    ) -> None:
        self.command = tuple(command)
        self.remote = remote
        self.url = url
        self.env = dict(env) if env is not None else os.environ.copy()
        self.cwd = Path(cwd) if cwd is not None else None
        self.timeout = timeout

    def with_env(self, **updates: str) -> ProtocolDriver:
        environment = self.env.copy()
        environment.update(updates)
        return ProtocolDriver(
            self.command,
            remote=self.remote,
            url=self.url,
            env=environment,
            cwd=self.cwd,
            timeout=self.timeout,
        )

    def run(self, *lines: str) -> ProtocolResult:
        return self.run_input("".join(f"{line}\n" for line in lines))

    def run_input(self, stdin: str) -> ProtocolResult:
        completed = subprocess.run(
            [*self.command, self.remote, self.url],
            input=stdin,
            text=True,
            capture_output=True,
            env=self.env,
            cwd=self.cwd,
            timeout=self.timeout,
            check=False,
        )
        return ProtocolResult(
            stdin=stdin,
            stdout=completed.stdout,
            stderr=completed.stderr,
            exit_code=completed.returncode,
            argv=tuple(completed.args),
        )

    def capabilities(self) -> ProtocolResult:
        return self.run("capabilities")

    def list(self, *, for_push: bool = False) -> ProtocolResult:
        return self.run("list for-push" if for_push else "list")

    def fetch(self, *refspecs: str) -> ProtocolResult:
        return self.run(*(f"fetch {refspec}" for refspec in refspecs), "")

    def push(self, *refspecs: str) -> ProtocolResult:
        return self.run(*(f"push {refspec}" for refspec in refspecs), "")

    def option(self, name: str, value: str = "true") -> ProtocolResult:
        return self.run(f"option {name} {value}")
