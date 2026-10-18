"""Ref-level rejections: exact git tokens, stable precedence, exit zero."""

from __future__ import annotations

import sys

import pytest
from push_support import (
    IDENT,
    commit,
    git,
    head_tree,
    lock_path,
    make_pushed_repo,
    push,
    target_tree,
    up_to_date_message,
)


def helper_driver(make_driver, fake_ssh, env, repo):
    return make_driver(
        [sys.executable, "-m", "tarssh.remote"],
        remote="target",
        url=fake_ssh.url,
        env=env,
        cwd=repo,
    )


@pytest.mark.parametrize(
    ("spec", "dst", "error"),
    [
        (
            "+refs/heads/main:refs/heads/main",
            "refs/heads/main",
            "force pushes are not supported",
        ),
        (
            "+:refs/heads/main",
            "refs/heads/main",
            "force pushes are not supported",
        ),
        (
            ":refs/heads/main",
            "refs/heads/main",
            "deleting branches is not supported",
        ),
        (
            "refs/heads/main:refs/heads/other",
            "refs/heads/other",
            "only refs/heads/main is deployed",
        ),
        # Precedence: force, then ref deletion, then destination.
        (
            "+:refs/heads/other",
            "refs/heads/other",
            "force pushes are not supported",
        ),
        (
            ":refs/heads/other",
            "refs/heads/other",
            "deleting branches is not supported",
        ),
    ],
)
def test_refspec_rejections_use_the_exact_tokens_and_exit_zero(
    make_driver, fake_ssh, target, real_git_env, tmp_path, spec, dst, error
):
    repo = make_pushed_repo(fake_ssh, tmp_path, real_git_env)
    before = target_tree(target)

    result = helper_driver(make_driver, fake_ssh, real_git_env, repo).push(spec)

    result.assert_exit(0)
    result.assert_stdout_lines(f"error {dst} {error}", "")
    result.assert_stderr_empty()
    assert target_tree(target) == before


def test_a_mixed_rejection_batch_prints_one_stable_status_per_ref(
    make_driver, fake_ssh, target, real_git_env, tmp_path
):
    repo = make_pushed_repo(fake_ssh, tmp_path, real_git_env)
    before = target_tree(target)

    result = helper_driver(make_driver, fake_ssh, real_git_env, repo).push(
        "+refs/heads/main:refs/heads/main",
        ":refs/heads/main",
        "refs/heads/main:refs/heads/other",
    )

    result.assert_exit(0)
    result.assert_stdout_lines(
        "error refs/heads/main force pushes are not supported",
        "error refs/heads/main deleting branches is not supported",
        "error refs/heads/other only refs/heads/main is deployed",
        "",
    )
    result.assert_stderr_empty()
    assert target_tree(target) == before


def test_a_malformed_push_line_is_still_a_protocol_error(
    make_driver, fake_ssh, target, real_git_env, tmp_path
):
    repo = make_pushed_repo(fake_ssh, tmp_path, real_git_env)

    result = helper_driver(make_driver, fake_ssh, real_git_env, repo).run("push", "")

    result.assert_exit(1)
    result.assert_stdout_empty()
    assert "malformed push line" in result.stderr
    assert not lock_path(target).exists()


def test_a_force_push_through_git_is_remote_rejected(fake_ssh, target, real_git_env, tmp_path):
    repo = make_pushed_repo(fake_ssh, tmp_path, real_git_env)
    (repo / "a.txt").write_text("changed\n", encoding="utf-8")
    commit(repo, real_git_env)
    before = target_tree(target)

    completed = push(repo, real_git_env, "--force")

    assert completed.returncode != 0
    assert "force pushes are not supported" in completed.stderr
    assert "remote rejected" in completed.stderr
    assert target_tree(target) == before


def test_a_branch_deletion_through_git_is_remote_rejected_and_has_no_paths(
    fake_ssh, target, real_git_env, tmp_path
):
    repo = make_pushed_repo(fake_ssh, tmp_path, real_git_env)
    before = target_tree(target)

    completed = git(["push", "target", ":main"], repo, real_git_env, check=False)

    assert completed.returncode != 0
    assert "deleting branches is not supported" in completed.stderr
    assert "remote rejected" in completed.stderr
    assert "cannot delete" not in completed.stderr
    assert target_tree(target) == before
    assert not any(" rm -f ./" in call.command for call in fake_ssh.calls)


def test_a_non_main_destination_through_git_is_remote_rejected(
    fake_ssh, target, real_git_env, tmp_path
):
    repo = make_pushed_repo(fake_ssh, tmp_path, real_git_env)
    (repo / "a.txt").write_text("changed\n", encoding="utf-8")
    commit(repo, real_git_env)
    before = target_tree(target)

    completed = git(
        ["push", "target", "main:refs/heads/other"],
        repo,
        real_git_env,
        check=False,
    )

    assert completed.returncode != 0
    assert "only refs/heads/main is deployed" in completed.stderr
    assert "remote rejected" in completed.stderr
    assert target_tree(target) == before
    assert target_tree(target) != head_tree(repo, real_git_env)


def test_an_unreachable_target_fails_the_push_on_stderr_and_exits_nonzero(
    fake_ssh, target, real_git_env, tmp_path
):
    repo = make_pushed_repo(fake_ssh, tmp_path, real_git_env)
    (repo / "a.txt").write_text("changed\n", encoding="utf-8")
    commit(repo, real_git_env)
    fake_ssh.fail_connection()

    completed = push(repo, real_git_env)

    assert completed.returncode != 0
    assert "Connection refused" in completed.stderr
    assert "git-remote-tarssh:" in completed.stderr
    assert "deploying" not in completed.stderr
    assert not lock_path(target).exists()


def test_a_stale_lock_is_reported_by_its_full_path_and_left_in_place(
    make_driver, fake_ssh, target, real_git_env, tmp_path
):
    repo = make_pushed_repo(fake_ssh, tmp_path, real_git_env)
    lock = lock_path(target)
    lock.mkdir()
    before = target_tree(target)
    calls_before = len(fake_ssh.calls)
    try:
        result = helper_driver(make_driver, fake_ssh, real_git_env, repo).list(for_push=True)

        result.assert_exit(1)
        result.assert_stdout_empty()
        assert str(lock) in result.stderr
        assert lock.exists()
        commands = [call.command for call in fake_ssh.calls[calls_before:]]
        assert f"mkdir {lock}" in commands
        assert f"rm -rf {lock}" not in commands
        assert not any(command.startswith(f"cd {target.path} && find") for command in commands)
        assert target_tree(target) == before
    finally:
        lock.rmdir()


def test_a_failed_extraction_releases_the_lock_and_the_half_state_blocks_push(
    fake_ssh, target, real_git_env, tmp_path
):
    repo = make_pushed_repo(fake_ssh, tmp_path, real_git_env, {"a.txt": (b"alpha\n", 0o644)})
    remote_oid = git(["rev-parse", "refs/remotes/target/main"], repo, real_git_env).stdout.strip()
    (repo / "a.txt").write_text("beta\n", encoding="utf-8")
    commit(repo, real_git_env)
    fake_ssh.fail_extraction()

    failed = push(repo, real_git_env)

    assert failed.returncode != 0
    assert "cannot deploy to target" in failed.stderr
    assert not lock_path(target).exists()
    assert target.read_text("a.txt") == "alpha\n"
    assert (
        git(["rev-parse", "refs/remotes/target/main"], repo, real_git_env).stdout.strip()
        == remote_oid
    )

    # The harness refuses the whole archive before writing; put the half state
    # an interrupted extraction would have left in place instead.
    fake_ssh.restore()
    target.write("a.txt", "beta\n")
    blocked = push(repo, real_git_env)

    assert blocked.returncode != 0
    assert "target has local changes: a.txt" in blocked.stderr
    assert "remote rejected" in blocked.stderr
    assert target.read_text("a.txt") == "beta\n"
    assert (
        git(["rev-parse", "refs/remotes/target/main"], repo, real_git_env).stdout.strip()
        == remote_oid
    )

    git(["fetch", "target"], repo, real_git_env)
    git(
        ["merge", "--no-edit", "target/main"],
        repo,
        {**real_git_env, **IDENT},
    )
    reconciled = push(repo, real_git_env)

    assert reconciled.returncode == 0, reconciled.stderr
    assert up_to_date_message(target) in reconciled.stderr
    assert target.read_text("a.txt") == "beta\n"
    assert (
        git(["rev-parse", "refs/remotes/target/main"], repo, real_git_env).stdout.strip()
        == git(["rev-parse", "HEAD"], repo, real_git_env).stdout.strip()
    )


def test_a_failed_deletion_releases_the_lock_and_names_each_path(
    fake_ssh, target, real_git_env, tmp_path
):
    repo = make_pushed_repo(
        fake_ssh,
        tmp_path,
        real_git_env,
        {
            "a.txt": (b"alpha\n", 0o644),
            "b.txt": (b"beta\n", 0o644),
        },
    )
    remote_oid = git(["rev-parse", "refs/remotes/target/main"], repo, real_git_env).stdout.strip()
    (repo / "a.txt").unlink()
    (repo / "b.txt").unlink()
    commit(repo, real_git_env)
    fake_ssh.fail_removal()

    failed = push(repo, real_git_env)

    assert failed.returncode != 0
    assert "git-remote-tarssh: cannot delete a.txt from target" in failed.stderr
    assert "git-remote-tarssh: cannot delete b.txt from target" in failed.stderr
    assert "cannot delete from target" in failed.stderr
    assert any(item.kind == "removal" for item in fake_ssh.failures)
    assert not lock_path(target).exists()
    assert target.exists("a.txt")
    assert target.exists("b.txt")
    assert (
        git(["rev-parse", "refs/remotes/target/main"], repo, real_git_env).stdout.strip()
        == remote_oid
    )

    fake_ssh.restore()
    retried = push(repo, real_git_env)

    assert retried.returncode == 0, retried.stderr
    assert not target.exists("a.txt")
    assert not target.exists("b.txt")
    assert (
        git(["rev-parse", "refs/remotes/target/main"], repo, real_git_env).stdout.strip()
        == git(["rev-parse", "HEAD"], repo, real_git_env).stdout.strip()
    )


def test_a_failed_deletion_names_only_the_paths_the_target_reports(
    fake_ssh, target, real_git_env, tmp_path
):
    repo = make_pushed_repo(
        fake_ssh,
        tmp_path,
        real_git_env,
        {
            "a.txt": (b"alpha\n", 0o644),
            "a.txt.bak": (b"backup\n", 0o644),
        },
    )
    (repo / "a.txt").unlink()
    (repo / "a.txt.bak").unlink()
    commit(repo, real_git_env)
    fake_ssh.fail_removal("rm: can't remove './a.txt': Permission denied")

    failed = push(repo, real_git_env)

    assert failed.returncode != 0
    assert "git-remote-tarssh: cannot delete a.txt from target" in failed.stderr
    assert "git-remote-tarssh: cannot delete a.txt.bak from target" not in failed.stderr
    assert "cannot delete from target" in failed.stderr
    assert not lock_path(target).exists()
