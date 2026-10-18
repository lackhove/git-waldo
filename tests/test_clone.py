"""End-to-end git behaviour against the fake target through the real helper."""

from __future__ import annotations

import subprocess
import sys

EMPTY_TREE = "4b825dc642cb6eb9a060e54bf8d69288fbee4904"


def _git(args, cwd, env, *, check=True):
    completed = subprocess.run(
        ["git", *args],
        cwd=cwd,
        text=True,
        capture_output=True,
        env=env,
        check=False,
    )
    if check and completed.returncode != 0:
        raise AssertionError(f"git {' '.join(args)} failed: {completed.stderr}")
    return completed


def test_clone_of_an_empty_target_creates_the_snapshot_on_main(
    fake_ssh, target, real_git_env, tmp_path
):
    target.create()
    clone = tmp_path / "clone"

    completed = _git(
        ["clone", fake_ssh.url, str(clone)], tmp_path, real_git_env, check=False
    )

    assert completed.returncode == 0, completed.stderr
    head = _git(["rev-parse", "HEAD"], clone, real_git_env).stdout.strip()
    commit = _git(["cat-file", "commit", head], clone, real_git_env).stdout
    assert "author tarssh <tarssh@localhost>" in commit
    assert f"snapshot of {fake_ssh.host}:{target.path}" in commit
    assert _git(["rev-parse", "HEAD^{tree}"], clone, real_git_env).stdout.strip() == EMPTY_TREE
    assert (
        _git(["rev-parse", "refs/remotes/origin/main"], clone, real_git_env).stdout.strip()
        == head
    )
    assert "?" not in completed.stdout


def test_clone_uses_the_descriptor_only_url_with_environment_overrides(
    fake_ssh, target, real_git_env, tmp_path
):
    target.create()
    env = dict(real_git_env)
    env.update(TARSSH_HOST=fake_ssh.host, TARSSH_DIR=str(target.path))
    clone = tmp_path / "clone-descriptor"

    completed = _git(["clone", "tarssh::", str(clone)], tmp_path, env, check=False)

    assert completed.returncode == 0, completed.stderr
    head = _git(["rev-parse", "HEAD"], clone, real_git_env).stdout.strip()
    assert (
        _git(["rev-parse", "HEAD^{tree}"], clone, real_git_env).stdout.strip() == EMPTY_TREE
    )
    assert len(head) == 40


def test_ls_remote_outside_a_repository_prints_the_real_oid_and_symref(
    fake_ssh, target, real_git_env, tmp_path
):
    target.create()

    completed = _git(
        ["ls-remote", "--symref", fake_ssh.url], tmp_path, real_git_env, check=False
    )

    assert completed.returncode == 0, completed.stderr
    lines = completed.stdout.splitlines()
    oid_line = next(line for line in lines if line.endswith("\trefs/heads/main"))
    oid, _ = oid_line.split("\t")
    assert len(oid) == 40
    assert all(character in "0123456789abcdef" for character in oid)
    assert "ref: refs/heads/main\tHEAD" in lines
    assert "?" not in completed.stdout


def test_fetch_records_the_remote_branch_and_a_repeat_fetch_does_not_move_it(
    fake_ssh, target, real_git_env, tmp_path
):
    target.create()
    repo = tmp_path / "repo"
    _git(["init", "-q", str(repo)], tmp_path, real_git_env)
    _git(["remote", "add", "origin", fake_ssh.url], repo, real_git_env)

    first = _git(["fetch", "origin"], repo, real_git_env, check=False)

    assert first.returncode == 0, first.stderr
    oid = _git(["rev-parse", "refs/remotes/origin/main"], repo, real_git_env).stdout.strip()
    assert len(oid) == 40
    assert "?" not in first.stdout

    second = _git(["fetch", "origin"], repo, real_git_env, check=False)

    assert second.returncode == 0, second.stderr
    assert (
        _git(["rev-parse", "refs/remotes/origin/main"], repo, real_git_env).stdout.strip()
        == oid
    )


def test_descriptor_only_url_reaches_the_helper_through_git(
    fake_ssh, target, real_git_env, tmp_path
):
    target.create()
    repo = tmp_path / "repo"
    _git(["init", "-q", str(repo)], tmp_path, real_git_env)
    (repo / ".tarssh.toml").write_text(
        "\n".join(
            [
                'user = "root"',
                f'host = "{fake_ssh.host}"',
                'ssh_port = 22222',
                f'dir = "{target.path}"',
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    _git(["remote", "add", "origin", "tarssh::"], repo, real_git_env)

    completed = _git(["ls-remote", "origin"], repo, real_git_env, check=False)

    assert completed.returncode == 0, completed.stderr
    assert "\trefs/heads/main" in completed.stdout
    call = fake_ssh.calls[-1]
    assert (call.host, call.user, call.port) == ("fake-target", "root", 22222)


def test_a_bare_tarssh_colon_never_reaches_the_helper(
    fake_ssh, real_git_env, tmp_path
):
    completed = _git(["ls-remote", "tarssh:"], tmp_path, real_git_env, check=False)

    assert completed.returncode != 0
    assert "not a tarssh helper URL" not in completed.stderr


def test_a_sha256_repository_is_a_startup_error_naming_both_formats(
    make_driver, fake_ssh, target, tarssh_env, tmp_path
):
    target.create()
    repo = tmp_path / "sha256"
    subprocess.run(
        ["git", "init", "-q", "--object-format=sha256", str(repo)], check=True
    )

    result = make_driver(
        [sys.executable, "-m", "tarssh.remote"],
        url=fake_ssh.url,
        env=tarssh_env,
        cwd=repo,
    ).capabilities()

    assert result.exit_code != 0
    assert result.stdout == ""
    assert "sha1" in result.stderr
    assert "sha256" in result.stderr
