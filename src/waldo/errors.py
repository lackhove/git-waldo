"""Transport-level failures become one stderr line and a non-zero exit."""

from __future__ import annotations


class ProtocolError(Exception):
    """The helper cannot speak the protocol for this invocation.

    Everything here is an operator-facing failure (unreachable host, missing
    target, unreadable file). Ref-level push rejections are protocol results,
    not exceptions.
    """
