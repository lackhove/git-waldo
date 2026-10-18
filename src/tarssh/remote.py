"""Entry point for ``git-remote-tarssh``.

A leading ``-`` in the first argument always means a tool verb; anything else
is git's remote-helper protocol (``<remote> <url>``).
"""

from __future__ import annotations

import sys
from collections.abc import Sequence
from typing import TextIO

from tarssh import __version__
from tarssh import descriptor as descriptor_module
from tarssh.errors import ProtocolError
from tarssh.gitcmd import GitStore
from tarssh.snapshot import MAIN_REF, snapshot
from tarssh.target import Target

USAGE = "usage: git-remote-tarssh <remote> <url> | --version"

#: Options git may ask about. ticket 02 has no push, so ``push`` is absent from
#: the advertised capabilities even though the option vocabulary is real.
CAPABILITIES = ("fetch", "option")
SUPPORTED_OPTIONS = {"dry-run", "verbosity", "followtags", "cloning"}


def out(stream: TextIO, line: str = "") -> None:
    print(line, file=stream, flush=True)


def err(line: str) -> None:
    print(line, file=sys.stderr, flush=True)


def tool_mode(argv: Sequence[str]) -> int:
    verb = argv[0]
    if verb == "--version":
        print(f"tarssh {__version__}")
        return 0
    if verb == "--config":
        err("git-remote-tarssh: --config is not implemented yet")
        return 2
    err(f"git-remote-tarssh: unknown option: {verb}")
    err(USAGE)
    return 2


def read_batch(stdin: TextIO, first: str) -> list[str]:
    """Read the rest of a batch; git terminates it with a blank line."""
    lines = [first]
    for raw in stdin:
        line = raw.rstrip("\n")
        if line == "":
            break
        lines.append(line)
    return lines


def handle_fetch(store: GitStore, stdin: TextIO, first: str, stdout: TextIO) -> None:
    for line in read_batch(stdin, first):
        parts = line.split(" ", 1)
        if parts[0] != "fetch" or len(parts) != 2 or not parts[1].strip():
            raise ProtocolError(f"malformed fetch line: {line!r}")
        oid, _, name = parts[1].partition(" ")
        if not store.has_commit(oid):
            raise ProtocolError(
                f"fetch: object {oid} for {name or 'a ref'} is not in the local object store"
            )
    out(stdout)


def handle_list(
    store: GitStore,
    target: Target,
    descriptor: descriptor_module.Descriptor,
    remote: str,
    *,
    for_push: bool,
    stdout: TextIO,
) -> None:
    if for_push:
        # Push arrives in ticket 04. An empty advertisement is "no refs yet";
        # ``?`` would mean "unknown value" and would make git fail.
        out(stdout)
        return
    oid = snapshot(store, target, descriptor, remote)
    out(stdout, f"@{MAIN_REF} HEAD")
    out(stdout, f"{oid} {MAIN_REF}")
    out(stdout)


def command_loop(
    stdin: TextIO,
    stdout: TextIO,
    *,
    remote: str,
    descriptor: descriptor_module.Descriptor,
    target: Target,
    store: GitStore,
) -> int:
    for raw in stdin:
        line = raw.rstrip("\n")
        if line == "":
            continue
        command, _, rest = line.partition(" ")
        if command == "capabilities":
            for capability in CAPABILITIES:
                out(stdout, capability)
            out(stdout)
        elif command == "option":
            name = rest.split(" ", 1)[0]
            out(stdout, "ok" if name in SUPPORTED_OPTIONS else "unsupported")
        elif command == "list":
            handle_list(
                store,
                target,
                descriptor,
                remote,
                for_push=rest == "for-push",
                stdout=stdout,
            )
        elif command == "fetch":
            handle_fetch(store, stdin, line, stdout)
        elif command == "push":
            raise ProtocolError("push is not implemented until ticket 04")
        else:
            raise ProtocolError(f"unknown protocol command: {line}")
    return 0


def helper_mode(argv: Sequence[str]) -> int:
    if len(argv) < 2:
        err("git-remote-tarssh: helper mode needs <remote> <url>")
        err(USAGE)
        return 2
    remote, url = argv[0], argv[1]

    resolved = descriptor_module.resolve(url)
    for warning in resolved.warnings:
        err(warning)

    store = GitStore.discover()
    try:
        target = Target(resolved.descriptor)
        return command_loop(
            sys.stdin,
            sys.stdout,
            remote=remote,
            descriptor=resolved.descriptor,
            target=target,
            store=store,
        )
    finally:
        store.close()


def main(argv: Sequence[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if not args:
        err(USAGE)
        return 2
    try:
        if args[0].startswith("-"):
            return tool_mode(args)
        return helper_mode(args)
    except ProtocolError as error:
        err(f"git-remote-tarssh: {error}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
