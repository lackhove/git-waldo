"""Fixtures shared by the tarssh protocol tests."""

from __future__ import annotations

import shlex
import sys
from pathlib import Path

import pytest
from harness import DEFAULT_STUB_OID, FakeSSH, ProtocolDriver, Target


@pytest.fixture
def target(tmp_path):
    """A fake target directory, cleaned up and permission-restored per test."""
    fake = Target(tmp_path / "target")
    yield fake
    fake.restore()


@pytest.fixture
def fake_ssh(target, tmp_path):
    """The SSH seam; pass ``fake_ssh.env()`` to the helper under test."""
    return FakeSSH(target, tmp_path / "fake-ssh")


@pytest.fixture
def stub_helper():
    """The in-test helper executable, replaced by the real one in ticket 02."""
    return Path(__file__).with_name("stub_helper.py")


@pytest.fixture
def stub_command(stub_helper):
    """Argv that starts the in-test helper without relying on PATH."""
    return [sys.executable, str(stub_helper)]


@pytest.fixture
def stub_oid():
    return DEFAULT_STUB_OID


@pytest.fixture
def helper_env(fake_ssh):
    """Environment that makes a helper's ``ssh`` calls reach the fake target."""
    return fake_ssh.env()


@pytest.fixture
def make_driver(fake_ssh, stub_command):
    """Build a protocol driver for any executable; defaults to the stub helper."""

    def make(command=None, **kwargs):
        if command is None:
            command = stub_command
        kwargs.setdefault("env", fake_ssh.env())
        kwargs.setdefault("url", fake_ssh.url)
        return ProtocolDriver(command, **kwargs)

    return make


@pytest.fixture
def driver(make_driver):
    """The stub helper behind git's protocol command lines."""
    return make_driver()


@pytest.fixture
def git_env(fake_ssh, stub_command):
    """Environment for real git: ``git-remote-tarssh`` resolves to the stub."""
    return fake_ssh.env({"TARSSH_HELPER": shlex.join(stub_command)})
