# Remote-helper protocol surface: what the helper implements, what git may do

Type: grilling
Status: resolved
Blocked by: 01

## Question

Design the helper's protocol behaviour against git's actual expectations (ticket 01 supplies the facts):

- **Exposure**: which refs `list` reports (`refs/heads/main` only?), what happens for `list for-push`, and whether tags or extra branches are rejected or ignored.
- **Snapshot construction**: the helper builds a commit from the target tree locally (`hash-object -w`, temporary index, `write-tree`, `commit-tree`), including deletions, author/committer ident and message for a commit no human authored, and the parent chain. The objects must be written **during `list`**, since `?` does not advertise objects; `list` advertises the real oid and `fetch` acks with a blank line. Decide the ident/message convention (tool version? target host? timestamp?).
- **`list for-push` and clone**: whether the tool supports `git clone` (requires the `fetch` ack and `@refs/heads/main HEAD`), and what `list for-push` advertises before the clean check runs.
- **Pull**: which behaviour is `git fetch <remote>` vs a convenience `pull`, and what `git fetch --prune` should mean when the target is empty or unreadable.
- **Push**: what the helper receives, and what it validates that git cannot pre-check (fast-forward under `+`/`--force`, unknown old oids, races, clean target). Use `error <dst> non-fast forward` for `[rejected]`. `--dry-run` requires advertising `option` and answering `ok` to `option dry-run true`, then simulating the push.
- **Rejections**: exact behaviour for force pushes, deletion refspecs, pushing a ref other than `main`, and pushing when the target has drifted.
- **Stop conditions**: which protocol gaps we accept (no `option progress`, no `export`, no marks) and what git does when those are absent.

## Answer

Evidence: `docs/research/git-remote-helper-prior-art.md` (branch `research/prior-art`, ticket 01). The `? <oid>` premise in this ticket's question is void — see the ADR correction below.

**Capabilities.** `fetch`, `push`, `option`. No `import`/`export` (no `refspec`, no marks, no fast-import stream), no `object-format` — SHA-1 only, and a SHA-256 config repo is a startup error naming both formats. `list` prints exactly `@refs/heads/main HEAD`, `<oid> refs/heads/main`, blank line; no tags, so `option followtags` finds nothing. `list for-push` refreshes the target snapshot, runs the clean check, and prints the **real** oid — never `?`; git's fast-forward pre-check depends on it. `fetch` is acked with a single blank line per batch (objects were already written in `list`; clone is the case that actually calls it). `option`: `ok` for `dry-run`, `verbosity`, `followtags`, `cloning`; `unsupported` for `progress` and `cas`. `--prune` needs no code: git prunes from `list` alone. The helper never writes `refs/remotes/*` on fetch or push — git owns those.

**Snapshot commit.** Ident `tarssh <tarssh@localhost>`, subject `snapshot of <host>:<path>`, author and committer date = now, parent = the current `refs/remotes/<remote>/main` when it exists (root otherwise). If the built tree equals the parent's tree, no commit is emitted and the parent's oid is advertised unchanged — a clean target must never move `target/main` or invent empty commits.

**Missing vs empty target.** A missing or unreadable target fails `list` with the URL and the path echoed to stderr and a non-zero exit; a genuinely empty directory is an empty tree.

**Push.** Input is `[+]<src>:<dst>` or `:<dst>`; the old oid is not in the line, so the helper remembers what `list for-push` advertised (same process) and re-reads the target for the clean check. Per-ref outcomes:

| case | helper sends | operator sees |
|---|---|---|
| fast-forward, clean target | `ok <dst>` | normal update |
| non-fast-forward | `error <dst> non-fast forward` | `[rejected] (non-fast-forward)` |
| `+` / force | `error <dst> force pushes are not supported` | `[remote rejected]` |
| `:<dst>` deletion | `error <dst> deleting branches is not supported` | `[remote rejected]` |
| any other `dst` | `error <dst> only refs/heads/main is deployed` | `[remote rejected]` |
| target drifted | `error <dst> target has local changes: <paths>` | `[remote rejected]` |

All rejections exit `0` after printing status lines: git must see a protocol result, not a crash. Only protocol-level failures (SSH down, unreadable target, failed extraction) go to stderr with a non-zero exit, which git reports as a transport failure.

**Pull surface.** No `pull` verb, no auto-merge. `git fetch target` records the target, `git merge target/main` merges, `git pull target main` does both. One-time setup in the config repo's docs: `git push -u target main`, after which bare `git push` and `git pull` behave normally. `--force-with-lease` is unavailable (`option cas` is `unsupported`), which is the intended outcome.

**ADR correction.** ADR-0001's consequence "advertises the already-local snapshot with the `?` capability" is false; it was amended with a dated correction. The decision it supports — no pack ever crosses the wire — stands, and now rests on the real mechanism: the objects are written into the local object database during `list`, so `check_exist_and_connected()` skips the transport fetch.
