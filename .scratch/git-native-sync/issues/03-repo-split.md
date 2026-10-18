# Split the repo: tool here, fresh config repo there

Type: grilling
Status: resolved
Blocked by: 02

## Question

Turn ADR-0002 into a concrete plan, precise enough to execute in one pass:

- **What moves where**: `config/**` leaves this repo for a new repo whose root *is* the target's config dir; `the bridge` stays (to be replaced); which of `AGENTS.md`, `docs/agents/`, `docs/adr/`, `GLOSSARY.md`, `skills-lock.json` stay with the tool and which are rewritten for the config repo.
- **The config repo's seed commit**: one import commit containing the current mirrored set; which files are furniture (`.gitignore`, workflow docs, `.tarssh.toml` example) and which are content; whether the target's `.gitignore` is committed as-is at the repo root.
- **Ignore rules**: `config/.gitignore` becomes the root `.gitignore`; it must also ignore the tool's target config. Anything else to add or drop now that ignored files are the only fence around secrets and runtime state?
- **This repo after the split**: delete `config/`, rewording of `AGENTS.md`, and what the replacement tool is called alongside the naming decision from 02.
- **Ordering**: does the split land before or after the helper exists, and can the old `the bridge` keep running against either layout in the meantime?

## Answer

Settled. Live findings that shaped it: the target holds one non-ignored file the mirror lacks (`photo.jpg`, byte-identical to the `public/` copy that `overrides.yaml` actually serves), and the target's `.gitignore` is still the application's stock `.*`/`!.state/*_registry` file — the mirror's fence has never been deployed. The other 16 files match the mirror byte for byte, so no pull is needed: the split is a *push* of one file plus a deletion.

**Ordering: split now, before the helper.** The tool is what replaces the bridge, not what enables the split. The seed is hand-made, and the day the helper lands the first `git fetch target` produces a root snapshot whose tree equals the import commit's tree; reconciling is one `git merge -s ours --allow-unrelated-histories target/main` followed by a push that deploys the furniture. That merge is a no-op by construction, because the import tree is verified equal to the target tree at split time.

### What moves where

Tool repo (`tarssh`):

- Stays: `AGENTS.md` (rewritten), `GLOSSARY.md`, `docs/adr/`, `docs/agents/`, `.scratch/`, root `.gitignore` (tool tooling only, comment reworded), `skills-lock.json`, `.agents/`, `.claude/`.
- Leaves: all of `config/**`.
- `the bridge` stays as the temporary bridge, patched: a `--repo <path>` argument replaces the hard-coded `CONFIG = repo/config`, the ignore rules come from that repo's root `.gitignore` alone (one spec, no `config/` prefix, no root spec), and the `the config check` call is removed — the tool never knows about the application, not even during the bridge. It is deleted the day the helper works.

Config repo (`config-repo`, root *is* `/srv/config`):

- Content: the 17 files currently mirrored, at the repo root. `photo.jpg` is not among them: it is deleted from the target instead of imported.
- Furniture: `.gitignore` (the fence), `AGENTS.md`, `.tarssh.example.toml`. No `README`, no ADRs, no issue tracker, no glossary — those are tool-side, so the config repo's `AGENTS.md` must not reference `docs/agents/`.
- The application-specific knowledge from today's `AGENTS.md` moves into the config repo's `AGENTS.md`: `condition: window.is_closed` only matches `device_class: window`, the two door-class contacts need plain `condition: state` (list their entity ids), `input_select.example_mode` is YAML-defined with options `Away` / `Home`, and `the config check` can exit with `Another job is running for job group container_application` (retry). It also documents the workflow — fetch, merge, commit, push, then manual `the config check` and reload — and states once that furniture deploys like content.

### Ignore rules

`config/.gitignore` becomes the config repo's root `.gitignore`, with three additions at the top, ahead of the `.state` block:

```gitignore
# Unlisted dotfiles are runtime state: the application adds new ones across upgrades and an
# unlisted one would otherwise become permanent target drift.
.*
!.gitignore
!.state/

# Target config for the tool - host, port, path. Never committed.
.tarssh.toml
```

Verified against git's own semantics: `.*` ignores `.uuid` and the directory `.state`; `!.state/` re-includes the directory so the existing `.state/*` + `!` allowlist keeps working (`person` tracked, `core.*` ignored); `.gitignore` and `secrets.yaml` keep their intended verdicts. Nothing else is added or dropped: the current rules already cover every non-tracked path on the live target (checked against all 3,225 files).

### The two commits

1. **Import** — exactly the target's 17 non-ignored files, at the repo root, with the fence as `.gitignore`. Tree equality with the target is an acceptance criterion, verified by comparing `sha1sum` output for both sides (path-sorted, 17 lines each).
2. **Furniture** — `AGENTS.md` and `.tarssh.example.toml` only. Deliberately *not* part of the import: it is the first real delta the tool will deploy.

### Execution order

1. `mv ~/code/config-repo ~/code/tarssh`; start the session there.
2. In the tool repo: `git archive HEAD:config | tar -x -C <new config repo>` to seed the 16 content files.
3. On the target: delete the dead root `photo.jpg`, and deploy the new fence as `.gitignore` (write it over SSH into `/srv/config/.gitignore`).
4. New repo: `git init -b main`, add the fence, commit the import; verify tree equality (see acceptance criteria).
5. Commit the furniture.
6. Tool repo: `git rm -r config`, patch `the bridge`, rewrite `AGENTS.md`, reword the root `.gitignore` comment, commit. Nothing is pushed: neither repo has a remote.

### Acceptance criteria

- Both repos have one commit (`tarssh`: its existing history; config: two).
- `sha1sum` of the 17 mirrored paths on target and in the config repo's import commit agree exactly.
- `git -C ~/code/tarssh ls-files` shows no path under `config/`, and `rg config/` finds no stale path references in `AGENTS.md` or `the bridge`.
- The bridge still deploys: `uv run the bridge --repo ~/code/config-repo push --dry-run`-equivalent listing shows nothing to push, and a trivial test edit round-trips.
- `git check-ignore` in the config repo agrees with the probe: `.uuid` ignored, `.state/person` tracked, `.tarssh.toml` ignored, `.tarssh.example.toml` tracked.

## Execution (2026-10-18)

Done as planned, with three corrections found while doing it:

- The import is **16** files, not 17. The earlier count included the stray `photo.jpg`: 16 tracked + the stray = the 17 non-ignored files, and after deleting the stray the target holds 16.
- The bridge only sends *uncommitted* changes — it predates refs and has no idea what was deployed — so it cannot deploy committed-but-undeployed state. The furniture was therefore written once with the same tar pipe, leaving the target equal to the config repo's `HEAD`.
- `the bridge` carried a latent bug from before the split: `-y` was parsed into `args.y` while the code read `args.yes`, so `push -y` always crashed. Now `dest="yes"`.

Results: tool repo `~/code/tarssh` (`5ee7309` design, `7d8c34a` split); config repo `~/code/config-repo` (import, then furniture; 18 tracked files); target tree equal to the config repo's `HEAD` verified by `sha1sum` on both sides; `the config check` passed; the `research/prior-art` worktree was repaired after the directory move; symmetric ownership preserved on the target (`tar -o`) with everything root-owned.
