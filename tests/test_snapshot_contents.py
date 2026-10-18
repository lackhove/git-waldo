"""Snapshots of real target contents: fence, modes, symlinks and refusals."""

from __future__ import annotations

import os
import socket
import stat
import subprocess
import sys

import pytest

IDENT = {
    "GIT_AUTHOR_NAME": "operator",
    "GIT_AUTHOR_EMAIL": "operator@example.com",
    "GIT_COMMITTER_NAME": "operator",
    "GIT_COMMITTER_EMAIL": "operator@example.com",
}


def _git(repo, *args, env=None, data=None, check=True):
    payload = data.encode() if isinstance(data, str) else data
    completed = subprocess.run(
        ["git", *args],
        cwd=repo,
        input=payload,
        capture_output=True,
        env=env,
        check=False,
    )
    if check and completed.returncode != 0:
        stderr = completed.stderr
        if isinstance(stderr, bytes):
            stderr = stderr.decode("utf-8", "replace")
        raise AssertionError(f"git {' '.join(args)} failed: {stderr}")
    return completed


def _init_repo(tmp_path, env):
    repo = tmp_path / "repo"
    _git(tmp_path, "init", "-q", "-b", "main", str(repo), env=env)
    return repo


def _list(make_driver, url, env, repo, *, remote="origin"):
    return make_driver(
        [sys.executable, "-m", "tarssh.remote"],
        remote=remote,
        url=url,
        env=env,
        cwd=repo,
    ).list()


def _oid(result):
    result.assert_exit(0)
    assert result.stderr_lines == []
    assert result.stdout_lines[0] == "@refs/heads/main HEAD"
    oid, ref = result.stdout_lines[1].split(" ")
    assert ref == "refs/heads/main"
    assert len(oid) == 40
    return oid


def _ls_tree(repo, rev, env):
    """Map path bytes to (mode, blob oid) for every tracked path."""
    completed = _git(repo, "ls-tree", "-r", "-z", rev, env=env)
    entries = {}
    for record in completed.stdout.split(b"\0"):
        if not record:
            continue
        metadata, path = record.split(b"\t", 1)
        mode, kind, oid = metadata.split(b" ")
        assert kind == b"blob"
        entries[path] = (mode.decode(), oid.decode())
    return entries


def _blob(repo, oid, env):
    return _git(repo, "cat-file", "blob", oid, env=env).stdout


def _commit_objects(repo, env):
    completed = _git(
        repo,
        "cat-file",
        "--batch-all-objects",
        "--batch-check=%(objecttype)",
        env=env,
    )
    return sum(1 for line in completed.stdout.splitlines() if line == b"commit")


def _base_commit(repo, env, fence: str):
    blob = _git(repo, "hash-object", "-w", "--stdin", env=env, data=fence.encode())
    tree = _git(
        repo,
        "mktree",
        env=env,
        data=f"100644 blob {blob.stdout.strip().decode()}\t.gitignore\n",
    )
    return (
        _git(
            repo,
            "commit-tree",
            tree.stdout.strip().decode(),
            "-m",
            "base",
            env={**env, **IDENT},
        )
        .stdout.strip()
        .decode()
    )


def test_snapshot_carries_files_across_directories_symlinks_and_modes(
    make_driver, fake_ssh, target, tarssh_env, tmp_path
):
    target.create()
    regular = {
        "settings.yaml": b"application:\n",
        "nested/scripts/night.yaml": b"alias: night\n\x00binary-ish\n",
        "nested/with space.txt": b"spaces survive\n",
        "unicod\u00e9.txt": b"unicode name\n",
    }
    target.populate(regular)
    target.write("bin/run.sh", b"#!/bin/sh\nexit 0\n", mode=0o755)
    target.write("bin/read.sh", b"#!/bin/sh\necho hi\n", mode=0o644)
    target.symlink("current", "nested/scripts/night.yaml")
    target.symlink("scripts-link", "nested/scripts")
    target.mkdir("empty")
    target.mkdir("empty/nested")
    repo = _init_repo(tmp_path, tarssh_env)

    result = _list(make_driver, fake_ssh.url, tarssh_env, repo)
    oid = _oid(result)
    tree = _ls_tree(repo, oid, tarssh_env)

    expected = {
        "settings.yaml": "100644",
        "nested/scripts/night.yaml": "100644",
        "nested/with space.txt": "100644",
        "unicod\u00e9.txt": "100644",
        "bin/run.sh": "100755",
        "bin/read.sh": "100644",
        "current": "120000",
        "scripts-link": "120000",
    }
    assert {path.decode(): mode for path, (mode, _) in tree.items()} == expected

    for name, content in regular.items():
        mode, blob = tree[name.encode()]
        assert mode == "100644"
        assert _blob(repo, blob, tarssh_env) == content
    assert _blob(repo, tree[b"bin/run.sh"][1], tarssh_env) == b"#!/bin/sh\nexit 0\n"
    assert (
        _blob(repo, tree[b"current"][1], tarssh_env)
        == (target.path / "current").readlink().as_posix().encode()
    )
    assert (
        _blob(repo, tree[b"scripts-link"][1], tarssh_env)
        == (target.path / "scripts-link").readlink().as_posix().encode()
    )
    assert all(b"empty" not in path for path in tree)
    assert fake_ssh.forbidden == []

    commands = [call.command for call in fake_ssh.calls]
    assert any("find ." in command and "-type f" in command for command in commands)
    assert any("tar -cf - -T -" in command for command in commands)


def test_target_gitignore_is_the_fence_only_when_no_local_fence_exists(
    make_driver, fake_ssh, target, tarssh_env, tmp_path
):
    target.create()
    target.write(".gitignore", b"secret.txt\nruntime/\n")
    target.populate(
        {
            "settings.yaml": b"application:\n",
            "secret.txt": b"token: hunter2\n",
            "runtime/state.json": b'{"state": "on"}\n',
        }
    )
    repo = _init_repo(tmp_path, tarssh_env)

    first = _list(make_driver, fake_ssh.url, tarssh_env, repo)
    oid = _oid(first)
    tree = _ls_tree(repo, oid, tarssh_env)
    assert {path.decode() for path in tree} == {".gitignore", "settings.yaml"}

    _git(repo, "update-ref", "refs/remotes/origin/main", oid, env=tarssh_env)
    commits = _commit_objects(repo, tarssh_env)

    target.write("secret.txt", b"token: rotated\n")
    target.write("runtime/state.json", b'{"state": "off"}\n')
    second = _list(make_driver, fake_ssh.url, tarssh_env, repo)

    assert _oid(second) == oid
    assert (
        _git(repo, "rev-parse", "refs/remotes/origin/main", env=tarssh_env).stdout.strip().decode()
        == oid
    )
    assert _commit_objects(repo, tarssh_env) == commits


def test_a_remote_branch_fence_hides_paths_not_ignored_at_head(
    make_driver, fake_ssh, target, tarssh_env, tmp_path
):
    target.create()
    target.write(".gitignore", b"head-secret.txt\n")
    target.populate(
        {
            "visible.txt": b"visible\n",
            "remote-secret.txt": b"remote secret\n",
            "head-secret.txt": b"head secret\n",
        }
    )
    repo = _init_repo(tmp_path, tarssh_env)
    base = _base_commit(repo, tarssh_env, "remote-secret.txt\n")
    _git(repo, "update-ref", "refs/remotes/origin/main", base, env=tarssh_env)

    result = _list(make_driver, fake_ssh.url, tarssh_env, repo)
    oid = _oid(result)
    tree = _ls_tree(repo, oid, tarssh_env)

    assert {path.decode() for path in tree} == {
        ".gitignore",
        "visible.txt",
        "head-secret.txt",
    }
    commit = _git(repo, "cat-file", "commit", oid, env=tarssh_env).stdout.decode()
    assert f"parent {base}" in commit


def test_a_head_fence_hides_paths_not_ignored_at_the_remote_branch(
    make_driver, fake_ssh, target, tarssh_env, tmp_path
):
    target.create()
    target.write(".gitignore", b"remote-secret.txt\n")
    target.populate(
        {
            "visible.txt": b"visible\n",
            "remote-secret.txt": b"remote secret\n",
            "head-secret.txt": b"head secret\n",
        }
    )
    repo = _init_repo(tmp_path, tarssh_env)
    base = _base_commit(repo, tarssh_env, "head-secret.txt\n")
    _git(repo, "update-ref", "refs/heads/main", base, env=tarssh_env)

    result = _list(make_driver, fake_ssh.url, tarssh_env, repo)
    oid = _oid(result)
    tree = _ls_tree(repo, oid, tarssh_env)

    assert {path.decode() for path in tree} == {
        ".gitignore",
        "visible.txt",
        "remote-secret.txt",
    }
    commit = _git(repo, "cat-file", "commit", oid, env=tarssh_env).stdout.decode()
    assert "parent " not in commit


def test_both_local_fences_hide_their_own_paths(
    make_driver, fake_ssh, target, tarssh_env, tmp_path
):
    target.create()
    target.populate(
        {
            "visible.txt": b"visible\n",
            "remote-secret.txt": b"remote secret\n",
            "head-secret.txt": b"head secret\n",
        }
    )
    repo = _init_repo(tmp_path, tarssh_env)
    remote_base = _base_commit(repo, tarssh_env, "remote-secret.txt\n")
    _git(repo, "update-ref", "refs/remotes/origin/main", remote_base, env=tarssh_env)
    head_base = _base_commit(repo, tarssh_env, "head-secret.txt\n")
    _git(repo, "update-ref", "refs/heads/main", head_base, env=tarssh_env)

    result = _list(make_driver, fake_ssh.url, tarssh_env, repo)
    tree = _ls_tree(repo, _oid(result), tarssh_env)

    assert {path.decode() for path in tree} == {"visible.txt"}


def test_a_negation_cannot_reinclude_a_file_under_an_ignored_directory(
    make_driver, fake_ssh, target, tarssh_env, tmp_path
):
    target.create()
    target.write(".gitignore", b"runtime/\n!.gitignore\n")
    target.populate(
        {
            "visible.txt": b"visible\n",
            "runtime/.gitignore": b"",
            "runtime/state.json": b'{"state": "on"}\n',
        }
    )
    repo = _init_repo(tmp_path, tarssh_env)
    base = _base_commit(repo, tarssh_env, "runtime/\n!.gitignore\n")
    _git(repo, "update-ref", "refs/heads/main", base, env=tarssh_env)

    result = _list(make_driver, fake_ssh.url, tarssh_env, repo)
    tree = _ls_tree(repo, _oid(result), tarssh_env)

    assert {path.decode() for path in tree} == {".gitignore", "visible.txt"}


def test_a_changed_target_is_parented_on_the_existing_remote_branch(
    make_driver, fake_ssh, target, tarssh_env, tmp_path
):
    target.create()
    target.populate({"one.txt": b"one\n"})
    repo = _init_repo(tmp_path, tarssh_env)
    first = _oid(_list(make_driver, fake_ssh.url, tarssh_env, repo))
    _git(repo, "update-ref", "refs/remotes/origin/main", first, env=tarssh_env)

    target.write("two.txt", b"two\n")
    second = _oid(_list(make_driver, fake_ssh.url, tarssh_env, repo))

    assert second != first
    commit = _git(repo, "cat-file", "commit", second, env=tarssh_env).stdout.decode()
    assert f"parent {first}" in commit
    assert {path.decode() for path in _ls_tree(repo, second, tarssh_env)} == {
        "one.txt",
        "two.txt",
    }


def test_empty_directories_are_ignored(make_driver, fake_ssh, target, tarssh_env, tmp_path):
    target.create()
    target.mkdir("empty")
    target.mkdir("empty/deeper")
    target.populate({"file.txt": b"content\n"})
    repo = _init_repo(tmp_path, tarssh_env)

    result = _list(make_driver, fake_ssh.url, tarssh_env, repo)

    assert {path.decode() for path in _ls_tree(repo, _oid(result), tarssh_env)} == {"file.txt"}


def _assert_refused(make_driver, fake_ssh, tarssh_env, repo, expected):
    result = _list(make_driver, fake_ssh.url, tarssh_env, repo)
    assert result.exit_code != 0
    assert result.stdout == ""
    assert expected in result.stderr
    assert "cannot represent target path" in result.stderr


def test_a_fifo_is_refused_by_name(make_driver, fake_ssh, target, tarssh_env, tmp_path):
    target.create()
    target.populate({"visible.txt": b"visible\n"})
    os.mkfifo(target.path / "pipe")
    repo = _init_repo(tmp_path, tarssh_env)

    _assert_refused(make_driver, fake_ssh, tarssh_env, repo, "pipe")


def test_a_socket_is_refused_by_name(make_driver, fake_ssh, target, tarssh_env, tmp_path):
    target.create()
    target.populate({"visible.txt": b"visible\n"})
    server = socket.socket(socket.AF_UNIX)
    try:
        server.bind(str(target.path / "service.sock"))
        repo = _init_repo(tmp_path, tarssh_env)
        _assert_refused(make_driver, fake_ssh, tarssh_env, repo, "service.sock")
    finally:
        server.close()


def test_a_device_node_is_refused_by_name(make_driver, fake_ssh, target, tarssh_env, tmp_path):
    target.create()
    target.populate({"visible.txt": b"visible\n"})
    try:
        os.mknod(target.path / "device", stat.S_IFCHR | 0o600, os.makedev(1, 3))
    except (PermissionError, OSError):
        pytest.skip("creating device nodes needs CAP_MKNOD")
    repo = _init_repo(tmp_path, tarssh_env)

    _assert_refused(make_driver, fake_ssh, tarssh_env, repo, "device")


@pytest.mark.skipif(os.geteuid() == 0, reason="root ignores permission bits")
def test_an_unreadable_file_is_refused_by_name(make_driver, fake_ssh, target, tarssh_env, tmp_path):
    target.create()
    target.populate({"visible.txt": b"visible\n", "secret.txt": b"secret\n"})
    target.make_unreadable("secret.txt")
    repo = _init_repo(tmp_path, tarssh_env)

    result = _list(make_driver, fake_ssh.url, tarssh_env, repo)

    assert result.exit_code != 0
    assert result.stdout == ""
    assert "secret.txt" in result.stderr


def test_a_non_utf8_name_is_refused_by_name(make_driver, fake_ssh, target, tarssh_env, tmp_path):
    target.create()
    target.populate({"visible.txt": b"visible\n"})
    raw_name = b"bad-\xff.txt"
    path = os.fsencode(target.path) + b"/" + raw_name
    descriptor = os.open(path, os.O_CREAT | os.O_WRONLY, 0o644)
    try:
        os.write(descriptor, b"nope\n")
    finally:
        os.close(descriptor)
    repo = _init_repo(tmp_path, tarssh_env)

    result = _list(make_driver, fake_ssh.url, tarssh_env, repo)

    assert result.exit_code != 0
    assert result.stdout == ""
    assert "bad-" in result.stderr
    assert "UTF-8" in result.stderr
