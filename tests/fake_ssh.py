"""A localhost-only SSH stand-in for the busybox target.

``ssh`` invocations are parsed, restricted to the commands a busybox host has,
and executed against the fake target. Every failure mode the helper must cope
with (connection refused, extraction failure, missing or unreadable target)
is driven by the state file the harness writes.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

BUSYBOX_COMMANDS = ("find", "tar", "rm", "mkdir", "xargs", "sha1sum")

SSH_FLAGS = {
    "4",
    "6",
    "A",
    "a",
    "C",
    "n",
    "q",
    "T",
    "t",
    "v",
    "x",
    "X",
    "Y",
}
SSH_OPTIONS_WITH_VALUE = {"F", "i", "l", "o", "p"}


def load_state() -> dict:
    path = os.environ.get("FAKE_SSH_STATE")
    if not path:
        message = "fake-ssh: FAKE_SSH_STATE is not set"
        raise SystemExit(message)
    return json.loads(Path(path).read_text())


def log(state: dict, entry: dict) -> None:
    path = Path(state["log"])
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(entry) + "\n")


def refuse(state: dict, reason: str, returncode: int = 127) -> int:
    log(state, {"kind": "forbidden", "reason": reason})
    print(f"fake-ssh: {reason}", file=sys.stderr)
    return returncode


def parse_ssh(  # noqa: C901, PLR0912, PLR0915  # mirrors busybox/OpenSSH option forms
    argv: list[str],
) -> tuple[str, str | None, int, bool, list[str]]:
    """Return destination host, user, port, subsystem flag and command argv."""
    host: str | None = None
    user: str | None = None
    port = 22
    subsystem = False
    index = 0
    while index < len(argv):
        arg = argv[index]
        if host is not None:
            return host, user, port, subsystem, argv[index:]

        if arg == "--":
            index += 1
            if index >= len(argv):
                message = "ssh: -- without a destination"
                raise ValueError(message)
            host = argv[index]
            index += 1
            continue
        if not arg.startswith("-") or arg == "-":
            host = arg
            index += 1
            continue
        if arg == "-s":
            subsystem = True
            index += 1
            continue
        if arg in ("-p", "-l", "-o", "-i", "-F"):
            if index + 1 >= len(argv):
                raise ValueError(f"ssh: option {arg} requires an argument")
            value = argv[index + 1]
            if arg == "-p":
                try:
                    port = int(value)
                except ValueError as error:
                    raise ValueError(f"ssh: invalid port: {value}") from error
            elif arg == "-l":
                user = value
            index += 2
            continue
        if arg[:2] in ("-p", "-l", "-o", "-i", "-F") and len(arg) > 2:
            option, value = arg[:2], arg[2:]
            if option == "-p":
                try:
                    port = int(value)
                except ValueError as error:
                    raise ValueError(f"ssh: invalid port: {value}") from error
            elif option == "-l":
                user = value
            index += 1
            continue
        if len(arg) == 2 and arg[1] in SSH_FLAGS:
            index += 1
            continue
        if len(arg) > 2 and set(arg[1:]) <= SSH_FLAGS:
            index += 1
            continue
        raise ValueError(f"ssh: option not supported by the fake target: {arg}")

    if host is None:
        message = "ssh: no destination host"
        raise ValueError(message)
    return host, user, port, subsystem, []


def split_user(host: str) -> tuple[str | None, str]:
    if "@" in host:
        user, host = host.rsplit("@", 1)
        return user, host
    return None, host


def run_command(state: dict, command: str) -> int:
    workdir = Path(state["workdir"])
    shell = state["shell"]
    script = workdir / "remote-shell.sh"
    env = {
        "PATH": state["target_bin"],
        "HOME": str(workdir),
        "FAKE_SSH_STATE": str(Path(os.environ["FAKE_SSH_STATE"])),
        "FAKE_SSH_COMMAND": command,
        "LC_ALL": "C",
        "LANG": "C",
    }
    completed = subprocess.run([shell, str(script)], cwd=workdir, env=env, check=False)
    return completed.returncode


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    state = load_state()

    if argv[:1] == ["--fake-tool"]:
        tool = argv[1] if len(argv) > 1 else "unknown"
        reason = f"{tool} is not available; the target has no {tool}"
        return refuse(state, reason)

    try:
        destination, user, port, subsystem, command_argv = parse_ssh(argv)
    except ValueError as error:
        return refuse(state, str(error), 255)

    embedded_user, host = split_user(destination)
    user = embedded_user or user

    if state.get("connection_failure"):
        message = state["connection_failure"]
        log(
            state,
            {
                "kind": "ssh-failure",
                "host": host,
                "port": port,
                "user": user,
                "reason": message,
            },
        )
        print(f"ssh: connect to host {host} port {port}: {message}", file=sys.stderr)
        return 255

    if subsystem:
        requested = command_argv[0] if command_argv else "unknown"
        return refuse(
            state,
            f"SSH subsystems are not available (requested: {requested}); no SFTP",
            255,
        )

    if not command_argv:
        return refuse(state, "ssh: no remote command; the target only runs commands", 255)

    command = " ".join(command_argv)
    returncode = run_command(state, command)
    log(
        state,
        {
            "kind": "ssh",
            "host": host,
            "port": port,
            "user": user,
            "command": command,
            "returncode": returncode,
        },
    )
    return returncode


if __name__ == "__main__":
    sys.exit(main())
