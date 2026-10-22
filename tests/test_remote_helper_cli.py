"""The executable's non-protocol surface: a leading dash means a tool verb."""

from __future__ import annotations

import getpass
import subprocess
import sys
import tomllib
from importlib.metadata import entry_points, version
from typing import TYPE_CHECKING

import pytest

import waldo

if TYPE_CHECKING:
    from pathlib import Path

TOML_NAME = ".waldo.toml"


def _run(*args: str, cwd: Path | None = None, stdin: str = "") -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "waldo.remote", *args],
        input=stdin,
        text=True,
        capture_output=True,
        cwd=cwd,
        check=False,
    )


def _repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    return repo


def _git(repo: Path, *args: str) -> str:
    completed = subprocess.run(["git", *args], cwd=repo, text=True, capture_output=True, check=True)
    return completed.stdout.strip()


def test_version_verb_prints_the_tool_version():
    completed = _run("--version")

    assert completed.returncode == 0
    assert waldo.__version__ in completed.stdout
    assert completed.stderr == ""


def test_unknown_verb_fails_clearly_instead_of_becoming_a_remote():
    completed = _run("--no-such-verb")

    assert completed.returncode == 2
    assert "--no-such-verb" in completed.stderr
    assert "usage" in completed.stderr.lower()
    assert completed.stdout == ""


def test_helper_mode_without_a_url_fails_clearly():
    completed = _run("origin")

    assert completed.returncode == 2
    assert "url" in completed.stderr.lower()
    assert "usage" in completed.stderr.lower()


@pytest.mark.parametrize(
    "args",
    [
        ("--version", "extra"),
        ("--config", "extra"),
        ("origin", "waldo::", "extra"),
        ("-",),
    ],
)
def test_extra_arguments_exit_2_with_usage(args):
    completed = _run(*args)

    assert completed.returncode == 2
    assert "usage" in completed.stderr.lower()
    assert completed.stdout == ""


def test_the_installed_console_script_points_at_the_helper():
    scripts = [
        entry for entry in entry_points(group="console_scripts") if entry.name == "git-remote-waldo"
    ]

    assert [entry.value for entry in scripts] == ["waldo.remote:main"]


def test_version_verb_prints_the_installed_package_version():
    completed = _run("--version")

    assert completed.returncode == 0
    assert completed.stdout == f"git-waldo {version('git-waldo')}\n"
    assert completed.stderr == ""


def test_config_outside_a_repository_fails_without_writing_anything(tmp_path):
    completed = _run("--config", cwd=tmp_path)

    assert completed.returncode != 0
    assert "repository" in completed.stderr.lower()
    assert not (tmp_path / TOML_NAME).exists()


def test_config_writes_the_descriptor_at_the_repo_root_from_a_subdirectory(tmp_path):
    repo = _repo(tmp_path)
    subdirectory = repo / "config" / "nested"
    subdirectory.mkdir(parents=True)

    completed = _run(
        "--config",
        cwd=subdirectory,
        stdin="deployer\nexample.test\n2222\n/srv/config\n",
    )

    assert completed.returncode == 0, completed.stderr
    descriptor = tomllib.loads((repo / TOML_NAME).read_text(encoding="utf-8"))
    assert descriptor == {
        "user": "deployer",
        "host": "example.test",
        "ssh_port": 2222,
        "dir": "/srv/config",
    }
    assert not (subdirectory / TOML_NAME).exists()
    assert _git(repo, "remote", "get-url", "target") == "waldo::"


def test_config_offers_the_local_user_and_port_22_as_defaults(tmp_path):
    repo = _repo(tmp_path)

    completed = _run("--config", cwd=repo, stdin="\nexample.test\n\n/srv/config\n")

    assert completed.returncode == 0, completed.stderr
    descriptor = tomllib.loads((repo / TOML_NAME).read_text(encoding="utf-8"))
    assert descriptor["user"] == getpass.getuser()
    assert descriptor["ssh_port"] == 22


@pytest.mark.parametrize(
    ("stdin", "missing"),
    [
        ("deployer\n\n2222\n/srv/config\n", "host"),
        ("deployer\nexample.test\n2222\n\n", "dir"),
    ],
)
def test_config_rejects_an_empty_required_field(tmp_path, stdin, missing):
    repo = _repo(tmp_path)

    completed = _run("--config", cwd=repo, stdin=stdin)

    assert completed.returncode != 0
    assert missing in completed.stderr
    assert not (repo / TOML_NAME).exists()
    assert _git(repo, "remote") == ""


def test_config_rejects_an_invalid_ssh_port(tmp_path):
    repo = _repo(tmp_path)

    completed = _run(
        "--config", cwd=repo, stdin="deployer\nexample.test\nnot-a-port\n/srv/config\n"
    )

    assert completed.returncode != 0
    assert "port" in completed.stderr.lower()
    assert not (repo / TOML_NAME).exists()


def test_config_refuses_to_clobber_without_confirmation(tmp_path):
    repo = _repo(tmp_path)
    descriptor = repo / TOML_NAME
    original = 'user = "old-user"\nhost = "old-host"\n'
    descriptor.write_text(original, encoding="utf-8")

    completed = _run("--config", cwd=repo, stdin="n\n")

    assert completed.returncode != 0
    assert descriptor.read_text(encoding="utf-8") == original
    assert _git(repo, "remote") == ""


def test_config_overwrites_after_confirmation_using_existing_values_as_defaults(tmp_path):
    repo = _repo(tmp_path)
    descriptor = repo / TOML_NAME
    descriptor.write_text(
        'user = "old-user"\nhost = "old-host"\nssh_port = 2200\ndir = "/old/dir"\n',
        encoding="utf-8",
    )

    completed = _run(
        "--config",
        cwd=repo,
        stdin="y\nnew-user\n\n\n/new/dir\n",
    )

    assert completed.returncode == 0, completed.stderr
    written = tomllib.loads(descriptor.read_text(encoding="utf-8"))
    assert written == {
        "user": "new-user",
        "host": "old-host",
        "ssh_port": 2200,
        "dir": "/new/dir",
    }


def test_config_leaves_an_existing_target_remote_untouched_and_says_so(tmp_path):
    repo = _repo(tmp_path)
    existing = "waldo://user@elsewhere:2222/srv/config"
    subprocess.run(["git", "remote", "add", "target", existing], cwd=repo, check=True)

    completed = _run(
        "--config",
        cwd=repo,
        stdin="deployer\nexample.test\n2222\n/srv/config\n",
    )

    assert completed.returncode == 0, completed.stderr
    assert _git(repo, "remote", "get-url", "target") == existing
    assert "target" in completed.stderr
    assert "untouched" in completed.stderr
