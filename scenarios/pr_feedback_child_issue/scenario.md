# PR Feedback Child Issue Scenario

A "[PR Feedback]" child issue that inherits its parent's feature branch, is
dispatched via the lock-release queue (not immediately), runs a 1-iteration
automated code review cycle (approved on first pass), then a 4-type sequential
repair cycle (compilation → unit → integration → ci), all passing on the first
attempt. Derived from Switchyard run `5d4a562b` (context-library issue #438,
2026-04-12, ~15 minutes).

## Board flow

```
Backlog → Ready* → Development → Code Review → Testing (repair cycle) → Staged
          (lock)   (senior_se)   (code_reviewer)  (qa_engineer + repair agents)
                                      │                   │
                                 on_failure          on_failure
                                 → Development       → Development
```

`*` pipeline trigger — lock acquired when item enters `Ready`. Lock is held
across all automated columns and released when item enters `Staged`. The work
item enters `Ready` via the lock-release queue (queued dispatch), not an
immediate trigger.

## What it validates

1. **PR-feedback child issue dispatched via queue**: item enters `Ready` through
   the lock-release queue rather than immediate promotion, modeling the
   queue-based dispatch observed in the Switchyard benchmark.
2. **Parent branch inheritance**: the child issue (#438) works on the parent's
   feature branch (`feature/issue-415-feat-coordinated-adapter-rese`) rather
   than creating a new branch.
3. **1-iteration code review approved on first pass**: `code_reviewer` completes
   a single review iteration with approval, routing directly to Testing without
   any rejection loops.
4. **4-type sequential repair cycle (all first-attempt passes)**: Testing column
   triggers a repair cycle with four test types in order — compilation, unit,
   integration, ci — each passing on the first attempt (no retry iterations).
5. **Tools restriction on code_reviewer**: `code_reviewer` is declared without
   `web_search` or playwright MCP, validating that tool sets are per-agent and
   not globally inherited.
6. **Lock spanning full pipeline**: pipeline lock acquired at `Ready`, held
   across Development → Code Review → Testing → repair cycle, released at
   `Staged`.
7. **Repair cycle failure routing**: `on_failure_column: Development` for
   unrecoverable repair cycle failures — not Backlog.
8. **Staged as post-repair human gate**: repair cycle deposits item in `Staged`;
   human action required before item is complete.

## Agents

| Agent | Column | Tools / MCP | Role |
|---|---|---|---|
| senior_software_engineer | Development, repair cycle | file_operations, git_integration, web_search; MCP: context7 + playwright | Implements PR feedback changes; handles `code_fix`, `systemic_analysis`, `systemic_fix` in repair cycle |
| code_reviewer | Code Review | file_operations, git_integration ONLY (no web_search, no playwright); MCP: context7 only | Reviews code; 1-iteration approval → Testing |
| qa_engineer | Testing | — | Runs tests; handles `test_execution` and `env_verification` in repair cycle |

## Repair Cycle Sub-Task Routing

| Sub-task | Agent | What it does |
|---|---|---|
| `test_execution` | qa_engineer | Runs tests and parses results |
| `code_fix` | senior_software_engineer | Fixes code-level test failures per file |
| `systemic_analysis` | senior_software_engineer | Classifies root causes across failure set |
| `systemic_fix` | senior_software_engineer | Applies cross-cutting fixes |

> Note: `env_rebuild` and `env_verification` sub-tasks are not assigned — this
> scenario's repair cycle is code-only; no environment rebuild is needed.
> The repair cycle test types are compilation, unit, integration, and ci —
> all passing on the first attempt.

## Benchmark Reference

Run `5d4a562b-39bc-49f9-a5d2-0861868e76c9` recorded on 2026-04-12:
- Project: `context-library` | Issue #438: "[PR Feedback] Test Coverage Gaps"
- Parent issue: #415 (branch: `feature/issue-415-feat-coordinated-adapter-rese`)
- Duration: ~15 minutes | commit_policy: auto
- Phases: Development → Code Review (1 iteration, approved) → Testing (repair
  cycle: compilation → unit → integration → ci, all first-attempt passes) → Staged
- Outcome: All four test types passed on first attempt; auto-commit on exit

## Files

### `orchestrator/` — always applied (Codetoreum-owned config)

| File | Owns |
|---|---|
| `simulation.yaml` | Clock speed (100×), scenario identity, benchmark metadata |
| `agents.yaml` | 3 agents (senior_software_engineer, code_reviewer, qa_engineer) |
| `workflows.yaml` | 3-stage workflow (development → code-review → testing) |
| `board_policy.yaml` | Column chain, pipeline trigger, SLAs, failure routing, `repair_cycle_agents` |

### `external/` — simulation only (data owned by external system)

| File | Owns |
|---|---|
| `projects.yaml` | context-library project with repository URL |
| `work_items.yaml` | Parent issue #415 (branch anchor) + child issue #438 (active item) |
| `board_structure.yaml` | 6-column board (Backlog, Ready, Development, Code Review, Testing, Staged) |
| `board_placements.yaml` | Issue #438 starts in Backlog; #415 not placed on board |
