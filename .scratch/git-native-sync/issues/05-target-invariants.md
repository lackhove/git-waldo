# Target invariants and deploy mechanics

Type: grilling
Status: open
Blocked by: 04

## Question

The helper is the only thing that touches the target; settle how it does so safely:

- **Clean check**: how to decide "the target tree equals the remote branch's tree" without git on the target — transfer the mirror set and hash locally, remote `sha1sum`, or a per-file strategy — and what the failure message contains (per-file diff?).
- **Snapshot read**: how `find` + `tar` produce the set to hash, which path types are supported (symlinks, modes, empty directories) and which are refused rather than silently dropped.
- **Delta deploy**: applying `remote/main..HEAD` — writes and overwrites via `tar`, deletions via an explicit remove list, and never touching paths outside the delta (untracked and ignored files on the target survive).
- **Interruption and concurrency**: what a half-applied push leaves behind, whether the target's dirty state then blocks the next push until a pull, and how two concurrent pushes are prevented.
- **First push**: the target directory is empty or missing; is that a clean target with no ref, and what is created.
- **Reporting**: what the push prints so the operator can tell a no-op from a deploy.
