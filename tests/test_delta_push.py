"""Delta pushes: only the changes since the remote branch reach the target."""

from __future__ import annotations

import sys

from push_support import (
    IDENT,
    commit,
    deploy_message,
    git,
    head_tree,
    lock_path,
    make_pushed_repo,
    push,
    target_tree,
    up_to_date_message,
)


def test_a_push_adds_a_new_path(fake_ssh, target, real_git_env, tmp_path):
    repo = make_pushed_repo(fake_ssh, tmp_path, real_git_env)
    (repo / "added.txt").write_text("new\n", encoding="utf-8")
    commit(repo, real_git_env)

    completed = push(repo, real_git_env)

    assert completed.returncode == 0, completed.stderr
    assert target_tree(target) == head_tree(repo, real_git_env)
    assert deploy_message(target, 1, 0) in completed.stderr
    assert target.read_text("added.txt") == "new\n"


def test_a_push_modifies_an_existing_path(fake_ssh, target, real_git_env, tmp_path):
    repo = make_pushed_repo(fake_ssh, tmp_path, real_git_env)
    (repo / "a.txt").write_text("changed\n", encoding="utf-8")
    commit(repo, real_git_env)

    completed = push(repo, real_git_env)

    assert completed.returncode == 0, completed.stderr
    assert target.read_text("a.txt") == "changed\n"
    assert deploy_message(target, 1, 0) in completed.stderr


def test_a_push_deletes_a_removed_path(fake_ssh, target, real_git_env, tmp_path):
    repo = make_pushed_repo(fake_ssh, tmp_path, real_git_env)
    (repo / "a.txt").unlink()
    commit(repo, real_git_env)

    completed = push(repo, real_git_env)

    assert completed.returncode == 0, completed.stderr
    assert not target.exists("a.txt")
    assert deploy_message(target, 0, 1) in completed.stderr
    assert any(
        call.command.endswith("rm -f ./a.txt") for call in fake_ssh.calls
    )


def test_a_combined_delta_writes_and_deletes_exactly_once(
    fake_ssh, target, real_git_env, tmp_path
):
    repo = make_pushed_repo(
        fake_ssh,
        tmp_path,
        real_git_env,
        {
            "keep.txt": (b"keep\n", 0o644),
            "modify.txt": (b"before\n", 0o644),
            "delete.txt": (b"gone\n", 0o644),
        },
    )
    (repo / "modify.txt").write_text("after\n", encoding="utf-8")
    (repo / "delete.txt").unlink()
    (repo / "nested/new.txt").parent.mkdir()
    (repo / "nested/new.txt").write_text("new\n", encoding="utf-8")
    commit(repo, real_git_env)
    before = len(fake_ssh.calls)

    completed = push(repo, real_git_env)

    assert completed.returncode == 0, completed.stderr
    assert target_tree(target) == head_tree(repo, real_git_env)
    assert deploy_message(target, 2, 1) in completed.stderr
    extractions = [
        call.command
        for call in fake_ssh.calls[before:]
        if call.command.startswith("tar -o -xf")
    ]
    removals = [
        call.command for call in fake_ssh.calls[before:] if " rm -f " in call.command
    ]
    assert len(extractions) == 1
    assert len(removals) == 1
    assert removals[0].endswith("rm -f ./delete.txt")


def test_an_empty_delta_reports_already_up_to_date(
    fake_ssh, target, real_git_env, tmp_path
):
    repo = make_pushed_repo(fake_ssh, tmp_path, real_git_env)
    git(
        ["commit", "-q", "--allow-empty", "-m", "empty"],
        repo,
        {**real_git_env, **IDENT},
    )
    before = target_tree(target)
    calls_before = len(fake_ssh.calls)

    completed = push(repo, real_git_env)

    assert completed.returncode == 0, completed.stderr
    assert up_to_date_message(target) in completed.stderr
    assert target_tree(target) == before
    assert not any(
        call.command.startswith("tar -o -xf") or " rm -f " in call.command
        for call in fake_ssh.calls[calls_before:]
    )
    assert (
        git(["rev-parse", "refs/remotes/target/main"], repo, real_git_env).stdout.strip()
        == git(["rev-parse", "HEAD"], repo, real_git_env).stdout.strip()
    )


def test_ignored_target_files_survive_a_delta_and_do_not_cause_drift(
    fake_ssh, target, real_git_env, tmp_path
):
    repo = make_pushed_repo(
        fake_ssh,
        tmp_path,
        real_git_env,
        {
            ".gitignore": (b"runtime/\nlocal-*.txt\n", 0o644),
            "a.txt": (b"alpha\n", 0o644),
        },
    )
    target.write("runtime/state.json", '{"state": "on"}\n')
    target.write("local-notes.txt", "operator only\n")

    (repo / "a.txt").write_text("changed\n", encoding="utf-8")
    commit(repo, real_git_env)

    completed = push(repo, real_git_env)

    assert completed.returncode == 0, completed.stderr
    assert deploy_message(target, 1, 0) in completed.stderr
    assert target.read_text("runtime/state.json") == '{"state": "on"}\n'
    assert target.read_text("local-notes.txt") == "operator only\n"
    assert target.read_text("a.txt") == "changed\n"


def test_directories_emptied_by_a_deletion_stay(
    fake_ssh, target, real_git_env, tmp_path
):
    repo = make_pushed_repo(
        fake_ssh,
        tmp_path,
        real_git_env,
        {
            "keep.txt": (b"keep\n", 0o644),
            "olddir/old.txt": (b"old\n", 0o644),
        },
    )
    (repo / "olddir/old.txt").unlink()
    commit(repo, real_git_env)

    completed = push(repo, real_git_env)

    assert completed.returncode == 0, completed.stderr
    assert not target.exists("olddir/old.txt")
    assert (target.path / "olddir").is_dir()
    assert target.read_text("keep.txt") == "keep\n"


def test_drift_is_rejected_with_the_first_ten_paths_and_a_count(
    fake_ssh, target, real_git_env, tmp_path
):
    repo = make_pushed_repo(
        fake_ssh,
        tmp_path,
        real_git_env,
        {"tracked.txt": (b"tracked\n", 0o644)},
    )
    for index in range(12):
        target.write(f"drift-{index:02d}.txt", f"target {index}\n")
    (repo / "tracked.txt").write_text("local change\n", encoding="utf-8")
    commit(repo, real_git_env)
    before = target_tree(target)

    completed = push(repo, real_git_env)

    assert completed.returncode != 0
    assert "target has local changes:" in completed.stderr
    for index in range(10):
        assert f"drift-{index:02d}.txt" in completed.stderr
    assert "drift-10.txt" not in completed.stderr
    assert "and 2 more (12 paths)" in completed.stderr
    assert "remote rejected" in completed.stderr
    assert target_tree(target) == before


def test_a_non_fast_forward_push_sends_gits_rejection_token(
    make_driver, fake_ssh, target, real_git_env, tarssh_env, tmp_path
):
    repo = make_pushed_repo(fake_ssh, tmp_path, real_git_env)
    expected = git(
        ["rev-parse", "refs/remotes/target/main"], repo, real_git_env
    ).stdout.strip()
    tree = git(["rev-parse", "HEAD^{tree}"], repo, real_git_env).stdout.strip()
    unrelated = git(
        ["commit-tree", tree, "-m", "unrelated"],
        repo,
        {**real_git_env, **IDENT},
    ).stdout.strip()
    before = target_tree(target)

    result = make_driver(
        [sys.executable, "-m", "tarssh.remote"],
        remote="target",
        url=fake_ssh.url,
        env=tarssh_env,
        cwd=repo,
    ).run("list for-push", f"push {unrelated}:refs/heads/main", "")

    result.assert_exit(0)
    result.assert_stdout_lines(
        f"{expected} refs/heads/main",
        "",
        "error refs/heads/main non-fast forward",
        "",
    )
    result.assert_stderr_empty()
    assert target_tree(target) == before


def test_dry_run_simulates_the_delta_and_writes_nothing(
    fake_ssh, target, real_git_env, tmp_path
):
    repo = make_pushed_repo(
        fake_ssh,
        tmp_path,
        real_git_env,
        {
            "keep.txt": (b"keep\n", 0o644),
            "delete.txt": (b"gone\n", 0o644),
        },
    )
    (repo / "delete.txt").unlink()
    (repo / "added.txt").write_text("new\n", encoding="utf-8")
    (repo / "keep.txt").write_text("changed\n", encoding="utf-8")
    commit(repo, real_git_env)
    before = target_tree(target)
    remote_before = git(
        ["rev-parse", "refs/remotes/target/main"], repo, real_git_env
    ).stdout.strip()
    calls_before = len(fake_ssh.calls)

    completed = push(repo, real_git_env, "--dry-run")

    assert completed.returncode == 0, completed.stderr
    assert deploy_message(target, 2, 1) in completed.stderr
    assert target_tree(target) == before
    assert (
        git(["rev-parse", "refs/remotes/target/main"], repo, real_git_env).stdout.strip()
        == remote_before
    )
    assert not any(
        call.command.startswith("tar -o -xf") or " rm -f " in call.command
        for call in fake_ssh.calls[calls_before:]
    )
    assert not lock_path(target).exists()


def test_the_lock_is_held_from_list_for_push_through_the_deploy(
    make_driver, fake_ssh, target, real_git_env, tarssh_env, tmp_path
):
    repo = make_pushed_repo(fake_ssh, tmp_path, real_git_env)
    (repo / "a.txt").write_text("changed\n", encoding="utf-8")
    commit(repo, real_git_env)
    remote_oid = git(
        ["rev-parse", "refs/remotes/target/main"], repo, real_git_env
    ).stdout.strip()
    head = git(["rev-parse", "HEAD"], repo, real_git_env).stdout.strip()
    calls_before = len(fake_ssh.calls)

    result = make_driver(
        [sys.executable, "-m", "tarssh.remote"],
        remote="target",
        url=fake_ssh.url,
        env=tarssh_env,
        cwd=repo,
    ).run("list for-push", "push refs/heads/main:refs/heads/main", "")

    result.assert_exit(0)
    result.assert_stdout_lines(
        f"{remote_oid} refs/heads/main",
        "",
        "ok refs/heads/main",
        "",
    )
    assert deploy_message(target, 1, 0) in result.stderr_lines
    commands = [call.command for call in fake_ssh.calls[calls_before:]]
    lock = lock_path(target)
    taken = commands.index(f"mkdir {lock}")
    read = next(
        index
        for index, command in enumerate(commands)
        if command.startswith(f"cd {target.path} && find .")
    )
    extracted = next(
        index
        for index, command in enumerate(commands)
        if command.startswith("tar -o -xf")
    )
    released = commands.index(f"rm -rf {lock}")
    assert taken < read < extracted < released
    assert not lock.exists()
    assert target_tree(target) == head_tree(repo, real_git_env)
    assert (
        git(["rev-parse", "refs/remotes/target/main"], repo, real_git_env).stdout.strip()
        == remote_oid
    )
    assert head != remote_oid


def test_the_lock_is_released_when_git_never_sends_a_push(
    make_driver, fake_ssh, target, real_git_env, tarssh_env, tmp_path
):
    repo = make_pushed_repo(fake_ssh, tmp_path, real_git_env)
    calls_before = len(fake_ssh.calls)

    result = make_driver(
        [sys.executable, "-m", "tarssh.remote"],
        remote="target",
        url=fake_ssh.url,
        env=tarssh_env,
        cwd=repo,
    ).run_input("list for-push\n")

    result.assert_exit(0)
    assert result.stdout_lines[0].endswith(" refs/heads/main")
    assert result.stdout_lines[1] == ""
    commands = [call.command for call in fake_ssh.calls[calls_before:]]
    lock = lock_path(target)
    taken = commands.index(f"mkdir {lock}")
    read = next(
        index
        for index, command in enumerate(commands)
        if command.startswith(f"cd {target.path} && find .")
    )
    released = commands.index(f"rm -rf {lock}")
    assert taken < read < released
    assert not lock.exists()


def test_the_helper_never_writes_the_remote_branch(
    make_driver, fake_ssh, target, real_git_env, tarssh_env, tmp_path
):
    repo = make_pushed_repo(fake_ssh, tmp_path, real_git_env)
    remote_oid = git(
        ["rev-parse", "refs/remotes/target/main"], repo, real_git_env
    ).stdout.strip()
    (repo / "a.txt").write_text("changed\n", encoding="utf-8")
    commit(repo, real_git_env)
    head = git(["rev-parse", "HEAD"], repo, real_git_env).stdout.strip()

    result = make_driver(
        [sys.executable, "-m", "tarssh.remote"],
        remote="target",
        url=fake_ssh.url,
        env=tarssh_env,
        cwd=repo,
    ).run("list for-push", "push refs/heads/main:refs/heads/main", "")

    result.assert_exit(0)
    result.assert_stdout_lines(
        f"{remote_oid} refs/heads/main", "", "ok refs/heads/main", ""
    )
    assert (
        git(["rev-parse", "refs/remotes/target/main"], repo, real_git_env).stdout.strip()
        == remote_oid
    )
    assert head != remote_oid
    assert target_tree(target) == head_tree(repo, real_git_env)


def test_added_paths_are_archived_in_chunks_below_arg_max(
    fake_ssh, target, real_git_env, tmp_path
):
    repo = make_pushed_repo(fake_ssh, tmp_path, real_git_env)
    for index in range(501):
        path = repo / f"bulk/file-{index:03d}.txt"
        path.parent.mkdir(exist_ok=True)
        path.write_text(f"{index}\n", encoding="utf-8")
    commit(repo, real_git_env)
    calls_before = len(fake_ssh.calls)

    completed = push(repo, real_git_env)

    assert completed.returncode == 0, completed.stderr
    assert deploy_message(target, 501, 0) in completed.stderr
    extractions = [
        call
        for call in fake_ssh.calls[calls_before:]
        if call.command.startswith("tar -o -xf")
    ]
    assert len(extractions) == 2
    assert target.read_text("bulk/file-500.txt") == "500\n"


def test_deleted_paths_are_removed_in_chunks_below_arg_max(
    fake_ssh, target, real_git_env, tmp_path
):
    repo = make_pushed_repo(
        fake_ssh,
        tmp_path,
        real_git_env,
        {f"bulk/file-{index:03d}.txt": (f"{index}\n".encode(), 0o644) for index in range(501)},
    )
    for index in range(501):
        (repo / f"bulk/file-{index:03d}.txt").unlink()
    commit(repo, real_git_env)
    calls_before = len(fake_ssh.calls)

    completed = push(repo, real_git_env)

    assert completed.returncode == 0, completed.stderr
    assert deploy_message(target, 0, 501) in completed.stderr
    removals = [
        call for call in fake_ssh.calls[calls_before:] if " rm -f " in call.command
    ]
    assert len(removals) == 2
    assert not target.exists("bulk/file-000.txt")
    assert (target.path / "bulk").is_dir()
