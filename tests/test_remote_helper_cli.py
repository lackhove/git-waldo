"""The executable's non-protocol surface: a leading dash means a tool verb."""

from __future__ import annotations

import subprocess
import sys
from importlib.metadata import entry_points

import tarssh


def _run(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "tarssh.remote", *args],
        input="",
        text=True,
        capture_output=True,
        check=False,
    )


def test_version_verb_prints_the_tool_version():
    completed = _run("--version")

    assert completed.returncode == 0
    assert tarssh.__version__ in completed.stdout
    assert completed.stderr == ""


def test_unknown_verb_fails_clearly_instead_of_becoming_a_remote():
    completed = _run("--no-such-verb")

    assert completed.returncode != 0
    assert "--no-such-verb" in completed.stderr
    assert completed.stdout == ""


def test_helper_mode_without_a_url_fails_clearly():
    completed = _run("origin")

    assert completed.returncode != 0
    assert "url" in completed.stderr.lower()


def test_the_installed_console_script_points_at_the_helper():
    scripts = [
        entry
        for entry in entry_points(group="console_scripts")
        if entry.name == "git-remote-tarssh"
    ]

    assert [entry.value for entry in scripts] == ["tarssh.remote:main"]
