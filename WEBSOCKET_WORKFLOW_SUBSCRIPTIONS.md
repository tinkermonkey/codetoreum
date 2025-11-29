# WebSocket Workflow Event Subscriptions - Implementation Documentation

## Overview

This document describes the implementation of WebSocket workflow event subscriptions for real-time workflow state updates, completing the deferred feature from PR #75.

## Implementation Summary

### What Was Implemented

1. **Frontend WebSocket Store Extensions** (`frontend/src/store/websocketStore.ts`)
   - Added `subscribeToWorkflowRun(workflowRunId, eventTypes?)` method
   - Added `unsubscribeFromWorkflowRun(workflowRunId)` method
   - Sends server-side filtering parameters for efficient event delivery

2. **Workflow-Specific Hook** (`frontend/src/hooks/useWorkflowRunEvents.ts`)
   - New hook for subscribing to events for a specific workflow run
   - Automatically manages subscription lifecycle (subscribe on mount, unsubscribe on unmount)
   - Filters events client-side as a safety layer
   - Returns workflow-specific events for UI consumption

3. **UI Integration** (`frontend/src/pages/PipelineRunDetailsPage.tsx`)
   - Uses `useWorkflowRunEvents` hook for the selected workflow run
   - Invalidates React Query cache when workflow events are received
   - Provides real-time updates without polling

4. **Integration Tests** (`tests/integration/test_websocket_adapter.py`)
   - Added `TestWebSocketWorkflowFiltering` test class with 4 tests:
     - `test_subscribe_to_specific_workflow_run` - Basic subscription
     - `test_subscribe_to_workflow_with_event_types` - Subscription with event type filtering
     - `test_multiple_workflow_subscriptions` - Multiple simultaneous workflow subscriptions
     - `test_unsubscribe_from_workflow_run` - Unsubscription handling

## Architecture

### Server-Side (Already Implemented in PR #75)

The WebSocket adapter (`src/codetoreum/adapters/primary/websocket_adapter.py`) already had comprehensive filtering support:

- **EventFilter dataclass** (line 88): Contains `workflow_run_id` field
- **SubscribeMessage** (line 121): Accepts `workflow_run_id` parameter
- **Reverse Index** (line 292): `workflow_subscribers: Dict[str, Set[str]]` for efficient lookups
- **Subscription Tracking** (line 563-566): Adds connections to workflow_run_id index
- **Event Filtering** (line 849-854): Filters events by workflow_run_id server-side

### Client-Side (New Implementation)

#### WebSocket Store

```typescript
subscribeToWorkflowRun(workflowRunId: string, eventTypes?: string[])
```

Sends subscription message with default event types:
- WorkflowStarted
- WorkflowCompleted
- WorkflowFailed
- StageStarted
- StageCompleted
- StageFailed
- AgentExecutionStarted
- AgentExecutionCompleted
- AgentExecutionFailed

#### useWorkflowRunEvents Hook

```typescript
export function useWorkflowRunEvents(
  workflowRunId: string | null | undefined,
  isAuthenticated: boolean,
  isAuthLoading: boolean
): UseWorkflowRunEventsReturn
```

**Lifecycle:**
1. Connects to WebSocket if authenticated
2. Subscribes to specific workflow run when connected
3. Filters incoming events by workflow_run_id
4. Unsubscribes on component unmount or workflowRunId change

**Event Filtering:**
Checks multiple possible locations for `workflow_run_id`:
- `data.workflow_run_id`
- `data.data.workflow_run_id` (EventMessage wrapper)
- `data.payload.workflow_run_id` (payload structure)

#### PipelineRunDetailsPage Integration

```typescript
const { workflowEvents } = useWorkflowRunEvents(
  selectedWorkflowId,
  isAuthenticated,
  isAuthLoading
);

useEffect(() => {
  if (workflowEvents.length > 0 && selectedWorkflowId) {
    queryClient.invalidateQueries({
      queryKey: ['workflow-runs', selectedWorkflowId],
    });
    queryClient.invalidateQueries({
      queryKey: ['workflow-events', selectedWorkflowId],
    });
  }
}, [workflowEvents, selectedWorkflowId, queryClient]);
```

## Protocol

### Subscribe to Workflow Run

**Client → Server:**
```json
{
  "type": "subscribe",
  "subscription_type": "workflow_events",
  "workflow_run_id": "workflow-run-123",
  "event_types": ["WorkflowStarted", "StageStarted", ...]
}
```

**Server → Client (Confirmation):**
```json
{
  "type": "subscribed",
  "subscription_type": "workflow_events",
  "filters": {
    "workflow_run_id": "workflow-run-123",
    "event_types": ["WorkflowStarted", "StageStarted", ...],
    ...
  },
  "timestamp": "2025-11-29T..."
}
```

### Unsubscribe from Workflow Run

**Client → Server:**
```json
{
  "type": "unsubscribe",
  "workflow_run_id": "workflow-run-123"
}
```

**Server → Client:**
```json
{
  "type": "unsubscribed",
  "timestamp": "2025-11-29T..."
}
```

### Event Delivery

**Server → Client:**
```json
{
  "type": "event",
  "event_id": "uuid",
  "event_type": "WorkflowStarted",
  "data": {
    "workflow_run_id": "workflow-run-123",
    "payload": { ... },
    ...
  },
  "timestamp": "2025-11-29T..."
}
```

## Performance Characteristics

### Server-Side Filtering Benefits

1. **Efficient Lookups**: Uses reverse index `workflow_subscribers` for O(1) connection lookup
2. **Reduced Network Traffic**: Only sends events for subscribed workflow runs
3. **Scalable**: Multiple clients can subscribe to different workflows without performance degradation

### Client-Side Benefits

1. **Single WebSocket Connection**: Singleton pattern prevents connection proliferation
2. **Automatic Subscription Management**: Subscribe/unsubscribe handled by React hooks
3. **React Query Integration**: Leverages existing caching and invalidation

## Testing

### Integration Tests (4 tests, all passing)

```bash
pytest tests/integration/test_websocket_adapter.py::TestWebSocketWorkflowFiltering -v
```

**Test Coverage:**
- Basic workflow run subscription
- Event type filtering with workflow run
- Multiple simultaneous workflow subscriptions
- Unsubscription handling

### Manual Testing

1. Start the development server
2. Navigate to `/workflows/runs/:id`
3. Open browser DevTools → Network → WS
4. Observe WebSocket messages:
   - Subscribe message sent on page load
   - Subscription confirmation received
   - Events filtered by workflow_run_id
   - Unsubscribe sent on navigation away

## Files Modified

### Frontend
- `frontend/src/store/websocketStore.ts` - Added workflow subscription methods
- `frontend/src/hooks/useWorkflowRunEvents.ts` - New hook (created)
- `frontend/src/pages/PipelineRunDetailsPage.tsx` - Integrated workflow subscriptions

### Backend
- No changes (existing adapter already supported filtering)

### Tests
- `tests/integration/test_websocket_adapter.py` - Added 4 new tests

## Acceptance Criteria (All Met)

- ✅ Clients can subscribe to events for specific workflow run IDs
- ✅ Server filters events by workflow_run_id
- ✅ UI updates in real-time when workflow state changes
- ✅ Integration tests cover event filtering
- ✅ No performance degradation with multiple subscriptions

## Future Enhancements

1. **Event Batching**: For high-frequency events, batch updates to reduce re-renders
2. **Optimistic Updates**: Update UI immediately before server confirmation
3. **Reconnection State**: Preserve subscriptions across reconnections
4. **Event Replay**: Request missed events after reconnection
5. **Subscription State UI**: Show active subscriptions in DevTools/debug panel

## Related Documentation

- Original PR: #75
- Deferred Feature Note: `WORKFLOW_RUN_API_IMPLEMENTATION.md:230-239`
- WebSocket Adapter Design: `src/codetoreum/adapters/primary/websocket_adapter.py:1-14`
- Event Types: `src/codetoreum/domain/events.py`

## Conclusion

The WebSocket workflow event subscriptions feature is now complete. The implementation:
- Leverages existing server-side filtering infrastructure
- Provides clean React hooks for subscription management
- Maintains the singleton WebSocket connection pattern
- Includes comprehensive integration tests
- Enables real-time UI updates for workflow state changes

All acceptance criteria have been met, and the feature is ready for production use.
