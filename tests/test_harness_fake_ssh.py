"""The SSH seam must behave like a busybox-only host and fail loudly otherwise."""

from __future__ import annotations

import os
import shlex
import subprocess

import pytest


def _quote(path) -> str:
    return shlex.quote(str(path))


def test_allowed_busybox_commands_run_against_the_target(fake_ssh, target):
    target.populate({"a.txt": "hello\n", "nested/b.txt": "world\n"})

    result = fake_ssh.run_remote(f"cd {_quote(target.path)} && find . -type f -print")

    assert result.returncode == 0
    assert sorted(result.stdout.splitlines()) == ["./a.txt", "./nested/b.txt"]
    assert result.stderr == ""
    assert fake_ssh.forbidden == []
    assert fake_ssh.calls[-1].command.startswith("cd ")


def test_command_outside_the_busybox_set_fails_naming_it(fake_ssh):
    result = fake_ssh.run_remote("git status")

    assert result.returncode != 0
    assert "git" in result.stderr
    assert [item.reason for item in fake_ssh.forbidden] == ["command not available: git"]


@pytest.mark.parametrize(
    ("command", "option"),
    [
        ("tar --sort=name -cf - .", "--sort"),
        ("find . -printf '%p\\n'", "-printf"),
        ("rm --preserve-root .", "--preserve-root"),
    ],
)
def test_option_outside_the_busybox_set_fails_naming_it(fake_ssh, target, command, option):
    target.populate({"a.txt": "x"})

    result = fake_ssh.run_remote(f"cd {_quote(target.path)} && {command}")

    assert result.returncode != 0
    assert option in result.stderr
    assert any(option in item.reason for item in fake_ssh.forbidden)


def test_sftp_subsystem_is_refused_loudly(fake_ssh):
    result = fake_ssh.run_ssh("-s", "fake-target", "sftp")

    assert result.returncode == 255
    assert "SFTP" in result.stderr
    assert any("SFTP" in item.reason for item in fake_ssh.forbidden)


def test_scp_and_rsync_are_refused_loudly(fake_ssh, tmp_path):
    for tool in ("scp", "rsync"):
        result = fake_ssh.run_client(tool, "x", "fake-target:/tmp/x")
        assert result.returncode != 0
        assert tool in result.stderr
        assert any(tool in item.reason for item in fake_ssh.forbidden)


def test_ssh_connection_failure_is_simulatable_and_reversible(fake_ssh, target):
    target.populate({"a.txt": "x"})
    fake_ssh.fail_connection()

    failed = fake_ssh.run_remote(f"find {_quote(target.path)} -type f")

    assert failed.returncode == 255
    assert "Connection refused" in failed.stderr
    assert "fake-target" in failed.stderr

    fake_ssh.restore()
    recovered = fake_ssh.run_remote(f"find {_quote(target.path)} -type f")
    assert recovered.returncode == 0
    assert recovered.stdout.strip() == str(target.path / "a.txt")


def test_extraction_failure_is_simulatable(fake_ssh, target):
    target.populate({"a.txt": "x"})
    fake_ssh.fail_extraction()

    result = fake_ssh.run_remote(f"tar -o -xf - -C {_quote(target.path)}", data="")

    assert result.returncode != 0
    assert "extract" in result.stderr.lower()
    assert any(item.kind == "extraction" for item in fake_ssh.failures)


def test_removal_failure_is_simulatable_without_breaking_the_lock_release(fake_ssh, target):
    target.populate({"a.txt": "x"})
    fake_ssh.fail_removal()

    failed = fake_ssh.run_remote(f"cd {_quote(target.path)} && rm -f ./a.txt")

    assert failed.returncode != 0
    assert "deletion failed" in failed.stderr
    assert any(item.kind == "removal" for item in fake_ssh.failures)
    assert target.exists("a.txt")

    released = fake_ssh.run_remote(f"rm -rf {_quote(target.path)}/lock")
    assert released.returncode == 0


def test_missing_target_fails_in_the_target_command(fake_ssh):
    target = fake_ssh.target
    target.remove()

    result = fake_ssh.run_remote(f"find {_quote(target.path)} -type f")

    assert result.returncode != 0
    assert str(target.path) in result.stderr
    assert fake_ssh.forbidden == []


@pytest.mark.skipif(os.geteuid() == 0, reason="root ignores permission bits")
def test_unreadable_target_fails_in_the_target_command(fake_ssh, target):
    target.populate({"a.txt": "x"})
    target.make_unreadable()

    result = fake_ssh.run_remote(f"find {_quote(target.path)} -type f")

    assert result.returncode != 0
    assert "Permission denied" in result.stderr
    assert str(target.path) in result.stderr


def test_ssh_calls_are_recorded(fake_ssh, target):
    fake_ssh.run_remote("find . -type f")

    call = fake_ssh.calls[-1]
    assert call.host == "fake-target"
    assert call.port == 22
    assert call.command == "find . -type f"
    assert call.returncode == 0


def test_remote_path_contains_only_the_busybox_commands(fake_ssh):
    result = fake_ssh.run_remote("printf '%s\\n' \"$PATH\"")

    assert result.returncode == 0
    entries = result.stdout.strip().split(":")
    assert len(entries) == 1
    assert entries[0] == str(fake_ssh.target_bin)
    assert sorted(path.name for path in fake_ssh.target_bin.iterdir()) == [
        "find",
        "mkdir",
        "rm",
        "sha1sum",
        "tar",
        "xargs",
    ]


def test_shell_builtins_still_work_on_the_target(fake_ssh, target):
    target.populate({"a.txt": "x"})

    result = fake_ssh.run_remote(f"cd {_quote(target.path)} && pwd && test -f a.txt")

    assert result.returncode == 0
    assert result.stdout.strip() == str(target.path)


def test_every_busybox_command_is_available(fake_ssh, target):
    target.populate({"a.txt": "x\n"})
    quoted = _quote(target.path)

    commands = [
        f"mkdir -p {quoted}/new",
        f"rm -f {quoted}/absent",
        f"sha1sum {quoted}/a.txt",
        f"cd {quoted} && printf './a.txt\\n' | xargs rm -f",
        f"cd {quoted} && tar -cf - . > /dev/null",
        f"find {quoted} -type f -print",
    ]
    for command in commands:
        result = fake_ssh.run_remote(command)
        assert result.returncode == 0, (command, result.stderr)
    assert fake_ssh.forbidden == []


def test_a_child_process_finds_the_ssh_shim_through_path(fake_ssh, target):
    target.populate({"a.txt": "x"})

    completed = subprocess.run(
        ["ssh", fake_ssh.host, f"find {_quote(target.path)} -type f"],
        capture_output=True,
        text=True,
        env=fake_ssh.env(),
        check=False,
    )

    assert completed.returncode == 0
    assert completed.stdout.strip() == str(target.path / "a.txt")


def test_the_remote_command_cannot_widen_path(fake_ssh):
    result = fake_ssh.run_remote("export PATH=/usr/bin:/bin; git status")

    assert result.returncode != 0
    assert "git" in result.stderr
    assert any(item.reason == "command not available: git" for item in fake_ssh.forbidden)


def test_ssh_options_are_parsed_and_recorded(fake_ssh):
    result = fake_ssh.run_ssh("-p", "22222", "-o", "BatchMode=yes", "user@fake-target", "true")

    assert result.returncode == 0
    call = fake_ssh.calls[-1]
    assert call.host == "fake-target"
    assert call.user == "user"
    assert call.port == 22222
