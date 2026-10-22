# Rename the project to git-waldo

Status: resolved

## Problem Statement

The project is called `tarssh`, which names its two implementation details —
tar and SSH — and neither the interface nor the outcome. To someone who has not
read the README, it reads like a backup or transport utility for tar over SSH,
not like a git remote helper, and it does not suggest that configuration is
deployed to an appliance. The name sits one layer below the value: tar and SSH
are exactly what the documentation promises the operator will never have to
think about.

The name also carries a collision outside the project's ecosystem: `tarssh` is
an existing SSH tarpit on crates.io, in the same domain, so search results are
muddy.

Because the project is unpublished (`0.1.0`, never released) and has exactly one
consumer — one config repo on one workstation — every name is still cheap to
change. The URL scheme is the one identifier that becomes expensive after the
first release, and it has not been released.

## Solution

Rename the project to **git-waldo**, with **waldo** as the interface and URL
scheme. A *waldo* is the established term for a remote manipulator: a device
that copies a human operator's movements and has no autonomy of its own. The
operator stays at the workstation; the machine has no local intelligence. That
is the relationship this tool implements.

The rename is complete and unshimmed:

| What | From | To |
|---|---|---|
| distribution | `tarssh` | `git-waldo` |
| import and wheel package | `tarssh` | `waldo` |
| executable | `git-remote-tarssh` | `git-remote-waldo` |
| URL scheme | `tarssh://`, `tarssh::` | `waldo://`, `waldo::` |
| environment overrides | `TARSSH_*` | `WALDO_*` |
| target descriptor | `.tarssh.toml` | `.waldo.toml` |
| committed descriptor example | `.tarssh.example.toml` | `.waldo.example.toml` |
| device lock | `/tmp/tarssh-<hash>.lock` | `/tmp/waldo-<hash>.lock` |
| agent skill | `skills/tarssh/` | `skills/waldo/` |
| snapshot ident | `tarssh <tarssh@localhost>` | `waldo <waldo@localhost>` |

The distribution and import package deliberately differ: the distribution name
says what ecosystem the project belongs to, while the package, scheme,
descriptor and environment use the short interface name.

The README title is `git-waldo`; its first screen remains:

> **Agentless GitOps for appliances: `git push` to a host that has no git.**

There is no compatibility shim, no alias for the old scheme, and no code path
that parses `.tarssh.toml` — only an existence check that turns a forgotten
migration into a named error. The one consumer is migrated by a runbook. The
naming criteria are recorded in ADR-0003.

## User Stories

1. As an operator, I want the project to be called `git-waldo`, so that its
   name says which ecosystem it belongs to and does not name tar or SSH.
2. As an operator, I want `git-remote-waldo` on `PATH`, so that git discovers
   the helper without extra configuration.
3. As an operator, I want `waldo://[user@]host[:port]/absolute/path` for
   one-off inspection, so that the URL is short and matches the scheme name.
4. As an operator, I want `waldo::` to remain the descriptor-only form that
   `--config` writes, so that a config repo never hard-codes a host.
5. As an operator, I want `WALDO_USER`, `WALDO_HOST`, `WALDO_SSH_PORT` and
   `WALDO_DIR` to override the descriptor, so that one-off retargets work
   without editing tracked files.
6. As an operator, I want `.waldo.toml` beside `.waldo.example.toml`, so that
   the descriptor's name matches the tool that reads it.
7. As an operator, I want the target-side lock to be `/tmp/waldo-<hash>.lock`,
   so that the artifact left on a device identifies its owner.
8. As an operator, I want `--config` to write `.waldo.toml` and register
   `target` as `waldo::`, so that setup produces only new-world names.
9. As an operator, I want `--version` to print `git-waldo`, so that support
   conversations identify the project.
10. As an operator with an old config repo, I want a clear error when
    `.tarssh.toml` exists but `.waldo.toml` does not, so that I learn about the
    rename instead of hunting a "no target host" failure.
11. As an operator, I want the cutover runbook to tell me the exact order —
    including "no push in flight" — so that changing the lock path cannot let
    two pushes run concurrently.
12. As an operator, I want a snapshot's author ident to be `waldo`, so that
    `git log target/main` attributes device state to the current tool.
13. As an agent, I want the skill to be named `waldo` and to use the new
    vocabulary and scheme, so that I do not emit commands that no longer exist.
14. As a contributor, I want `GLOSSARY.md`, the design spec and the ADR to use
    `git-waldo`/`waldo` consistently, so that I am not translating names while
    reading.
15. As a contributor, I want ADR-0003 to record why the name changed and which
    candidates were rejected, so that a future suggestion starts from the same
    criteria.
16. As a maintainer, I want the full test suite to pass with only mechanical
    identifier changes, so that the rename carries no protocol risk.
17. As a maintainer, I want no release and no version bump, so that publishing
    stays a separate decision.
18. As a future maintainer, I want no compatibility shim, so that the old name
    does not become permanent surface.

## Implementation Decisions

- **Name.** Distribution `git-waldo`; import and wheel package `waldo`;
  executable `git-remote-waldo`. Version stays `0.1.0`; there is no release.
- **Scheme.** Accept `waldo://[user@]host[:port]/path` and `waldo::`.
  Precedence, the disagreement warning and the refusal of relative paths are
  unchanged. A bare `waldo:` is not a helper URL and keeps git's scp-like
  interpretation.
- **Environment and descriptor.** `WALDO_*` replaces the `TARSSH_*` set one for
  one. The descriptor is `.waldo.toml`, found through the repository root; the
  committed example is `.waldo.example.toml`.
- **Old-descriptor diagnostic.** When no host is otherwise resolvable and
  `.tarssh.toml` exists while `.waldo.toml` does not, resolution fails with an
  error naming both files and saying the project was renamed. The old file is
  never parsed.
- **Old-scheme behaviour.** A remote still pointing at `tarssh::` fails at git's
  transport lookup because no `git-remote-tarssh` exists. No alias is shipped.
- **Lock.** The target-side lock directory becomes
  `/tmp/waldo-<16 hex of the target path>.lock`, outside the target. Its
  lifecycle, stale-lock reporting and "never auto-break" rule are unchanged.
- **Snapshot.** The ident becomes `waldo <waldo@localhost>`; subject, parent,
  skip rule and tree construction are unchanged. Existing snapshots are not
  rewritten.
- **Skill.** The skill directory, `name` field and interface metadata become
  `waldo`; its body keeps the loop, fence, hard rules, rejection table,
  stop-and-ask list and recovery procedures with identifiers updated. The
  config repo receives a copy, not a symlink.
- **Documentation.** README, glossary, design spec, ADR-0001/0002 and agent docs
  use the new identifiers. ADR-0003 records the naming criteria and rejected
  alternatives.
- **Test infrastructure.** The harness shim, `WALDO_HELPER` and fixtures move to
  the new identifiers. This is test-only plumbing.
- **Order of work.** Rename code and test identifiers together; then docs and
  ADR; then the config-repo cutover; then the end-to-end check. The work lands
  on the current integration branch.
- **Cutover runbook.** `docs/agents/migrate-to-waldo.md` covers: confirm no push
  is in flight; force-reinstall `git-waldo` and uninstall `tarssh`;
  `git remote set-url target waldo::`; rename the descriptor and example and
  the `.gitignore` entries; replace the copied skill and update the config
  repo's `AGENTS.md`; fetch and require an empty
  `git diff --stat HEAD target/main` before committing; commit the migration;
  run `git push --dry-run target main`; push; then remove the temporary
  old-example fence exception and repeat the gate.

## Testing Decisions

The existing highest seam is reused: real `git` and the protocol driver against
the fake target over the localhost SSH shim, with a restricted busybox `PATH`.
No new seam is introduced. Tests assert on git's own output and the helper
protocol, not on internals.

The mechanical identifier update keeps existing assertions. The additions are:

- real `git` discovers `git-remote-waldo` and `git ls-remote` works against both
  `waldo://…` and `waldo::`;
- `--config` writes `.waldo.toml` and registers the remote as `waldo::`;
- `--version` prints `git-waldo`;
- the old-descriptor diagnostic fires for `.tarssh.toml`, and does not fire
  when `.waldo.toml` exists;
- a push takes a lock whose path names `waldo`, as observed through the fake
  target's SSH calls;
- new snapshots carry the `waldo` ident;
- the old scheme fails at git's transport lookup.

**Acceptance criteria.**

- [x] `scripts/check` passes: pytest, mypy, ruff check and ruff format.
- [x] No occurrence of the old identifiers remains outside documented history
      and migration diagnostics.
- [x] The old scheme fails at git's transport lookup; the new scheme works.
- [x] `.tarssh.toml` alone produces the rename diagnostic, never a silent
      "no target host".
- [x] The migration runbook, executed against the config repo, ends with an
      empty `git diff --stat HEAD target/main` and a successful dry run.
- [x] No test contacts the live target.
- [x] The package is not published and the version is unchanged.

## Out of Scope

- Publishing to PyPI, reserving the `git-waldo` or `waldo` names, or a version
  bump.
- A compatibility shim: no `git-remote-tarssh`, no `tarssh://` alias, no reader
  for `.tarssh.toml`.
- Any protocol, snapshot-shape or push-order change.
- Rewriting git history, renaming the local checkout directory, or renaming the
  config repo.
- Creating or renaming a GitHub repository.
- Fleet support, multiple targets per config repo, or any "edge orchestration"
  claim.

## Resolution

Resolved 2026-10-22 on `main`. The code, tests and docs were renamed in one
commit; the migration runbook was executed against the private config repo. The
final `git diff --stat HEAD target/main` was empty and
`git push --dry-run target main` succeeded.

The target had real drift before the migration. It was fetched and
fast-forwarded into the config repo before the rename was committed. The
migration itself kept `!.tarssh.example.toml` temporarily, pushed so the old
example was deleted, then removed the exception and pushed the cleanup.
