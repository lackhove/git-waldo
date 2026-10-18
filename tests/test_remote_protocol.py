"""The helper's protocol surface, driven exactly as git drives it."""

from __future__ import annotations

import subprocess
import sys

import pytest


def _driver(make_driver, tmp_path, url, env, cwd=None):
    return make_driver(
        [sys.executable, "-m", "tarssh.remote"],
        url=url,
        env=env,
        cwd=cwd or tmp_path,
    )


def test_capabilities_are_sent_only_in_response_to_git(
    make_driver, fake_ssh, tarssh_env, tmp_path
):
    silent = _driver(make_driver, tmp_path, fake_ssh.url, tarssh_env).run_input("")

    silent.assert_exit(0)
    silent.assert_stdout_empty()
    silent.assert_stderr_empty()


def test_capabilities_are_fetch_push_and_option(
    make_driver, fake_ssh, tarssh_env, tmp_path
):
    result = _driver(make_driver, tmp_path, fake_ssh.url, tarssh_env).capabilities()

    result.assert_exit(0)
    result.assert_stdout_lines("fetch", "push", "option", "")
    result.assert_stderr_empty()


@pytest.mark.parametrize("name", ["dry-run", "verbosity", "followtags", "cloning"])
def test_supported_options_answer_ok(make_driver, fake_ssh, tarssh_env, tmp_path, name):
    result = _driver(make_driver, tmp_path, fake_ssh.url, tarssh_env).option(name, "true")

    result.assert_exit(0)
    result.assert_stdout_lines("ok")


@pytest.mark.parametrize("name", ["progress", "cas"])
def test_unsupported_options_answer_unsupported(
    make_driver, fake_ssh, tarssh_env, tmp_path, name
):
    result = _driver(make_driver, tmp_path, fake_ssh.url, tarssh_env).option(name, "false")

    result.assert_exit(0)
    result.assert_stdout_lines("unsupported")


def test_list_for_push_is_empty_without_fabricating_an_oid(
    make_driver, fake_ssh, tarssh_env, tmp_path
):
    result = _driver(make_driver, tmp_path, fake_ssh.url, tarssh_env).list(for_push=True)

    result.assert_exit(0)
    result.assert_stdout_lines("")
    assert "?" not in result.stdout


def test_list_for_push_advertises_the_real_remote_branch_oid(
    make_driver, fake_ssh, target, tarssh_env, tmp_path
):
    target.create()
    repo = tmp_path / "repo"
    subprocess.run(["git", "init", "-q", "-b", "main", str(repo)], check=True)
    subprocess.run(
        ["git", "-C", str(repo), "commit", "-q", "--allow-empty", "-m", "seed"],
        check=True,
        env={
            **tarssh_env,
            "GIT_AUTHOR_NAME": "test",
            "GIT_AUTHOR_EMAIL": "test@example.com",
            "GIT_COMMITTER_NAME": "test",
            "GIT_COMMITTER_EMAIL": "test@example.com",
        },
    )
    head = subprocess.run(
        ["git", "-C", str(repo), "rev-parse", "HEAD"],
        text=True,
        capture_output=True,
        check=True,
    ).stdout.strip()
    subprocess.run(
        ["git", "-C", str(repo), "update-ref", "refs/remotes/origin/main", head],
        check=True,
    )

    result = _driver(make_driver, tmp_path, fake_ssh.url, tarssh_env, cwd=repo).list(
        for_push=True
    )

    result.assert_exit(0)
    result.assert_stdout_lines(f"{head} refs/heads/main", "")
    result.assert_stderr_empty()
    assert "?" not in result.stdout


def test_fetch_verifies_a_real_local_oid_and_prints_one_blank_line(
    make_driver, fake_ssh, target, tarssh_env, tmp_path
):
    target.create()
    repo = tmp_path / "repo"
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    driver = _driver(make_driver, tmp_path, fake_ssh.url, tarssh_env, cwd=repo)
    listed = driver.list()
    oid = listed.stdout_lines[1].split(" ")[0]

    result = driver.fetch(f"{oid} refs/heads/main")

    result.assert_exit(0)
    result.assert_stdout_lines("")
    result.assert_stderr_empty()


def test_fetch_of_an_absent_oid_fails_loudly(
    make_driver, fake_ssh, tarssh_env, tmp_path
):
    oid = "0" * 40
    result = _driver(make_driver, tmp_path, fake_ssh.url, tarssh_env).fetch(
        f"{oid} refs/heads/main"
    )

    assert result.exit_code != 0
    assert result.stdout == ""
    assert oid in result.stderr


def test_an_unknown_protocol_command_fails_loudly(
    make_driver, fake_ssh, tarssh_env, tmp_path
):
    result = _driver(make_driver, tmp_path, fake_ssh.url, tarssh_env).run("bogus")

    assert result.exit_code != 0
    assert result.stdout == ""
    assert "bogus" in result.stderr
