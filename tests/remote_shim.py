"""The ``git-remote-waldo`` executable on the test PATH.

The helper under test is selected by ``WALDO_HELPER``:

- ``module:waldo.remote`` runs ``python -m waldo.remote``;
- anything else is a command line, e.g. ``python /path/to/stub_helper.py``.

Keeping this indirection in one place lets git discover the helper exactly as
it would after ``uv tool install``.
"""

from __future__ import annotations

import os
import shlex
import sys


def main() -> int:
    spec = os.environ.get("WALDO_HELPER")
    if not spec:
        print("git-remote-waldo: WALDO_HELPER is not set", file=sys.stderr)
        return 127
    if spec.startswith("module:"):
        command = [sys.executable, "-m", spec.removeprefix("module:")]
    else:
        command = shlex.split(spec)
    if not command:
        print("git-remote-waldo: WALDO_HELPER is empty", file=sys.stderr)
        return 127
    try:
        os.execv(command[0], [*command, *sys.argv[1:]])  # noqa: S606  # selected helper
    except OSError as error:
        print(f"git-remote-waldo: cannot run {command[0]}: {error}", file=sys.stderr)
        return 127
    return 127


if __name__ == "__main__":
    sys.exit(main())
