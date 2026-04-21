# Planning & Design Review Cycle Scenario

Automated PR code review and requirements verification workflow integrated into the Planning & Design board.
Derived from Switchyard benchmark runs `854460d9` and `fe4fa87f` (requirements_verification and review_cycle workflows).

## Board flow

```
Backlog (manual)
→ In Review (automated, PR REVIEW CYCLE)
  │
  ├─ on_issues_found → In Development
  │  (6 sub-issues created with pr-review label)
  │
  └─ on_approved → Done
```

## What it validates

- **PR Review Cycle integration**: Automated code review triggered when item enters "In Review" column
- **Phase execution**: Four phases in order:
  - Phase 1: Code Review (pr_code_reviewer agent)
  - Phase 2.1: Verification against parent_issue context
  - Phase 3: CI check validation
  - Phase 4: Consolidation of findings
- **Issues-found path**: Review identifies issues → creates 6 sub-issues on SDLC Execution board → moves parent to In Development
- **Approved path**: Review finds no issues → moves parent to Done without creating sub-issues
- **Sub-issue creation**: All created sub-issues carry `pr-review` label and reference parent issue

## Test Paths

### Path 1: Issues Found (Switchyard run 854460d9)
- MockPRReviewCycleAdapter configured with `ISSUES_FOUND` outcome
- 6 findings (at least 1 critical)
- Asserts:
  - `PRReviewCycleStartedEvent` fired
  - Phase events in order (Phase 1 → 2.1 → 3 → 4)
  - `PRReviewCycleSubIssuesCreatedEvent` with count=6
  - `PRReviewCycleIssuesFoundEvent` with critical >= 1
  - Parent item moved to "In Development"
  - 6 child work items created with `parent_issue_id` set and `pr-review` label

### Path 2: Approved (Switchyard run fe4fa87f)
- MockPRReviewCycleAdapter configured with `set_approved_immediately()`
- Asserts:
  - `PRReviewCycleApprovedEvent` present
  - `PRReviewCycleSubIssuesCreatedEvent` absent (no sub-issues created)
  - Parent item moved to "Done"

## Agents

| Agent | Phase |
|---|---|
| pr_code_reviewer | Phase 1: Code Review |
| requirements_verifier | Phase 2: Verification |

## Benchmark Reference

Runs `854460d9` and `fe4fa87f` (requirements_verification workflow):
- Project: context-studio
- Board: Planning & Design
- Duration: ~2-5 minutes per cycle (depending on findings)
- Outcome: Sub-issues created or approved; item progresses accordingly

## Files

### `orchestrator/` — always applied (Codetoreum-owned config)

| File | Owns |
|---|---|
| `simulation.yaml` | Clock speed (100×), scenario identity, benchmark metadata |
| `board_policy.yaml` | Column chain, pipeline trigger, PR review cycle config |
| `agents.yaml` | 2 agents (pr_code_reviewer, requirements_verifier) |
| `workflows.yaml` | Single-stage workflow (review) |

### `external/` — simulation only (data owned by external system)

| File | Owns |
|---|---|
| `projects.yaml` | Planning & Design project |
| `work_items.yaml` | 1 work item for review |
| `board_structure.yaml` | 3-column board (Backlog, In Review, Done) |
| `board_placements.yaml` | Item starts in Backlog |
