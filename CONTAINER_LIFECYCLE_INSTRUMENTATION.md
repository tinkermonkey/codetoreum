# Docker Container Lifecycle Instrumentation

**Status:** Complete
**Goal:** Add OpenTelemetry instrumentation to all Docker container lifecycle operations (Issue #249)

## Summary

This phase instruments all Docker container lifecycle operations with OpenTelemetry spans. This enables comprehensive observability and tracing of container management throughout the system.

## What Was Instrumented

### 1. **DockerContainerAdapter** (`src/codetoreum/adapters/secondary/docker_container_adapter.py`)

Added `@instrument_async_function` decorators to the following lifecycle methods:

- **`run()`** - Execute a command in a new container
  - Span name: `container.run`
  - Captures image, command, volumes, environment arguments

- **`create()`** - Create a container without starting it
  - Span name: `container.create`
  - Captures image, name, labels, volumes, environment arguments

- **`start()`** - Start a created container
  - Span name: `container.start`
  - Captures container_id

- **`stop()`** - Stop a running container
  - Span name: `container.stop`
  - Captures container_id and timeout

- **`kill()`** - Kill a container immediately
  - Span name: `container.kill`
  - Captures container_id and signal

- **`remove()`** - Remove a container
  - Span name: `container.remove`
  - Captures container_id and force flag

- **`logs()`** - Retrieve container logs
  - Span name: `container.logs`
  - Captures container_id, stream, follow, tail flags

- **`status()`** - Get container status and metadata
  - Span name: `container.status`
  - Captures container_id

- **`exec()`** - Execute a command in a running container
  - Span name: `container.exec`
  - Captures container_id, command, user, working_dir, environment

- **`list_containers()`** - List containers with filters
  - Span name: `container.list_containers`
  - Captures all, filters arguments

- **`pull_image()`** - Pull a container image
  - Span name: `container.pull_image`
  - Captures image and tag

- **`image_exists()`** - Check if an image exists locally
  - Span name: `container.image_exists`
  - Captures image and tag

- **`inspect()`** - Get detailed container information
  - Span name: `container.inspect`
  - Captures container_id

- **`wait()`** - Wait for a container to stop
  - Span name: `container.wait`
  - Captures container_id and timeout

- **`copy_to_container()`** - Copy files into a container
  - Span name: `container.copy_to_container`
  - Captures container_id, source, destination

- **`copy_from_container()`** - Copy files from a container
  - Span name: `container.copy_from_container`
  - Captures container_id, source, destination

### 2. **DockerContainerRecoveryAdapter** (`src/codetoreum/adapters/secondary/docker_container_recovery_adapter.py`)

Added `@instrument_async_function` decorators to recovery operations:

- **`get_running_agent_containers()`** - List running agent containers
  - Span name: `container_recovery.get_running_agent_containers`
  - Returns list of agent containers with Codetoreum labels

- **`get_running_repair_cycle_containers()`** - List running repair cycle containers
  - Span name: `container_recovery.get_running_repair_cycle_containers`
  - Separately enumerates repair cycle containers

- **`assess_container()`** - Assess recovery action for a container
  - Span name: `container_recovery.assess_container`
  - Captures container metadata, evaluates recovery decision tree

- **`assess_repair_cycle_container()`** - Assess repair cycle container
  - Span name: `container_recovery.assess_repair_cycle_container`
  - Evaluates checkpoint staleness and age

- **`execute_recovery_action()`** - Execute reconnect or kill action
  - Span name: `container_recovery.execute_recovery_action`
  - Captures recovery assessment and executes determined action

- **`process_orphaned_repair_results()`** - Process completed repair cycle results
  - Span name: `container_recovery.process_orphaned_repair_results`
  - Scans storage for unprocessed completed repairs

### 3. **ContainerRecoveryService** (`src/codetoreum/application/container_recovery_service.py`)

Added instrumentation to orchestration service:

- **`recover_or_cleanup_containers()`** - Full recovery/cleanup cycle on startup
  - Span name: `container_recovery.recover_or_cleanup_containers`
  - Orchestrates complete recovery workflow:
    1. Process orphaned repair cycle results
    2. Discover repair cycle containers
    3. Discover agent containers
    4. Assess and execute recovery actions
    5. Emit completion event

## Instrumentation Details

### Span Attributes

All instrumented methods include:
- **`service`** - Identifies the adapter/service (e.g., `docker_container_adapter`)
- **`operation`** - Describes the operation (e.g., `run`, `start`, `kill`)
- **`code.function`** - Function name (auto-added)
- **`code.namespace`** - Module path (auto-added)

### Argument/Result Capture

- Most lifecycle methods have `capture_args=True` for debugging
- Large result sets use `capture_result=False` to avoid excessive span size
- Log output methods use `capture_result=False` to avoid capturing large logs

### Exception Handling

All spans automatically record exceptions with:
- Exception type and message
- Stack trace
- Span status set to ERROR

## Integration with Existing Infrastructure

### OpenTelemetry Setup

Uses existing infrastructure from `src/codetoreum/infrastructure/observability/`:
- **`instrumentation.py`** - Provides `@instrument_async_function` decorator
- **`otel_setup.py`** - OTLP exporter configuration
- **`config.py`** - Observability configuration with env vars

### Span Context Propagation

Container operations can leverage existing:
- **`trace_context_propagation.py`** - W3C Trace Context standard
- **`event_bus_instrumentation.py`** - Event correlation across async boundaries

### Logging Integration

Spans automatically correlate with logs via:
- **`logging_integration.py`** - Injects trace_id/span_id into log records
- Enables cross-referencing logs and traces in Signoz

## Testing

Created comprehensive integration test suite:
- **File:** `tests/integration/observability/test_container_lifecycle_instrumentation.py`

Test coverage includes:
- ✅ DockerContainerAdapter span creation for all methods
- ✅ DockerContainerRecoveryAdapter span creation for recovery ops
- ✅ ContainerRecoveryService span creation for orchestration
- ✅ Span attributes validation
- ✅ Exception recording

Tests use:
- In-memory span exporter for isolated test execution
- Mock Docker client to avoid Docker daemon dependency
- Async/await testing with pytest-asyncio

## Benefits

1. **End-to-End Tracing**: Complete visibility into container lifecycle from creation to removal
2. **Performance Monitoring**: Automatic duration tracking for all operations
3. **Error Diagnosis**: Exceptions recorded with context in spans
4. **Audit Trail**: Integration with event sourcing for complete audit trail
5. **Resource Tracking**: Container IDs and metadata captured in spans
6. **Correlation**: Logs and traces linked via trace_id/span_id
7. **Production Ready**: Graceful degradation if OpenTelemetry unavailable

## Configuration

Container lifecycle instrumentation respects existing observability settings:

```bash
# Enable/disable OpenTelemetry
export OTEL_ENABLED=true
export OTEL_TRACES_ENABLED=true

# Sampling strategy (always_on, always_off, traceidratio, parentbased_always_on)
export OTEL_TRACES_SAMPLER=parentbased_always_on
export OTEL_TRACES_SAMPLER_ARG=0.1  # 10% sample rate

# Signoz connection
export SIGNOZ_HOST=localhost
export SIGNOZ_PORT=5317
export SIGNOZ_TRACE_API_KEY=optional_key
```

## Files Modified

1. `src/codetoreum/adapters/secondary/docker_container_adapter.py` - Added 15 decorators
2. `src/codetoreum/adapters/secondary/docker_container_recovery_adapter.py` - Added 6 decorators
3. `src/codetoreum/application/container_recovery_service.py` - Added 1 decorator

## Files Created

1. `tests/integration/observability/test_container_lifecycle_instrumentation.py` - Comprehensive test suite

## Backward Compatibility

✅ **Fully backward compatible**
- Instrumentation is transparent to callers
- No changes to method signatures
- No changes to behavior or return values
- Graceful degradation if OpenTelemetry disabled

## Next Steps

The complete instrumentation roadmap now includes:
1. ✅ Phase 1: Basic OpenTelemetry setup
2. ✅ Phase 2: Log correlation with trace IDs
3. ✅ Phase 3: Event bus W3C Trace Context propagation
4. ✅ Phase 4: WebSocket instrumentation
5. ✅ Phase 5: Pipeline locking
6. ✅ **Phase 6: Docker container lifecycle operations** (THIS PHASE)

Remaining phases would focus on:
- Application services (orchestrator, scheduler, execution)
- Domain layer business operations
- External integrations (GitHub API, LLM providers)
- Metrics collection and reporting
- Custom business KPIs

---

**Implementation Status:** Complete and tested
**Ready for Production:** Yes
**Requires Review:** Design and test coverage validation
