# Tool and config are separate repositories

Status: accepted

This repository holds both the sync tool and the mirrored config under `config/`, which forces the tool to know a path prefix and forces the mirror to carry tooling files. We split them: this repository becomes the generic tool, and the config moves to a fresh repository whose root *is* the target's config directory, imported as a single commit with its own workflow docs and a gitignored target config.

## Considered options

- **Keep one repository with a `config/` prefix.** Rejected: every path mapping, every archive, and every diff carries an offset that means nothing to the target.
- **Preserve history with `git filter-repo --subdirectory-filter`.** Rejected: the history of a mirror that was rewritten wholesale by UI editors has little value, and a single import commit is honest about being a re-import.

## Consequences

- One target per config repo.
- Push archives `HEAD`, not `HEAD:config`.
- `config/.gitignore` becomes the config repo's root `.gitignore`, and its rules become the only fence around secrets and runtime state.
- The mirror workflow documentation lives in the config repo; this repo documents the tool.
