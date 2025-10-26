# System and Integration Events Design

## Overview

This document covers the remaining event categories in Codetoreum:
- **System Events**: Startup, shutdown, health monitoring
- **GitHub Integration Events**: Board operations, issue/PR management
- **Container Events**: Docker lifecycle management
- **Configuration Events**: Config loading and reconciliation
- **Stream Events**: Real-time Claude Code output

These events provide visibility into system operations, external integrations, and infrastructure management.

---

## System Events

System events track orchestrator lifecycle and health monitoring.

### system_started

**Purpose**: Records that system startup sequence has begun.

**Emitted By**: `main.py::main()`

**When Emitted**: At the beginning of main() function

**Event Structure**:
```python
{
    'timestamp': '2025-10-26T09:00:00.000Z',
    'event_id': 'uuid-system-0001',
    'event_type': 'system_started',
    'agent': None,
    'task_id': None,
    'project': 'system',
    'data': {
        'version': '2.0.0',
        'environment': 'production',
        'python_version': '3.11.5',
        'platform': 'linux',
        'redis_host': 'redis:6379',
        'elasticsearch_host': 'elasticsearch:9200',
        'recovery_mode': False
    }
}
```

**Consumer Use Cases**:
- Monitoring dashboards show system uptime
- Alerting on unexpected restarts
- Version tracking

---

### system_ready

**Purpose**: Signals that all subsystems are initialized and system is ready for work.

**Emitted By**: `main.py::main()` (after initialization complete)

**When Emitted**: After all infrastructure connections verified and project reconciliation complete

**Event Structure**:
```python
{
    'timestamp': '2025-10-26T09:01:30.000Z',
    'event_id': 'uuid-system-0002',
    'event_type': 'system_ready',
    'agent': None,
    'task_id': None,
    'project': 'system',
    'data': {
        'startup_duration_ms': 90000,  # 90 seconds
        'components_initialized': [
            'redis',
            'elasticsearch',
            'github_integration',
            'docker',
            'workspace_manager',
            'observability',
            'task_queue',
            'project_monitor'
        ],
        'projects_ready': ['context-studio', 'codetoreum'],
        'containers_recovered': 2,
        'tasks_queued': 1,
        'ready_for_work': True
    }
}
```

**Consumer Use Cases**:
- Health monitoring confirms system operational
- Performance tracking of startup time
- Ready signal for load balancer

---

### cleanup_started

**Purpose**: Records start of startup cleanup operations.

**Emitted By**: `main.py::main()` (cleanup phase)

**When Emitted**: Before orphaned container/state cleanup

**Event Structure**:
```python
{
    'timestamp': '2025-10-26T09:00:30.000Z',
    'event_id': 'uuid-system-0003',
    'event_type': 'cleanup_started',
    'agent': None,
    'task_id': None,
    'project': 'system',
    'data': {
        'cleanup_operations': [
            'orphaned_containers',
            'stuck_execution_states',
            'stale_pipeline_runs',
            'stale_agent_events',
            'orphaned_redis_keys'
        ]
    }
}
```

---

### cleanup_completed

**Purpose**: Records results of startup cleanup.

**Emitted By**: `main.py::main()` (after cleanup)

**When Emitted**: After all cleanup operations complete

**Event Structure**:
```python
{
    'timestamp': '2025-10-26T09:01:00.000Z',
    'event_id': 'uuid-system-0004',
    'event_type': 'cleanup_completed',
    'agent': None,
    'task_id': None,
    'project': 'system',
    'data': {
        'duration_ms': 30000,
        'containers_killed': 3,
        'containers_recovered': 2,
        'execution_states_cleared': 5,
        'pipeline_runs_marked_interrupted': 2,
        'redis_keys_deleted': 8,
        'errors': []
    }
}
```

**Consumer Use Cases**:
- Understand cleanup impact
- Track recovery effectiveness
- Identify recurring cleanup issues

---

### health_check_passed / health_check_failed

**Purpose**: Records results of periodic health checks.

**Emitted By**: `HealthMonitor` (periodic checks)

**When Emitted**: Every 5 minutes (configurable)

**Event Structure**:
```python
{
    'timestamp': '2025-10-26T09:05:00.000Z',
    'event_id': 'uuid-system-0005',
    'event_type': 'health_check_passed',  # or health_check_failed
    'agent': None,
    'task_id': None,
    'project': 'system',
    'data': {
        'check_type': 'full',  # 'full' | 'redis' | 'elasticsearch' | 'github' | 'docker'
        'components_checked': {
            'redis': {'status': 'healthy', 'response_time_ms': 2},
            'elasticsearch': {'status': 'healthy', 'response_time_ms': 45},
            'github': {'status': 'healthy', 'rate_limit_remaining': 4850},
            'docker': {'status': 'healthy', 'containers_running': 12}
        },
        'overall_health': 'healthy',  # 'healthy' | 'degraded' | 'unhealthy'
        'warnings': []
    }
}
```

**Consumer Use Cases**:
- Alerting on health check failures
- Monitoring component availability
- Identifying degraded performance

---

## GitHub Integration Events

Events tracking GitHub API operations.

### github_card_movement_detected

**Purpose**: Records when card movement detected on GitHub board.

**Emitted By**: `ProjectMonitor._detect_card_movement()`

**When Emitted**: When card column changes

**Event Structure**:
```python
{
    'timestamp': '2025-10-26T10:30:00.000Z',
    'event_id': 'uuid-gh-0001',
    'event_type': 'github_card_movement_detected',
    'agent': None,
    'task_id': None,
    'project': 'context-studio',
    'data': {
        'issue_number': 123,
        'board': 'Development',
        'from_column': 'To Do',
        'to_column': 'In Progress',
        'issue_title': 'Add user authentication',
        'issue_labels': ['feature', 'priority:high'],
        'detection_latency_seconds': 15,  # Time from GitHub update to detection
        'will_queue_task': True
    }
}
```

**Consumer Use Cases**:
- Understand trigger source for tasks
- Track detection latency
- Debugging task creation

---

### github_comment_posted

**Purpose**: Records when agent output is posted as GitHub comment.

**Emitted By**: `GitHubIntegration.post_agent_output()`

**When Emitted**: After comment successfully created

**Event Structure**:
```python
{
    'timestamp': '2025-10-26T10:36:00.000Z',
    'event_id': 'uuid-gh-0002',
    'event_type': 'github_comment_posted',
    'agent': 'business_analyst',
    'task_id': 'task_123',
    'project': 'context-studio',
    'data': {
        'issue_number': 123,
        'workspace_type': 'issues',  # or 'discussions'
        'comment_id': 'IC_kwDOABCDEF01',
        'comment_url': 'https://github.com/org/repo/issues/123#issuecomment-12345',
        'comment_length': 12450,
        'threaded': False,
        'reply_to_id': None,  # If threaded
        'api_latency_ms': 450
    }
}
```

**Consumer Use Cases**:
- Link agent execution to GitHub output
- Track API performance
- Debugging posting failures

---

### github_board_reconciled

**Purpose**: Records successful board reconciliation with configuration.

**Emitted By**: `GitHubProjectManager.reconcile_project()`

**When Emitted**: After board structure synced with config

**Event Structure**:
```python
{
    'timestamp': '2025-10-26T09:01:15.000Z',
    'event_id': 'uuid-gh-0003',
    'event_type': 'github_board_reconciled',
    'agent': None,
    'task_id': None,
    'project': 'context-studio',
    'data': {
        'board': 'Development',
        'columns_created': 2,
        'columns_updated': 1,
        'labels_created': 3,
        'config_hash': 'abc123def456',
        'reconciliation_duration_ms': 5000,
        'changes_made': [
            'Created column: Code Review',
            'Updated column: Testing',
            'Created label: pipeline:development'
        ]
    }
}
```

**Consumer Use Cases**:
- Track configuration changes
- Audit board modifications
- Debugging reconciliation issues

---

### github_pr_created

**Purpose**: Records when pull request is created.

**Emitted By**: `GitWorkflowManager.create_pull_request()`

**When Emitted**: After PR successfully created via gh CLI

**Event Structure**:
```python
{
    'timestamp': '2025-10-26T11:00:00.000Z',
    'event_id': 'uuid-gh-0004',
    'event_type': 'github_pr_created',
    'agent': 'senior_software_engineer',
    'task_id': 'task_456',
    'project': 'context-studio',
    'data': {
        'issue_number': 124,
        'pr_number': 456,
        'pr_url': 'https://github.com/org/repo/pull/456',
        'branch': 'feature/issue-124',
        'base_branch': 'main',
        'commits': 8,
        'files_changed': 15,
        'auto_created': True
    }
}
```

---

## Container Events

Events tracking Docker container lifecycle.

### container_started

**Purpose**: Records when Docker container starts.

**Emitted By**: `DockerAgentRunner.run_agent_in_container()`

**When Emitted**: After docker run command succeeds

**Event Structure**:
```python
{
    'timestamp': '2025-10-26T10:30:10.000Z',
    'event_id': 'uuid-container-0001',
    'event_type': 'container_started',
    'agent': 'business_analyst',
    'task_id': 'task_123',
    'project': 'context-studio',
    'data': {
        'container_name': 'claude-agent-context-studio-task_business_analyst_1729945800',
        'container_id': 'docker-abc123',
        'image': 'context-studio-agent:latest',
        'network': 'orchestrator_default',
        'volumes': [
            '/workspace/context-studio:/workspace',
            '/home/orchestrator/.ssh/id_ed25519:/home/orchestrator/.ssh/id_ed25519:ro'
        ],
        'environment': ['CLAUDE_CODE_OAUTH_TOKEN', 'HOME'],
        'command': 'claude --print --verbose ...',
        'tracking_key': 'agent_container:claude-agent-context-studio-task_business_analyst_1729945800'
    }
}
```

**Consumer Use Cases**:
- Track active containers
- Monitor resource usage
- Debugging container issues

---

### container_recovered

**Purpose**: Records when container recovered on system restart.

**Emitted By**: `AgentContainerRecovery.recover_or_cleanup_containers()`

**When Emitted**: During startup cleanup when running container has valid tracking key

**Event Structure**:
```python
{
    'timestamp': '2025-10-26T09:00:45.000Z',
    'event_id': 'uuid-container-0002',
    'event_type': 'container_recovered',
    'agent': 'business_analyst',
    'task_id': 'task_123',
    'project': 'context-studio',
    'data': {
        'container_name': 'claude-agent-context-studio-task_business_analyst_1729945800',
        'container_id': 'docker-abc123',
        'tracking_key_found': True,
        'container_running': True,
        'uptime_seconds': 3600,  # 1 hour
        'recovery_action': 'leave_running'
    }
}
```

**Consumer Use Cases**:
- Track successful recovery
- Understand container longevity
- Verify recovery logic

---

### container_killed

**Purpose**: Records when orphaned container is killed.

**Emitted By**: `AgentContainerRecovery.recover_or_cleanup_containers()`

**When Emitted**: During startup cleanup when running container has no tracking key

**Event Structure**:
```python
{
    'timestamp': '2025-10-26T09:00:50.000Z',
    'event_id': 'uuid-container-0003',
    'event_type': 'container_killed',
    'agent': None,
    'task_id': None,
    'project': None,
    'data': {
        'container_name': 'claude-agent-orphaned-12345',
        'container_id': 'docker-xyz789',
        'tracking_key_found': False,
        'uptime_seconds': 86400,  # 24 hours
        'kill_reason': 'orphaned',  # 'orphaned' | 'timeout' | 'error'
        'cleanup_action': 'removed'
    }
}
```

**Consumer Use Cases**:
- Track orphaned containers
- Identify cleanup issues
- Debugging container leaks

---

## Configuration Events

Events related to configuration loading and changes.

### config_loaded

**Purpose**: Records when configuration is loaded from disk.

**Emitted By**: `ConfigManager.__init__()`

**When Emitted**: During ConfigManager initialization

**Event Structure**:
```python
{
    'timestamp': '2025-10-26T09:00:05.000Z',
    'event_id': 'uuid-config-0001',
    'event_type': 'config_loaded',
    'agent': None,
    'task_id': None,
    'project': 'system',
    'data': {
        'config_files': [
            'config/foundations/agents.yaml',
            'config/foundations/pipelines.yaml',
            'config/foundations/workflows.yaml',
            'config/foundations/mcp.yaml',
            'config/projects/context-studio.yaml',
            'config/projects/codetoreum.yaml'
        ],
        'agents_loaded': 17,
        'pipelines_loaded': 3,
        'workflows_loaded': 3,
        'projects_loaded': 2,
        'config_hash': 'abc123def456',
        'load_duration_ms': 150
    }
}
```

**Consumer Use Cases**:
- Track configuration changes
- Audit config loads
- Performance monitoring

---

### config_reconciliation_needed

**Purpose**: Records when config hash changed and reconciliation is needed.

**Emitted By**: `StateManager.needs_reconciliation()`

**When Emitted**: When current config hash differs from saved hash

**Event Structure**:
```python
{
    'timestamp': '2025-10-26T09:01:10.000Z',
    'event_id': 'uuid-config-0002',
    'event_type': 'config_reconciliation_needed',
    'agent': None,
    'task_id': None,
    'project': 'context-studio',
    'data': {
        'previous_config_hash': 'old123abc456',
        'current_config_hash': 'new789def012',
        'config_file': 'config/projects/context-studio.yaml',
        'last_synchronized': '2025-10-25T14:30:00Z',
        'changes_detected': True
    }
}
```

---

### dev_container_verified

**Purpose**: Records when dev container image is verified.

**Emitted By**: `DevEnvironmentVerifierAgent` or `DevContainerState.verify_and_update_status()`

**When Emitted**: After Docker image verification succeeds

**Event Structure**:
```python
{
    'timestamp': '2025-10-26T09:05:00.000Z',
    'event_id': 'uuid-config-0003',
    'event_type': 'dev_container_verified',
    'agent': 'dev_environment_verifier',
    'task_id': 'task_789',
    'project': 'context-studio',
    'data': {
        'image_name': 'context-studio-agent:latest',
        'image_id': 'sha256:abc123...',
        'image_size_mb': 1250,
        'build_duration_ms': 180000,  # 3 minutes
        'verification_tests': [
            {'test': 'claude_cli_installed', 'passed': True},
            {'test': 'git_installed', 'passed': True},
            {'test': 'python_dependencies', 'passed': True}
        ],
        'status': 'VERIFIED'
    }
}
```

---

## Stream Events

Real-time events from Claude Code execution.

### claude_stream_text

**Purpose**: Captures text chunks from Claude's response.

**Emitted By**: Stream callback (from Claude Code)

**When Emitted**: When Claude emits text in response

**Event Structure**:
```python
{
    'timestamp': '2025-10-26T10:31:15.000Z',
    'event_id': 'uuid-stream-0001',
    'event_type': 'claude_stream_text',
    'agent': 'business_analyst',
    'task_id': 'task_123',
    'project': 'context-studio',
    'pipeline_run_id': 'pipeline_context-studio_123_1729945800',
    'data': {
        'agent_execution_id': 'exec-uuid-9876-5432',
        'text': 'Based on the requirements provided, I will analyze...',
        'chunk_index': 0,
        'is_final': False
    }
}
```

**Consumer Use Cases**:
- Web UI displays streaming text in real-time
- Users see agent "thinking" live
- Debugging response generation

---

### claude_stream_tool_use

**Purpose**: Captures tool use events from Claude.

**Emitted By**: Stream callback (from Claude Code)

**When Emitted**: When Claude uses a tool

**Event Structure**:
```python
{
    'timestamp': '2025-10-26T10:31:00.000Z',
    'event_id': 'uuid-stream-0002',
    'event_type': 'claude_stream_tool_use',
    'agent': 'business_analyst',
    'task_id': 'task_123',
    'project': 'context-studio',
    'pipeline_run_id': 'pipeline_context-studio_123_1729945800',
    'data': {
        'agent_execution_id': 'exec-uuid-9876-5432',
        'tool_name': 'Read',
        'tool_input': {
            'file_path': '/workspace/src/main.py'
        },
        'tool_use_id': 'tool-use-abc123'
    }
}
```

**Consumer Use Cases**:
- Web UI shows "Reading file..." in real-time
- Track tool usage patterns
- Debugging tool issues

---

### claude_stream_error

**Purpose**: Captures errors in Claude stream.

**Emitted By**: Stream callback (from Claude Code)

**When Emitted**: When error event received in stream

**Event Structure**:
```python
{
    'timestamp': '2025-10-26T10:32:00.000Z',
    'event_id': 'uuid-stream-0003',
    'event_type': 'claude_stream_error',
    'agent': 'business_analyst',
    'task_id': 'task_123',
    'project': 'context-studio',
    'pipeline_run_id': 'pipeline_context-studio_123_1729945800',
    'data': {
        'agent_execution_id': 'exec-uuid-9876-5432',
        'error_type': 'RateLimitError',
        'error_message': 'Rate limit exceeded',
        'error_code': 429,
        'recoverable': True
    }
}
```

**Consumer Use Cases**:
- Web UI displays error to user
- Alerting on errors
- Automatic retry logic

---

### claude_session_continued

**Purpose**: Records when Claude session is continued (conversational mode).

**Emitted By**: `run_claude_code()` (when session_id provided)

**When Emitted**: When resuming existing Claude session

**Event Structure**:
```python
{
    'timestamp': '2025-10-26T11:00:00.000Z',
    'event_id': 'uuid-stream-0004',
    'event_type': 'claude_session_continued',
    'agent': 'business_analyst',
    'task_id': 'task_124',
    'project': 'context-studio',
    'pipeline_run_id': 'pipeline_context-studio_123_1729948800',
    'data': {
        'agent_execution_id': 'exec-uuid-1234-5678',
        'session_id': 'session_abc123',
        'previous_task_id': 'task_123',
        'conversation_turn': 2,
        'session_age_seconds': 3600
    }
}
```

**Consumer Use Cases**:
- Track conversational sessions
- Understand session continuity
- Debugging conversation state

---

## Event Integration Patterns

### Cross-System Event Correlation

Events from different systems can be correlated:

```python
# GitHub event → Task queued → Agent execution → GitHub comment posted
github_card_movement_detected (issue_number: 123)
  └─> task_queued (issue_number: 123, task_id: task_123)
      └─> task_received (task_id: task_123)
          └─> agent_completed (task_id: task_123)
              └─> github_comment_posted (issue_number: 123, task_id: task_123)
```

### Container Lifecycle Tracking

```python
# Container start → Agent execution → Container cleanup
container_started (container_name: claude-agent-...)
  └─> agent_initialized (container_name: claude-agent-...)
      └─> claude_call_started (container_name: claude-agent-...)
          └─> [claude stream events...]
          └─> claude_call_completed
      └─> agent_completed
  └─> container_removed (container_name: claude-agent-...)
```

## Performance Considerations

### Stream Event Volume
- Claude stream events are high-frequency (100+ per agent execution)
- Consider sampling or buffering for Elasticsearch
- Redis Pub/Sub handles real-time delivery
- Redis Streams with TTL for recent history

### GitHub API Rate Limits
- Track rate limit in health_check events
- Alert when remaining requests < threshold
- Implement exponential backoff on failures

## Testing

```python
def test_github_event_emission():
    github_mock = Mock(GitHubIntegration)
    obs_mock = Mock()

    result = await github_mock.post_agent_output(context, comment)

    # Verify event emitted
    obs_mock.emit.assert_called_once()
    event = obs_mock.emit.call_args[0]
    assert event['event_type'] == 'github_comment_posted'
    assert 'comment_id' in event['data']
    assert 'comment_url' in event['data']
```

## Migration from Legacy

### Changes
1. **Standardized structure**: All events use common format
2. **Stream events**: Now captured and forwarded to Redis
3. **Container events**: Enhanced with tracking key references

### Backward Compatibility
- Event names unchanged where possible
- New fields are additive
- Legacy consumers can ignore new fields

## Summary

System and integration events provide visibility into:

- **System operations**: Startup, health, shutdown
- **GitHub integration**: Board monitoring, comment posting
- **Container lifecycle**: Start, recovery, cleanup
- **Configuration**: Loading, reconciliation, verification
- **Claude streaming**: Real-time output, tool use, errors

These events complete the observability picture, covering infrastructure, external integrations, and real-time operations alongside agent execution and decision events.
