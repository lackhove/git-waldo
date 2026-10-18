"""Descriptor precedence, disagreement warnings and URL shapes."""

from __future__ import annotations

import getpass
import subprocess
import sys
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from pathlib import Path

TOML_NAME = ".tarssh.toml"


def _driver(make_driver, tmp_path, url, env, cwd=None):
    return make_driver(
        [sys.executable, "-m", "tarssh.remote"],
        url=url,
        env=env,
        cwd=cwd or tmp_path,
    )


def _repo_with_toml(tmp_path: Path, **fields) -> Path:
    repo = tmp_path / "repo"
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    lines = []
    for key, value in fields.items():
        if isinstance(value, str):
            lines.append(f'{key} = "{value}"')
        else:
            lines.append(f"{key} = {value}")
    (repo / TOML_NAME).write_text("\n".join(lines) + "\n", encoding="utf-8")
    return repo


def test_a_full_url_supplies_user_host_port_and_path(
    make_driver, fake_ssh, target, tarssh_env, tmp_path
):
    target.create()
    url = f"tarssh://user@fake-target:22222{target.path}"

    result = _driver(make_driver, tmp_path, url, tarssh_env).list()

    result.assert_exit(0)
    result.assert_stderr_empty()
    call = fake_ssh.calls[-1]
    assert (call.host, call.user, call.port) == ("fake-target", "user", 22222)


def test_descriptor_only_url_resolves_everything_from_toml(
    make_driver, fake_ssh, target, tarssh_env, tmp_path
):
    target.create()
    repo = _repo_with_toml(
        tmp_path,
        user="root",
        host="fake-target",
        ssh_port=22222,
        dir=str(target.path),
    )

    result = _driver(make_driver, tmp_path, "", tarssh_env, cwd=repo).list()

    result.assert_exit(0)
    result.assert_stderr_empty()
    call = fake_ssh.calls[-1]
    assert (call.host, call.user, call.port) == ("fake-target", "root", 22222)


def test_environment_wins_over_url_and_toml_per_field(
    make_driver, fake_ssh, target, tarssh_env, tmp_path
):
    target.create()
    repo = _repo_with_toml(
        tmp_path,
        user="toml-user",
        host="toml-host",
        ssh_port=2222,
        dir="/toml/dir",
    )
    env = dict(tarssh_env)
    env.update(
        TARSSH_USER="env-user",
        TARSSH_HOST="fake-target",
        TARSSH_SSH_PORT="22222",
        TARSSH_DIR=str(target.path),
    )

    result = _driver(
        make_driver,
        tmp_path,
        "tarssh://url-user@url-host:2200/url/dir",
        env,
        cwd=repo,
    ).list()

    result.assert_exit(0)
    result.assert_stderr_empty()
    call = fake_ssh.calls[-1]
    assert (call.host, call.user, call.port) == ("fake-target", "env-user", 22222)


def test_user_and_port_default_when_nothing_supplies_them(
    make_driver, fake_ssh, target, tarssh_env, tmp_path
):
    target.create()

    result = _driver(make_driver, tmp_path, f"tarssh://fake-target{target.path}", tarssh_env).list()

    result.assert_exit(0)
    call = fake_ssh.calls[-1]
    assert call.user == getpass.getuser()
    assert call.port == 22


def test_url_and_toml_disagreement_is_one_stderr_line(
    make_driver, fake_ssh, target, tarssh_env, tmp_path
):
    target.create()
    repo = _repo_with_toml(tmp_path, host="file-host")

    result = _driver(
        make_driver, tmp_path, f"tarssh://fake-target{target.path}", tarssh_env, cwd=repo
    ).list()

    result.assert_exit(0)
    assert len(result.stderr_lines) == 1
    line = result.stderr_lines[0]
    assert "fake-target" in line
    assert "file-host" in line
    assert "remote URL" in line
    assert TOML_NAME in line
    assert fake_ssh.calls[-1].host == "fake-target"


def test_several_url_disagreements_are_still_one_stderr_line(
    make_driver, fake_ssh, target, tarssh_env, tmp_path
):
    target.create()
    repo = _repo_with_toml(
        tmp_path,
        user="file-user",
        host="file-host",
        ssh_port=2222,
        dir="/file/dir",
    )
    url = f"tarssh://url-user@fake-target:22222{target.path}"

    result = _driver(make_driver, tmp_path, url, tarssh_env, cwd=repo).list()

    result.assert_exit(0)
    assert len(result.stderr_lines) == 1
    line = result.stderr_lines[0]
    assert "remote URL" in line
    assert TOML_NAME in line
    for value in (
        "url-user",
        "fake-target",
        "22222",
        str(target.path),
        "file-user",
        "file-host",
        "2222",
        "/file/dir",
    ):
        assert value in line
    call = fake_ssh.calls[-1]
    assert (call.host, call.user, call.port) == ("fake-target", "url-user", 22222)


def test_an_environment_override_suppresses_the_warning_for_that_field(
    make_driver, fake_ssh, target, tarssh_env, tmp_path
):
    target.create()
    repo = _repo_with_toml(tmp_path, host="file-host", dir=str(target.path))
    env = dict(tarssh_env)
    env["TARSSH_HOST"] = "fake-target"

    result = _driver(
        make_driver, tmp_path, f"tarssh://fake-target{target.path}", env, cwd=repo
    ).list()

    result.assert_exit(0)
    result.assert_stderr_empty()
    assert fake_ssh.calls[-1].host == "fake-target"


def test_a_relative_directory_from_toml_is_refused_naming_the_url(
    make_driver, fake_ssh, target, tarssh_env, tmp_path
):
    repo = _repo_with_toml(tmp_path, host="fake-target", dir="relative/path")

    result = _driver(make_driver, tmp_path, "", tarssh_env, cwd=repo).list()

    assert result.exit_code != 0
    assert result.stdout == ""
    assert "tarssh::" in result.stderr
    assert "relative/path" in result.stderr
    assert "not absolute" in result.stderr


def test_a_url_without_a_path_is_refused_naming_the_url(make_driver, tarssh_env, tmp_path):
    url = "tarssh://fake-target"

    result = _driver(make_driver, tmp_path, url, tarssh_env).list()

    assert result.exit_code != 0
    assert result.stdout == ""
    assert url in result.stderr


def test_a_bare_tarssh_colon_is_not_a_helper_url(make_driver, tarssh_env, tmp_path):
    result = _driver(make_driver, tmp_path, "tarssh:", tarssh_env).list()

    assert result.exit_code != 0
    assert result.stdout == ""
    assert "not a tarssh helper URL" in result.stderr
    assert "tarssh:" in result.stderr


def test_a_full_url_works_outside_a_repository_and_ignores_a_stray_toml(
    make_driver, fake_ssh, target, tarssh_env, tmp_path
):
    target.create()
    # This file is in the cwd, not at a repository root. It must not be read.
    (tmp_path / TOML_NAME).write_text('host = "stray-host"\ndir = "/stray/dir"\n', encoding="utf-8")

    result = _driver(make_driver, tmp_path, f"tarssh://fake-target{target.path}", tarssh_env).list()

    result.assert_exit(0)
    result.assert_stderr_empty()
    assert fake_ssh.calls[-1].host == "fake-target"


@pytest.mark.parametrize("url", ["tarssh::", ""])
def test_descriptor_only_url_without_a_descriptor_names_the_url(
    make_driver, tarssh_env, tmp_path, url
):
    result = _driver(make_driver, tmp_path, url, tarssh_env).list()

    assert result.exit_code != 0
    assert "tarssh::" in result.stderr
