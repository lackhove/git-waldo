"""Command and option gate for the fake target's restricted PATH.

Each of the six busybox commands on the target is a wrapper that calls this
module. It validates the invocation, records it, and either rejects it loudly
or replaces itself with the real command.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

BUSYBOX_COMMANDS = ("find", "tar", "rm", "mkdir", "xargs", "sha1sum")

TAR_SHORT = set("cxtfCTozvjJhkmpOX")
TAR_LONG = {
    "--create",
    "--extract",
    "--get",
    "--list",
    "--file",
    "--directory",
    "--files-from",
    "--to-stdout",
    "--verbose",
    "--gzip",
    "--bzip2",
    "--xz",
    "--no-recursion",
    "--exclude",
    "--exclude-from",
    "--overwrite",
    "--no-same-owner",
    "--same-owner",
    "--touch",
    "--preserve-permissions",
    "--numeric-owner",
    "--help",
    "--version",
}

FIND_FLAGS = {
    "H",
    "L",
    "P",
    "depth",
    "maxdepth",
    "mindepth",
    "xdev",
    "mount",
    "follow",
    "noleaf",
    "type",
    "name",
    "iname",
    "path",
    "ipath",
    "regex",
    "iregex",
    "empty",
    "perm",
    "user",
    "group",
    "size",
    "links",
    "mtime",
    "atime",
    "ctime",
    "newer",
    "print",
    "print0",
    "prune",
    "quit",
    "true",
    "false",
    "not",
    "a",
    "o",
    "and",
    "or",
}
FIND_TAKES_VALUE = {
    "maxdepth",
    "mindepth",
    "type",
    "name",
    "iname",
    "path",
    "ipath",
    "regex",
    "iregex",
    "perm",
    "user",
    "group",
    "size",
    "links",
    "mtime",
    "atime",
    "ctime",
    "newer",
}

RM_SHORT = set("firRdv")
RM_LONG: set[str] = set()

MKDIR_SHORT = set("pmv")
MKDIR_LONG = {"--parents", "--mode", "--verbose"}

XARGS_SHORT = set("0adEILnPrstx")
XARGS_LONG = {
    "--null",
    "--arg-file",
    "--delimiter",
    "--eof",
    "--replace",
    "--max-lines",
    "--max-args",
    "--max-procs",
    "--no-run-if-empty",
    "--max-chars",
    "--verbose",
    "--exit",
}

SHA1SUM_SHORT = set("csbtw")
SHA1SUM_LONG = {"--check", "--status", "--binary", "--text", "--warn"}

SHORT_OPTIONS = {
    "tar": TAR_SHORT,
    "rm": RM_SHORT,
    "mkdir": MKDIR_SHORT,
    "xargs": XARGS_SHORT,
    "sha1sum": SHA1SUM_SHORT,
}
LONG_OPTIONS = {
    "tar": TAR_LONG,
    "rm": RM_LONG,
    "mkdir": MKDIR_LONG,
    "xargs": XARGS_LONG,
    "sha1sum": SHA1SUM_LONG,
}


class Rejected(Exception):
    def __init__(self, reason: str, returncode: int = 2) -> None:
        super().__init__(reason)
        self.reason = reason
        self.returncode = returncode


def state_path() -> Path:
    raw = os.environ.get("FAKE_SSH_STATE")
    if not raw:
        raise Rejected("fake target guard: FAKE_SSH_STATE is not set", 127)
    return Path(raw)


def load_state() -> dict:
    return json.loads(state_path().read_text())


def log(entry: dict) -> None:
    try:
        path = Path(load_state()["log"])
    except (KeyError, OSError, json.JSONDecodeError):
        return
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(entry) + "\n")


def reject(reason: str, returncode: int = 2) -> None:
    log({"kind": "forbidden", "reason": reason})
    print(f"fake-target: {reason}", file=sys.stderr)
    raise SystemExit(returncode)


def is_extract(args: list[str]) -> bool:
    for arg in args:
        if arg in ("--extract", "--get"):
            return True
        if arg.startswith("-") and not arg.startswith("--") and "x" in arg[1:]:
            return True
    return False


def validate_short(command: str, args: list[str]) -> None:
    allowed = SHORT_OPTIONS[command]
    for arg in args:
        if arg == "-":
            continue
        if arg.startswith("--"):
            if command == "rm":
                raise Rejected(
                    f"rm: option not available on target: {arg} (busybox rm has no --)", 2
                )
            name = arg.split("=", 1)[0]
            if name not in LONG_OPTIONS[command]:
                raise Rejected(f"{command}: option not available on target: {name}", 2)
            continue
        if not arg.startswith("-"):
            continue
        for letter in arg[1:]:
            if letter not in allowed:
                raise Rejected(f"{command}: option not available on target: -{letter}", 2)


def validate_find(args: list[str]) -> None:
    index = 0
    while index < len(args):
        arg = args[index]
        if not arg.startswith("-") or arg == "-":
            index += 1
            continue
        if arg.startswith("--"):
            raise Rejected(f"find: option not available on target: {arg}", 2)
        name = arg[1:]
        if name not in FIND_FLAGS:
            raise Rejected(f"find: option not available on target: -{name}", 2)
        index += 2 if name in FIND_TAKES_VALUE else 1


XARGS_LONG_WITH_VALUE = {
    "--arg-file",
    "--delimiter",
    "--eof",
    "--replace",
    "--max-lines",
    "--max-args",
    "--max-procs",
    "--max-chars",
}
XARGS_FLAGS_WITH_VALUE = set("aEdILnPs")


def validate_xargs(args: list[str]) -> None:
    """Validate xargs' own options, then the command it will exec."""
    index = 0
    while index < len(args):
        arg = args[index]
        if not arg.startswith("-") or arg == "-":
            break
        if arg.startswith("--"):
            name = arg.split("=", 1)[0]
            if name not in XARGS_LONG:
                raise Rejected(f"xargs: option not available on target: {name}", 2)
            if name in XARGS_LONG_WITH_VALUE and "=" not in arg:
                index += 2
            else:
                index += 1
            continue
        name = arg[1:2]
        if name not in XARGS_SHORT:
            raise Rejected(f"xargs: option not available on target: {arg}", 2)
        index += 2 if name in XARGS_FLAGS_WITH_VALUE and len(arg) == 2 else 1

    if index >= len(args):
        raise Rejected("xargs: no command to run on target", 2)
    command, command_args = args[index], args[index + 1 :]
    if command not in BUSYBOX_COMMANDS:
        raise Rejected(f"command not available: {command}", 127)
    validate(command, command_args)


def validate(command: str, args: list[str]) -> None:
    if command not in BUSYBOX_COMMANDS:
        raise Rejected(f"command not available: {command}", 127)
    if command == "find":
        validate_find(args)
        return
    if command == "xargs":
        validate_xargs(args)
        return
    validate_short(command, args)


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv:
        print("fake-target: guard called without a command", file=sys.stderr)
        return 127

    if argv[0] == "--forbidden":
        name = argv[1] if len(argv) > 1 else "unknown"
        reject(f"command not available: {name}", 127)

    command, args = argv[0], argv[1:]
    try:
        state = load_state()
        validate(command, args)
        if command == "tar" and is_extract(args) and state.get("extraction_failure"):
            reason = state["extraction_failure"]
            log({"kind": "extraction", "reason": reason})
            print(f"fake-target: extraction failed: {reason}", file=sys.stderr)
            return 2
        real = state["real"][command]
    except Rejected as rejected:
        reject(rejected.reason, rejected.returncode)
    except (KeyError, OSError, json.JSONDecodeError) as error:
        reject(f"guard cannot read fake target state: {error}", 127)

    log({"kind": "command", "command": command, "argv": args})
    try:
        os.execv(real, [command, *args])
    except OSError as error:
        reject(f"{command}: cannot execute real command: {error}", 127)
    return 127


if __name__ == "__main__":
    sys.exit(main())
