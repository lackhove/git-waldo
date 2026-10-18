# Map: git-native sync for a busybox-only target

## Destination

A settled design for a git remote helper (name pending ticket 02) that makes any SSH host with only busybox `find` and `tar` a first-class git remote, plus the plan to split this repo into a tool repo and a fresh config repo — precise enough that implementation needs no further decisions.

## Notes

- **The spec is git's own behaviour.** When in doubt, do what git does (`fetch`, `merge`, `push`, fast-forward only, clean worktree), not what a bespoke sync tool would do.
- The tool is **generic**: no the application knowledge, one target per config repo, target config in a gitignored `.tarssh.toml`, environment overrides for one-offs.
- The settled model is in `docs/adr/0001-target-is-a-git-remote.md`; the repo split is in `docs/adr/0002-tool-and-config-are-separate-repos.md`.
- Vocabulary: `GLOSSARY.md` at the repo root.
- Ticket 01 is in flight elsewhere; this repo has no remote configured, so nothing is pushed.
- **02 (naming)** settled: helper `git-remote-tarssh`, scheme `tarssh://`, remote `target`, branch `main`, config `.tarssh.toml`, env `TARSSH_*`, tool repo `tarssh`, config repo `config-repo`.

## Decisions so far

<!-- one line per closed ticket: gist + link; the ticket holds the detail -->

- The target-is-a-git-remote model was settled during charting and recorded in `docs/adr/0001-target-is-a-git-remote.md` rather than in a ticket.
- [01 — Prior art](issues/01-prior-art.md): nothing existing does this; and `?` does not advertise objects, so build the snapshot during `list`, advertise the real oid, and ack `fetch` with a blank line. This unblocks 04.
- [02 — Naming](issues/02-naming.md): `tarssh://` as the scheme and `git-remote-tarssh` as the only executable, `target` as the remote name, `main` on both sides, `.tarssh.toml` + `TARSSH_*`, tool repo `tarssh` and config repo `config-repo`. Reopened once by the collision check (a same-domain SSH tarpit named `tarssh`; no `git-remote-tarssh` exists) and kept deliberately.
- [03 — Repo split](issues/03-repo-split.md): split now, before the helper; the config repo is seeded with a hand-made import commit whose tree is byte-identical to the target (dead `photo.jpg` deleted, the fence deployed as part of the split), furniture as a second commit; `the bridge` becomes a temporary `--repo` bridge with the the application check removed; the fence gains a `.*` catch-all.
- [04 — Helper protocol](issues/04-helper-protocol.md): expose only `refs/heads/main` (plus `HEAD` symref) with `fetch push option`; snapshot commit parented on `target/main` and skipped when the tree is unchanged; every rejection is a per-ref `error` with `git`'s exact tokens; no `pull` verb; ADR-0001 amended — snapshots are advertised with their real oid, not `?`.
- [05 — Target invariants](issues/05-target-invariants.md): clean check is a tree comparison reusing the `list for-push` snapshot; the fence at `target/main` ∪ `HEAD` filters the read; blobs written with `--no-filters`; delta via `git archive` + `tar -o -x`, deletions as `./`-relative `rm -f` chunks; a `mkdir` lock in `/tmp` taken before the clean check; reporting on stderr only.
- [06 — Design spec](issues/06-design-spec.md): `docs/design/spec.md` plus both `AGENTS.md` drafts; glossary gained `Remote helper`, `Fence`, `Target descriptor`, `Delta`, `Deploy`; three contradictions resolved (descriptor precedence, ADR-0002's commit shape, bare `tarssh:` not reaching the helper).

All six tickets are closed and the destination is met: the design is settled and traced to ADRs and tickets, the split is planned to the command, and implementation can start from `docs/design/spec.md`. The remaining fog (packaging, test harness, large-target cost, protocol mismatch) is work for after implementation, not open design.

## Not yet specified

<!-- in-scope fog: questions we can see coming but cannot phrase sharply yet -->

- **Packaging and installation**: how `uv tool install` puts `git-remote-<name>` on `PATH`, how the tool reports its version, and what happens when the installed tool and the target disagree about the protocol.
- **Testing a remote helper**: a protocol-level harness and a fake busybox-only target; whether any of it can run in CI without SSH.
- **The config repo's workflow docs**: the application check and reload become manual post-push steps once the tool knows nothing about the application.
- **Error UX**: how drift, rejection and partially-applied deploys are worded, and how much of the target's state is echoed back.
- **Cost on large targets**: the clean check and snapshot build for trees far bigger than the current 17 files.

## Out of scope

<!-- consciously ruled beyond the destination; never graduates -->

- Shipping a static `git` binary to the target. The target stays busybox-only; that constraint is the point.
- More than one target per config repo, or several targets per repo.
- the application behaviour inside the tool (`the config check`, reload hints). It moves to the config repo's docs.
- History-preserving split of `config/` into the new repo. The config repo starts with a single import commit.
