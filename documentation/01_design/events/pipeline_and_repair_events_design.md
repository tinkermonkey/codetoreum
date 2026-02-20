# Pipeline and Repair Cycle Events Design

## Overview

Pipeline and repair cycle events track the execution of multi-stage workflows and test-driven repair cycles. These events provide visibility into complex, long-running processes that span multiple agent executions and test iterations.

## Pipeline Events

Pipeline events track the execution of multi-stage pipelines from start to completion, including stage transitions, checkpointing, and error recovery.

### Event Flow

```
pipeline_started
├── stage_started (stage 1)
│   ├── [agent lifecycle events]
│   └── stage_completed
├── checkpoint_saved
├── stage_started (stage 2)
│   ├── [review cycle events if review required]
│   └── stage_completed
├── checkpoint_saved
└── pipeline_completed (or pipeline_failed)
```

---

### pipeline_started

**Purpose**: Signals that a pipeline execution has begun.

**Emitted By**: `SequentialPipeline.execute()`

**When Emitted**: At the start of pipeline execution, before first stage

**Event Structure**:
```python
{
    'timestamp': '2025-10-26T10:00:00.000Z',
    'event_id': 'uuid-1234-5678',
    'event_type': 'pipeline_started',
    'agent': None,  # No specific agent yet
    'task_id': 'task_123',
    'project': 'context-studio',
    'workflow_run_id': 'pipeline_context-studio_123_1729945200',
    'data': {
        'issue_number': 123,
        'board': 'Development',
        'pipeline_template': 'sdlc_execution',
        'total_stages': 5,
        'stage_names': [
            'requirements_analysis',
            'architecture_design',
            'implementation',
            'code_review',
            'testing'
        ],
        'workspace_type': 'issues',
        'branch_name': 'feature/issue-123',
        'trigger': 'card_movement',
        'estimated_duration_minutes': 45
    }
}
```

**Key Fields**:
- `pipeline_template`: Template used to construct pipeline
- `total_stages`: Number of stages in pipeline
- `stage_names`: Ordered list of stage names
- `estimated_duration_minutes`: Rough time estimate

**Consumer Use Cases**:
- Web UI displays "Pipeline executing" with progress bar
- Monitoring tracks pipeline start rate
- Analytics on pipeline duration

---

### stage_started

**Purpose**: Signals that a pipeline stage has begun execution.

**Emitted By**: `SequentialPipeline._execute_stage()`

**When Emitted**: Before stage execution begins

**Event Structure**:
```python
{
    'timestamp': '2025-10-26T10:05:00.000Z',
    'event_id': 'uuid-1234-5679',
    'event_type': 'stage_started',
    'agent': 'business_analyst',
    'task_id': 'task_123',
    'project': 'context-studio',
    'workflow_run_id': 'pipeline_context-studio_123_1729945200',
    'data': {
        'issue_number': 123,
        'board': 'Development',
        'stage_index': 0,
        'stage_name': 'requirements_analysis',
        'stage_type': 'agent',  # 'agent' | 'repair_cycle'
        'agent': 'business_analyst',
        'review_required': True,
        'reviewer_agent': 'requirements_reviewer',
        'depends_on': [],  # Empty for first stage
        'previous_stage_output': None
    }
}
```

**Key Fields**:
- `stage_index`: Position in pipeline (0-indexed)
- `stage_type`: Type of stage (agent or repair_cycle)
- `review_required`: Whether stage requires review
- `depends_on`: Previous stages this stage depends on

**Consumer Use Cases**:
- Web UI updates progress: "Stage 1/5: Requirements Analysis"
- Monitoring tracks stage start
- Alerts if stage doesn't start within expected time

---

### stage_completed

**Purpose**: Signals that a pipeline stage has completed successfully.

**Emitted By**: `SequentialPipeline._execute_stage()`

**When Emitted**: After stage execution completes successfully

**Event Structure**:
```python
{
    'timestamp': '2025-10-26T10:20:00.000Z',
    'event_id': 'uuid-1234-5680',
    'event_type': 'stage_completed',
    'agent': 'business_analyst',
    'task_id': 'task_123',
    'project': 'context-studio',
    'workflow_run_id': 'pipeline_context-studio_123_1729945200',
    'data': {
        'issue_number': 123,
        'board': 'Development',
        'stage_index': 0,
        'stage_name': 'requirements_analysis',
        'duration_ms': 900000,  # 15 minutes
        'success': True,
        'review_cycle_completed': True,
        'review_iterations': 2,
        'output_length': 12450,
        'github_comment_id': 'IC_kwDOABCDEF01',
        'next_stage': 'architecture_design'
    }
}
```

**Key Metrics**:
- `duration_ms`: Stage execution time
- `review_cycle_completed`: Whether review cycle (if any) completed
- `review_iterations`: Number of maker-checker iterations

**Consumer Use Cases**:
- Web UI updates progress: "Stage 1/5 Complete (15 minutes)"
- Performance analytics on stage duration
- Advance to next stage

---

### stage_failed

**Purpose**: Signals that a pipeline stage failed.

**Emitted By**: `SequentialPipeline._execute_stage()` (exception handler)

**When Emitted**: When stage execution raises exception

**Event Structure**:
```python
{
    'timestamp': '2025-10-26T10:15:00.000Z',
    'event_id': 'uuid-1234-5681',
    'event_type': 'stage_failed',
    'agent': 'business_analyst',
    'task_id': 'task_123',
    'project': 'context-studio',
    'workflow_run_id': 'pipeline_context-studio_123_1729945200',
    'data': {
        'issue_number': 123,
        'board': 'Development',
        'stage_index': 0,
        'stage_name': 'requirements_analysis',
        'duration_ms': 600000,  # Failed after 10 minutes
        'success': False,
        'error_type': 'TimeoutError',
        'error_message': 'Agent execution exceeded timeout',
        'error_traceback': '...',
        'retry_attempted': True,
        'retry_count': 3,
        'pipeline_will_continue': False
    }
}
```

**Key Fields**:
- `error_type`: Exception type
- `retry_attempted`: Whether automatic retry was tried
- `pipeline_will_continue`: Whether pipeline continues or aborts

**Consumer Use Cases**:
- Web UI displays "Stage Failed" with error
- Alerting system triggers notification
- Pipeline decides whether to continue or abort

---

### checkpoint_saved

**Purpose**: Records that pipeline state was saved to disk for recovery.

**Emitted By**: `StateManager.save_checkpoint()`

**When Emitted**: After each stage completes or at configurable intervals

**Event Structure**:
```python
{
    'timestamp': '2025-10-26T10:20:05.000Z',
    'event_id': 'uuid-1234-5682',
    'event_type': 'checkpoint_saved',
    'agent': None,
    'task_id': 'task_123',
    'project': 'context-studio',
    'workflow_run_id': 'pipeline_context-studio_123_1729945200',
    'data': {
        'issue_number': 123,
        'checkpoint_id': 'checkpoint_123_1729945200_stage0',
        'checkpoint_path': '/app/orchestrator_data/state/checkpoint_123_1729945200_stage0.yaml',
        'current_stage': 0,
        'completed_stages': ['requirements_analysis'],
        'checkpoint_size_bytes': 45678,
        'can_resume_from': True
    }
}
```

**Key Fields**:
- `checkpoint_id`: Unique identifier for this checkpoint
- `current_stage`: Last completed stage index
- `can_resume_from`: Whether pipeline can resume from this checkpoint

**Consumer Use Cases**:
- Recovery system uses checkpoints to resume after failure
- Monitoring tracks checkpoint frequency
- Debugging uses checkpoints to understand pipeline state

---

### checkpoint_loaded

**Purpose**: Records that pipeline state was restored from disk.

**Emitted By**: `StateManager.load_checkpoint()`

**When Emitted**: During pipeline recovery after system restart

**Event Structure**:
```python
{
    'timestamp': '2025-10-26T11:00:00.000Z',
    'event_id': 'uuid-1234-5683',
    'event_type': 'checkpoint_loaded',
    'agent': None,
    'task_id': 'task_123',
    'project': 'context-studio',
    'workflow_run_id': 'pipeline_context-studio_123_1729945200',
    'data': {
        'issue_number': 123,
        'checkpoint_id': 'checkpoint_123_1729945200_stage0',
        'checkpoint_age_seconds': 2400,  # 40 minutes old
        'resume_from_stage': 1,
        'completed_stages': ['requirements_analysis'],
        'remaining_stages': [
            'architecture_design',
            'implementation',
            'code_review',
            'testing'
        ]
    }
}
```

**Consumer Use Cases**:
- Monitoring tracks recovery success rate
- Debugging understands recovery scenarios
- Web UI displays "Pipeline Resumed" status

---

### pipeline_completed

**Purpose**: Signals that entire pipeline completed successfully.

**Emitted By**: `SequentialPipeline.execute()`

**When Emitted**: After final stage completes successfully

**Event Structure**:
```python
{
    'timestamp': '2025-10-26T11:30:00.000Z',
    'event_id': 'uuid-1234-5684',
    'event_type': 'pipeline_completed',
    'agent': None,
    'task_id': 'task_123',
    'project': 'context-studio',
    'workflow_run_id': 'pipeline_context-studio_123_1729945200',
    'data': {
        'issue_number': 123,
        'board': 'Development',
        'success': True,
        'total_duration_ms': 5400000,  # 90 minutes
        'stages_completed': 5,
        'stages_failed': 0,
        'total_review_iterations': 8,
        'final_output': {
            'branch': 'feature/issue-123',
            'commit_sha': 'abc123def456',
            'pull_request_url': 'https://github.com/org/repo/pull/456'
        },
        'work_summary': [
            'Requirements analyzed and documented',
            'Architecture designed',
            'Code implemented',
            'Code reviewed and approved',
            'Tests passing'
        ]
    }
}
```

**Key Metrics**:
- `total_duration_ms`: End-to-end pipeline time
- `stages_completed`: Successful stages
- `total_review_iterations`: Sum of all review cycles

**Consumer Use Cases**:
- Web UI displays "Pipeline Complete" with success banner
- Monitoring tracks completion rate and duration
- Analytics on pipeline performance
- Notification to stakeholders

---

## Repair Cycle Events

Repair cycle events track test-driven repair cycles where an agent iteratively fixes code until tests pass.

### Event Flow

```
repair_cycle_started
├── repair_cycle_container_started
├── repair_cycle_iteration (iteration 1)
│   ├── repair_cycle_test_execution_completed (failed)
│   ├── repair_cycle_file_fix_started (file 1)
│   ├── repair_cycle_file_fix_completed
│   ├── repair_cycle_file_fix_started (file 2)
│   └── repair_cycle_file_fix_completed
├── repair_cycle_container_checkpoint_updated
├── repair_cycle_iteration (iteration 2)
│   ├── repair_cycle_test_execution_completed (passed)
│   └── repair_cycle_warning_review_started (if configured)
└── repair_cycle_completed
```

---

### repair_cycle_started

**Purpose**: Signals that a repair cycle has been initiated.

**Emitted By**: `RepairCycleStage.execute()`

**When Emitted**: At start of repair cycle, before container creation

**Event Structure**:
```python
{
    'timestamp': '2025-10-26T12:00:00.000Z',
    'event_id': 'uuid-2345-6789',
    'event_type': 'repair_cycle_started',
    'agent': 'senior_software_engineer',
    'task_id': 'task_456',
    'project': 'context-studio',
    'workflow_run_id': 'pipeline_context-studio_124_1729948800',
    'data': {
        'issue_number': 124,
        'board': 'Development',
        'run_id': 'repair_context-studio_124_1729948800',
        'test_types': ['unit', 'integration', 'lint'],
        'max_total_agent_calls': 100,
        'checkpoint_interval': 5,
        'test_configs': [
            {
                'type': 'unit',
                'command': 'pytest tests/unit/',
                'timeout': 300,
                'max_iterations': 5,
                'review_warnings': True
            },
            {
                'type': 'integration',
                'command': 'pytest tests/integration/',
                'timeout': 600,
                'max_iterations': 3,
                'review_warnings': False
            }
        ]
    }
}
```

**Key Fields**:
- `test_types`: Types of tests to run
- `max_total_agent_calls`: Circuit breaker limit
- `checkpoint_interval`: Checkpoint frequency

**Consumer Use Cases**:
- Web UI displays "Repair Cycle Starting"
- Monitoring tracks repair cycle initiation
- Estimates time based on test suite size

---

### repair_cycle_container_started

**Purpose**: Records that a dedicated repair cycle container was created.

**Emitted By**: `RepairCycleRunner.run_repair_cycle_in_container()`

**When Emitted**: After Docker container is created and tracked in Redis

**Event Structure**:
```python
{
    'timestamp': '2025-10-26T12:00:15.000Z',
    'event_id': 'uuid-2345-6790',
    'event_type': 'repair_cycle_container_started',
    'agent': 'senior_software_engineer',
    'task_id': 'task_456',
    'project': 'context-studio',
    'workflow_run_id': 'pipeline_context-studio_124_1729948800',
    'data': {
        'issue_number': 124,
        'container_name': 'repair-context-studio-124',
        'container_id': 'docker-abc123',
        'redis_tracking_key': 'repair_cycle:context-studio:124',
        'ttl_seconds': 7200,  # 2 hours
        'can_recover': True,
        'workspace_path': '/workspace'
    }
}
```

**Key Fields**:
- `container_name`: Docker container name
- `redis_tracking_key`: Key for state persistence
- `can_recover`: Whether container can be recovered on restart

**Consumer Use Cases**:
- Container recovery on system restart
- Monitoring tracks active repair containers
- Cleanup on timeout or completion

---

### repair_cycle_iteration

**Purpose**: Signals the start of a repair cycle iteration (test → fix loop).

**Emitted By**: `RepairCycleRunner` (iteration loop)

**When Emitted**: At the start of each test → fix iteration

**Event Structure**:
```python
{
    'timestamp': '2025-10-26T12:01:00.000Z',
    'event_id': 'uuid-2345-6791',
    'event_type': 'repair_cycle_iteration',
    'agent': 'senior_software_engineer',
    'task_id': 'task_456',
    'project': 'context-studio',
    'workflow_run_id': 'pipeline_context-studio_124_1729948800',
    'data': {
        'issue_number': 124,
        'iteration': 1,
        'test_type': 'unit',
        'agent_call_count': 0,
        'max_iterations': 5,
        'max_total_agent_calls': 100,
        'iterations_remaining': 4,
        'calls_remaining': 100
    }
}
```

**Key Fields**:
- `iteration`: Current iteration number (1-indexed)
- `agent_call_count`: Total agent calls so far
- `iterations_remaining`: Before max iterations
- `calls_remaining`: Before circuit breaker

**Consumer Use Cases**:
- Web UI updates progress: "Iteration 1/5"
- Monitoring tracks iteration count
- Estimates remaining time

---

### repair_cycle_test_execution_completed

**Purpose**: Records the result of a test execution within a repair cycle.

**Emitted By**: `RepairCycleRunner` (after test execution)

**When Emitted**: After test command completes

**Event Structure**:
```python
{
    'timestamp': '2025-10-26T12:03:00.000Z',
    'event_id': 'uuid-2345-6792',
    'event_type': 'repair_cycle_test_execution_completed',
    'agent': 'senior_software_engineer',
    'task_id': 'task_456',
    'project': 'context-studio',
    'workflow_run_id': 'pipeline_context-studio_124_1729948800',
    'data': {
        'issue_number': 124,
        'test_type': 'unit',
        'success': False,
        'duration_ms': 12000,
        'total_tests': 145,
        'passed': 138,
        'failed': 7,
        'skipped': 0,
        'warnings': 12,
        'failures': [
            {
                'file': 'tests/unit/test_service.py',
                'test': 'test_create_user',
                'error': 'AssertionError: Expected 201, got 400',
                'traceback': '...'
            },
            # ... more failures
        ],
        'files_with_failures': ['tests/unit/test_service.py', 'tests/unit/test_repo.py']
    }
}
```

**Key Fields**:
- `success`: Overall test result
- Test counts: `total_tests`, `passed`, `failed`, `skipped`
- `failures`: Detailed failure information
- `files_with_failures`: Files needing fixes

**Consumer Use Cases**:
- Web UI displays test results: "7 tests failing"
- Monitoring tracks test success rate
- Agent receives failure details for fixing

---

### repair_cycle_file_fix_started

**Purpose**: Signals that agent is starting to fix failures in a specific file.

**Emitted By**: `RepairCycleRunner` (file fix loop)

**When Emitted**: Before agent is called to fix a file

**Event Structure**:
```python
{
    'timestamp': '2025-10-26T12:04:00.000Z',
    'event_id': 'uuid-2345-6793',
    'event_type': 'repair_cycle_file_fix_started',
    'agent': 'senior_software_engineer',
    'task_id': 'task_456',
    'project': 'context-studio',
    'workflow_run_id': 'pipeline_context-studio_124_1729948800',
    'data': {
        'issue_number': 124,
        'file': 'tests/unit/test_service.py',
        'failure_count': 3,
        'failures': [
            {'test': 'test_create_user', 'error': 'AssertionError...'},
            {'test': 'test_update_user', 'error': 'AssertionError...'},
            {'test': 'test_delete_user', 'error': 'AssertionError...'}
        ],
        'file_fix_iteration': 1,
        'max_file_iterations': 3,
        'previous_fix_attempts': []
    }
}
```

**Key Fields**:
- `file`: File being fixed
- `failure_count`: Number of failures in this file
- `file_fix_iteration`: Attempt number for this file
- `previous_fix_attempts`: History of fixes (for context)

**Consumer Use Cases**:
- Web UI displays "Fixing tests/unit/test_service.py (3 failures)"
- Monitoring tracks file fix attempts
- Debugging understands fix history

---

### repair_cycle_file_fix_completed

**Purpose**: Records the result of an agent's attempt to fix a file.

**Emitted By**: `RepairCycleRunner` (after agent execution and re-test)

**When Emitted**: After agent fixes file and tests are re-run for that file

**Event Structure**:
```python
{
    'timestamp': '2025-10-26T12:08:00.000Z',
    'event_id': 'uuid-2345-6794',
    'event_type': 'repair_cycle_file_fix_completed',
    'agent': 'senior_software_engineer',
    'task_id': 'task_456',
    'project': 'context-studio',
    'workflow_run_id': 'pipeline_context-studio_124_1729948800',
    'data': {
        'issue_number': 124,
        'file': 'tests/unit/test_service.py',
        'file_fix_iteration': 1,
        'success': True,  # File tests now pass
        'duration_ms': 240000,  # 4 minutes
        'failures_before': 3,
        'failures_after': 0,
        'tests_now_passing': ['test_create_user', 'test_update_user', 'test_delete_user'],
        'changes_made': 'Fixed HTTP status code validation'
    }
}
```

**Key Fields**:
- `success`: Whether file tests now pass
- `failures_before` / `failures_after`: Progress metric
- `tests_now_passing`: Which tests were fixed

**Consumer Use Cases**:
- Web UI displays "File fixed: 3 tests now passing"
- Monitoring tracks fix success rate
- Move to next file or next iteration

---

### repair_cycle_container_checkpoint_updated

**Purpose**: Records that repair cycle state was checkpointed to Redis.

**Emitted By**: `RepairCycleRunner` (checkpoint interval)

**When Emitted**: Every N agent calls (checkpoint_interval)

**Event Structure**:
```python
{
    'timestamp': '2025-10-26T12:10:00.000Z',
    'event_id': 'uuid-2345-6795',
    'event_type': 'repair_cycle_container_checkpoint_updated',
    'agent': 'senior_software_engineer',
    'task_id': 'task_456',
    'project': 'context-studio',
    'workflow_run_id': 'pipeline_context-studio_124_1729948800',
    'data': {
        'issue_number': 124,
        'container_name': 'repair-context-studio-124',
        'checkpoint': {
            'iteration': 2,
            'test_type': 'unit',
            'agent_call_count': 5,
            'files_fixed': ['tests/unit/test_service.py'],
            'timestamp': '2025-10-26T12:10:00.000Z'
        },
        'can_recover': True,
        'checkpoint_age_seconds': 0
    }
}
```

**Key Fields**:
- `checkpoint`: Full checkpoint state
- `can_recover`: Whether recovery is possible from this checkpoint

**Consumer Use Cases**:
- Recovery system uses checkpoint to resume after crash
- Monitoring tracks checkpoint frequency
- Debugging uses checkpoint to understand repair state

---

### repair_cycle_completed

**Purpose**: Signals that repair cycle finished (tests passed or max iterations reached).

**Emitted By**: `RepairCycleStage.execute()`

**When Emitted**: After all test types pass or circuit breaker triggers

**Event Structure**:
```python
{
    'timestamp': '2025-10-26T12:30:00.000Z',
    'event_id': 'uuid-2345-6796',
    'event_type': 'repair_cycle_completed',
    'agent': 'senior_software_engineer',
    'task_id': 'task_456',
    'project': 'context-studio',
    'workflow_run_id': 'pipeline_context-studio_124_1729948800',
    'data': {
        'issue_number': 124,
        'success': True,
        'total_duration_ms': 1800000,  # 30 minutes
        'total_iterations': 8,
        'total_agent_calls': 15,
        'test_results': {
            'unit': {'success': True, 'iterations': 3},
            'integration': {'success': True, 'iterations': 2},
            'lint': {'success': True, 'iterations': 1}
        },
        'files_modified': [
            'tests/unit/test_service.py',
            'tests/unit/test_repo.py',
            'tests/integration/test_api.py'
        ],
        'circuit_breaker_triggered': False,
        'escalation_required': False
    }
}
```

**Key Metrics**:
- `total_duration_ms`: End-to-end repair time
- `total_iterations` / `total_agent_calls`: Work metrics
- `test_results`: Per-test-type results
- `files_modified`: Which files were changed

**Consumer Use Cases**:
- Web UI displays "Repair Cycle Complete: All tests passing"
- Monitoring tracks repair cycle success rate and duration
- Analytics on repair efficiency
- Move to next pipeline stage

---

## Event Relationships

### Pipeline Run Tracing
All events within a pipeline run share the same `workflow_run_id`, enabling complete trace reconstruction:

```sql
SELECT * FROM events
WHERE workflow_run_id = 'pipeline_context-studio_123_1729945200'
ORDER BY timestamp ASC;
```

This returns the complete timeline from `pipeline_started` to `pipeline_completed`.

### Stage-to-Agent Correlation
Stage events link to agent lifecycle events via `task_id`:

```
stage_started (task_id: task_123, stage_index: 0)
  └─> task_received (task_id: task_123)
      └─> agent_initialized (task_id: task_123)
          └─> agent_completed (task_id: task_123)
              └─> stage_completed (task_id: task_123, stage_index: 0)
```

## Performance Considerations

### Checkpoint Frequency
- **Too frequent**: Performance overhead, disk I/O
- **Too infrequent**: More work lost on failure
- **Recommended**: Every 5 agent calls or 10 minutes

### Event Size
- Repair cycle events can be large (failure details)
- Consider truncating tracebacks in events
- Store full details in separate artifact storage

## Testing

```python
def test_pipeline_events():
    pipeline = SequentialPipeline(stages)
    obs_mock = Mock()

    result = await pipeline.execute(context, obs_mock)

    # Verify event sequence
    assert obs_mock.emit.call_count >= 4  # start, stage_start, stage_complete, complete
    assert obs_mock.emit.call_args_list[0]['event_type'] == 'pipeline_started'
    assert obs_mock.emit.call_args_list[-1]['event_type'] == 'pipeline_completed'
```

## Summary

Pipeline and repair cycle events provide comprehensive visibility into complex, multi-stage processes:

- **Pipeline events**: Track end-to-end workflow execution
- **Repair cycle events**: Track test-driven iterative fixing
- **Checkpointing**: Enable recovery after failures
- **Traceability**: Complete audit trail via workflow_run_id

These events enable monitoring, debugging, recovery, and analytics for the most complex operations in Codetoreum.
