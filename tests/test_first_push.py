"""First-use push: create the target, deploy the full commit, report counts."""

from __future__ import annotations

import sys

import pytest
from push_support import (
    CONFIG_FILES,
    deploy_message,
    git,
    head_tree,
    lock_path,
    make_repo,
    push,
    target_tree,
    up_to_date_message,
)


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
    assert deploy_message(target, 2, 0) in completed.stderr
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
    assert deploy_message(target, 2, 0) in completed.stderr


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
    assert deploy_message(target, 2, 0) in completed.stderr
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
    result.assert_stderr_lines(deploy_message(target, 2, 0))
    assert not target.path.exists()


def test_a_first_push_of_an_empty_commit_reports_already_up_to_date(
    fake_ssh, target, real_git_env, tmp_path
):
    repo = make_repo(tmp_path, real_git_env, {}, allow_empty=True)
    git(["remote", "add", "target", fake_ssh.url], repo, real_git_env)

    completed = push(repo, real_git_env, "-u")

    assert completed.returncode == 0, completed.stderr
    assert up_to_date_message(target) in completed.stderr
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
    result.assert_stderr_lines(deploy_message(target, 2, 0))
    assert target_tree(target) == head_tree(repo, tarssh_env)
