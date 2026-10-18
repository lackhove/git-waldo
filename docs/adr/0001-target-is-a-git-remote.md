# The target is a git remote, reached by a git remote helper

Status: accepted

The old sync script pushes the local worktree without knowing what the target already contains, so a change made on the target (e.g. through a UI) can be silently overwritten, and nothing forces a pull before a push. We decided to model the target as an ordinary git remote: a commit built from the target's working tree — the *snapshot* — updates the remote-tracking branch `<remote>/main`; pull merges it exactly like `git pull`; push is fast-forward-only and deploys the commit delta, refusing when the target's working tree is dirty relative to `<remote>/main`. Git's own semantics are the specification, so there is no force, no content-equality heuristic, and no exclusions: `.gitignore` deploys to the target like any other file. Because the target has no git, the transport is a `git-remote-<name>` helper rather than a bespoke CLI.

## Considered options

- **A bespoke `pull`/`push` CLI reimplementing the checks.** Rejected: it would hand-roll fast-forward rejection, ref updates, `--dry-run`, and remote-ref history that git already provides.
- **Gating push on content equality with `HEAD`** instead of a clean target. Rejected: it answers a different question and leaves remote refs meaningless.
- **Never deleting target files, or offering `--force`.** Rejected: both contradict the semantics of a push.
- **Copying files into a temporary directory and asking git's own commands to push.** Not possible: the target has no git and no SFTP, only busybox `find` and `tar`.
- **Shipping a static git binary to the target.** Rejected: it mutates an appliance with an unsupported binary, and the target's minimalism is the constraint the tool is built around.

## Consequences

- `git fetch <remote>`, `git log --all`, `git diff <remote>/main main`, `git push <remote> main` and `--dry-run` all work as usual; the target appears in the repository like any other remote.
- Deletions propagate: a file removed in a pushed commit is removed on the target. Untracked and ignored files on the target survive.
- Every commit must be built from the target's tree locally, because git must never transfer a pack: the helper writes the snapshot objects while answering `list`, advertises their real oid, and acks the subsequent `fetch` with a blank line. (The `?` reply in `gitremote-helpers(7)` means "ref value unavailable", not "object present" — see ticket 01.)
- `.gitignore` is the only fence around secrets and runtime state, and it now travels to the target.
- The tool must know nothing about the application; post-push verification and reloading belong to the config repo's workflow.

## Correction (2026-10-18, from ticket 01)

The consequence above says the helper "advertises the already-local snapshot with the `?` capability". That is wrong: `?` in `list` means *the helper could not get the value of the ref* and leaves the oid null, after which git asks for `0000…0` and fails with `bad object`. The decision stands and the mechanism is now known: the helper builds the snapshot objects in `list`, advertises the real oid, and no pack crosses the wire because the objects are already in the local object database — git skips the transport fetch via `check_exist_and_connected()`, and `git clone`, which always fetches, is acked with a blank line. Evidence: `docs/research/git-remote-helper-prior-art.md` (branch `research/prior-art`, ticket 01).
