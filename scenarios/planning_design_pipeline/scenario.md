# Planning & Design Pipeline Scenario

A 4-agent Planning & Design pipeline modeled on Switchyard run
`6a5ddb21-f7ac-45e4-be3a-8c98000db2d7` (documentation_robotics, issue #591
"Optimize the Regression Test Cycle", 2026-04-08, 946 s real time).

All work is discussion-based — no VCS operations, no branches, no PRs. Agents
collaborate through a shared GitHub Discussion thread. The pipeline exits when
`work_breakdown_agent` creates child sub-issues and the item is promoted to
`In Development` by the orchestrator.

## Board flow

```
Backlog → Research* → Requirements → Design → Work Breakdown → In Development (exit)
          (idea_researcher)  (business_analyst) (software_architect) (work_breakdown_agent)
          conversational      conversational      conversational        task_queue
```

`*` pipeline trigger — lock acquired when item enters `Research`. Lock is
released when item enters `In Development`.

## What it validates

1. **Discussion-only workspace**: all four agents write to a shared GitHub
   Discussion thread (`D_kwDOQaznN84Ali-E`); no code commits, no branches, no
   PRs are created at any stage.
2. **Conversational execution mode**: `idea_researcher`, `business_analyst`, and
   `software_architect` operate in `conversational` mode — multi-turn dialogue
   with feedback-wait between agent completion and column advancement.
3. **Task-queue execution mode**: `work_breakdown_agent` operates in
   `task_queue` mode — receives context files from prior agents
   (`initial_request.md`, `business_analyst_output.md`,
   `software_architect_output.md`) and executes as a single atomic task.
4. **Inter-stage context file handoff**: structured markdown output files are
   passed forward through the pipeline, enabling `work_breakdown_agent` to
   produce grounded sub-issues.
5. **Sub-issue creation as exit trigger**: `work_breakdown_agent` creates 5
   child sub-issues on the SDLC board; the orchestrator promotes the parent item
   to `In Development` on completion, which is the exit column.
6. **Card-move feedback mechanism**: stage advancement is driven by card-move
   detection, not human comment reply.
7. **Heavy-context agents**: `idea_researcher` (~167K tokens) and
   `software_architect` (~143K tokens) exercise large-context LLM execution;
   both require `max_tokens: 16384` in the agent config.
8. **SLA calibration from real run**: per-column SLA values are derived from
   actual Switchyard stage timings with a 2× buffer (Research: 600 s,
   Requirements: 480 s, Design: 420 s, Work Breakdown: 180 s).

## Stage timing (from benchmark)

| Stage          | Real time | Agent time | Feedback wait |
|----------------|-----------|------------|---------------|
| Research       | 322 s     | 228 s      | 92 s          |
| Requirements   | 277 s     | 35 s       | 239 s         |
| Design         | 248 s     | 196 s      | 61 s          |
| Work Breakdown | 91 s      | 49 s       | — (none)      |
| **Total**      | **938 s** |            |               |

At 100× speed multiplier: ~9.5 s simulated.

## Agents

| Agent                | Column         | Execution mode | Tools / MCP                         |
|----------------------|----------------|----------------|-------------------------------------|
| idea_researcher      | Research       | conversational | file_ops, web_search; MCP: context7 |
| business_analyst     | Requirements   | conversational | file_ops; MCP: context7             |
| software_architect   | Design         | conversational | file_ops, web_search; MCP: context7 |
| work_breakdown_agent | Work Breakdown | task_queue     | file_ops only; MCP: context7        |

## Benchmark Reference

Run `6a5ddb21-f7ac-45e4-be3a-8c98000db2d7` recorded on 2026-04-08:
- Project: `documentation_robotics` | Issue #591: "Optimize the Regression Test Cycle"
- Duration: 946 s | Discussion: `D_kwDOQaznN84Ali-E`
- Sub-issues created: 5 child issues on SDLC board
- Outcome: item graduated to `In Development`; pipeline lock released

## Files

### `orchestrator/` — always applied (Codetoreum-owned config)

| File                | Owns                                                      |
|---------------------|-----------------------------------------------------------|
| `simulation.yaml`   | Clock speed (100×), scenario identity, benchmark metadata |
| `agents.yaml`       | 4 planning-phase agent configurations                     |
| `workflows.yaml`    | 4-stage planning workflow definition                      |
| `board_policy.yaml` | Column triggers, SLAs, failure routing                    |

### `external/` — simulation only (data owned by external system)

| File                   | Owns                                              |
|------------------------|---------------------------------------------------|
| `projects.yaml`        | documentation_robotics project                    |
| `work_items.yaml`      | Issue #591 "Optimize the Regression Test Cycle"   |
| `board_structure.yaml` | 6-column Planning & Design board                  |
| `board_placements.yaml`| Issue #591 starts in Backlog                      |
