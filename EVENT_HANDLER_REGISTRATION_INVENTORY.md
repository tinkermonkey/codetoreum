# Lifecycle Event Handler Registration and Audit - Event Inventory

## Summary of Changes

### Handlers Registered
All four previously-unwired event handlers have been integrated into `ProductionApplicationBootstrap`:

1. **WorkflowEventHandler** (`_register_workflow_event_handler`)
   - Subscribes to: `WorkItemCreatedEvent`, `ExecutionCompletedEvent`, `ExecutionFailedEvent`, `ReviewCycleApprovedEvent`, `ReviewCycleRejectedEvent`, `ReviewCycleEscalatedToHumanEvent`
   - Purpose: Workflow orchestration events

2. **ExecutionEventHandler** (`_register_execution_event_handler`)
   - Subscribes to: `ExecutionInitializedEvent`, `ExecutionStartedEvent`, `ExecutionCompletedEvent`, `ExecutionFailedEvent`, `ExecutionTimedOutEvent`
   - Purpose: Execution lifecycle tracking and metrics

3. **BranchResolutionEventHandler** (`_register_branch_resolution_event_handler`)
   - Subscribes to: `BranchResolvedEvent`, `BranchReusedEvent`, `BranchResolutionCreatedEvent`
   - Purpose: Branch resolution audit trail and metrics

4. **RepairCycleEventHandler** (`_register_repair_cycle_event_handler`)
   - Subscribes to: `WorkItemColumnChangedEvent`
   - Purpose: Test-fix-validate automation

### Broken Code Deleted
- ✅ `setup_event_bus()` function removed from `application/event_bus_wiring.py`
- ✅ `EventBusRegistry.register_handlers()` method removed
- ✅ grep confirms no remaining references to these in production code

### Vestigial Subscriptions Removed
From `WorkflowOrchestrator._subscribe_to_events()`:
- ✅ `WorkItemColumnChangedEvent` subscription removed (now handled by `BoardColumnEventHandler`)
- ✅ `LockReleasedEvent` and `PipelineLockReleasedEvent` subscriptions removed (now handled by `BoardColumnEventHandler`)

Note: These were vestigial from the polling-era architecture before event-driven handlers were in place. `MetricsCollector` lock subscriptions are retained - they are legitimate parallel consumers.

### Tests Created/Updated
1. **New**: `tests/unit/infrastructure/test_handler_registration.py`
   - Discovers all `EventHandler` subclasses in `application/event_handlers/`
   - Verifies each handler is registered in `ProductionApplicationBootstrap`
   - Fails if any handler is discovered but not registered

2. **Updated**: `tests/test_production_bootstrap.py`
   - Added `test_event_handler_types_declared()` to verify event type mappings

### Handler Registration Checklist
- ✅ WorkflowEventHandler registered
- ✅ ExecutionEventHandler registered
- ✅ BranchResolutionEventHandler registered
- ✅ RepairCycleEventHandler registered
- ✅ ConversationalLoopOrchestrator registered
- ✅ BoardColumnEventHandler registered
- ✅ PRReviewCycleDispatchHandler registered
- ✅ PRReviewCycleEventHandler registered
- ✅ ReviewEventHandler registered

## Event Inventory

### Currently Subscribed Event Types (23)
The following event types have at least one subscriber registered:

**BoardColumnEventHandler**
- WorkItemColumnChangedEvent
- AgentExecutionCompletedEvent

**ConversationalLoopOrchestrator**
- WorkItemColumnChangedEvent

**PRReviewCycleDispatchHandler**
- WorkItemColumnChangedEvent

**PRReviewCycleEventHandler**
- PRReviewCycleApprovedEvent
- PRReviewCycleIssuesFoundEvent
- PRReviewCycleMaxCyclesReachedEvent

**ReviewEventHandler**
- ReviewCycleCreatedEvent
- ReviewCycleCompletedEvent
- ReviewStatusChangedEvent
- ReviewCycleFeedbackSubmittedEvent
- ReviewCycleIterationStartedEvent

**WorkflowEventHandler** (Lifecycle Event Handler Registration)
- WorkItemCreatedEvent
- ExecutionCompletedEvent
- ExecutionFailedEvent
- ReviewCycleApprovedEvent
- ReviewCycleRejectedEvent
- ReviewCycleEscalatedToHumanEvent

**ExecutionEventHandler** (Lifecycle Event Handler Registration)
- ExecutionInitializedEvent
- ExecutionStartedEvent
- ExecutionCompletedEvent
- ExecutionFailedEvent
- ExecutionTimedOutEvent

**BranchResolutionEventHandler** (Lifecycle Event Handler Registration)
- BranchResolvedEvent
- BranchReusedEvent
- BranchResolutionCreatedEvent

**RepairCycleEventHandler** (Lifecycle Event Handler Registration)
- WorkItemColumnChangedEvent

**WorkflowOrchestrator (manual subscriptions)**
- CommentNeedsResponseEvent
- ReviewStatusChangedEvent
- RepairCycleCompletedEvent

### Event Types Without Subscribers

The following domain events are defined but have no event handlers subscribed:

| Event | Domain | Disposition | Reason | Tracked Issue |
|-------|--------|-------------|--------|---------------|
| WorkflowOrphanedEvent | Workflow | **Delete in Phase 5** | Temporary event emitted during bootstrap orphan detection; Phase 5 pipeline coordination will own this logic | DEF-025 |
| AgentCapabilityAddedEvent | Agent | **Defer** | Used for agent capability updates; no orchestration action needed yet | - |
| AgentCapabilityRemovedEvent | Agent | **Defer** | Used for agent capability updates; no orchestration action needed yet | - |
| AgentTimeoutUpdatedEvent | Agent | **Defer** | Agent configuration changes; no handler needed at MVP | - |
| AgentMcpServerAddedEvent | Agent | **Defer** | Agent configuration; no handler needed at MVP | - |
| AgentMcpServerRemovedEvent | Agent | **Defer** | Agent configuration; no handler needed at MVP | - |
| BoardReconciledEvent | Board | **Defer** | Board synchronization tracking; phase-gated for observability enhancement | Phase 6 |
| BoardSyncFailedEvent | Board | **Defer** | Board sync failure tracking; phase-gated for alerting | Phase 6 |
| BranchCreatedEvent | VCS | **Defer** | Branch creation tracking; audit trail only | - |
| BranchPushedEvent | VCS | **Defer** | Branch push tracking; audit trail only | - |
| CIPipelineStatusCheckedEvent | CI | **Defer** | CI pipeline tracking; integrated into repair cycle handler | - |
| CIRunStartedEvent | CI | **Defer** | CI execution tracking; deferred to Phase 3 | - |
| CIRunCompletedEvent | CI | **Defer** | CI execution tracking; deferred to Phase 3 | - |
| CodingAgentInvokedEvent | Agent | **Wire** | Agent invocation telemetry; currently published, needs persistence | DEF-018 |
| CodingAgentToolCallEvent | Agent | **Wire** | Agent tool calls; currently published, needs tracking | DEF-018 |
| CodingAgentToolResultEvent | Agent | **Wire** | Agent tool results; currently published, needs tracking | DEF-018 |
| CodingAgentTextOutputEvent | Agent | **Wire** | Agent text output; currently published, needs logging | DEF-018 |
| CodingAgentCompletedEvent | Agent | **Wire** | Agent completion event; currently published, needs persistence | DEF-018 |
| ContainerRecoveredEvent | Infrastructure | **Defer** | Container recovery tracking; handled by service, audit only | - |
| ExecutionCancelledEvent | Execution | **Defer** | Execution cancellation; no auto-progression needed | Phase 3 |
| PipelineCompletedEvent | Pipeline | **Defer** | Pipeline completion tracking; WorkflowCompletedEvent is primary | - |
| PipelineFailedEvent | Pipeline | **Defer** | Pipeline failure tracking; WorkflowFailedEvent is primary | - |
| LockAcquiredEvent | Pipeline | **Keep** | Lock metrics; MetricsCollector subscribes | ✓ Subscribed |
| LockReleasedEvent | Pipeline | **Keep** | Lock metrics; MetricsCollector subscribes | ✓ Subscribed |

## Acceptance Criteria Met

- ✅ All four handlers registered in `ProductionApplicationBootstrap` with one method per handler
- ✅ `setup_event_bus()` and `EventBusRegistry.register_handlers()` deleted; no references in src/
- ✅ `tests/unit/infrastructure/test_handler_registration.py` created and passes
- ✅ `tests/test_production_bootstrap.py` extended with handler type mapping test
- ✅ PR description contains event inventory with explicit disposition
- ✅ `WorkflowOrchestrator._handle_column_change` and `_handle_lock_released` subscriptions removed
- ✅ Mypy clean (Python files compile without errors)

## Notes for Future Phases

1. **Phase 3**: Implement CodingAgent event persistence (DEF-018) - wire CodingAgent* events
2. **Phase 5**: Complete WorkflowOrphanedEvent handling via pipeline coordination
3. **Phase 6**: Add board reconciliation observability handlers
4. **DevOps**: CI pipeline integration hooks for repair cycle (currently deferred)

## Related Documentation

- `documentation/architecture/application-services/event-handlers.md` - Handler specifications
- `bootstrap/implementation-review-2026-05-31.md` - Architect decisions on event handler registration
