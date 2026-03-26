# Stress Test Scenario

High-volume scenario for throughput and scalability testing. Uses a minimal
three-column board and `auto_advance: true` to process as many items as
possible as fast as possible.

## Board flow

```
Backlog → In Progress* → Done
          (worker)
```

`*` pipeline trigger. Single automated column with no failure routing and no
SLA escalation — the goal is maximum throughput, not comprehensive error
handling.

## What it validates

- **Concurrent pipeline execution**: multiple work items moving through
  `In Progress` simultaneously; validates that lock acquisition, agent
  dispatch, and auto-progression are safe under concurrent load.
- **auto_advance mode**: the simulation clock advances automatically without
  manual calls to `advance_time()`, exercising the clock's self-driving path.
- **Memory and resource management**: 10 items in this YAML; extend with
  `seeder.create_work_items(count=90)` to reach the target of 100. The system
  should process all items without growing unboundedly in memory or event
  queue depth.
- **Event bus throughput**: each item emits multiple domain events
  (`WorkItemColumnChangedEvent`, lock events, agent execution events). Validates
  that the event bus does not drop or reorder events under load.
- **Baseline performance benchmark**: simulated duration ~30 seconds wall-clock
  at 100× speed. Regressions in scheduler or event-handler efficiency show up
  as this number growing.

## Agents

| Agent     | Column      | Role                               |
|-----------|-------------|------------------------------------|
| worker    | In Progress | Processes work items               |
| validator | (workflow)  | Validates output (workflow stage)  |

> `validator` is defined in the workflow stage model but the board only has
> one automated column (`worker`). The workflow stage can be extended to a
> two-column board when two-stage throughput testing is needed.

## Extending to 100 items

The YAML seeds 10 items. To run the full stress test:

```python
seeder = SimulationDataSeeder(bootstrap, ...)
await seeder.seed_from_yaml(Path("scenarios/stress_test"))
await seeder.create_work_items(count=90, project_name="stress-test-project")
```

## Files

### `orchestrator/` — always applied (Codetoreum-owned config)

| File                 | Owns                                                    |
|----------------------|---------------------------------------------------------|
| `simulation.yaml`    | Clock speed (100×), `auto_advance: true`, identity      |
| `agents.yaml`        | Worker and validator agent configurations               |
| `workflows.yaml`     | 2-stage parallel workflow                               |
| `board_policy.yaml`  | Column triggers, SLAs (minimal — no failure routing)    |

### `external/` — simulation only (data owned by external system)

| File                   | Owns                                              |
|------------------------|---------------------------------------------------|
| `projects.yaml`        | Stress-test project                               |
| `work_items.yaml`      | 10 representative items (of 100 target)           |
| `board_structure.yaml` | 3-column board id, name, and column list          |
| `board_placements.yaml`| Initial work item column placements               |
