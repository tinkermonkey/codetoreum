# Agent Lifecycle Events Design

## Overview

Agent lifecycle events track the complete execution lifecycle of AI agents from task reception to completion or failure. These events are critical for monitoring agent performance, debugging failures, and providing real-time feedback to users.

## Event Flow

The typical agent lifecycle follows this event sequence:

```
task_received → agent_initialized → prompt_constructed →
claude_call_started → [claude_stream_events...] → claude_call_completed →
agent_completed (or agent_failed)
```

## Event Definitions

### 1. task_received

**Purpose**: Signals that an agent task has been received by the AgentExecutor and is about to begin processing.

**Emitted By**: `AgentExecutor.execute_agent()`

**When Emitted**: Immediately after task is dequeued and before any processing begins

**Event Structure**:
```python
{
    'timestamp': '2025-10-26T10:30:00.000Z',
    'event_id': 'uuid-1234-5678',
    'event_type': 'task_received',
    'agent': 'business_analyst',
    'task_id': 'task_business_analyst_1729945800',
    'project': 'context-studio',
    'workflow_run_id': 'pipeline_context-studio_123_1729945800',
    'data': {
        'issue_number': 123,
        'board': 'Planning',
        'column': 'Requirements Analysis',
        'workspace_type': 'discussions',
        'trigger': 'card_movement',
        'agent_config': {
            'model': 'claude-sonnet-4-5-20250929',
            'timeout': 3600,
            'requires_docker': True
        }
    }
}
```

**Consumer Use Cases**:
- Web UI displays "Task received" status
- Monitoring system tracks task reception rate
- Alerts if task sits in "received" state too long

---

### 2. agent_initialized

**Purpose**: Signals that an agent instance has been created, configured, and is ready to execute. Returns a unique `agent_execution_id` for tracking this specific execution.

**Emitted By**: `AgentExecutor.execute_agent()`

**When Emitted**: After agent instance is created, workspace is prepared, and execution context is built, but before prompt construction

**Event Structure**:
```python
{
    'timestamp': '2025-10-26T10:30:05.000Z',
    'event_id': 'uuid-1234-5679',
    'event_type': 'agent_initialized',
    'agent': 'business_analyst',
    'task_id': 'task_business_analyst_1729945800',
    'project': 'context-studio',
    'workflow_run_id': 'pipeline_context-studio_123_1729945800',
    'data': {
        'agent_execution_id': 'exec-uuid-9876-5432',  # NEW: Unique execution ID
        'issue_number': 123,
        'agent_config': {
            'model': 'claude-sonnet-4-5-20250929',
            'timeout': 3600,
            'makes_code_changes': False,
            'requires_dev_container': False
        },
        'branch_name': 'feature/issue-123',  # If issues workspace
        'discussion_id': 'D_kwDOABCDEF01',  # If discussions workspace
        'container_name': 'claude-agent-context-studio-task_business_analyst_1729945800',
        'execution_mode': 'initial'  # 'initial' | 'question' | 'revision'
    }
}
```

**Key Fields**:
- `agent_execution_id`: UUID returned to caller for tracking this specific execution
- `branch_name`: Git branch if using issues workspace
- `discussion_id`: Discussion ID if using discussions workspace
- `container_name`: Docker container name (if using Docker)
- `execution_mode`: Agent execution mode (initial, question, revision)

**Consumer Use Cases**:
- Web UI displays "Agent initializing" with progress bar
- Monitoring tracks initialization time
- Recovery system uses agent_execution_id to link init/complete events

---

### 3. prompt_constructed

**Purpose**: Signals that the agent prompt has been fully constructed and is ready to send to Claude.

**Emitted By**: `run_claude_code()`

**When Emitted**: After prompt is built but before Claude API call

**Event Structure**:
```python
{
    'timestamp': '2025-10-26T10:30:08.000Z',
    'event_id': 'uuid-1234-5680',
    'event_type': 'prompt_constructed',
    'agent': 'business_analyst',
    'task_id': 'task_business_analyst_1729945800',
    'project': 'context-studio',
    'workflow_run_id': 'pipeline_context-studio_123_1729945800',
    'data': {
        'agent_execution_id': 'exec-uuid-9876-5432',
        'prompt_length': 1234,  # Characters
        'execution_mode': 'initial',
        'has_previous_output': False,
        'has_feedback': False,
        'thread_history_length': 0,
        'mcp_servers': ['context7', 'artifact_storage']
    }
}
```

**Consumer Use Cases**:
- Debugging prompt construction issues
- Analytics on prompt sizes and complexity
- Tracking correlation between prompt characteristics and outcomes

---

### 4. claude_call_started

**Purpose**: Signals that the Claude API call has been initiated.

**Emitted By**: `run_claude_code()` or `DockerAgentRunner.run_agent_in_container()`

**When Emitted**: Immediately after Claude Code CLI process starts

**Event Structure**:
```python
{
    'timestamp': '2025-10-26T10:30:10.000Z',
    'event_id': 'uuid-1234-5681',
    'event_type': 'claude_call_started',
    'agent': 'business_analyst',
    'task_id': 'task_business_analyst_1729945800',
    'project': 'context-studio',
    'workflow_run_id': 'pipeline_context-studio_123_1729945800',
    'data': {
        'agent_execution_id': 'exec-uuid-9876-5432',
        'model': 'claude-sonnet-4-5-20250929',
        'execution_environment': 'docker',  # 'docker' | 'local'
        'container_name': 'claude-agent-context-studio-task_business_analyst_1729945800',
        'timeout': 3600,
        'continuing_session': False,
        'session_id': None  # Or session_id if continuing
    }
}
```

**Consumer Use Cases**:
- Web UI displays "Calling Claude..." with spinner
- Monitoring tracks Claude API call duration
- Alerts if call duration exceeds timeout

---

### 5. claude_call_completed

**Purpose**: Signals that the Claude API call has completed successfully.

**Emitted By**: `run_claude_code()` or `DockerAgentRunner.run_agent_in_container()`

**When Emitted**: After Claude Code CLI process exits successfully

**Event Structure**:
```python
{
    'timestamp': '2025-10-26T10:35:45.000Z',
    'event_id': 'uuid-1234-5682',
    'event_type': 'claude_call_completed',
    'agent': 'business_analyst',
    'task_id': 'task_business_analyst_1729945800',
    'project': 'context-studio',
    'workflow_run_id': 'pipeline_context-studio_123_1729945800',
    'data': {
        'agent_execution_id': 'exec-uuid-9876-5432',
        'duration_ms': 335000,  # 5 minutes 35 seconds
        'input_tokens': 5420,
        'output_tokens': 2890,
        'total_tokens': 8310,
        'session_id': 'session_abc123',  # For continuity
        'output_length': 12450  # Characters
    }
}
```

**Key Metrics**:
- `duration_ms`: Total Claude call duration
- Token counts: For billing and performance tracking
- `session_id`: For session continuity in conversational mode

**Consumer Use Cases**:
- Cost tracking (tokens * model price)
- Performance monitoring (duration trends)
- Session continuity management

---

### 6. agent_completed

**Purpose**: Signals that the agent has completed successfully, output has been posted, and workspace has been finalized.

**Emitted By**: `AgentExecutor.execute_agent()`

**When Emitted**: After all post-processing (GitHub posting, git operations) complete successfully

**Event Structure**:
```python
{
    'timestamp': '2025-10-26T10:36:00.000Z',
    'event_id': 'uuid-1234-5683',
    'event_type': 'agent_completed',
    'agent': 'business_analyst',
    'task_id': 'task_business_analyst_1729945800',
    'project': 'context-studio',
    'workflow_run_id': 'pipeline_context-studio_123_1729945800',
    'data': {
        'agent_execution_id': 'exec-uuid-9876-5432',
        'success': True,
        'duration_ms': 350000,  # Total agent execution time
        'output_length': 12450,
        'github_comment_id': 'IC_kwDOABCDEF01',
        'github_comment_url': 'https://github.com/org/repo/issues/123#issuecomment-12345',
        'branch_pushed': False,  # If issues workspace
        'commit_sha': None,  # If code changes made
        'discussion_comment_id': 'DC_kwDOABCDEF02',  # If discussions workspace
        'completed_work': [
            'Requirements analysis completed',
            'User stories created',
            'Acceptance criteria defined'
        ]
    }
}
```

**Key Fields**:
- `duration_ms`: Total time from task_received to completed
- `github_comment_id`: Link to posted output
- `completed_work`: Summary of work items

**Consumer Use Cases**:
- Web UI displays "Agent completed" with link to output
- Monitoring tracks success rate and duration
- Analytics on work item completion

---

### 7. agent_failed

**Purpose**: Signals that the agent execution failed due to an error.

**Emitted By**: `AgentExecutor.execute_agent()` (in exception handler)

**When Emitted**: When any exception occurs during agent execution

**Event Structure**:
```python
{
    'timestamp': '2025-10-26T10:32:15.000Z',
    'event_id': 'uuid-1234-5684',
    'event_type': 'agent_failed',
    'agent': 'business_analyst',
    'task_id': 'task_business_analyst_1729945800',
    'project': 'context-studio',
    'workflow_run_id': 'pipeline_context-studio_123_1729945800',
    'data': {
        'agent_execution_id': 'exec-uuid-9876-5432',
        'success': False,
        'duration_ms': 125000,
        'error_type': 'TimeoutError',
        'error_message': 'Claude call exceeded timeout of 3600 seconds',
        'error_traceback': '...',  # Full traceback
        'failure_stage': 'claude_call',  # Where it failed
        'retry_attempted': False,
        'retry_count': 0
    }
}
```

**Key Fields**:
- `error_type`: Exception class name
- `error_message`: Human-readable error
- `failure_stage`: Which stage failed (task_validation, workspace_prep, claude_call, etc.)
- `retry_attempted`: Whether automatic retry was attempted

**Consumer Use Cases**:
- Web UI displays "Agent failed" with error message
- Alerting system triggers notifications
- Analytics on failure rates and types
- Automatic retry logic

---

### 8. tool_execution_started

**Purpose**: Signals that Claude is executing a tool (file read, bash command, etc.).

**Emitted By**: Stream callback (from Claude Code stream events)

**When Emitted**: When Claude emits a tool_use event

**Event Structure**:
```python
{
    'timestamp': '2025-10-26T10:31:00.000Z',
    'event_id': 'uuid-1234-5685',
    'event_type': 'tool_execution_started',
    'agent': 'business_analyst',
    'task_id': 'task_business_analyst_1729945800',
    'project': 'context-studio',
    'workflow_run_id': 'pipeline_context-studio_123_1729945800',
    'data': {
        'agent_execution_id': 'exec-uuid-9876-5432',
        'tool_name': 'Read',
        'tool_input': {
            'file_path': '/workspace/src/main.py'
        }
    }
}
```

**Consumer Use Cases**:
- Web UI displays "Reading file..." in real-time
- Debugging tool usage patterns
- Analytics on tool frequency

---

### 9. tool_execution_completed

**Purpose**: Signals that Claude's tool execution completed.

**Emitted By**: Stream callback (from Claude Code stream events)

**When Emitted**: When Claude emits a tool_result event

**Event Structure**:
```python
{
    'timestamp': '2025-10-26T10:31:05.000Z',
    'event_id': 'uuid-1234-5686',
    'event_type': 'tool_execution_completed',
    'agent': 'business_analyst',
    'task_id': 'task_business_analyst_1729945800',
    'project': 'context-studio',
    'workflow_run_id': 'pipeline_context-studio_123_1729945800',
    'data': {
        'agent_execution_id': 'exec-uuid-9876-5432',
        'tool_name': 'Read',
        'success': True,
        'output_length': 2340,
        'error': None
    }
}
```

**Consumer Use Cases**:
- Web UI displays tool completion
- Performance tracking for tool execution
- Error analysis for failed tools

---

## Event Relationships

### Parent-Child Relationships

```
task_received (parent)
├── agent_initialized
├── prompt_constructed
├── claude_call_started (parent)
│   ├── tool_execution_started (child)
│   ├── tool_execution_completed (child)
│   └── ... more tool executions
├── claude_call_completed
└── agent_completed OR agent_failed
```

### Timing Relationships

```
Event                    | Typical Timing
-------------------------|----------------
task_received            | T+0s
agent_initialized        | T+2-5s (workspace prep)
prompt_constructed       | T+5-8s
claude_call_started      | T+8-10s
  [Claude processing]    | 30s - 10min (variable)
claude_call_completed    | T+40s - 10min
agent_completed          | T+45s - 10min (+ GitHub posting)
```

## Event Consumption Patterns

### Real-Time Monitoring (Web UI)
```python
# Subscribe to Redis Pub/Sub
redis.subscribe('orchestrator:agent_events')

for message in redis.listen():
    event = json.loads(message['data'])

    if event['event_type'] == 'agent_initialized':
        ui.show_progress_bar(event['agent'])

    elif event['event_type'] == 'agent_completed':
        ui.show_success(event['data']['github_comment_url'])

    elif event['event_type'] == 'agent_failed':
        ui.show_error(event['data']['error_message'])
```

### Historical Analysis (Analytics)
```python
# Query Elasticsearch
es.search(
    index='agent-events-*',
    body={
        'query': {
            'bool': {
                'must': [
                    {'term': {'event_type': 'agent_completed'}},
                    {'range': {'timestamp': {'gte': 'now-7d'}}}
                ]
            }
        },
        'aggs': {
            'avg_duration': {
                'avg': {'field': 'data.duration_ms'}
            },
            'by_agent': {
                'terms': {'field': 'agent'}
            }
        }
    }
)
```

### Recovery Logic (Startup Cleanup)
```python
# Find incomplete agent executions
events = redis.xread({'orchestrator:event_stream': '0'}, count=1000)

initialized = {}
completed = set()

for event in events:
    if event['event_type'] == 'agent_initialized':
        initialized[event['agent_execution_id']] = event

    elif event['event_type'] in ['agent_completed', 'agent_failed']:
        completed.add(event['agent_execution_id'])

# Incomplete executions
incomplete = set(initialized.keys()) - completed

for execution_id in incomplete:
    event = initialized[execution_id]
    # Emit synthetic agent_failed event
    # Cleanup container if exists
```

## Performance Considerations

### Event Size
- Keep event payloads small (<10KB)
- Avoid embedding large outputs in events
- Use references (URLs, IDs) instead of full content

### Event Frequency
- Agent lifecycle events: ~10 events per agent execution
- Tool execution events: 10-100+ per agent (high frequency)
- Consider sampling or aggregation for high-frequency events

### Elasticsearch Impact
- Daily rollover prevents index bloat
- Index template defines field mappings
- ILM policy manages retention and deletion

## Testing Considerations

### Event Emission Testing
```python
def test_agent_lifecycle_events():
    # Mock observability manager
    obs_mock = Mock(ObservabilityManager)

    # Execute agent
    executor = AgentExecutor(obs_mock)
    result = await executor.execute_agent('business_analyst', 'project', context)

    # Verify event sequence
    calls = obs_mock.emit.call_args_list
    assert calls[0][0][0] == EventType.TASK_RECEIVED
    assert calls[1][0][0] == EventType.AGENT_INITIALIZED
    assert calls[-1][0][0] == EventType.AGENT_COMPLETED
```

### Event Consumer Testing
```python
def test_web_ui_event_handling():
    # Inject test events
    redis.publish('orchestrator:agent_events', json.dumps({
        'event_type': 'agent_completed',
        'agent': 'test_agent',
        'data': {'github_comment_url': 'https://...'}
    }))

    # Verify UI update
    assert ui.get_status('test_agent') == 'completed'
    assert ui.get_link('test_agent') == 'https://...'
```

## Migration from Legacy System

### Changes from Legacy
1. **New field**: `agent_execution_id` returned from `agent_initialized`
2. **Standardized structure**: All events now use `data` field for payload
3. **Consolidated tool events**: Previously multiple event types, now just 2

### Backward Compatibility
- Legacy consumers can ignore new fields
- Event type names unchanged
- Distribution channels unchanged (Redis Pub/Sub, Elasticsearch)

## Related Events

- **Decision Events**: `agent_routing_decision` - Why this agent was selected
- **Pipeline Events**: `stage_completed` - Agent completion in pipeline context
- **GitHub Events**: `github_comment_posted` - Output posted to GitHub
- **Stream Events**: `claude_stream_*` - Real-time Claude output

## Summary

Agent lifecycle events provide complete visibility into agent execution from task reception to completion. These events enable:

- **Real-time monitoring**: Track agent progress in web UI
- **Performance analytics**: Measure duration, token usage, success rates
- **Debugging**: Understand failure points and error conditions
- **Recovery**: Detect and cleanup incomplete executions
- **Billing**: Track token usage for cost allocation

The standardized event structure and comprehensive payload ensure all necessary information is captured for observability, debugging, and analytics.
