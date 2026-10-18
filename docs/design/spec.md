# tarssh — design

Status: settled; the handoff for implementation. Every decision here traces to an ADR or a ticket in `.scratch/git-native-sync/issues/` (see [Traceability](#traceability)).

## 1. What this is

`tarssh` is a git remote helper. It makes a host that has **no git** — only SSH and busybox `find`/`tar` — a first-class git remote: `git fetch` records what the host's directory contains as a commit, `git merge` merges it, `git push` deploys a commit's delta into that directory. There is no bespoke sync command; git's own semantics are the specification (ADR-0001).

Nothing in the tool knows about the application. The config repo's own documentation covers `the config check` and reloading.

## 2. Vocabulary

See `GLOSSARY.md`. The load-bearing terms: **target** (the remote directory), **config repo** (the repo deployed to it), **snapshot** (the commit built from the target), **remote branch** (`refs/remotes/target/main`), **clean target**, **target drift**, **fence** (the tracked `.gitignore`).

## 3. Surface

### URL

```
tarssh://[user@]host[:port]/absolute/path
```

- The path must be absolute; a relative path is refused with an error naming the URL.
- `user` defaults to the local username (ssh's own rule); the example config uses `root`.
- `port` defaults to 22.
- Only `scheme://` is accepted. `tarssh::…` is not parsed — the target needs a port, and `ssh://`-shaped URLs are what operators already know.

### Remote name

`target`, in every config repo: `refs/remotes/target/main`, `git push target main`, `git diff target/main HEAD`. One-time setup: `git push -u target main`, after which bare `git push`/`git pull` work.

### Target descriptor and precedence

Four layers describe the same target. Each field is resolved independently, most specific first:

1. `TARSSH_USER`, `TARSSH_HOST`, `TARSSH_SSH_PORT`, `TARSSH_DIR` — one-off overrides.
2. The remote URL, for whichever components it carries.
3. `.tarssh.toml` at the config repo root — the committed default, so a fresh clone needs no host knowledge. Located via `git rev-parse --show-toplevel`, never the current directory:

   ```toml
   user = "root"
   host = "host.example"
   ssh_port = 22222
   dir = "/srv/config"
   ```

   `.tarssh.toml` is gitignored; `.tarssh.example.toml` is committed as furniture.

4. Defaults: `user` = local username, port 22, no dir (required).

Two URL shapes are meaningful:

- `tarssh://[user@]host[:port]/absolute/path` — carries the target. Used for one-off inspection (`git ls-remote tarssh://…`) and for retargeting a clone (`git remote set-url`).
- `tarssh::` — carries nothing; the descriptor comes from `.tarssh.toml`. This is the shape `--config` writes (`git remote add target tarssh::`), so nobody types it by hand.

A bare `tarssh:` is **not** a helper URL: git parses it as scp-like `host:path` and tries to SSH to a host called `tarssh` (verified against git 2.56). Only `tarssh://…` and `tarssh::` reach the helper.

When the URL contradicts `.tarssh.toml`, the helper proceeds and prints one stderr line naming both values, for every field the URL carries explicitly whose effective value still comes from the URL (a `TARSSH_*` override suppresses that field) — `using user=root, ssh_port=22222 from the remote URL; .tarssh.toml says user=deployer, ssh_port=22`. A retarget is `git remote set-url`, not a commit; the committed file only has to be right for new clones. The guard against deploying to the wrong host is the clean check plus the target named on stderr, not this precedence.

### Executables

One binary, `git-remote-tarssh`, installed by `uv tool install tarssh`. No separate `tarssh` command. Tool-mode verbs are double-dash prefixed and a leading `-` in `argv[1]` always means a verb, never a remote:

- `git-remote-tarssh --config` — interactive writer for `.tarssh.toml` (refuses to clobber without confirmation), then registers the remote as `git remote add target tarssh::` when none exists.
- `git-remote-tarssh --version` — prints the tool version.

Any other invocation is the helper protocol: `git-remote-tarssh <remote> <url>`.

## 4. Protocol surface

Capabilities: `fetch`, `push`, `option`. No `import`/`export`, no `refspec`, no marks, no `object-format` (SHA-1 only; a SHA-256 config repo is a startup error naming both formats).

| command | behaviour |
|---|---|
| `list` | build the snapshot, print `@refs/heads/main HEAD`, `<real oid> refs/heads/main`, blank line. No tags. |
| `list for-push` | take the lock, refresh the snapshot, run the clean check, print the **real** oid. Never `?`. |
| `fetch` | verify the named oids exist locally, print one blank line per batch. |
| `push` | parse one line per ref, validate, apply, print one status per ref, blank line. |
| `option` | `ok` for `dry-run`, `verbosity`, `followtags`, `cloning`; `unsupported` for `progress` and `cas`. |

`?` is not "I already have this object": it means "the value is unknown", leaves the oid null, and makes git fail with `bad object`. Nothing is transferred because the objects are written into the local object database during `list`, so git's `check_exist_and_connected()` skips the transport fetch; `git clone`, which always fetches, gets the blank-line ack (ADR-0001 correction).

The helper never writes `refs/remotes/*`; git owns those. `git fetch --prune` needs no helper support. `git push --dry-run` requires `option` + `ok`, and the helper must still receive and simulate the push lines.

### Rejections

| case | helper sends | operator sees |
|---|---|---|
| fast-forward, clean target | `ok <dst>` | normal update |
| non-fast-forward | `error <dst> non-fast forward` | `[rejected] (non-fast-forward)` |
| `+`/force | `error <dst> force pushes are not supported` | `[remote rejected]` |
| `:<dst>` deletion | `error <dst> deleting branches is not supported` | `[remote rejected]` |
| `dst` ≠ `refs/heads/main` | `error <dst> only refs/heads/main is deployed` | `[remote rejected]` |
| target drift | `error <dst> target has local changes: <paths>` | `[remote rejected]` |

Rejections exit 0 after printing statuses — git must see a protocol result. Only protocol-level failures (SSH unreachable, unreadable target, failed extraction) go to stderr with a non-zero exit. `--force-with-lease` is unavailable by design (`option cas` → `unsupported`).

## 5. Snapshot

A snapshot records the target's state as a commit no human authored.

- **Ident** `tarssh <tarssh@localhost>`; **subject** `snapshot of <host>:<path>`; author and committer date = now.
- **Parent**: the current `refs/remotes/target/main` when it exists, none otherwise. This is what makes pulls mergeable instead of unrelated-rooted.
- **Skip rule**: if the built tree equals the parent's tree, emit no commit and advertise the parent's oid unchanged. A clean target must never move `target/main` or invent empty commits.

### Read order

1. Read the committed `.gitignore` — the fence — with a single-file tar.
2. `find . \( -type f -o -type l \)` on the target.
3. Filter the names through git's ignore semantics against the **union** of the fences at `target/main` and `HEAD`. A path ignored by either is invisible: over-ignoring costs a blind spot, under-ignoring costs a leaked secret. When neither local fence exists — cloning a non-empty target, or a first snapshot in a repo without `HEAD` — the target's own `.gitignore` is the fallback fence; normal fetches always use only the local union.
4. `tar -cf - -T -` the survivors, using `./`-relative names.

Locally, blobs are written with `git hash-object -w --no-filters` and the tree assembled with `git update-index --cacheinfo` against a temporary `GIT_INDEX_FILE`. Never `git add`: it applies the operator's `core.autocrlf` and clean filters, which would rewrite content silently.

### Representable paths

Regular files (0644/0755) and symlinks (mode 120000, stored as-is, never followed); directories are implied. Empty directories are ignored rather than refused. FIFOs, sockets, device nodes, unreadable files and non-UTF-8 names are fatal errors naming the path.

## 6. Push

Order of operations for a push batch:

1. Take the lock: `mkdir /tmp/tarssh-<hash of target path>.lock` **on the target**, outside the target directory so it can never become drift. Released on every exit path; a stale lock is reported by path, never auto-broken.
2. Verify the target is clean: tree equality between the freshly built snapshot and `refs/remotes/target/main` (both local; no extra transfer, no `sha1sum` pass). Drift detail from `git diff-tree -r --name-status` — first ten paths, then a count.
3. Verify fast-forward against the oid advertised by `list for-push` (remembered in-process; the `push` line carries no old oid), unless the ref is being created.
4. Apply, unless `--dry-run`:
   - writes/overwrites: `git archive --format=tar <new> -- <added|modified>` piped to `ssh … tar -o -xf - -C <dir>`. `-o` keeps ownership with the target's user instead of the client's uid.
   - deletions: `rm -f` over chunks of ~500 `./`-relative paths, one SSH call per chunk (busybox `rm` has no `--`).
   - directories emptied by a deletion are left in place.
5. Print statuses; git updates `refs/remotes/target/main` itself.

An interrupted push leaves the target drifted; the next push refuses until the operator fetches the half state and decides. There is no journal and no staging area.

## 7. First use

- Missing target directory: created with `mkdir -p`.
- No `refs/remotes/target/main`: the expected oid is null, the push is a branch creation, and the full `git archive HEAD` is deployed.
- Empty target directory: a legitimate empty tree, not an error.
- Missing or unreadable target: `list` fails loudly with the URL and path echoed. A mistyped path must never look like "nothing there".

## 8. Reporting

stdout is the protocol. Everything for the operator goes to stderr:

- one line naming the target and counts: `deploying 3 changes to user@10.0.0.7:22222:/srv/config: 2 written, 1 deleted`
- `already up to date with user@10.0.0.7:22222:/srv/config` for a no-op (git prints `Everything up-to-date` only when it never invoked the helper)
- the drift path list on rejection
- per-file lines only when a deletion is refused

## 9. Deliberately absent

Force pushes, branch deletion, tags, extra branches, `pull`/`sync` verbs, auto-merge, and any the application behaviour (`the config check`, reload hints). See `map.md` → Out of scope.

## 10. Repo split

Executed once, after this spec: `config/**` moved to a new `config-repo` repo whose root *is* the target directory; this repo became `tarssh` (ADR-0002). The seed is a hand-made import commit whose tree is byte-identical to the target, furniture second. The temporary bridge was retired at cutover (ticket 08) once `git-remote-tarssh` worked; the tool repo carries no deploy script. The split's six-step order and acceptance criteria are in ticket 03; the cutover and its end-to-end check are in ticket 08.

## 11. Not covered here

- Packaging details beyond `uv tool install tarssh` providing `git-remote-tarssh` (`map.md` → Not yet specified).
- A protocol-level test harness and a fake busybox-only target.
- Cost on targets far larger than today's 17 files.
- Behaviour when the installed tool and an existing config repo disagree about the protocol.

## Traceability

| Decision | Source |
|---|---|
| Target is a git remote, git semantics are the spec, no force/CLI | ADR-0001 |
| Tool and config are separate repos; one target per config repo | ADR-0002 |
| Tool named `tarssh`; `target` as remote name; `main` on both sides; one binary; `--config`/`--version` | 02 |
| Committed descriptor, env overrides, URL wins with a disagreement warning | 02, 06 (Q7b) |
| Capabilities, `list`/`list for-push`/`fetch`/`push`/`option`, status tokens, no `?` | 01, 04 |
| Snapshot ident/message/parent/skip rule | 04 |
| Fence union, `--no-filters`, path types, delta mechanics, lock, stderr reporting | 05 |
| Split plan, seed, fence additions | 03 |
| Cutover of the live config repo, bridge retirement | 08 |
| `.gitignore` travels and is the only fence | ADR-0001 |
