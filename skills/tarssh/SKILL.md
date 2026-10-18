---
name: tarssh
description: Deploy a config repo to a minimal SSH host through the tarssh git remote named target. Use when fetching, merging, or pushing target, reconciling target drift, or recovering from a rejected or interrupted deploy.
---

# tarssh

`target` is a normal git remote for a directory on a host that has no git, no
rsync and no SFTP. `git fetch target` records that directory as a snapshot
commit; `git merge target/main` reconciles device-side changes; `git push target
main` deploys a commit's delta. Git's own semantics are the interface: there is
no separate sync command, and the tool knows nothing about the application.

Never substitute `scp`, `rsync`, a hand-written script, or direct edits over
SSH. Only the helper writes to the target.

## Vocabulary

Use these words in reports and commits; the alternatives under _Avoid_ are
wrong.

| Term | Meaning |
|---|---|
| **target** | The remote directory treated as a git working tree. _Avoid_: remote, server |
| **config repo** | The repository whose tracked files are deployed. _Avoid_: mirror |
| **snapshot** | The commit built from the target's working tree, authored by `tarssh`. _Avoid_: sync commit, mirror commit |
| **remote branch** | `refs/remotes/target/main`, the target state the config repo last saw. _Avoid_: shadow branch |
| **clean target** | The target's tree equals the remote branch's tree; the push precondition. _Avoid_: in sync |
| **target drift** | Any difference between the target and the remote branch. _Avoid_: dirty remote, conflict |
| **fence** | The tracked `.gitignore`; it decides what the tool may read and write. _Avoid_: filter, exclude list |
| **delta** | The added, modified and removed paths between the remote branch and the pushed commit. _Avoid_: changeset, patch |
| **furniture** | A tracked file the application does not read but that still deploys. _Avoid_: metadata |

## Before acting

1. Work from the config repo root: `git rev-parse --show-toplevel`.
2. Read the config repo's own `AGENTS.md`. Application checks, reloads and
   restarts are defined there; this skill does not know the application.
3. Confirm the tool and remote:

   ```sh
   git-remote-tarssh --version
   git remote get-url target      # tarssh:: or tarssh://...
   ```

4. Run `git status --short`. A push deploys commits, not the working tree;
   finish or stash local work first.

The target is resolved per field from `TARSSH_*` variables, then the remote URL,
then the gitignored `.tarssh.toml`, then defaults (local user, port 22; `dir` is
required). A warning that the URL disagrees with `.tarssh.toml` means two
targets are in play: stop and confirm the host before pushing.

## The loop

```sh
git fetch target                    # record the target as target/main
git diff --stat HEAD target/main    # target drift since the last snapshot
git merge target/main               # reconcile; resolve conflicts as usual
# ...edit and commit...
git push --dry-run target main      # optional: same checks, no writes
git push target main                # deploy exactly the delta
```

After a push, verify before reporting success:

```sh
git diff --stat HEAD target/main    # must be empty
```

Then run the application check documented in the config repo's `AGENTS.md`.
A change that needs a restart or an interruption of the service: ask the
operator first.

`git pull` and `git push` work without arguments after the first
`git push -u target main`.

### First use

```sh
uv tool install tarssh
git-remote-tarssh --config          # writes .tarssh.toml, adds the target remote
git push -u target main             # creates the directory, deploys everything
```

The first push is the only one that deploys the whole commit; a missing target
directory is created, and an empty one is legitimate. `.tarssh.toml` is
gitignored; `.tarssh.example.toml` is committed furniture.

To retarget an existing clone, use
`git remote set-url target 'tarssh://user@host:port/absolute/path'`, not a
hand-edited descriptor.

## The fence

`.gitignore` is the fence. It is tracked, deploys to the target, and is the only
thing separating configuration from runtime state and secrets. The fence is the
committed file: a path ignored at `target/main` or at `HEAD` is invisible in
both directions, never read into a snapshot and never written by a push.

- Edit the fence only with explicit operator approval.
- Never edit the fence to make a drift rejection or a diff disappear.
- Never `git add -f` an ignored file, and never commit a secret to "test" it.
- Files ignored on the target survive pushes; that is how runtime state lives.

If a secret or runtime path becomes tracked, stop and report it. Do not fix it
silently.

## Hard rules

- Never force: no `+`, no `--force`, no `--force-with-lease`.
- Never delete a branch, push a tag, or push anything but `main`.
- Never resolve target drift with `git merge -s ours` or by resetting
  `target/main`. Merge the snapshot.
- Never rewrite or hand-edit `refs/remotes/target/main`, and never amend or edit
  a snapshot commit.
- Never edit files on the target over SSH. Read-only checks are fine.
- One writer at a time. Do not start a second push while one is running.

## Recognize the outcome

| Git says | Meaning | Action |
|---|---|---|
| `ok refs/heads/main` and `deploying N changes to <target>` | deployed | verify |
| `target has local changes: <paths>` | target drift | fetch, diff, merge, push |
| `[rejected] (non-fast-forward)` | your branch does not contain `target/main` | fetch, merge, push |
| `force pushes are not supported` | a `+` or `--force` refspec | retry without force |
| `deleting branches is not supported` | a `:<branch>` refspec | push a commit instead |
| `only refs/heads/main is deployed` | any other ref | push `main` only |

Rejections are results, not transport failures: git exits after printing them.
Only transport-level failures (SSH, lock, target read, extraction) exit
non-zero.

## Stop and ask

Stop, keep the state, and report to the operator when:

- drift appears that you cannot explain from the config repo's history;
- a non-fast-forward survives a fetch and merge;
- a lock is reported at `/tmp/tarssh-<hash>.lock` — never delete it yourself; a
  running push may own it, and a stale lock is the operator's call;
- the target is missing or unreadable, or the descriptor is incomplete;
- the target has a FIFO, socket, device node, unreadable file, or a non-UTF-8
  name (the helper names the path and refuses);
- the repository is SHA-256 (tarssh requires SHA-1);
- a tracked secret is found, or a fence change is requested to silence drift;
- the URL and `.tarssh.toml` name different hosts.

Everything except drift reconciliation and interrupted-push recovery is an
operator decision.

## Recovery

**Interrupted or failed push.** The target is half-deployed and now drifts. Do
not re-push to "fix" it and do not force. Fetch the half state, inspect it, and
reconcile:

```sh
git fetch target
git diff --stat HEAD target/main
git merge target/main
# resolve, commit, then push the reconciled commit
git push target main
```

**Rejected push.** Read the status line, run the loop (fetch → merge → push),
and use `--dry-run` when you want the same checks with no writes.

**Stale lock.** Report the path. Only after the operator confirms no push is
running may the lock directory be removed on the target.

**First use against a non-empty target.** `git fetch target` produces a root
snapshot. If the config repo also has unrelated history, reconcile the roots
only when the trees already match:

```sh
git merge -s ours --allow-unrelated-histories target/main
```

Then push. This is a cutover, not routine drift: get the operator's
confirmation first.
