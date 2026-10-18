# Naming: tool repo, helper binary, remote, config file

Type: grilling
Status: resolved
Blocked by: —

## Question

The tool is generic and must not be named after the application. Settle, together:

- the **tool repo** name (currently `config-repo`, which must change);
- the **helper executable** name, which is not free-form: git only finds it as `git-remote-<name>`, so this fixes the URL scheme users type (`<name>::host:/path` or `<name>://host/path`);
- the **default remote name** used in `refs/remotes/<remote>/main` and in `git push <remote> main` — must not be `legacy`;
- the **config file** name (provisionally `.tarssh.toml`);
- whether the config repo's default branch is `main` (it must be, if the helper assumes a branch).

Ticket 01 may surface existing tools whose names we would collide with; read its findings before settling. Ticket 03 cannot proceed without the repo and helper names.

## Answer

Settled in three rounds.

**The name.** The tool is `tarssh`: the helper binary is `git-remote-tarssh`, git finds it on `$PATH`, and the URL scheme is `tarssh://[user@]host[:port]/path`. Only the `scheme://` form is accepted — no scp-style `tarssh::host:/path` — because the target is reached on a non-standard port (22222) and `ssh://`-shaped URLs are what people already know. `tarssh` was chosen over `busybox` (would collide with the BusyBox project and muddy search), `outpost`/`courier` (evocative but unexplained) and `nogit`: it names the mechanism that actually distinguishes it from `ssh://`.

**The remote.** Every config repo names its target `target`: `refs/remotes/target/main`, `git push target main`, `git diff target/main HEAD`. Not `tarssh`: that records the transport in the ref namespace instead of the destination, and would need migrating if the mechanism ever changed. Not `origin`, which would squat the conventional name. Not `legacy`.

**The branch.** The target exposes exactly one branch, `refs/heads/main`, fixed; the config repo's default branch is likewise `main`. No discovery, no config key — there is nothing on the target to read a branch name from. What `list` advertises and whether `HEAD` is advertised as a symref belongs to ticket 04.

**The config.** `.tarssh.toml` at the config repo root, gitignored, holding `host`, `ssh_port`, `dir`; a committed `.tarssh.example.toml` is furniture. One-off overrides are `TARSSH_HOST`, `TARSSH_SSH_PORT`, `TARSSH_DIR`.

**The executables.** One binary, `git-remote-tarssh`, and no separate `tarssh` command. Tool-mode verbs are double-dash prefixed — `git-remote-tarssh --config` (interactive writer for `.tarssh.toml`) and `--version` — and the rule is that a leading `-` in `argv[1]` always means a tool verb, never a remote: git's helper invocations pass a remote name and a URL, so the prefix makes the two modes unambiguous. This keeps every sync operation a plain git command, per ADR-0001, while still sparing the operator from hand-writing TOML once.

**The repositories.** The tool repo is `tarssh`, and this checkout (currently `~/code/config-repo`) becomes `~/code/tarssh`. The freed name `config-repo` is taken by the new config repo, whose root is the target's config directory. The distribution name is `tarssh` as well, so `uv tool install tarssh` provides `git-remote-tarssh`.

**Collision check.** No `git-remote-<candidate>` exists and no candidate is a git built-in. `tarssh` is, however, an SSH tarpit on crates.io with the same domain — accepted deliberately: the only namespace that can break the tool is `git-remote-tarssh` on `$PATH`, and it is free; PyPI is free too, so `uv tool install tarssh` works. `tartransport` stays the recorded fallback if that ever changes.

## Comments

**Collision check (background run, after the answer above).** No candidate is a git built-in, and no `git-remote-<candidate>` exists anywhere. But `tarssh` is occupied outside git: [Freaky/tarssh](https://github.com/Freaky/tarssh), an SSH tarpit (~8.4k crates.io downloads) — same domain, different ecosystem. PyPI is free for `tarssh`, `tartransport` and `hinterland`; `tartransport` is free everywhere.

Two facts from the same run that outlive this ticket and belong to 04:

- An external helper does **not** shadow a built-in transport for `<scheme>://`; git only consults `git-remote-<name>` for schemes it cannot handle itself. The `::` form always invokes the helper.
- Lookup is `$(git --exec-path)` before `$PATH`, so bundled curl helpers (`http`, `https`, `ftp`, `ftps`) can never be shadowed.

Recorded fallback was `tartransport`; the name was reopened rather than changed silently.
