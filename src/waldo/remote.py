"""Entry point for ``git-remote-waldo``.

A leading ``-`` in the first argument always means a tool verb; anything else
is git's remote-helper protocol (``<remote> <url>``).
"""

from __future__ import annotations

import argparse
import sys
from typing import TYPE_CHECKING, TextIO

from waldo import __version__
from waldo.descriptor import repository_root, resolve, write_descriptor
from waldo.errors import ProtocolError
from waldo.gitcmd import GitStore, git_output
from waldo.push import PushSession, push_refs
from waldo.snapshot import MAIN_REF, snapshot
from waldo.target import Target

if TYPE_CHECKING:
    from collections.abc import Sequence
    from pathlib import Path

PROG = "git-remote-waldo"
USAGE = "%(prog)s <remote> <url> | --config | --version"

#: Options git may ask about. ``push`` is advertised so git sends the
#: ``list for-push``/``push`` commands instead of failing before the handshake.
CAPABILITIES = ("fetch", "push", "option")
SUPPORTED_OPTIONS = {"dry-run", "verbosity", "followtags", "cloning"}


def out(stream: TextIO, line: str = "") -> None:
    stream.write(f"{line}\n")
    stream.flush()


def err(line: str) -> None:
    sys.stderr.write(f"{line}\n")
    sys.stderr.flush()


def ensure_target_remote(root: Path) -> None:
    """Register ``target`` as ``waldo::`` unless it already exists."""
    existing = git_output(["remote", "get-url", "target"], root)
    if existing.returncode == 0:
        err(
            f"git-remote-waldo: target remote already exists "
            f"({existing.stdout.strip()}); left untouched"
        )
        return

    added = git_output(["remote", "add", "target", "waldo::"], root)
    if added.returncode != 0:
        detail = (added.stderr or added.stdout).strip()
        raise ProtocolError(f"cannot add the target remote: {detail}")
    err("git-remote-waldo: added target remote waldo::")


def config_mode() -> int:
    root = repository_root()
    if root is None:
        message = "--config must run inside a git repository: git rev-parse --show-toplevel failed"
        raise ProtocolError(message)
    path = write_descriptor(root, stdin=sys.stdin, stdout=sys.stderr)
    err(f"git-remote-waldo: wrote {path}")
    ensure_target_remote(root)
    return 0


def _tool_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog=PROG, usage=USAGE, add_help=False)
    verbs = parser.add_mutually_exclusive_group()
    verbs.add_argument("--version", action="store_true")
    verbs.add_argument("--config", action="store_true")
    return parser


def tool_mode(argv: Sequence[str]) -> int:
    parser = _tool_parser()
    args = parser.parse_args(argv)
    if args.version:
        out(sys.stdout, f"git-waldo {__version__}")
        return 0
    if args.config:
        return config_mode()
    parser.error(f"unknown option: {argv[0]}")
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
        command, separator, arguments = line.partition(" ")
        if command != "fetch" or not separator or not arguments.strip():
            raise ProtocolError(f"malformed fetch line: {line!r}")
        oid, _, name = arguments.partition(" ")
        if not store.has_commit(oid):
            raise ProtocolError(
                f"fetch: object {oid} for {name or 'a ref'} is not in the local object store"
            )
    out(stdout)


def handle_list(
    session: PushSession,
    *,
    for_push: bool,
    stdout: TextIO,
) -> None:
    if for_push:
        # Preparation happens here: the push line carries no old oid, so the
        # lock, snapshot and clean check must all precede the advertisement.
        # No remote branch means branch creation: an empty advertisement.
        session.prepare()
        if session.expected is not None:
            out(stdout, f"{session.expected} {MAIN_REF}")
        out(stdout)
        return
    oid = snapshot(session.store, session.target, session.descriptor, session.remote)
    out(stdout, f"@{MAIN_REF} HEAD")
    out(stdout, f"{oid} {MAIN_REF}")
    out(stdout)


def _handle_option(rest: str, stdout: TextIO, *, dry_run: bool) -> bool:
    name, _, value = rest.partition(" ")
    if name == "dry-run":
        dry_run = value.strip() == "true"
    out(stdout, "ok" if name in SUPPORTED_OPTIONS else "unsupported")
    return dry_run


def _handle_push(
    session: PushSession,
    stdin: TextIO,
    first: str,
    stdout: TextIO,
    *,
    dry_run: bool,
) -> None:
    lines = read_batch(stdin, first)
    result = push_refs(session, lines, dry_run=dry_run)
    for message in result.messages:
        err(message)
    for status in result.statuses:
        out(stdout, status.line())
    out(stdout)


def command_loop(stdin: TextIO, stdout: TextIO, session: PushSession) -> int:
    dry_run = False
    try:
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
                dry_run = _handle_option(rest, stdout, dry_run=dry_run)
            elif command == "list":
                handle_list(session, for_push=rest == "for-push", stdout=stdout)
            elif command == "fetch":
                handle_fetch(session.store, stdin, line, stdout)
            elif command == "push":
                _handle_push(session, stdin, line, stdout, dry_run=dry_run)
            else:
                message = f"unknown protocol command: {line}"
                raise ProtocolError(message)
    finally:
        # Holds the lock across list-for-push -> push; git may never send the
        # push batch at all.
        session.close()
    return 0


def _helper_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog=PROG, usage=USAGE, add_help=False)
    parser.add_argument("remote")
    parser.add_argument("url")
    return parser


def helper_mode(argv: Sequence[str]) -> int:
    args = _helper_parser().parse_args(argv)

    resolved = resolve(args.url)
    for warning in resolved.warnings:
        err(warning)

    store = GitStore.discover()
    try:
        target = Target(resolved.descriptor)
        session = PushSession(store, target, resolved.descriptor, args.remote)
        return command_loop(sys.stdin, sys.stdout, session)
    finally:
        store.close()


def main(argv: Sequence[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    try:
        if args and args[0].startswith("-"):
            return tool_mode(args)
        return helper_mode(args)
    except SystemExit as exit_code:
        code = exit_code.code
        return code if isinstance(code, int) else 0
    except ProtocolError as error:
        err(f"git-remote-waldo: {error}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
