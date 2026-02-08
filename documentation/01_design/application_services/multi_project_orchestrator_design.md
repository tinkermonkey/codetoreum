# MultiProjectOrchestrator Application Service Design

## Overview

The **MultiProjectOrchestrator** is an application service that orchestrates workflow execution across multiple independent projects within a single orchestrator process. It coordinates project initialization, per-project workflow execution, and cross-project state management.

**Location**: `src/codetoreum/application/multi_project_orchestrator.py`

**Port Interface**: `src/codetoreum/ports/output/multi_project_orchestrator.py`

## Architecture

The MultiProjectOrchestrator is the top-level orchestration service that:

1. **Manages Projects**: Loads and tracks enabled projects from configuration
2. **Ensures Availability**: Ensures project repositories are cloned and up-to-date
3. **Orchestrates Workflows**: Delegates per-project orchestration to WorkflowOrchestrator
4. **Coordinates State**: Maintains isolation between projects via namespacing
5. **Emits Events**: Publishes orchestration events for observability

```
┌─────────────────────────────────────────────────────────────┐
│         MultiProjectOrchestrator (Application Service)      │
├─────────────────────────────────────────────────────────────┤
│                                                               │
│  ┌─────────────────────────────────────────────────────┐   │
│  │ run_orchestration_cycle()                           │   │
│  │ ├─ Reload project configurations                   │   │
│  │ ├─ Get enabled projects                            │   │
│  │ └─ For each project:                               │   │
│  │    ├─ orchestrate_project()                        │   │
│  │    └─ Collect results                              │   │
│  └─────────────────────────────────────────────────────┘   │
│                          │                                   │
│         ┌────────────────┼────────────────┐                │
│         │                │                │                │
│    Delegates to:    Depends on:      Emits to:             │
│         │                │                │                │
│         ▼                ▼                ▼                │
│  ┌──────────────┐ ┌──────────────┐ ┌──────────────┐       │
│  │ Workflow     │ │ Project      │ │ Event        │       │
│  │ Orchestrator │ │ Manager      │ │ Emitter      │       │
│  │ (per-project)│ │ (config/git) │ │ (events)     │       │
│  └──────────────┘ └──────────────┘ └──────────────┘       │
│                                                               │
└─────────────────────────────────────────────────────────────┘
```

## Core Responsibilities

### 1. Orchestration Cycle Management

**Method**: `run_orchestration_cycle() -> OrchestrationCycleResult`

Executes a complete orchestration cycle:

```python
async def run_orchestration_cycle(self) -> OrchestrationCycleResult:
    """
    1. Record cycle start time
    2. Reload project configurations (detect added/disabled projects)
    3. Get list of enabled projects
    4. Orchestrate each enabled project:
       - Ensure repository cloned
       - Delegate to workflow orchestrator
       - Collect results
    5. Emit orchestration cycle completed event
    6. Return aggregated result
    """
```

**Key Features**:
- **Fault Tolerant**: Errors in one project don't block others
- **Configurable**: Supports configuration reloading each cycle
- **Observable**: Emits events for metrics and debugging
- **Measured**: Tracks cycle duration and metrics

### 2. Per-Project Orchestration

**Method**: `orchestrate_project(project_name: str) -> ProjectOrchestrationResult`

Orchestrates a single project:

```python
async def orchestrate_project(
    self, project_name: str
) -> ProjectOrchestrationResult:
    """
    1. Load project configuration
    2. Ensure repository is cloned
    3. Delegate to workflow orchestrator
    4. Return results
    """
```

**Error Handling**:
- `ResourceNotFoundError`: Project not found → return error result
- `ExternalServiceError`: Clone/API failure → return error result
- Unexpected errors → caught and logged

### 3. Project Status Tracking

**Method**: `get_project_status(project_name: str) -> Dict[str, Any]`

Returns current project status:
- Enabled/disabled state
- Repository URL and branch
- Workspace path
- Organization namespace

**Method**: `list_enabled_projects() -> List[str]`

Returns list of enabled projects for orchestration filtering.

## Port Interface Design

### IMultiProjectOrchestrator

**Location**: `src/codetoreum/ports/output/multi_project_orchestrator.py`

Core port interface defining contracts:

```python
class IMultiProjectOrchestrator(ABC):
    @abstractmethod
    async def run_orchestration_cycle(self) -> OrchestrationCycleResult:
        """Execute complete orchestration across all enabled projects"""
        pass

    @abstractmethod
    async def orchestrate_project(
        self, project_name: str
    ) -> ProjectOrchestrationResult:
        """Execute orchestration for single project"""
        pass

    @abstractmethod
    async def get_project_status(self, project_name: str) -> Dict[str, Any]:
        """Get current status for a project"""
        pass

    @abstractmethod
    async def list_enabled_projects(self) -> List[str]:
        """Get list of enabled projects"""
        pass
```

## Data Models

### OrchestrationCycleResult

Result of a complete orchestration cycle:

```python
@dataclass
class OrchestrationCycleResult:
    success: bool                    # Cycle completed successfully
    projects_processed: int          # Number of projects processed
    total_actions: int               # Total actions across all projects
    total_errors: int                # Total errors encountered
    cycle_duration_ms: float         # Time in milliseconds
    timestamp: datetime              # When cycle completed
    error_message: Optional[str]     # Error details if failed
```

### ProjectOrchestrationResult

Result of orchestrating a single project:

```python
@dataclass
class ProjectOrchestrationResult:
    project_name: str               # Name of the project
    success: bool                   # Project orchestration succeeded
    actions_taken: int              # Number of actions taken
    errors: List[str]               # List of errors
    workspace_path: str             # Project workspace path
    timestamp: datetime             # When orchestration completed
```

## Dependency Injection

The MultiProjectOrchestrator requires the following dependencies:

```python
class MultiProjectOrchestrator(IMultiProjectOrchestrator):
    def __init__(
        self,
        project_manager: IProjectManagerService,
        workflow_orchestrator: "IWorkflowOrchestrator",
        board_service: IBoardService,
        event_emitter: Optional[IEventEmitter] = None,
        poll_interval_seconds: int = 30,
    ) -> None:
        self._project_manager = project_manager
        self._workflow_orchestrator = workflow_orchestrator
        self._board_service = board_service
        self._event_emitter = event_emitter
        self._poll_interval_seconds = poll_interval_seconds
```

### Dependencies

1. **IProjectManagerService** (Required)
   - Loads project configurations
   - Ensures repositories cloned
   - Derives workspace paths
   - Reloads configuration

2. **IWorkflowOrchestrator** (Required)
   - Executes per-project workflows
   - Returns action count
   - Handles card movements and agent execution

3. **IBoardService** (Required)
   - Reconciles project boards
   - Synchronizes with external system
   - Can be None in simulation mode (guarded with None check)

4. **IEventEmitter** (Optional)
   - Emits orchestration events
   - Used for observability and debugging

5. **poll_interval_seconds** (Optional)
   - Seconds to wait between orchestration cycles (default: 30)
   - Only used when start() is called for continuous polling

## Event Emissions

The MultiProjectOrchestrator emits domain events for observability:

### OrchestrationCycleCompletedEvent

Emitted at the end of each orchestration cycle:

```python
event = OrchestrationCycleCompletedEvent(
    type="orchestration.cycle_completed",
    timestamp=iso_timestamp,
    source="multi_project_orchestrator",
    projects_processed=3,
    boards_processed=0,  # Not tracked at orchestrator level
    work_items_found=15,  # Total actions = work items processed
    cycle_duration_ms=1500,
)
```

**Fields**:
- `projects_processed`: Number of enabled projects processed
- `boards_processed`: 0 (not tracked at orchestrator level)
- `work_items_found`: Total actions taken across all projects
- `cycle_duration_ms`: Elapsed time for cycle

## Project Isolation

Projects are isolated through namespacing:

### State Isolation

- **Pipeline Locks**: Use `{project_id}:{board_id}` namespace
- **Queue State**: Use `{project_id}_{board_id}.yaml` path
- **Session State**: Use `{project_id}_workitem_{id}.yaml` path
- **Workspace Directories**: Isolated per repository

### Error Isolation

Errors in one project don't block others:
- Each project's orchestration wrapped in try-except
- Errors collected and reported separately
- Cycle continues to next project
- Overall cycle fails only if critical infrastructure fails

## Error Handling Strategy

### Classification

1. **Configuration Errors** (ResourceNotFoundError)
   - Project not found
   - Return error result, don't crash cycle

2. **External Service Errors** (ExternalServiceError)
   - Repository clone failed
   - Workflow orchestrator unavailable
   - Return error result, retry next cycle

3. **Unexpected Errors** (RuntimeError, etc.)
   - Caught and logged with full trace
   - Return error result
   - Don't propagate up to crash entire cycle

### Resilience Patterns

- **Non-blocking Failures**: One project failure doesn't block others
- **Retry-able Errors**: Emitted as events, retried next cycle
- **Error Aggregation**: Total error count returned in cycle result
- **Logging**: All errors logged with context (project, timestamp)

## Testing

### Unit Tests

20 comprehensive unit tests covering:

**Location**: `tests/unit/application/test_multi_project_orchestrator.py`

**Test Classes**:
1. `TestOrchestrationCycle` - Cycle execution and error handling
2. `TestPerProjectOrchestration` - Per-project orchestration
3. `TestProjectStatus` - Status retrieval and listing
4. `TestCycleMetrics` - Metrics tracking and events
5. `TestErrorHandling` - Error resilience

**Coverage**: 15/15 tests passing, ~100% method coverage

### Simulation Tests

Comprehensive end-to-end simulation scenario:

**Location**: `tests/simulation/scenarios/scenario_13_multi_project.py`

**Scenario 13: Multi-Project Orchestration**
- 3 projects: api-service, web-app, data-service
- 18 total work items (5+7+6)
- Multiple agents per project
- Repository clone events
- Work item processing
- Cycle completion events

**Test**: `tests/simulation/test_scenarios.py::test_scenario_13_multi_project`

## Integration Points

### IProjectManagerService

Used to:
- Reload project configurations
- Get enabled project list
- Load per-project configuration
- Ensure repositories cloned

### IWorkflowOrchestrator

Used to:
- Execute per-project workflow orchestration
- Return action count for the project
- Handle board polling and card movements
- Queue agent executions

### IEventEmitter

Used to:
- Emit OrchestrationCycleCompletedEvent
- Track cycle metrics
- Enable debugging and observability

## Performance Characteristics

### Time Complexity

- **Configuration Reload**: O(P) where P = number of projects
- **Repository Operations**: O(P) - sequential cloning
- **Per-Project Orchestration**: O(P * W) where W = work items per project
- **Overall Cycle**: O(P * W) - sequential processing

### Space Complexity

- **In-Memory State**: O(P + E) where E = events captured
- **Project Results**: O(P) - one result per project

### Optimization Opportunities

1. **Parallel Project Processing**: Process projects concurrently (currently sequential)
2. **Caching**: Cache project configurations between cycles
3. **Incremental Updates**: Only reload changed projects
4. **Batch Operations**: Group repository operations

## Usage Example

```python
# Initialize orchestrator
orchestrator = MultiProjectOrchestrator(
    project_manager=project_manager,
    workflow_orchestrator=workflow_orchestrator,
    board_service=board_service,
    event_emitter=event_emitter,
    poll_interval_seconds=30,
)

# Run orchestration cycle
result = await orchestrator.run_orchestration_cycle()

if result.success:
    print(f"Orchestrated {result.projects_processed} projects")
    print(f"Actions taken: {result.total_actions}")
else:
    print(f"Cycle failed: {result.error_message}")
    print(f"Errors: {result.total_errors}")

# Check project status
status = await orchestrator.get_project_status("api-service")
print(f"api-service status: {status}")

# List enabled projects
projects = await orchestrator.list_enabled_projects()
```

## Future Enhancements

1. **Parallel Processing**: Process multiple projects concurrently
2. **Incremental Updates**: Only process changed projects
3. **Rate Limiting**: Control overall system load across projects
4. **Priority Queuing**: Process projects by priority
5. **Health Checks**: Monitor project health between cycles
6. **Distributed Orchestration**: Scale to multiple orchestrator instances

## Related Documents

- `consolidated_services_design.md` - Other application services
- `../ports/output/project_manager_service.py` - Project manager port
- `../ports/output/workflow_orchestrator.py` - Workflow orchestrator port
- `../ports/output/board_service.py` - Board service port
- `../domains/events/project_events.py` - Project domain events
