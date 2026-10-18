"""The fake target is a real directory that tests may populate and break."""

from __future__ import annotations


def test_target_can_be_created_populated_read_and_removed(target):
    target.create()
    target.populate(
        {
            "settings.yaml": "application:\n",
            "scripts/night.yaml": b"alias: night\n",
        }
    )

    assert target.path.is_dir()
    assert target.read_text("settings.yaml") == "application:\n"
    assert target.read("scripts/night.yaml") == b"alias: night\n"
    assert target.exists("scripts/night.yaml")

    target.empty()
    assert target.path.is_dir()
    assert list(target.path.iterdir()) == []

    target.remove()
    assert not target.path.exists()


def test_target_can_make_a_path_unreadable_and_restore_it(target):
    target.create()
    target.populate({"secret.yaml": "token: hunter2\n"})

    target.make_unreadable("secret.yaml")

    assert (target.path / "secret.yaml").stat().st_mode & 0o777 == 0
    target.restore()
    assert target.read_text("secret.yaml") == "token: hunter2\n"
