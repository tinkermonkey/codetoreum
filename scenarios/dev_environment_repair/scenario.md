# Dev Environment Repair Scenario

Full SDLC pipeline culminating in a repair cycle that rebuilds the development
environment and iterates through test-fix-validate loops until all tests pass.
Derived from Switchyard benchmark run `db1dbf2a` (context-studio issue #376,
2026-03-27).

## Board flow

```
Backlog → Ready* → Development → Code Review → Testing (repair cycle) → Staged
                   (senior_se)   (code_reviewer)  (qa_engineer + repair agents)
                                      │                   │
                                 on_failure          on_failure
                                 → Development       → Development
                                                          │
                                                    sla_escalation
                                                    → Backlog
```

`*` pipeline trigger — lock acquired when item enters `Ready`. Lock held across
all automated columns and released when item enters `Staged`.

## What it validates

- **Full pipeline with repair cycle**: four consecutive automated columns,
  each handing off to the next via `auto_progress_on_completion`, with the
  Testing column triggering a repair cycle instead of a simple agent pass.
- **`repair_cycle_agents` specialization**: six sub-tasks each dispatched to
  the optimal specialist — `qa_engineer` for test execution and environment
  verification, `senior_software_engineer` for code fixes and systemic
  analysis, `devops_engineer` for environment rebuild.
- **Lock spanning a full pipeline**: pipeline lock is acquired at `Ready` and
  not released until `Staged`, covering the entire Development → Code Review →
  Testing → repair cycle path.
- **Code Review failure routing**: `on_failure_column: Development` sends items
  back for rework rather than to Backlog, modelling reviewer-found issues.
- **Testing failure routing**: `on_failure_column: Development` for
  unrecoverable test failures (exhausted repair cycle); `sla_escalation_column:
  Backlog` for stalled items.
- **Staged as post-repair human gate**: repair cycle deposits items in `Staged`
  (not `Done`) — a human must take the next action before the item is complete.
- **Local/host-mode agents**: `dev_environment_setup` and
  `dev_environment_verifier` are registered with `execution_mode: local` in
  metadata, modelling agents that run on the orchestrator host rather than
  inside a Docker container.

## Agents

| Agent | Column | Role |
|---|---|---|
| senior_software_engineer | Development | Implements features; handles `code_fix`, `systemic_analysis`, `systemic_fix` in repair cycle |
| code_reviewer | Code Review | Reviews code; approval → Testing, rejection → Development |
| qa_engineer | Testing | Runs tests; handles `test_execution` and `env_verification` in repair cycle |
| devops_engineer | (repair cycle) | Handles `env_rebuild` sub-task — rebuilds Docker image |
| dev_environment_setup | (local, repair cycle) | Sets up dev environment on orchestrator host; has Docker socket access |
| dev_environment_verifier | (local, repair cycle) | Verifies rebuilt environment health; gates repair cycle completion |

## Repair Cycle Sub-Task Routing

| Sub-task | Agent | What it does |
|---|---|---|
| `test_execution` | qa_engineer | Runs tests and parses results |
| `code_fix` | senior_software_engineer | Fixes code-level test failures per file |
| `systemic_analysis` | senior_software_engineer | Classifies root causes across failure set |
| `systemic_fix` | senior_software_engineer | Applies cross-cutting fixes |
| `env_rebuild` | devops_engineer | Rebuilds Dockerfile and project container |
| `env_verification` | qa_engineer | Verifies rebuilt environment can run tests |

## Benchmark Reference

Run `db1dbf2a-a0cb-413e-998c-06a8be61d902` recorded on 2026-03-27:
- Project: `context-studio` | Issue #376: "[PR Feedback] Persistence Layer"
- Duration: ~56 minutes | Board: SDLC Execution
- Phases: Development (246 s) → Code Review (4 iterations, ~20 min) → Testing
  (repair cycle container ran 34 min, ~8 sub-task iterations) → Staged
- Outcome: Repair cycle completed successfully; auto-commit triggered on exit

## Files

### `orchestrator/` — always applied (Codetoreum-owned config)

| File | Owns |
|---|---|
| `simulation.yaml` | Clock speed (100×), fidelity, scenario identity, benchmark metadata |
| `agents.yaml` | 6 agents (4 pipeline + 2 local environment agents) |
| `workflows.yaml` | 3-stage workflow (implementation → code-review → testing) |
| `board_policy.yaml` | Column chain, pipeline trigger, SLAs, failure routing, `repair_cycle_agents` |

### `external/` — simulation only (data owned by external system)

| File | Owns |
|---|---|
| `projects.yaml` | Platform-engineering project with repository URL |
| `work_items.yaml` | 2 persistence layer work items (both expect repair cycle) |
| `board_structure.yaml` | 6-column board (Backlog, Ready, Development, Code Review, Testing, Staged) |
| `board_placements.yaml` | Both items start in Backlog |
