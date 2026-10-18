"""tarssh: a git remote helper for hosts with only busybox find and tar."""

from __future__ import annotations

from importlib.metadata import PackageNotFoundError, version

#: The installed distribution's version. Running straight from a source tree
#: without an installed package still has to answer ``--version`` sensibly.
try:
    __version__ = version("tarssh")
except PackageNotFoundError:  # pragma: no cover - only when not installed
    __version__ = "0.1.0"
