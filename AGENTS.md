# tarssh

A git remote helper. It makes an SSH host with **no git** — only busybox `find` and `tar` — a normal git remote: `git fetch` records the host's directory as a snapshot commit, `git merge` merges it, `git push` deploys the commit delta. The tool knows nothing about any particular application; it is generic.

Design: `docs/design/spec.md` (settled, traceable to ADRs and tickets). Model: `docs/adr/0001-target-is-a-git-remote.md`. Split: `docs/adr/0002-tool-and-config-are-separate-repos.md`. Vocabulary: `GLOSSARY.md`. Git-side protocol facts: `docs/agents/git-helper-protocol.md`.

## Layout

- `src/tarssh/` — the helper (`uv`-managed package; entry point `git-remote-tarssh = "tarssh.remote:main"`).
- `tests/` — protocol and target-invariant tests.
- `docs/` — ADRs, design, agent docs. `.scratch/` — issues and specs.

The config repo is separate; it holds the deployed files and the `target` remote. Its own documentation covers the workflow.

## Transport facts (do not relearn these the hard way)

- The target has no git, no rsync, no SFTP. Only `find`, `tar`, `rm`, `mkdir`, `xargs`, `sha1sum`.
- busybox 1.37 `tar`: `-T -` reads names from stdin, `-C`, `-o` (do not restore numeric owner), `--exclude`, `--no-recursion`; it overwrites by default.
- busybox `rm` has **no `--`**: pass `./`-relative paths only.
- Snapshots are advertised with their **real oid**, written during `list`. `?` means "unknown value" and cannot advertise an object.
- `git fetch` may never send `fetch` at all; `git clone` always does.

## Working on it

- `scripts/check` — pytest, mypy, ruff check, ruff format --check.
- `uv run pre-commit install` once per clone; commits run the fast checks, pushes run `scripts/check`.
- Test against a fake target over localhost, never against a live instance, except for the explicit end-to-end check in the config repo.
- Every change that alters the protocol, the snapshot shape or the push order needs a ticket under `.scratch/` and, if it contradicts an ADR, an ADR correction rather than a silent override.

## Agent skills

### Issue tracker

Issues live as local markdown files under `.scratch/<feature>/`. See `docs/agents/issue-tracker.md`.

### Domain docs

Single-context: `GLOSSARY.md` + `docs/adr/` at the repo root. See `docs/agents/domain.md`.
