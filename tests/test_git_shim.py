"""git finds the helper through the PATH shim, exactly as after installation."""

from __future__ import annotations

import subprocess


def _run_shim(fake_ssh, env, stdin: str, *args: str):
    return subprocess.run(
        [str(fake_ssh.client_bin / "git-remote-waldo"), *args],
        input=stdin,
        text=True,
        capture_output=True,
        env=env,
        check=False,
    )


def test_shim_runs_the_configured_helper(fake_ssh, git_env, stub_oid):
    completed = _run_shim(fake_ssh, git_env, "list\n", "origin", fake_ssh.url)

    assert completed.returncode == 0
    assert completed.stdout.splitlines() == [
        "@refs/heads/main HEAD",
        f"{stub_oid} refs/heads/main",
        "",
    ]
    assert completed.stderr == ""


def test_shim_can_run_a_module(fake_ssh, git_env, tmp_path):
    module = tmp_path / "probe_helper.py"
    module.write_text(
        "import sys\nprint('module helper', *sys.argv[1:])\n",
        encoding="utf-8",
    )
    env = dict(git_env)
    env["WALDO_HELPER"] = "module:probe_helper"
    env["PYTHONPATH"] = str(tmp_path)

    completed = _run_shim(fake_ssh, env, "", "origin", "waldo://fake-target/target")

    assert completed.returncode == 0
    assert completed.stdout == "module helper origin waldo://fake-target/target\n"


def test_shim_without_a_helper_names_the_missing_variable(fake_ssh, git_env):
    env = dict(git_env)
    env.pop("WALDO_HELPER")

    completed = _run_shim(fake_ssh, env, "list\n", "origin", fake_ssh.url)

    assert completed.returncode != 0
    assert "WALDO_HELPER" in completed.stderr


def test_real_git_discovers_the_shim_and_lists_refs(fake_ssh, git_env, stub_oid, tmp_path):
    completed = subprocess.run(
        ["git", "ls-remote", fake_ssh.url],
        text=True,
        capture_output=True,
        env=git_env,
        cwd=tmp_path,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    assert f"{stub_oid}\trefs/heads/main" in completed.stdout
    assert "?" not in completed.stdout
    assert fake_ssh.forbidden == []
