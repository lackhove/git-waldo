# Target invariants and deploy mechanics

Type: grilling
Status: resolved
Blocked by: 04

## Question

The helper is the only thing that touches the target; settle how it does so safely:

- **Clean check**: how to decide "the target tree equals the remote branch's tree" without git on the target — transfer the mirror set and hash locally, remote `sha1sum`, or a per-file strategy — and what the failure message contains (per-file diff?).
- **Snapshot read**: how `find` + `tar` produce the set to hash, which path types are supported (symlinks, modes, empty directories) and which are refused rather than silently dropped.
- **Delta deploy**: applying `remote/main..HEAD` — writes and overwrites via `tar`, deletions via an explicit remove list, and never touching paths outside the delta (untracked and ignored files on the target survive).
- **Interruption and concurrency**: what a half-applied push leaves behind, whether the target's dirty state then blocks the next push until a pull, and how two concurrent pushes are prevented.
- **First push**: the target directory is empty or missing; is that a clean target with no ref, and what is created.
- **Reporting**: what the push prints so the operator can tell a no-op from a deploy.

## Answer

Probed against the live target first (busybox 1.37.0): `tar` accepts `-T -`, `-C`, `-o`, `--exclude`, `--no-recursion`; it **overwrites by default** (verified) and **restores numeric ownership** unless `-o` (a test extraction came out owned by uid 1000). `rm [-irf]` has **no `--`**, so delete paths must be `./`-relative. `find`, `xargs` and `sha1sum` exist; no git, no rsync, no SFTP.

**Clean check costs nothing extra.** `list for-push` must read the target anyway to learn the real oid, so cleanliness is a tree comparison between the snapshot it just built and `refs/remotes/<remote>/main` — both local. Drift detail comes from `git diff-tree -r --name-status` between the two trees: first ten paths, then a count. No `sha1sum` pass, no second transfer, no per-file hashing protocol. Ignored paths cannot cause drift because they never enter the snapshot.

**Snapshot read, in order.** (1) Read the committed `.gitignore` — the fence — with a single-file tar. (2) `find . \( -type f -o -type l \)`, filter the names through git's own ignore semantics against the **union** of the fences at `target/main` and `HEAD`. (3) `tar -cf - -T -` with the surviving `./`-relative names. Locally, write blobs with `git hash-object -w --no-filters` and build the tree with `git update-index --cacheinfo` against a temporary `GIT_INDEX_FILE` — never `git add`, which would apply the operator's `core.autocrlf` or clean filters and silently rewrite content. The union rule is the one deliberate asymmetry: over-ignoring costs a blind spot, under-ignoring costs a leaked secret.

**Representable paths.** Regular files (0644/0755) and symlinks (mode 120000, stored as-is, never followed); directories are implied by their contents. Empty directories are not representable and are ignored, not refused. FIFOs, sockets, device nodes, unreadable files and non-UTF-8 names are fatal errors naming the path — a silent drop would make the target's cleanliness claim a lie.

**Delta deploy.** Writes and overwrites: `git archive --format=tar <new> -- <added|modified>` piped into `ssh … tar -o -xf - -C <dir>`; `-o` matters, otherwise deployed files inherit the client's uid (verified 1000 instead of root). Deletions: `rm -f` over chunks of ~500 `./`-relative paths, one SSH call per chunk, because busybox `rm` has no `--`. Directories emptied by a deletion are left in place: git doesn't track them, and pruning could remove something the application needs (`public/`). Nothing outside the delta is touched; untracked and ignored files survive by construction.

**Interruption and concurrency.** No journal and no staging: an interrupted push simply leaves the target drifted, which the next push refuses until the operator fetches the half state and decides. Concurrency is a `mkdir /tmp/tarssh-<hash of target path>.lock` on the target — outside the target directory so it can never become drift — taken **before** the clean check so two pushes cannot both pass it, released on every exit path, and reported (never auto-broken) when stale. Fetches take no lock; they only read.

**First push.** A missing target directory is created with `mkdir -p`. With no `refs/remotes/<remote>/main` the expected oid is null, so the push is a branch creation and deploys `git archive HEAD`.

**Reporting.** stdout is the protocol, so every operator-facing line goes to stderr: one line naming the target with counts (`deploying 3 changes: 2 written, 1 deleted`), a single `already up to date` line for a no-op — git prints `Everything up-to-date` only when it never invoked the helper — the drift path list on rejection, and per-file lines only when a deletion is refused.
