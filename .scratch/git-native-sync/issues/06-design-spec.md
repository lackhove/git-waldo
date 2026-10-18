# Write the handoff spec

Type: task
Status: open
Blocked by: 02, 03, 04, 05

## Question

Consolidate everything into the artifact the implementation session starts from:

- `docs/design/` spec: the model (ADR-0001), the split (ADR-0002), the helper's protocol surface, the target invariants, the CLI/URL surface, and the failure modes — with each decision traceable to its ticket.
- Update `AGENTS.md` in this repo for the tool, and draft the config repo's `AGENTS.md` (workflow: fetch, merge, commit, push; manual `the config check` and reload).
- Final `GLOSSARY.md` pass: every term the spec uses is defined, and no synonym drift.
- Verify no decision contradicts an ADR; surface anything that does rather than silently overriding it.
