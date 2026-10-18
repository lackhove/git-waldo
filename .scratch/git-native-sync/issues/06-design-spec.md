# Write the handoff spec

Type: task
Status: resolved
Blocked by: 02, 03, 04, 05

## Question

Consolidate everything into the artifact the implementation session starts from:

- `docs/design/` spec: the model (ADR-0001), the split (ADR-0002), the helper's protocol surface, the target invariants, the CLI/URL surface, and the failure modes — with each decision traceable to its ticket.
- Update `AGENTS.md` in this repo for the tool, and draft the config repo's `AGENTS.md` (workflow: fetch, merge, commit, push; manual `the config check` and reload).
- Final `GLOSSARY.md` pass: every term the spec uses is defined, and no synonym drift.
- Verify no decision contradicts an ADR; surface anything that does rather than silently overriding it.

## Answer

Deliverables:

- `docs/design/spec.md` — the handoff spec: model, vocabulary, URL/remote/descriptor surface with precedence, the full protocol surface (including rejection tokens and the `?` correction), snapshot construction, read order, path types, push order with lock and clean check, first use, stderr reporting, deliberate absences, the split summary, and a traceability table mapping every decision to its ADR or ticket.
- `docs/design/agents-tool.md` — the tool repo's `AGENTS.md`, ready to install when the split executes.
- `docs/design/agents-config.md` — the config repo's `AGENTS.md` as furniture: fetch/merge/commit/push workflow, manual `the config check` and reload, the moved the application gotchas, the fence explained.

The live `AGENTS.md` is deliberately untouched: until ticket 03 executes, this repo still contains `config/`, and rewriting it now would describe a layout that does not exist. Both drafts carry a note saying so.

**Glossary pass.** Added `Remote helper`, `Fence`, `Target descriptor`, `Delta`, `Deploy`; every other term the spec uses already existed, and the avoid-lists cover the synonyms the spec could drift into.

**Contradictions found and resolved rather than overridden:**

1. ADR-0001's `?` claim — corrected in the ADR (tickets 01, 04).
2. Three sources of truth for host/port/path (URL, `.tarssh.toml`, `TARSSH_*`) with no precedence — settled here (Q7b): `TARSSH_*` > URL > `.tarssh.toml` > defaults, per field, with a stderr warning when the URL and the file disagree.
3. ADR-0002's "single import commit with its own workflow docs" vs ticket 03's two commits — ADR-0002 gained a refinement note: import first (tree-identical to the target), furniture second.
4. A bare `tarssh:` would never reach the helper — git parses it as scp-like `host:path` and tries SSH to a host named `tarssh` (verified on git 2.56). The descriptor-from-file form is `tarssh::`, written by `--config`; a full `tarssh://…` URL remains the retargeting and one-off form.

**Known gaps left to their own work** (unchanged, see `map.md` → Not yet specified): packaging and version reporting, a protocol-level test harness with a fake busybox-only target, cost on large targets, and behaviour when the installed tool and a config repo disagree about the protocol.
