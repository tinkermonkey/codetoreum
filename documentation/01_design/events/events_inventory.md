# Events Inventory

This document provides a comprehensive inventory of all events in the Codetoreum system, organized by category.

## Overview

Events are the primary mechanism for observability, traceability, and system monitoring in Codetoreum. All significant actions, decisions, and state changes emit events that are stored in multiple destinations for different purposes.

## Event Architecture

The system uses a multi-tier event architecture:

1. **Event Generation**: Components emit events through the ObservabilityManager
2. **Event Distribution**: Events are published via Redis Pub/Sub for real-time consumption
3. **Event Storage**: Events are persisted to Redis Streams (short-term) and Elasticsearch (long-term)
4. **Event Consumption**: Web UI, monitoring dashboards, and analytics consume events

## Event Categories

### 1. Agent Lifecycle Events
Events tracking the complete lifecycle of agent execution from initialization to completion.

- **task_received** - Agent task received by executor
- **agent_initialized** - Agent instance created and initialized
- **agent_started** - Agent execution begins
- **agent_completed** - Agent execution completed successfully
- **agent_failed** - Agent execution failed with error
- **prompt_constructed** - Prompt built and ready for Claude
- **claude_call_started** - Claude API call initiated
- **claude_call_completed** - Claude API call finished
- **tool_execution_started** - Agent tool execution begins
- **tool_execution_completed** - Agent tool execution finishes

### 2. Decision Events
Events capturing all decision points and routing logic in the system. These are high-level strategic events.

#### 2.1 Routing Decisions
- **agent_routing_decision** - Agent selected for work item
- **workspace_routing_decision** - Workspace type selected (issues/discussions/hybrid)
- **discussion_category_routing_decision** - Discussion category selected

#### 2.2 Feedback Decisions
- **feedback_detected** - User feedback detected on agent output
- **feedback_listening_started** - System begins monitoring for feedback
- **feedback_ignored** - Feedback detected but ignored (with reason)
- **conversational_question_routed** - Question routed to agent for answer

#### 2.3 Progression Decisions
- **status_progression** - Work item moved between statuses
- **stage_transition** - Pipeline stage transition
- **column_advancement** - Board column advancement

#### 2.4 Review Cycle Decisions
- **review_cycle_decision** - Review cycle state change (maker selected, reviewer selected, approved, changes requested, etc.)
- **review_cycle_started** - Review cycle initiated
- **review_cycle_complete** - Review cycle completed
- **review_cycle_escalated** - Review cycle escalated to human

#### 2.5 Conversational Loop Decisions
- **conversational_loop_started** - Q&A conversation initiated
- **conversational_loop_paused** - Conversation paused (column exit)
- **conversational_loop_resumed** - Conversation resumed
- **conversational_loop_ended** - Conversation ended

#### 2.6 Error Handling Decisions
- **error_decision** - Error handling decision made
- **retry_decision** - Retry attempted
- **circuit_breaker_opened** - Circuit breaker opened due to failures
- **circuit_breaker_closed** - Circuit breaker closed after recovery

#### 2.7 Task Management Decisions
- **task_queued** - Task added to queue
- **task_dequeued** - Task removed from queue for processing
- **task_requeued** - Task returned to queue (retry)
- **task_cancelled** - Task cancelled

#### 2.8 Branch Management Decisions
- **branch_created** - New feature branch created
- **branch_reused** - Existing branch reused
- **branch_stale_detected** - Branch behind main
- **branch_conflict_detected** - Merge conflict detected
- **branch_parent_detected** - Parent issue detected

### 3. Workspace Events
Events related to workspace preparation and finalization.

- **workspace_prepared** - Workspace ready for agent execution
- **workspace_finalized** - Workspace cleanup completed
- **branch_checked_out** - Git branch checked out
- **branch_pushed** - Git branch pushed to remote
- **discussion_created** - Discussion created
- **discussion_comment_added** - Comment added to discussion

### 4. Pipeline Events
Events tracking pipeline execution and stages.

- **pipeline_started** - Pipeline execution started
- **pipeline_completed** - Pipeline execution completed
- **pipeline_failed** - Pipeline execution failed
- **stage_started** - Pipeline stage started
- **stage_completed** - Pipeline stage completed
- **stage_failed** - Pipeline stage failed
- **checkpoint_saved** - Pipeline state checkpointed
- **checkpoint_loaded** - Pipeline state restored

### 5. Repair Cycle Events
Events specific to test-driven repair cycles.

- **repair_cycle_started** - Repair cycle initiated
- **repair_cycle_completed** - Repair cycle finished
- **repair_cycle_iteration** - Repair cycle iteration started
- **repair_cycle_test_execution_completed** - Test execution finished
- **repair_cycle_file_fix_started** - File fix started
- **repair_cycle_file_fix_completed** - File fix completed
- **repair_cycle_warning_review_started** - Warning review started
- **repair_cycle_warning_review_completed** - Warning review completed
- **repair_cycle_container_started** - Repair container created
- **repair_cycle_container_recovered** - Repair container recovered
- **repair_cycle_container_checkpoint_updated** - Checkpoint updated
- **repair_cycle_container_completed** - Repair container cleanup

### 6. GitHub Integration Events
Events related to GitHub API interactions.

- **github_card_movement_detected** - Card moved on board
- **github_issue_created** - Issue created
- **github_issue_updated** - Issue updated
- **github_comment_posted** - Comment posted
- **github_label_added** - Label added
- **github_label_removed** - Label removed
- **github_pr_created** - Pull request created
- **github_board_reconciled** - Board reconciled with config

### 7. Container Events
Events related to Docker container lifecycle.

- **container_started** - Container started
- **container_stopped** - Container stopped
- **container_recovered** - Container recovered on restart
- **container_killed** - Container killed (orphaned)
- **container_removed** - Container removed

### 8. Stream Events (Claude Code)
Real-time streaming events from Claude Code execution.

- **claude_stream_text** - Text chunk from Claude
- **claude_stream_tool_use** - Tool use event
- **claude_stream_tool_result** - Tool result event
- **claude_stream_error** - Error in stream
- **claude_stream_complete** - Stream completed
- **claude_session_continued** - Session continuity preserved

### 9. Configuration Events
Events related to configuration changes and reconciliation.

- **config_loaded** - Configuration loaded
- **config_changed** - Configuration changed
- **config_reconciliation_needed** - Reconciliation required
- **config_reconciliation_completed** - Reconciliation completed
- **dev_container_verified** - Dev container image verified
- **dev_container_verification_failed** - Dev container verification failed

### 9.1 Project Management Events
Events related to multi-project orchestration and repository management.

- **project.cloned** - Project repository successfully cloned or updated
- **project.clone_failed** - Project clone/pull failed (transient error)
- **project.enabled** - Project became enabled in configuration
- **project.disabled** - Project became disabled in configuration
- **orchestration.cycle_completed** - Orchestration poll cycle completed

### 10. System Events
System-level operational events.

- **system_started** - System startup initiated
- **system_ready** - System ready for work
- **system_shutdown** - System shutdown initiated
- **cleanup_started** - Startup cleanup initiated
- **cleanup_completed** - Startup cleanup completed
- **health_check_passed** - Health check passed
- **health_check_failed** - Health check failed

## Event Distribution Channels

### Redis Pub/Sub
**Purpose**: Real-time event delivery to subscribers

**Channels**:
- `orchestrator:agent_events` - All agent lifecycle and decision events
- `orchestrator:claude_stream` - Live Claude Code output stream

**Characteristics**:
- No persistence (ephemeral)
- Multiple subscribers supported
- Low latency (<10ms)
- Fire-and-forget delivery

### Redis Streams
**Purpose**: Short-term event history for recovery and replay

**Streams**:
- `orchestrator:event_stream` - Agent and decision events (last 1000 events, 2hr TTL)
- `orchestrator:claude_logs_stream` - Claude stream events (last 1000 events, 2hr TTL)

**Characteristics**:
- Persistent (until TTL)
- Consumer groups supported
- Ordered delivery
- Replay capability

### Elasticsearch
**Purpose**: Long-term event storage for analytics and audit

**Indices**:
- `agent-events-YYYY-MM-DD` - Agent lifecycle events (daily rollover)
- `decision-events-YYYY-MM-DD` - Decision events (daily rollover)
- `pipeline-runs-YYYY-MM-DD` - Pipeline run metadata (daily rollover)

**Characteristics**:
- Persistent (retention policy configurable)
- Full-text search
- Aggregations and analytics
- Audit trail

## Event Structure

### Standard Event Fields
All events share these common fields:

```python
{
    'timestamp': str,          # ISO 8601 UTC timestamp
    'event_id': str,           # UUID for event deduplication
    'event_type': str,         # EventType enum value
    'agent': str,              # Agent name (if applicable)
    'task_id': str,            # Task identifier (if applicable)
    'project': str,            # Project name
    'pipeline_run_id': str,    # Pipeline run ID (if applicable)
    'data': Dict[str, Any]     # Event-specific payload
}
```

### Decision Event Structure
Decision events have additional standardized fields in the `data` section:

```python
{
    'decision_category': str,     # Category (routing, feedback, progression, etc.)
    'issue_number': int,          # Work item number
    'board': str,                 # Board/pipeline name
    'workspace_type': str,        # Workspace type

    'inputs': Dict[str, Any],     # Inputs to decision
    'decision': Dict[str, Any],   # The decision made
    'reason': str,                # Human-readable explanation
    'reasoning_data': Dict,       # Structured reasoning
}
```

## Event Consumption Patterns

### Real-Time Monitoring
- Web UI subscribes to Redis Pub/Sub channels
- Live dashboard updates
- Agent execution logs streamed to UI

### Historical Analysis
- Query Elasticsearch for historical events
- Build reports and analytics
- Identify patterns and trends

### System Recovery
- Read from Redis Streams on startup
- Detect incomplete operations
- Resume or cleanup stale work

## Event Emission Guidelines

### When to Emit Events

1. **Emit at decision points**: Every routing, selection, or strategic decision
2. **Emit at state changes**: Agent lifecycle, pipeline stages, work item movement
3. **Emit at boundaries**: System entry/exit points, external API calls
4. **Emit at errors**: All error conditions and recovery attempts

### When NOT to Emit Events

1. **Internal implementation details**: Low-level function calls
2. **High-frequency operations**: Loop iterations, polling checks
3. **Redundant information**: Already captured by parent event
4. **Sensitive data**: Credentials, secrets, PII

### Event Naming Conventions

1. **Past tense for completed actions**: `agent_completed`, `task_queued`
2. **Present continuous for in-progress**: `agent_running`, `test_executing`
3. **Descriptive and specific**: `branch_stale_detected` not `branch_issue`
4. **Category prefix for grouping**: `repair_cycle_*`, `review_cycle_*`

## Observability Tracing

### Pipeline Run Tracing
All events within a pipeline run include the `pipeline_run_id` field, allowing complete trace reconstruction.

Example flow:
```
pipeline_run_id: pipeline_context-studio_123_1234567890

Events:
1. pipeline_started
2. agent_initialized (stage: business_analyst)
3. agent_completed
4. review_cycle_decision (iteration: 1, maker selected)
5. agent_initialized (stage: code_reviewer)
6. agent_completed
7. review_cycle_decision (iteration: 1, approved)
8. pipeline_completed
```

### Agent Execution Tracing
Each agent execution has a unique `agent_execution_id` (UUID) for tracking from initialization to completion.

### Task Tracing
Each task has a `task_id` that links all events related to that specific work item.

## Event-Driven Features

### Feedback Detection
The system monitors for user feedback by:
1. Emitting `feedback_listening_started` after agent completes
2. Polling for new comments on GitHub
3. Emitting `feedback_detected` when found
4. Routing feedback via `conversational_question_routed`

### Circuit Breakers
Circuit breaker state changes emit events:
- `circuit_breaker_opened` - Too many failures detected
- `circuit_breaker_closed` - Recovery confirmed

### Auto-Advancement
Status progression events trigger auto-advancement logic:
- `status_progression` emitted on column movement
- System checks auto-advancement rules
- Next stage triggered if conditions met

## Event Schema Evolution

### Versioning Strategy
Events do not include explicit version fields. Instead:
- New fields are additive (backward compatible)
- Deprecated fields remain for 6 months
- Breaking changes require new event type

### Schema Documentation
Each event type has a detailed design document in `documentation/01_design/events/` describing:
- Purpose and context
- When event is emitted
- Event payload structure
- Consumer expectations
- Related events

## Monitoring and Alerting

### Critical Events
These events should trigger alerts:
- `agent_failed` - Agent execution failure
- `circuit_breaker_opened` - System degradation
- `health_check_failed` - Infrastructure issue
- `repair_cycle_escalated` - Maximum iterations reached

### Performance Metrics
Events used for performance tracking:
- `agent_completed` - Agent duration
- `claude_call_completed` - Claude API latency
- `test_execution_completed` - Test suite duration

## Event Retention

### Redis Streams
- **Retention**: 1000 events or 2 hours (whichever comes first)
- **Purpose**: Recent history for debugging

### Elasticsearch
- **Retention**: 90 days (configurable)
- **Purpose**: Long-term analytics and audit
- **Rollover**: Daily indices with ILM policy

## Summary

The Codetoreum event system provides comprehensive observability through:
- **70+ event types** covering all system operations
- **3 distribution channels** for different consumption patterns
- **Standardized structure** for consistent event handling
- **Complete traceability** via pipeline run IDs and task IDs
- **Real-time and historical** access to events

This event architecture enables debugging, monitoring, analytics, and audit capabilities essential for an autonomous AI development system.
