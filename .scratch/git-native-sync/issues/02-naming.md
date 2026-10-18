# Naming: tool repo, helper binary, remote, config file

Type: grilling
Status: open
Blocked by: —

## Question

The tool is generic and must not be named after the application. Settle, together:

- the **tool repo** name (currently `config-repo`, which must change);
- the **helper executable** name, which is not free-form: git only finds it as `git-remote-<name>`, so this fixes the URL scheme users type (`<name>::host:/path` or `<name>://host/path`);
- the **default remote name** used in `refs/remotes/<remote>/main` and in `git push <remote> main` — must not be `legacy`;
- the **config file** name (provisionally `.tarssh.toml`);
- whether the config repo's default branch is `main` (it must be, if the helper assumes a branch).

Ticket 01 may surface existing tools whose names we would collide with; read its findings before settling. Ticket 03 cannot proceed without the repo and helper names.
