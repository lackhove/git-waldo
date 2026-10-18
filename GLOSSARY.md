# Sync tool

A git remote helper that makes a host with no git a first-class git remote, plus the conventions that keep a shipped config both reviewable and recoverable.

## Language

**Target**:
The filesystem tree on the remote host that the tool treats as a git working tree.
_Avoid_: Remote, server, the host, the host OS

**Config repo**:
The repository whose tracked files are deployed to the target.
_Avoid_: Mirror repo, config mirror

**Tool repo**:
The repository holding the helper and its docs. There is exactly one per config repo's target.

**Snapshot**:
A commit built from the target's working tree, recording the target's state without a human authoring it.
_Avoid_: Remote commit, mirror commit, sync commit

**Remote branch**:
The reference recording the target state the config repo last saw, named after the target.
_Avoid_: Shadow branch, snapshot ref

**Clean target**:
A target whose working tree is identical to the remote branch's tree. The precondition for pushing.
_Avoid_: In sync, matching

**Target drift**:
Any difference between the target's working tree and the remote branch.
_Avoid_: Dirty remote, conflict, divergence

**Furniture**:
A file tracked in the config repo that the application on the target does not read, yet deploys like any other file.
_Avoid_: Metadata, tooling file

**Remote helper**:
The executable git invokes for a transport it cannot handle itself. git finds it as `git-remote-<scheme>`; ours is `git-remote-tarssh`.
_Avoid_: Transport plugin, driver

**Fence**:
The `.gitignore` tracked in the config repo. It decides which target paths the tool may read or write, and it is the only thing separating synced configuration from runtime state and secrets.
_Avoid_: Exclude list, filter, allowlist

**Target descriptor**:
The gitignored `.tarssh.toml` in the config repo, recording user, host, SSH port and directory for the target. Committed as `.tarssh.example.toml`; overridden by the remote URL, then by `TARSSH_*` variables.
_Avoid_: Config file, settings, target config

**Delta**:
The paths added, modified or removed between the remote branch and the pushed commit. A push touches exactly these paths and nothing else.
_Avoid_: Changeset, patch, diff

**Deploy**:
Writing a pushed commit's delta into the target's working tree.
_Avoid_: Upload, sync down
