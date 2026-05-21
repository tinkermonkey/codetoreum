---
name: production-adapter-extraction
description: Pattern and checklist for extracting production secondary adapters from simulation mocks, established when creating BasicReviewCycleAdapter and BasicPRReviewCycleAdapter
metadata:
  type: project
---

## Decision: Basic* production adapters extracted from Mock* simulation adapters (2026-05-20)

Two production adapters were created in `src/codetoreum/adapters/secondary/`:
- `basic_review_cycle_adapter.py` — implements `IReviewCycle`
- `basic_pr_review_cycle_adapter.py` — implements `IPRReviewCycle`

**Why:** The Mock adapters in `adapters/testing/` contain simulation scaffolding (SimulationClock, pre-programmed sequences, assertion helpers) that must never appear in production code. Production adapters need the same port-compliant logic with real timestamps and real-data-driven outcomes.

## Extraction checklist (apply to any future Mock→Basic extraction)

### Remove from mock:
- `SimulationClock` dependency — replace all `self._clock.now()` / `self.clock.now()` with `datetime.now(UTC)`, drop all `await self._clock.advance(...)` calls entirely
- `MockEventEmitter` base class — do NOT inherit it; emit via injected `_event_emitter`/`_event_bus`/`_event_store` using an async `_emit_event()` helper
- Pre-configured outcome/sequence state (`_review_sequences`, `_cycle_configs`, `_sequence_indices`) — remove entirely; derive outcome from actual data
- `_current_project` guard on event emission — remove; always emit
- All `set_*` configuration methods (e.g. `set_approve_immediately`, `set_outcome`, `set_ci_failing`)
- All `assert_*` test helpers
- All `get_all_events`, `get_handler_errors`, `clear` test-only retrieval methods
- `on`, `off`, `emit` (MockEventEmitter handler registration) — replaced by async `_emit_event` helper
- `_events`, `_event_handlers`, `_monitoring`, `_handler_errors` test-tracking state
- `_log_event` — simplified to `logger.debug(...)` only (no `_events.append`)
- `start_monitoring`, `stop_monitoring`, `get_monitoring_status` — removed (IMonitoredService not part of production contract)

### Keep:
- All `IPort` abstract method implementations
- `threading.RLock` for state thread-safety
- In-memory state dicts (`_cycles`, `_project_cycles`, `_cycle_states`)
- `_validate_request` — copy verbatim
- `parse_review` — copy verbatim (pure text logic)
- `_evaluate_maker_output` (renamed from `_evaluate_llm_output` in mock) — same heuristic logic

### Production outcome logic for BasicPRReviewCycleAdapter:
- `max_cycles_reached`: `request.cycle_number > request.config.max_outer_cycles` (not a pre-programmed flag)
- `ci_passed`: default `True` — `# TODO: inject ci_pipeline_service for real CI check`
- `findings`: start empty `[]` — come from real code review (future enhancement)
- `outcome`: `APPROVED` if no findings and CI passes; `ISSUES_FOUND` if CI fails or findings present

### Event source field:
- Use `"review_cycle"` (not `"mock_review_cycle"`)
- Use `"pr_review_cycle"` (not `"mock_pr_review_cycle"`)

### Constructor signatures:
- `BasicReviewCycleAdapter(event_emitter=None, event_bus=None, event_store=None)`
- `BasicPRReviewCycleAdapter(ticket_system=None, board_service=None, event_emitter=None, event_bus=None, event_store=None)`

### Internal dataclass:
- `BasicReviewCycleAdapter` uses a module-level `_ReviewDecisionItem` dataclass (replaces `ReviewSequenceItem` from the mock) as the return type from `_evaluate_maker_output`

### Import strategy:
- Domain events are imported inside methods (not at module level) to avoid circular import risk at module load time — this is the established pattern for adapter files that reference frozen event dataclasses

## How to apply:
When asked to "create a production adapter from a mock", apply this checklist. The resulting file lives in `src/codetoreum/adapters/secondary/`, never in `adapters/testing/`. Do not modify the mock source.
