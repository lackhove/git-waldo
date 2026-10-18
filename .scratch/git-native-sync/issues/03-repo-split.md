# Split the repo: tool here, fresh config repo there

Type: grilling
Status: open
Blocked by: 02

## Question

Turn ADR-0002 into a concrete plan, precise enough to execute in one pass:

- **What moves where**: `config/**` leaves this repo for a new repo whose root *is* the target's config dir; `the bridge` stays (to be replaced); which of `AGENTS.md`, `docs/agents/`, `docs/adr/`, `GLOSSARY.md`, `skills-lock.json` stay with the tool and which are rewritten for the config repo.
- **The config repo's seed commit**: one import commit containing the current mirrored set; which files are furniture (`.gitignore`, workflow docs, `.tarssh.toml` example) and which are content; whether the target's `.gitignore` is committed as-is at the repo root.
- **Ignore rules**: `config/.gitignore` becomes the root `.gitignore`; it must also ignore the tool's target config. Anything else to add or drop now that ignored files are the only fence around secrets and runtime state?
- **This repo after the split**: delete `config/`, rewording of `AGENTS.md`, and what the replacement tool is called alongside the naming decision from 02.
- **Ordering**: does the split land before or after the helper exists, and can the old `the bridge` keep running against either layout in the meantime?
