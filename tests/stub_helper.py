"""A deliberately tiny helper used to exercise the protocol harness.

It is not the real helper: it exists so the driver can be tested against a
process that answers git's command lines. The real implementation replaces it
in ticket 02.
"""

from __future__ import annotations

import os
import sys

DEFAULT_OID = "a" * 40
OPTION_NAMES = {"dry-run", "verbosity", "followtags", "cloning"}


def out(line: str = "") -> None:
    print(line, flush=True)


def err(line: str) -> None:
    print(line, file=sys.stderr, flush=True)


def read_batch(stream) -> list[str]:
    lines: list[str] = []
    for raw in stream:
        line = raw.rstrip("\n")
        if line == "":
            return lines
        lines.append(line)
    return lines


def parse_destination(refspec: str) -> str:
    if refspec.startswith(("+", ":")):
        return refspec.lstrip("+").split(":", 1)[-1]
    return refspec.split(":", 1)[-1]


def main() -> int:  # noqa: C901  # tiny protocol stub exercises every command
    mode = os.environ.get("STUB_HELPER_MODE", "normal")
    oid = os.environ.get("STUB_OID", DEFAULT_OID)

    if mode == "both":
        out("stub stdout")
        err("stub stderr")
        return 4
    if mode == "fail":
        err("stub: simulated failure")
        return 3

    for raw in sys.stdin:
        line = raw.rstrip("\n")
        if line == "":
            continue
        if line == "capabilities":
            out("fetch")
            out("push")
            out("option")
            out("")
        elif line in {"list", "list for-push"}:
            out("@refs/heads/main HEAD")
            out(f"{oid} refs/heads/main")
            out("")
        elif line.startswith("fetch "):
            read_batch(sys.stdin)
            out("")
        elif line.startswith("push "):
            refspecs = [line.split(" ", 1)[1], *read_batch(sys.stdin)]
            for refspec in refspecs:
                out(f"ok {parse_destination(refspec)}")
            out("")
        elif line.startswith("option "):
            name = line.split(" ", 2)[1]
            out("ok" if name in OPTION_NAMES else "unsupported")
        else:
            err(f"stub: unknown protocol command: {line}")
            return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
