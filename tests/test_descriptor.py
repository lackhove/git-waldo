"""Descriptor precedence, disagreement warnings and URL shapes."""

from __future__ import annotations

import getpass
import subprocess
import sys
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from pathlib import Path

TOML_NAME = ".waldo.toml"


def _driver(make_driver, tmp_path, url, env, cwd=None):
    return make_driver(
        [sys.executable, "-m", "waldo.remote"],
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


def _repo_with_legacy_toml(
    tmp_path: Path,
    *,
    host: str = "legacy-host",
    path: str = "/legacy/dir",
) -> Path:
    repo = tmp_path / "repo"
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    (repo / ".tarssh.toml").write_text(f'host = "{host}"\ndir = "{path}"\n', encoding="utf-8")
    return repo


def test_a_full_url_supplies_user_host_port_and_path(
    make_driver, fake_ssh, target, waldo_env, tmp_path
):
    target.create()
    url = f"waldo://user@fake-target:2222{target.path}"

    result = _driver(make_driver, tmp_path, url, waldo_env).list()

    result.assert_exit(0)
    result.assert_stderr_empty()
    call = fake_ssh.calls[-1]
    assert (call.host, call.user, call.port) == ("fake-target", "user", 2222)


def test_descriptor_only_url_resolves_everything_from_toml(
    make_driver, fake_ssh, target, waldo_env, tmp_path
):
    target.create()
    repo = _repo_with_toml(
        tmp_path,
        user="root",
        host="fake-target",
        ssh_port=2222,
        dir=str(target.path),
    )

    result = _driver(make_driver, tmp_path, "", waldo_env, cwd=repo).list()

    result.assert_exit(0)
    result.assert_stderr_empty()
    call = fake_ssh.calls[-1]
    assert (call.host, call.user, call.port) == ("fake-target", "root", 2222)


def test_environment_wins_over_url_and_toml_per_field(
    make_driver, fake_ssh, target, waldo_env, tmp_path
):
    target.create()
    repo = _repo_with_toml(
        tmp_path,
        user="toml-user",
        host="toml-host",
        ssh_port=2222,
        dir="/toml/dir",
    )
    env = dict(waldo_env)
    env.update(
        WALDO_USER="env-user",
        WALDO_HOST="fake-target",
        WALDO_SSH_PORT="2222",
        WALDO_DIR=str(target.path),
    )

    result = _driver(
        make_driver,
        tmp_path,
        "waldo://url-user@url-host:2200/url/dir",
        env,
        cwd=repo,
    ).list()

    result.assert_exit(0)
    result.assert_stderr_empty()
    call = fake_ssh.calls[-1]
    assert (call.host, call.user, call.port) == ("fake-target", "env-user", 2222)


def test_user_and_port_default_when_nothing_supplies_them(
    make_driver, fake_ssh, target, waldo_env, tmp_path
):
    target.create()

    result = _driver(make_driver, tmp_path, f"waldo://fake-target{target.path}", waldo_env).list()

    result.assert_exit(0)
    call = fake_ssh.calls[-1]
    assert call.user == getpass.getuser()
    assert call.port == 22


def test_url_and_toml_disagreement_is_one_stderr_line(
    make_driver, fake_ssh, target, waldo_env, tmp_path
):
    target.create()
    repo = _repo_with_toml(tmp_path, host="file-host")

    result = _driver(
        make_driver, tmp_path, f"waldo://fake-target{target.path}", waldo_env, cwd=repo
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
    make_driver, fake_ssh, target, waldo_env, tmp_path
):
    target.create()
    repo = _repo_with_toml(
        tmp_path,
        user="file-user",
        host="file-host",
        ssh_port=2200,
        dir="/file/dir",
    )
    url = f"waldo://url-user@fake-target:2222{target.path}"

    result = _driver(make_driver, tmp_path, url, waldo_env, cwd=repo).list()

    result.assert_exit(0)
    assert len(result.stderr_lines) == 1
    line = result.stderr_lines[0]
    assert "remote URL" in line
    assert TOML_NAME in line
    for value in (
        "url-user",
        "fake-target",
        "2222",
        str(target.path),
        "file-user",
        "file-host",
        "2200",
        "/file/dir",
    ):
        assert value in line
    call = fake_ssh.calls[-1]
    assert (call.host, call.user, call.port) == ("fake-target", "url-user", 2222)


def test_an_environment_override_suppresses_the_warning_for_that_field(
    make_driver, fake_ssh, target, waldo_env, tmp_path
):
    target.create()
    repo = _repo_with_toml(tmp_path, host="file-host", dir=str(target.path))
    env = dict(waldo_env)
    env["WALDO_HOST"] = "fake-target"

    result = _driver(
        make_driver, tmp_path, f"waldo://fake-target{target.path}", env, cwd=repo
    ).list()

    result.assert_exit(0)
    result.assert_stderr_empty()
    assert fake_ssh.calls[-1].host == "fake-target"


def test_a_relative_directory_from_toml_is_refused_naming_the_url(
    make_driver, fake_ssh, target, waldo_env, tmp_path
):
    repo = _repo_with_toml(tmp_path, host="fake-target", dir="relative/path")

    result = _driver(make_driver, tmp_path, "", waldo_env, cwd=repo).list()

    assert result.exit_code != 0
    assert result.stdout == ""
    assert "waldo::" in result.stderr
    assert "relative/path" in result.stderr
    assert "not absolute" in result.stderr


def test_a_url_without_a_path_is_refused_naming_the_url(make_driver, waldo_env, tmp_path):
    url = "waldo://fake-target"

    result = _driver(make_driver, tmp_path, url, waldo_env).list()

    assert result.exit_code != 0
    assert result.stdout == ""
    assert url in result.stderr


def test_a_bare_waldo_colon_is_not_a_helper_url(make_driver, waldo_env, tmp_path):
    result = _driver(make_driver, tmp_path, "waldo:", waldo_env).list()

    assert result.exit_code != 0
    assert result.stdout == ""
    assert "not a waldo helper URL" in result.stderr
    assert "waldo:" in result.stderr


def test_a_full_url_works_outside_a_repository_and_ignores_a_stray_toml(
    make_driver, fake_ssh, target, waldo_env, tmp_path
):
    target.create()
    # This file is in the cwd, not at a repository root. It must not be read.
    (tmp_path / TOML_NAME).write_text('host = "stray-host"\ndir = "/stray/dir"\n', encoding="utf-8")

    result = _driver(make_driver, tmp_path, f"waldo://fake-target{target.path}", waldo_env).list()

    result.assert_exit(0)
    result.assert_stderr_empty()
    assert fake_ssh.calls[-1].host == "fake-target"


@pytest.mark.parametrize("url", ["waldo::", ""])
def test_descriptor_only_url_without_a_descriptor_names_the_url(
    make_driver, waldo_env, tmp_path, url
):
    result = _driver(make_driver, tmp_path, url, waldo_env).list()

    assert result.exit_code != 0
    assert "waldo::" in result.stderr


def test_a_legacy_descriptor_alone_fails_with_a_rename_diagnostic(make_driver, waldo_env, tmp_path):
    repo = _repo_with_legacy_toml(tmp_path, host="fake-target", path="/srv/config")

    result = _driver(make_driver, tmp_path, "", waldo_env, cwd=repo).list()

    assert result.exit_code != 0
    assert result.stdout == ""
    assert ".tarssh.toml" in result.stderr
    assert ".waldo.toml" in result.stderr
    assert "renamed" in result.stderr
    assert "no target host" not in result.stderr


def test_a_legacy_descriptor_is_ignored_when_the_new_descriptor_exists(
    make_driver, fake_ssh, target, waldo_env, tmp_path
):
    target.create()
    repo = _repo_with_toml(tmp_path, host="fake-target", dir=str(target.path))
    (repo / ".tarssh.toml").write_text(
        'host = "legacy-host"\ndir = "/legacy/dir"\n', encoding="utf-8"
    )

    result = _driver(make_driver, tmp_path, "", waldo_env, cwd=repo).list()

    result.assert_exit(0)
    result.assert_stderr_empty()
    assert fake_ssh.calls[-1].host == "fake-target"


def test_a_url_that_supplies_the_host_is_not_blocked_by_a_legacy_descriptor(
    make_driver, fake_ssh, target, waldo_env, tmp_path
):
    target.create()
    repo = _repo_with_legacy_toml(tmp_path)

    result = _driver(
        make_driver,
        tmp_path,
        f"waldo://fake-target{target.path}",
        waldo_env,
        cwd=repo,
    ).list()

    result.assert_exit(0)
    result.assert_stderr_empty()
    assert fake_ssh.calls[-1].host == "fake-target"
