---
name: review-pipeline-queue-resilience-decorator
description: IPipelineQueueService resilience-tier review — QueueValidationError re-raise premise was stale (already fixed); found the real CRITICAL bug is factory.create_resilient_pipeline_queue_service() actually wiring BestEffortPipelineQueueServiceDecorator, silently downgrading a CRITICAL_ADAPTER_SLOT
metadata:
  type: project
---

## Context (2026-09-14)

Asked to review the resilience-decorator strategy for `IPipelineQueueService`
(`src/codetoreum/ports/output/pipeline_queue_service.py`). Two decorators exist
side by side in `src/codetoreum/infrastructure/resilience/decorators.py`:
- `BestEffortPipelineQueueServiceDecorator` — log + DLQ-route on failure, no
  circuit breaker/retry/timeout, business errors (`QueueServiceError`
  subclasses) re-raised immediately on both read and write paths.
- `ResilientPipelineQueueServiceDecorator` — hybrid: full CB+retry+timeout on
  writes (`enqueue_item`, `mark_item_active`, `remove_from_queue`,
  `sync_queue_with_board`) via a sentinel-object pattern that lets
  `QueueServiceError` bypass circuit-breaker failure counting; best-effort
  safe defaults (`False`/`None`/`[]`) on reads (`is_item_in_queue`,
  `get_next_waiting_item`, `get_queue_entries`).

## Finding 1 — premise about QueueValidationError swallowing is stale, already fixed

Read the actual code: **both** decorators already do
`except QueueServiceError: raise` before the generic `except Exception`
handler, on every read method. `QueueValidationError(QueueServiceError)` is a
subclass, so it already propagates correctly through both decorators — this
matches commit `7da9840f` ("Fix: Redis Pipeline Queue Service — Silent Error
Handling (Issue #1061)"), already merged on this branch. No action needed;
if asked again, confirm from decorators.py rather than assuming the bug
still exists (same pattern as [[review_resolver_discussion_adapter_validation]]
— a reported premise that the fix had already superseded).

## Finding 2 — CRITICAL: factory method name/impl mismatch silently downgrades a CRITICAL_ADAPTER_SLOT

`ResilienceFactory.create_resilient_pipeline_queue_service()`
(`src/codetoreum/infrastructure/resilience/factory.py` ~line 239) is named and
shaped like every sibling `create_resilient_*` factory method, but its body
and docstring both say "best-effort" and it **returns
`BestEffortPipelineQueueServiceDecorator`, not
`ResilientPipelineQueueServiceDecorator`**. `ResilientPipelineQueueServiceDecorator`
is fully implemented and even imported into `factory.py`, but is never
instantiated anywhere — dead code as currently wired.

The factory docstring justifies this by citing
`BestEffortExecutionTrackerDecorator` as "the precedent pattern... per
architectural guidance." **That precedent does not generalize here.**
`documentation/implementations/production-bootstrap.md` (Issue #1016 Phase 3)
classifies `queue_service` as a **CRITICAL_ADAPTER_SLOT** — "critical for
work-item ordering (BA FR7/US6)... production bootstrap refuses to start if a
mock queue adapter is detected, preventing silent work-item ordering
failures." The failure-mode analysis is the deciding factor, not "is it
internal Redis":
- `IWorkExecutionStateTracker` failure has a safe fallback baked into domain
  logic: recovery defaults to "kill" if no state hint is found at startup.
  Log-and-continue is correct — this is genuinely advisory.
- `IPipelineQueueService` write-path failure has **no safe fallback**: a
  swallowed/unretried `enqueue_item` failure is silent work-item starvation;
  a swallowed/unretried `remove_from_queue` failure is **permanent queue
  blockage** for every item behind it. This exact blockage class of bug was
  already hit in production and patched by commit `1b197ffc` ("Clean up
  orphaned reverse index entries to prevent permanent re-enqueue
  blockage") — hard evidence this queue's write path is not safely
  best-effort.

## Ruling

Wire `ResilientPipelineQueueServiceDecorator` (already coded, CB+retry+timeout
on writes, safe-default degradation on reads, business-error bypass via
sentinel) into `create_resilient_pipeline_queue_service()` for production.
Keep `BestEffortPipelineQueueServiceDecorator` in the codebase — the pattern
is still correct for genuinely advisory internal stores like the execution
tracker — but do not apply it to this port. Either rename the current method
to `create_best_effort_pipeline_queue_service()` (matching
`create_best_effort_execution_tracker()`'s naming) and add a correctly-wired
`create_resilient_pipeline_queue_service()`, or fix the existing method body
in place; either way the method name must match what it returns.

## Secondary/ADVISORY — no internal-service resilience preset exists

`infrastructure/resilience/config.py` only has external-API-shaped presets
(`GITHUB_RESILIENCE_CONFIG`, `CLAUDE_RESILIENCE_CONFIG`,
`CONTAINER_RESILIENCE_CONFIG`, `REPOSITORY_RESILIENCE_CONFIG`) — all built
around a 60s circuit-breaker open window and up to ~7s of retry backoff,
tuned for rate-limited external vendors. If `ResilientPipelineQueueServiceDecorator`
gets wired for production, it should get its own tighter
`ServiceResilienceConfig` (shorter `circuit_breaker.timeout_seconds`, smaller
`retry.base_delay`) rather than reusing GitHub-shaped defaults — a single
shared queue-service circuit breaker sitting open for 60s after 5 consecutive
Redis hiccups would stall pipeline progression **system-wide** (all
projects/boards share one `IPipelineQueueService` instance) far longer than
warranted for a same-tier internal dependency.

**How to apply:** when reviewing any `ResilienceFactory.create_resilient_*`
or `create_best_effort_*` method, always diff the constructor actually
invoked in the body against the method's own name and docstring claim before
trusting either — this is now the second review
([[review_execution_state_tracker_typed_port]] was the first) where the
composition root/port module said one thing and the wiring did another.
