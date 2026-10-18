# tarssh

**GitOps for devices that only have SSH and busybox.**

`tarssh` is a git remote helper. It turns a directory on a minimal SSH host into
a normal git remote, so you can use plain `git fetch`, `git merge`, and
`git push` to pull the device's configuration into git and deploy changes back.

The device does **not** need git, rsync, SFTP, an agent, or a sync daemon. It
needs an SSH daemon and busybox `find` and `tar`. There is no server-side
service, no control plane, and no database: the only thing on the device is the
directory you already manage.

```text
   config repo                         minimal device
   (git)                               (no git)

   git push target main   ──────────▶  files in /etc/app
   git fetch target       ◀──────────  snapshot of /etc/app
   git merge target/main               (drift from the device)
```

## Why

Configuration for an appliance usually lives in one of two bad shapes:

- a bespoke `sync` script that copies files without history, conflict checks, or
  a way to see what changed on the device;
- a full configuration-management stack that needs an agent, a server, and more
  runtime than the device has.

`tarssh` gives you the git workflow without putting git on the device:

- **Desired state is a git repo.** Review, branch, commit, and revert like any
  other code.
- **Actual state is a snapshot.** `git fetch target` records what the device
  currently contains as `target/main`; `git merge` reconciles changes made on
  the device.
- **Deployment is a push.** Only the changed paths are written or removed.
  Files outside the delta, including runtime state and secrets, are untouched.
- **Safety is git's own.** Pushes are fast-forward-only and refuse when the
  device has drifted. No force, no branch deletion, no silent overwrite.

This is GitOps with a device as the only runtime and a workstation as the
controller. Reconciliation is a command you run, not a daemon you operate.

## How it works

1. **Fetch** reads the device's tracked files and builds a *snapshot* commit.
   The snapshot is a real commit with no human author, parented on the previous
   `target/main`. If nothing changed, no commit is made and the branch does not
   move.
2. **Merge** treats the snapshot like any other remote branch. Device-side
   edits become ordinary merges and ordinary conflicts.
3. **Push** compares the pushed commit with `target/main`, refuses if the device
   has local changes or the push is not a fast-forward, and applies exactly the
   added, modified, and deleted paths.

Only one branch is exposed: `refs/heads/main`. Tags, force pushes, branch
deletion, and extra branches are deliberately unsupported.

**The device stores no history.** It holds the current files and nothing else:
no `.git` directory, no commits, no reflog. Snapshot commits and every version
you can diff, merge, or revert live in the config repo on your workstation. A
push sends the current delta, not the history behind it.

## Requirements

On your workstation:

- `git`
- Python 3.11+
- [`uv`](https://docs.astral.sh/uv/) to install the helper
- SSH access to the device

On the device:

- an SSH daemon
- busybox `find`, `tar`, `rm`, and `mkdir`
- write access to the target directory

## Install

From a checkout of this repository:

```sh
uv tool install .
```

The distribution name is `tarssh`, so once it is published the same install is
`uv tool install tarssh`.

Make sure the tool directory is on `PATH` so git can discover the helper:

```sh
export PATH="$HOME/.local/bin:$PATH"   # add to your shell profile
git-remote-tarssh --version
```

Git finds helpers as `git-remote-<scheme>`; the executable is
`git-remote-tarssh`.

## Quick start

In the repository that should own the device's configuration:

```sh
git init -b main
# ...add the files you want the device to have...

git-remote-tarssh --config
```

`--config` asks for the SSH user, host, port, and target directory, writes
`.tarssh.toml`, and registers the remote as `target`.

The first push creates the target directory if it is missing and deploys the
whole commit:

```sh
git add .
git commit -m "Initial configuration"
git push -u target main
```

After that, the everyday loop is ordinary git:

```sh
git fetch target                  # record the device's current state
git diff --stat main target/main  # see what changed on the device
git merge target/main             # reconcile device-side changes
# ...edit, commit...
git push target main              # deploy the delta
```

Because `-u` set the upstream, bare `git pull` and `git push` work too.

## The target descriptor

`.tarssh.toml` lives at the repository root and is gitignored:

```toml
user = "root"
host = "192.168.1.20"
ssh_port = 22222
dir = "/mnt/data/supervisor/homeassistant"
```

A committed `.tarssh.example.toml` is the furniture new clones copy. Fields are
resolved independently, most specific first:

1. `TARSSH_USER`, `TARSSH_HOST`, `TARSSH_SSH_PORT`, `TARSSH_DIR`
2. the remote URL
3. `.tarssh.toml`
4. defaults: local username, port 22; `dir` is required

A full URL carries its own target and is useful for one-off inspection or
retargeting a clone:

```sh
git ls-remote 'tarssh://root@192.168.1.20:22222/mnt/data/supervisor/homeassistant'
git remote set-url target 'tarssh://root@192.168.1.20:22222/mnt/data/supervisor/homeassistant'
```

When a full URL and `.tarssh.toml` disagree, the helper uses the more specific
value and prints one warning naming both. The committed file only has to be
right for new clones.

## The fence

`.gitignore` is the **fence**. It is tracked, deploys to the device like any
other file, and is the only thing separating configuration from runtime state
and secrets.

- A path ignored at `target/main` or at `HEAD` is invisible to the helper: it is
  never read into a snapshot and never written by a push.
- Ignored files on the device survive pushes.
- Put secrets, databases, logs, caches, and generated state in `.gitignore`;
  keep the files you want to review and recover in git.

```gitignore
secrets.yaml
*.log
*.db*
.storage/*
runtime/
.tarssh.toml
```

## What a push will and will not do

| Case | Result |
|---|---|
| Fast-forward, clean target | `ok`, delta deployed |
| Device has local changes | `[remote rejected] target has local changes: …` |
| Non-fast-forward | `[rejected] (non-fast-forward)` |
| `+` / force | `[remote rejected] force pushes are not supported` |
| `:<branch>` deletion | `[remote rejected] deleting branches is not supported` |
| Any ref other than `refs/heads/main` | `[remote rejected] only refs/heads/main is deployed` |
| `--dry-run` | Same counts and statuses; nothing written |

A push writes only the delta. Untracked and ignored device files survive, and
directories emptied by a deletion are left in place. Regular files are stored
as `0644` or `0755`; symlinks are preserved as links and never followed.
FIFOs, sockets, device nodes, unreadable files, and non-UTF-8 names are refused
by name rather than silently dropped.

## Good fit

- Home Assistant and other appliance configuration directories
- Raspberry Pi, NAS, router, and embedded-Linux configuration
- IoT gateways and field devices where installing agents is unwelcome
- Any host where the only sane transport is SSH and the only file tools are
  busybox

## Limits

- **Fast-forward only.** Rebase or merge locally; there is no force push and no
  branch deletion.
- **One branch.** The device exposes `refs/heads/main`; tags and extra branches
  are out of scope.
- **Configuration-sized trees.** Every fetch reads the target's non-ignored
  files to build the snapshot. It is designed for configuration, not for
  syncing large media or database files.
- **SHA-1 repositories.** A SHA-256 config repo is rejected at startup.
- **Unix-like target.** The target must provide the busybox tools above; this is
  not a Windows or arbitrary-SFTP transport.

## Development

```sh
scripts/check        # pytest, mypy, ruff check, ruff format --check
uv run pre-commit install
```

Tests drive the helper against a fake busybox-only target over a localhost SSH
seam; they never need a live device. See `tests/README.md`.

Design and decisions:

- `docs/design/spec.md` — the settled behaviour
- `docs/adr/` — the target-is-a-git-remote model and the tool/config split
- `docs/agents/git-helper-protocol.md` — the git-side protocol facts
- `docs/agents/cutover.md` — pointing a config repo at a live target
