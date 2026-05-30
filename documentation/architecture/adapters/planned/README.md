---
required_sections:
  - "## Purpose"
  - "## Current Contents"
  - "## Promotion Criteria"
  - "## Documentation Standards"
applies_to: "documentation/architecture/adapters/planned/README.md"
---

# Planned Adapters

> **Status**: This directory holds **design-only** adapter specifications. Each document describes an adapter whose shape has been designed but whose implementation has not yet landed.

## Purpose

The `planned/` directory exists because the `ICodingAgent` port redesign (DEF-015 in `bootstrap/ARCHITECTURE.md` §9) was driven by design pressure from approaching `GitHubCopilotAdapter` and `CodexAdapter` work. Phase D9 of the redesign requires that the port shape — proven against Claude Code through D1–D7 — be **validated against the other two target adapters before more code locks in the current shape**.

Validating the shape means writing the design specs for those adapters, mapping their vendor surfaces onto the new ports and the `CodingAgent*` event family, and surfacing any port-shape gaps now rather than after a second adapter has been built. This directory is where those specs live.

A document in `planned/` is a **future contract**: once the corresponding adapter's implementation cycle begins, the document either moves to `production/` (with refinements absorbed) or is rewritten as the implementation reveals new realities. Until then, the document is the canonical spec the implementation will be measured against.

## Current Contents

| Document | Adapter | Port | Status |
|---|---|---|---|
| `github-copilot-adapter.md` | `GitHubCopilotAdapter` | `ICodingAgent` (API mode) | Designed (D9). Implementation pending; target 6–8 weeks per proposal §Q6. |
| `codex-adapter.md` | `CodexAdapter` | `ICodingAgent` (CONTAINERIZED, HOST modes) | Designed (D9). Implementation pending; target 6–8 weeks per proposal §Q6. |
| `coding-agent-port-validation.md` | (Meta-doc) | All three target adapters | Validation summary — does `ICodingAgent` hold across Claude Code, Copilot, Codex? Surfaces shape gaps and recommends port changes if any. |

## Promotion Criteria

A `planned/` document moves to `production/` when:

1. The corresponding adapter has landed in `src/codetoreum/adapters/secondary/` with full test coverage (unit + contract + integration).
2. Bootstrap validation has exercised the adapter end-to-end (analogous to D7 for `ClaudeCodeAdapter`).
3. Any port-shape changes surfaced during implementation have been merged back into `ICodingAgent` / `IPromptBuilder` / the `CodingAgent*` event family.
4. The corresponding implementation-doc section in `documentation/implementations/` has been updated.

## Documentation Standards

Planned-adapter documents follow the same [Adapter Template](../../templates/adapter-template.md) used by `production/` docs, with one addition: **every speculative claim must be flagged**. Where official vendor documentation is sparse or beta-only, the spec should explicitly mark the assumption ("based on the limited Copilot Workspace beta docs; verify before D1 of the Copilot adapter cycle"). This avoids freezing speculative behaviour into the design.

Required sections (per the template, plus the planned-adapter additions in **bold**):

1. **Purpose** — one paragraph: who this adapter wraps, why
2. **Port Implementation** — `supported_invocation_modes()`, `execute()` shape, DI dependencies, credentials
3. **Invocation Modes** — modes supported and how each is implemented
4. **Internal Structure** — strategies / parser / renderer split (or simpler shape)
5. **Event Mapping** — vendor's output schema → `CodingAgent*` events; **flag mappings that don't fit cleanly**
6. **Configuration** — what `mode_config` keys this adapter consumes
7. **Resilience** — which `ResilientCodingAgentDecorator` behaviours apply
8. **Open Risks** — adapter-specific concerns
9. **Port-Shape Critique** — what (if anything) about this adapter doesn't fit `ICodingAgent` cleanly
10. **Diagram** — Mermaid class diagram (mirrors `production/` style)

Each document references the proposal at `~/.claude/plans/coding-agent-port-redesign.md` and the validation summary in this directory.

## Cross-References

- **Production adapters**: [`../production/`](../production/) — adapters that have landed and been validated
- **Reference implementation**: [`../production/claude-code-adapter.md`](../production/claude-code-adapter.md) — the template structure for all `ICodingAgent` adapter specs
- **Port specification**: [`../../ports/output/core-system.md#icodingagent`](../../ports/output/core-system.md) — the `ICodingAgent` interface
- **Prompt builder port**: [`../../ports/output/domain-services.md#ipromptbuilder`](../../ports/output/domain-services.md) — the `IPromptBuilder` interface
- **Event catalog**: [`../../domain/events.md#coding-agent-context`](../../domain/events.md) — the `CodingAgent*` event family
- **Source code**: `src/codetoreum/ports/output/coding_agent.py`, `src/codetoreum/ports/output/prompt_builder.py`, `src/codetoreum/domain/events/coding_agent_events.py`
- **Design proposal**: `~/.claude/plans/coding-agent-port-redesign.md`
- **Phase D9 entry**: `bootstrap/ARCHITECTURE.md` §9, DEF-015
