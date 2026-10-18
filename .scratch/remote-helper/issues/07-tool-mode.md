# 07: Tool mode: `--config` and `--version`

**What to build:** The non-protocol surface of the same executable. `--version` prints the tool version. `--config` interactively writes `.tarssh.toml` at the config repository root, refuses to clobber an existing file without confirmation, and registers the `target` remote as `tarssh::` when no such remote exists. A leading `-` in the first argument always means a verb, never a remote name.

**Blocked by:** 02 — Walking skeleton: clone an empty target

**Status:** ready-for-agent

- [ ] `git-remote-tarssh --version` prints the tool version and exits 0.
- [ ] `--config` writes `user`, `host`, `ssh_port`, and `dir` to `.tarssh.toml` at the repository root.
- [ ] An existing `.tarssh.toml` is not overwritten without explicit confirmation.
- [ ] When no `target` remote exists, `--config` adds it as `tarssh::`; when one exists, it is left untouched and the operator is told.
- [ ] A leading `-` in the first argument is always treated as a verb, never as a remote name.
- [ ] Running outside a git repository fails clearly.
- [ ] Tests use the harness or direct CLI invocation and never contact a live target.
