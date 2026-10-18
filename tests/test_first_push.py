"""First-use push: create the target, deploy the full commit, report counts."""

from __future__ import annotations

import hashlib
import os
import subprocess
import sys
from pathlib import Path

import pytest

IDENT = {
    "GIT_AUTHOR_NAME": "test",
    "GIT_AUTHOR_EMAIL": "test@example.com",
    "GIT_COMMITTER_NAME": "test",
    "GIT_COMMITTER_EMAIL": "test@example.com",
}


def git(args, cwd, env, *, check=True, text=True):
    completed = subprocess.run(
        ["git", *args],
        cwd=cwd,
        text=text,
        capture_output=True,
        env=env,
        check=False,
    )
    if check and completed.returncode != 0:
        stderr = completed.stderr if text else completed.stderr.decode("utf-8", "replace")
        raise AssertionError(f"git {' '.join(args)} failed: {stderr}")
    return completed


def make_repo(tmp_path, env, files, *, allow_empty=False):
    repo = tmp_path / "repo"
    repo.mkdir()
    git(["init", "-q", "-b", "main"], repo, env)
    for name, (content, mode) in files.items():
        path = repo / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
        path.chmod(mode)
    git(["add", "-A"], repo, env)
    commit = ["commit", "-q", "-m", "config"]
    if allow_empty:
        commit.append("--allow-empty")
    git(commit, repo, {**env, **IDENT})
    return repo


def head_tree(repo, env):
    """Map ``path`` to ``(mode, content)`` for every entry in ``HEAD``."""
    listing = git(["ls-tree", "-r", "-z", "HEAD"], repo, env).stdout
    entries = {}
    for record in listing.split("\0"):
        if not record:
            continue
        metadata, path = record.split("\t", 1)
        mode, kind, oid = metadata.split(" ")
        if kind == "commit":
            continue
        content = git(["cat-file", "blob", oid], repo, env, text=False).stdout
        entries[path] = (mode, content)
    return entries


def target_tree(target):
    entries = {}
    for path in sorted(target.path.rglob("*")):
        relative = path.relative_to(target.path).as_posix()
        if path.is_symlink():
            entries[relative] = ("120000", os.readlink(path).encode())
        elif path.is_file():
            mode = "100755" if path.stat().st_mode & 0o111 else "100644"
            entries[relative] = (mode, path.read_bytes())
    return entries


def lock_path(target):
    digest = hashlib.sha256(str(target.path).encode()).hexdigest()[:16]
    return Path("/tmp") / f"tarssh-{digest}.lock"


def push(repo, env, *args, remote="target"):
    return git(["push", *args, remote, "main"], repo, env, check=False)


CONFIG_FILES = {
    "a.txt": (b"alpha\n", 0o644),
    "sub/b.sh": (b"#!/bin/sh\necho beta\n", 0o755),
}


def test_first_push_to_a_missing_target_creates_it_and_deploys_head(
    fake_ssh, target, real_git_env, tmp_path
):
    repo = make_repo(tmp_path, real_git_env, CONFIG_FILES)
    git(["remote", "add", "target", fake_ssh.url], repo, real_git_env)
    assert not target.path.exists()

    completed = push(repo, real_git_env, "-u")

    assert completed.returncode == 0, completed.stderr
    assert target.path.is_dir()
    assert target_tree(target) == head_tree(repo, real_git_env)
    assert "deploying 2 changes: 2 written, 0 deleted" in completed.stderr
    assert f"mkdir -p {target.path}" in [call.command for call in fake_ssh.calls]
    assert (
        git(["rev-parse", "--abbrev-ref", "main@{upstream}"], repo, real_git_env)
        .stdout.strip()
        == "target/main"
    )


@pytest.mark.parametrize("existing", ["missing", "empty"])
def test_first_push_to_a_missing_or_empty_target(
    fake_ssh, target, real_git_env, tmp_path, existing
):
    if existing == "empty":
        target.create()
    repo = make_repo(tmp_path, real_git_env, CONFIG_FILES)
    git(["remote", "add", "target", fake_ssh.url], repo, real_git_env)

    completed = push(repo, real_git_env, "-u")

    assert completed.returncode == 0, completed.stderr
    assert target_tree(target) == head_tree(repo, real_git_env)
    assert "deploying 2 changes: 2 written, 0 deleted" in completed.stderr


def test_first_push_updates_the_remote_branch_locally(
    fake_ssh, target, real_git_env, tmp_path
):
    repo = make_repo(tmp_path, real_git_env, CONFIG_FILES)
    git(["remote", "add", "target", fake_ssh.url], repo, real_git_env)
    head = git(["rev-parse", "HEAD"], repo, real_git_env).stdout.strip()

    completed = push(repo, real_git_env, "-u")

    assert completed.returncode == 0, completed.stderr
    assert (
        git(["rev-parse", "refs/remotes/target/main"], repo, real_git_env).stdout.strip()
        == head
    )


def test_dry_run_reports_the_same_counts_and_writes_nothing(
    fake_ssh, target, real_git_env, tmp_path
):
    repo = make_repo(tmp_path, real_git_env, CONFIG_FILES)
    git(["remote", "add", "target", fake_ssh.url], repo, real_git_env)

    completed = push(repo, real_git_env, "--dry-run")

    assert completed.returncode == 0, completed.stderr
    assert "deploying 2 changes: 2 written, 0 deleted" in completed.stderr
    commands = [call.command for call in fake_ssh.calls]
    assert f"mkdir {lock_path(target)}" in commands
    assert f"rm -rf {lock_path(target)}" in commands
    assert not any(
        command.startswith(("mkdir -p ", "tar ")) for command in commands
    )
    assert not target.path.exists()
    assert not lock_path(target).exists()


def test_dry_run_still_receives_the_push_lines_at_protocol_level(
    make_driver, fake_ssh, target, tarssh_env, tmp_path
):
    repo = make_repo(tmp_path, tarssh_env, CONFIG_FILES)
    driver = make_driver(
        [sys.executable, "-m", "tarssh.remote"],
        remote="target",
        url=fake_ssh.url,
        env=tarssh_env,
        cwd=repo,
    )

    result = driver.run(
        "option dry-run true",
        "list for-push",
        "push refs/heads/main:refs/heads/main",
        "",
    )

    result.assert_exit(0)
    result.assert_stdout_lines("ok", "", "ok refs/heads/main", "")
    result.assert_stderr_lines("deploying 2 changes: 2 written, 0 deleted")
    assert not target.path.exists()


def test_a_first_push_of_an_empty_commit_reports_already_up_to_date(
    fake_ssh, target, real_git_env, tmp_path
):
    repo = make_repo(tmp_path, real_git_env, {}, allow_empty=True)
    git(["remote", "add", "target", fake_ssh.url], repo, real_git_env)

    completed = push(repo, real_git_env, "-u")

    assert completed.returncode == 0, completed.stderr
    assert "already up to date" in completed.stderr
    assert target.path.is_dir()
    assert target_tree(target) == {}


def test_deploy_extracts_with_target_side_ownership(
    fake_ssh, target, real_git_env, tmp_path
):
    repo = make_repo(tmp_path, real_git_env, CONFIG_FILES)
    git(["remote", "add", "target", fake_ssh.url], repo, real_git_env)

    completed = push(repo, real_git_env)

    assert completed.returncode == 0, completed.stderr
    extractions = [call.command for call in fake_ssh.calls if call.command.startswith("tar ")]
    assert len(extractions) == 1
    assert extractions[0].startswith("tar -o -xf - -C ")
    assert "--no-same-owner" not in extractions[0]


def test_the_lock_is_taken_before_deployment_and_released_afterwards(
    fake_ssh, target, real_git_env, tmp_path
):
    repo = make_repo(tmp_path, real_git_env, CONFIG_FILES)
    git(["remote", "add", "target", fake_ssh.url], repo, real_git_env)
    lock = lock_path(target)

    completed = push(repo, real_git_env)

    assert completed.returncode == 0, completed.stderr
    commands = [call.command for call in fake_ssh.calls]
    taken = commands.index(f"mkdir {lock}")
    created = commands.index(f"mkdir -p {target.path}")
    extracted = next(
        index for index, command in enumerate(commands) if command.startswith("tar ")
    )
    assert taken < created < extracted
    assert f"rm -rf {lock}" in commands
    assert not lock.exists()


def test_a_failed_extraction_still_releases_the_lock(
    fake_ssh, target, real_git_env, tmp_path
):
    repo = make_repo(tmp_path, real_git_env, CONFIG_FILES)
    git(["remote", "add", "target", fake_ssh.url], repo, real_git_env)
    fake_ssh.fail_extraction()

    completed = push(repo, real_git_env)

    assert completed.returncode != 0
    assert "cannot deploy to target" in completed.stderr
    assert not lock_path(target).exists()
    assert target.path.is_dir()
    assert not (target.path / "a.txt").exists()


def test_an_existing_lock_is_a_protocol_error_naming_the_path_and_is_not_broken(
    fake_ssh, target, real_git_env, tmp_path
):
    repo = make_repo(tmp_path, real_git_env, CONFIG_FILES)
    git(["remote", "add", "target", fake_ssh.url], repo, real_git_env)
    lock = lock_path(target)
    lock.mkdir()
    try:
        completed = push(repo, real_git_env)

        assert completed.returncode != 0
        assert str(lock) in completed.stderr
        assert not target.path.exists()
        assert lock.exists()
    finally:
        lock.rmdir()


def test_a_push_when_the_remote_branch_exists_is_refused_with_a_temporary_error(
    fake_ssh, target, real_git_env, tmp_path
):
    repo = make_repo(tmp_path, real_git_env, CONFIG_FILES)
    git(["remote", "add", "target", fake_ssh.url], repo, real_git_env)
    first = push(repo, real_git_env, "-u")
    assert first.returncode == 0, first.stderr
    first_tree = target_tree(target)
    before = len(fake_ssh.calls)

    (repo / "a.txt").write_text("changed\n", encoding="utf-8")
    git(["add", "-A"], repo, real_git_env)
    git(["commit", "-q", "-m", "change"], repo, {**real_git_env, **IDENT})
    second = push(repo, real_git_env)

    assert second.returncode != 0
    assert "delta pushes are not yet implemented" in second.stderr
    assert "remote rejected" in second.stderr
    assert target_tree(target) == first_tree
    assert not any(call.command.startswith("tar ") for call in fake_ssh.calls[before:])


def test_the_protocol_keeps_stdout_pure_and_operator_counts_on_stderr(
    make_driver, fake_ssh, target, tarssh_env, tmp_path
):
    repo = make_repo(tmp_path, tarssh_env, CONFIG_FILES)
    driver = make_driver(
        [sys.executable, "-m", "tarssh.remote"],
        url=fake_ssh.url,
        env=tarssh_env,
        cwd=repo,
    )

    result = driver.push("refs/heads/main:refs/heads/main")

    result.assert_exit(0)
    result.assert_stdout_lines("ok refs/heads/main", "")
    result.assert_stderr_lines("deploying 2 changes: 2 written, 0 deleted")
    assert target_tree(target) == head_tree(repo, tarssh_env)


def test_a_push_of_an_already_existing_remote_branch_is_refused_at_protocol_level(
    make_driver, fake_ssh, target, tarssh_env, tmp_path
):
    repo = make_repo(tmp_path, tarssh_env, CONFIG_FILES)
    head = git(["rev-parse", "HEAD"], repo, tarssh_env).stdout.strip()
    git(["update-ref", "refs/remotes/target/main", head], repo, tarssh_env)
    driver = make_driver(
        [sys.executable, "-m", "tarssh.remote"],
        remote="target",
        url=fake_ssh.url,
        env=tarssh_env,
        cwd=repo,
    )

    result = driver.push("refs/heads/main:refs/heads/main")

    result.assert_exit(0)
    result.assert_stdout_lines(
        "error refs/heads/main delta pushes are not yet implemented", ""
    )
    result.assert_stderr_empty()
    assert not target.path.exists()
