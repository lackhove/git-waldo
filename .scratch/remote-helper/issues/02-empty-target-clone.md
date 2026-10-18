# 02: Walking skeleton: clone an empty target

**What to build:** An installable `git-remote-tarssh` that git discovers, with URL and target-descriptor resolution, SSH access to an empty target, a root snapshot commit, and enough of the helper protocol for `git clone` and `git fetch` to record the target as a remote branch. Both `tarssh://[user@]host[:port]/absolute/path` and `tarssh::` work. Descriptor fields resolve most-specific first: `TARSSH_*`, then URL, then `.tarssh.toml` at the repository root found with `git rev-parse --show-toplevel`, then defaults. `list` and `list for-push` advertise the real oid, never `?`.

**Blocked by:** 01 — Fake target and protocol test harness

**Status:** ready-for-agent

- [ ] `git clone tarssh://…` of an empty target creates a repository whose `HEAD` is a snapshot commit with ident `tarssh <tarssh@localhost>` and subject `snapshot of <host>:<path>`.
- [ ] `git ls-remote`, including outside any repository, prints `@refs/heads/main HEAD`, the real oid, and a blank line; no `?` is advertised.
- [ ] `git fetch <remote>` records the snapshot at `refs/remotes/<remote>/main`; clone's fetch is acknowledged with the blank line; the helper never writes `refs/remotes/*`.
- [ ] `tarssh::` resolves from `.tarssh.toml`; a full URL supplies its own fields; `TARSSH_*` wins per field; when the URL and the file disagree, one stderr line names both.
- [ ] A relative path is refused naming the URL; only `tarssh://` and `tarssh::` reach the helper; a bare `tarssh:` is not treated as a helper form.
- [ ] `user` defaults to the local username and the SSH port to 22.
- [ ] A missing or unreadable target fails `list` with the URL and path echoed and a non-zero exit; an empty target is a legitimate empty tree.
- [ ] A SHA-256 config repo is a startup error naming both formats.
- [ ] Capabilities include `fetch` and `option`; `push` is added with the first-push ticket. `option` answers `ok` for `dry-run`, `verbosity`, `followtags`, and `cloning`, and `unsupported` for `progress` and `cas`.
- [ ] Tests use the ticket 01 harness and never contact a live target.
