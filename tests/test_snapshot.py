"""A root snapshot of an empty target, and loud failures for broken targets."""

from __future__ import annotations

import os
import re
import subprocess
import sys

import pytest

EMPTY_TREE = "4b825dc642cb6eb9a060e54bf8d69288fbee4904"
HEX_OID = re.compile(r"^[0-9a-f]{40}$")


def _driver(make_driver, tmp_path, url, env, cwd=None):
    return make_driver(
        [sys.executable, "-m", "tarssh.remote"],
        url=url,
        env=env,
        cwd=cwd or tmp_path,
    )


def _git(repo, *args):
    return subprocess.run(
        ["git", *args],
        cwd=repo,
        text=True,
        capture_output=True,
        check=True,
    ).stdout.strip()


def test_list_advertises_a_real_root_snapshot_of_an_empty_target(
    make_driver, fake_ssh, target, tarssh_env, tmp_path
):
    target.create()
    repo = tmp_path / "repo"
    subprocess.run(["git", "init", "-q", str(repo)], check=True)

    result = _driver(make_driver, tmp_path, fake_ssh.url, tarssh_env, cwd=repo).list()

    result.assert_exit(0)
    assert result.stderr_lines == []
    assert result.stdout_lines[0] == "@refs/heads/main HEAD"
    assert result.stdout_lines[2] == ""
    oid, ref = result.stdout_lines[1].split(" ")
    assert ref == "refs/heads/main"
    assert HEX_OID.match(oid), oid
    assert "?" not in result.stdout

    commit = _git(repo, "cat-file", "commit", oid)
    assert "author tarssh <tarssh@localhost>" in commit
    assert "committer tarssh <tarssh@localhost>" in commit
    assert commit.splitlines()[-1] == f"snapshot of {fake_ssh.host}:{target.path}"
    assert _git(repo, "rev-parse", f"{oid}^{{tree}}") == EMPTY_TREE


def test_a_missing_target_fails_list_naming_the_url_and_path(
    make_driver, fake_ssh, target, tarssh_env, tmp_path
):
    target.remove()

    result = _driver(make_driver, tmp_path, fake_ssh.url, tarssh_env).list()

    assert result.exit_code != 0
    assert result.stdout == ""
    assert fake_ssh.url in result.stderr
    assert str(target.path) in result.stderr


@pytest.mark.skipif(os.geteuid() == 0, reason="root ignores permission bits")
def test_an_unreadable_target_fails_list_naming_the_url_and_path(
    make_driver, fake_ssh, target, tarssh_env, tmp_path
):
    target.populate({"a.txt": "x"})
    target.make_unreadable()

    result = _driver(make_driver, tmp_path, fake_ssh.url, tarssh_env).list()

    assert result.exit_code != 0
    assert result.stdout == ""
    assert fake_ssh.url in result.stderr
    assert str(target.path) in result.stderr


def test_an_unchanged_tree_advertises_the_existing_remote_branch(
    make_driver, fake_ssh, target, tarssh_env, tmp_path
):
    target.create()
    repo = tmp_path / "repo"
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    driver = make_driver(
        [sys.executable, "-m", "tarssh.remote"],
        remote="upstream",
        url=fake_ssh.url,
        env=tarssh_env,
        cwd=repo,
    )
    first = driver.list()
    oid = first.stdout_lines[1].split(" ")[0]
    subprocess.run(
        ["git", "update-ref", "refs/remotes/upstream/main", oid],
        cwd=repo,
        check=True,
    )

    second = driver.list()

    second.assert_exit(0)
    assert second.stdout_lines[1] == f"{oid} refs/heads/main"


def test_a_changed_tree_is_parented_on_the_remote_branch(
    make_driver, fake_ssh, target, tarssh_env, tmp_path
):
    target.create()
    repo = tmp_path / "repo"
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    ident = {
        "GIT_AUTHOR_NAME": "operator",
        "GIT_AUTHOR_EMAIL": "operator@example.com",
        "GIT_COMMITTER_NAME": "operator",
        "GIT_COMMITTER_EMAIL": "operator@example.com",
    }
    blob = subprocess.run(
        ["git", "hash-object", "-w", "--stdin"],
        cwd=repo,
        input="content\n",
        text=True,
        capture_output=True,
        check=True,
    ).stdout.strip()
    tree = subprocess.run(
        ["git", "mktree"],
        cwd=repo,
        input=f"100644 blob {blob}\tfile.txt\n",
        text=True,
        capture_output=True,
        check=True,
    ).stdout.strip()
    base = subprocess.run(
        ["git", "commit-tree", tree, "-m", "base"],
        cwd=repo,
        env={**os.environ, **ident},
        text=True,
        capture_output=True,
        check=True,
    ).stdout.strip()
    subprocess.run(
        ["git", "update-ref", "refs/remotes/origin/main", base],
        cwd=repo,
        check=True,
    )

    result = _driver(make_driver, tmp_path, fake_ssh.url, tarssh_env, cwd=repo).list()

    result.assert_exit(0)
    oid = result.stdout_lines[1].split(" ")[0]
    commit = _git(repo, "cat-file", "commit", oid)
    assert f"parent {base}" in commit
