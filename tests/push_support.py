"""Helpers for driving real git pushes against the fake target."""

from __future__ import annotations

import hashlib
import os
import subprocess
from pathlib import Path

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


def commit(repo, env, message="change"):
    git(["add", "-A"], repo, env)
    git(["commit", "-q", "-m", message], repo, {**env, **IDENT})


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
