# Migrate a config repo from tarssh to git-waldo

One-off runbook for the single existing config repo. The rename has no
compatibility shim, so the old and new names do not coexist in the helper.
Work through the steps in this order.

## 1. Confirm no push is in flight

The target-side lock path changes from `/tmp/tarssh-<hash>.lock` to
`/tmp/waldo-<hash>.lock`, so an old and a new helper would not exclude each
other.

- No local helper process is running:

  ```sh
  pgrep -af 'git-remote-(waldo|tarssh)'
  ```

  The command must print nothing.
- No lock is held on the device. Using the host and port from the descriptor:

  ```sh
  ssh -p <port> <user>@<host> \
    'ls -d /tmp/tarssh-*.lock /tmp/waldo-*.lock 2>/dev/null'
  ```

  The command must print nothing. If a lock exists, stop and get the
  operator's decision; never delete a lock speculatively.

## 2. Install git-waldo and remove the old distribution

From the renamed tool checkout:

```sh
uv tool install --force .
uv tool uninstall tarssh   # ignore "not installed"
command -v git-remote-waldo
git-remote-waldo --version
```

`command -v` must name the new executable, and `--version` must mention
`git-waldo`.

## 3. Retarget the remote

In the config repo:

```sh
git remote get-url target
git remote set-url target waldo::   # or: git remote add target waldo::
```

The old `tarssh::` remote would fail at git's transport lookup, because no
`git-remote-tarssh` exists any more. Do not add an alias.

## 4. Rename the descriptor and its example

```sh
mv .tarssh.toml .waldo.toml
git mv .tarssh.example.toml .waldo.example.toml
```

Edit `.gitignore`: replace `.tarssh.toml` with `.waldo.toml`, and replace
`!.tarssh.example.toml` with `!.waldo.example.toml`. Keep
`!.tarssh.example.toml` as a temporary exception for the migration push (see
step 9). Without it, the new fence hides the old example before the push can
delete it, and the clean check reports it as drift.

Check that `git status --short` shows only the intended furniture change.

## 5. Replace the copied skill and update the config repo docs

The config repo holds a copy, not a symlink:

```sh
rm -rf skills/tarssh
cp -R /path/to/git-waldo/skills/waldo skills/waldo
```

If the config repo instead keeps project skills under `.agents/skills/`, use
that directory in both commands.

If an agent-level skill symlink points at the old directory, remove it and link
the new one:

```sh
ln -s /path/to/git-waldo/skills/waldo ~/.agents/skills/waldo
```

Update the config repo's `AGENTS.md` for the new command names, descriptor and
environment variables.

## 6. Fetch and prove the target has not drifted

Do this before committing the migration: `HEAD` is still the commit the target
was last synced from.

```sh
git fetch target
git diff --stat HEAD target/main
```

The diff must be empty. If it is not, stop: fetch and reconcile the drift
normally before pushing anything. A non-empty diff is real device-side change,
not a rename artifact.

## 7. Commit the migration

```sh
git add -A
git status --short
git commit -m "Rename the target tool to git-waldo"
```

The descriptor itself is gitignored; only the example, the fence, the skill and
`AGENTS.md` belong in this commit.

## 8. Dry run, then push

```sh
git push --dry-run target main
git push target main
```

The dry run must report the same checks and statuses as the real push. The
empty diff in step 6 is the drift gate; after the push git updates
`target/main` to the pushed commit, so a later `git diff --stat HEAD target/main`
is expected to be empty without proving anything new.

The lock taken during the push must be named
`/tmp/waldo-<16 hex of the target path>.lock`; no `tarssh` lock should remain.

## 9. Remove the temporary fence exception

The old example is now deleted from the target, so it no longer needs to stay
visible. Remove the `!.tarssh.example.toml` line and commit the cleanup:

```sh
git add .gitignore
git commit -m "Remove the temporary fence exception for the old example"
git fetch target
git diff --stat HEAD target/main
git push --dry-run target main
git push target main
```

Finish with the drift gate again:

```sh
git fetch target
git diff --stat HEAD target/main    # must be empty
```

## Failure handling

- Do not force, do not edit the target over SSH, and do not recreate the old
  helper as a workaround.
- If the fetch or push fails, keep the state, report the exact error, and stop.
  The old scheme failing at transport lookup is expected and is fixed by step 3,
  not by an alias.
- Existing snapshot commits keep their old ident. That is history; do not
  rewrite it.
