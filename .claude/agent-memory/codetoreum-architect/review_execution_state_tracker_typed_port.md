---
name: review-execution-state-tracker-typed-port
description: Approved design for typed ExecutionState value object on IWorkExecutionStateTracker; found a live broken import in InMemoryWorkExecutionStateTracker anticipating this exact fix
metadata:
  type: project
---

## Context (2026-09-01)

User (architect of record for this change) proposed two fixes:
1. Strip the `execution:state:{project}:{work_item_id}` key pattern out of
   `IContainerRecoveryTrackingStore`'s docstring (port) and
   `RedisContainerRecoveryTrackingStore`'s module/class docstrings (adapter) —
   that keyspace belongs to `IWorkExecutionStateTracker`, not this port.
2. Replace `IWorkExecutionStateTracker.load_state`'s `dict[str, Any] | None`
   return with a typed frozen dataclass `ExecutionState` (fields: `outcome:
   Literal["in_progress","failed"]`, `agent: str`, `reason: str | None`).

## Verdict: both approved, both are real bugs not just style preferences

### Issue 1 (docstring ownership) — MINOR/doc, confirmed
`src/codetoreum/ports/output/container_recovery_tracking_store.py` (class
docstring ~line 26) and
`src/codetoreum/adapters/secondary/redis_container_recovery_tracking_store.py`
(module docstring ~line 10) both list `execution:state:{project}:{work_item_id}`
as a key pattern this store owns. Verified by reading
`docker_container_recovery_adapter.py` end-to-end: `tracking_storage` (the
`IContainerRecoveryTrackingStore` instance) is only ever used with
`agent:container:*` and `repair_cycle:result:*` keys. The `execution:state:*`
keyspace is written exclusively by `RedisExecutionStateTracker`
(`redis_execution_state_tracker.py`, `_KEY_PREFIX = "codetoreum:execution:state"`
— note real key is prefixed with `codetoreum:`, docstring lacks the prefix, a
second minor drift). Fix: delete that line from both docstrings.

### Issue 2 (typed ExecutionState) — MAJOR, confirmed with hard evidence
Found `src/codetoreum/adapters/testing/in_memory_work_execution_state_tracker.py`
already does `from codetoreum.ports.output.work_execution_state_tracker import
(ExecutionState, IWorkExecutionStateTracker)` — but the port module (as it
stood before this fix) never defined `ExecutionState`. **This import
currently raises `ImportError`** — the simulation mock is broken today.
Worse, the mock's own body doesn't even use the dataclass it imports — it
stores raw `{"outcome": ..., "agent": ...}` dict literals into a field typed
`dict[tuple[str, str], ExecutionState]`. This is exactly the field-mismatch
risk the user described, caught in the act.

Real consumer of the untyped dict: `docker_container_recovery_adapter.py`
`assess_container()` (~lines 530, 542) does
`execution_state.get("outcome")` / `execution_state.get("agent")` — silent
`None` on any key typo, no static analysis coverage.

## Decision: ExecutionState lives in the port module, re-exported via ports/output/__init__.py

This matches every other output-port value object in the codebase:
`BoardColumn`/`BoardConfig` in `board_service.py`, `ContainerMetadata`/
`RecoveryAssessment`/`RecoveryResult` in `container_recovery.py`,
`CodingAgentResult` in `coding_agent.py` — all defined alongside their
interface, then re-exported from `ports/output/__init__.py`'s `__all__`.
`ExecutionState` should follow this precedent exactly, and
`ports/output/__init__.py` needs a new import line + `__all__` entry (it
currently only imports `IWorkExecutionStateTracker` from that module).

## Fix surface (files that must change together)
- `ports/output/work_execution_state_tracker.py` — define `ExecutionState`
  (frozen dataclass), change `load_state` signature to return
  `ExecutionState | None`.
- `ports/output/__init__.py` — import + export `ExecutionState`.
- `adapters/secondary/redis_execution_state_tracker.py` — `_decode` must
  construct `ExecutionState(...)` instead of returning raw `dict`;
  `mark_execution_started`/`mark_execution_failed` can keep `json.dumps` of
  a dict for the wire format but should build it via
  `dataclasses.asdict(ExecutionState(...))` or equivalent to keep write/read
  paths symmetric.
- `adapters/testing/in_memory_work_execution_state_tracker.py` — already
  imports `ExecutionState`; fix `mark_execution_started`/
  `mark_execution_failed` to store `ExecutionState(...)` instances, not dict
  literals (this is the pre-existing bug).
- `adapters/secondary/docker_container_recovery_adapter.py` — `assess_container()`
  switch `execution_state.get("outcome")` → `execution_state.outcome`,
  `execution_state.get("agent")` → `execution_state.agent`.

**Why this matters:** confirms the general precedent — port-adjacent value
objects always live in the port module, never as bare dicts, and simulation
mocks must be exercised (this one wasn't — an untested import path masked a
broken mock for an unknown period).

**How to apply:** when reviewing any output port still returning
`dict[str, Any]`, treat it as a MAJOR finding by default and check whether a
mock/adapter has already started assuming a typed replacement (grep for the
type name) — that's a strong signal the fix is overdue, not speculative.
