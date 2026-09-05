"""Tests for trace propagation through services with MockTracer.

Tests cover:
- Trace context propagation from workflow orchestrator through adapters
- Service-to-adapter handoff with span parent-child relationships
- Multi-service execution with cross-service tracing
- Agent execution lifecycle with trace visibility
- Repair cycle propagation through service layers
- Exception handling and error span recording
"""

import pytest

from codetoreum.infrastructure.simulation.mock_tracer import SpanKind, SpanStatus
from codetoreum.infrastructure.simulation.simulation_config import SimulationConfig
from codetoreum.infrastructure.simulation.simulation_runner import SimulationRunner


@pytest.mark.asyncio
class TestServiceTracePropaagation:
    """Tests for trace propagation through service orchestration."""

    async def test_workflow_orchestration_trace(self):
        """Test trace propagation from WorkflowOrchestrator through adapter chain."""
        config = SimulationConfig.create_fast_config("test_orchestration")
        runner = SimulationRunner(config)

        async def scenario(sim):
            # Root span for workflow orchestration
            orchestrator_span = await sim.mock_tracer.start_span(
                "workflow_orchestration",
                kind=SpanKind.INTERNAL,
            )
            await sim.mock_tracer.set_attribute(orchestrator_span, "workflow_id", "workflow_123")

            # Child span for board interaction
            board_span = await sim.mock_tracer.start_span(
                "board_operation",
                kind=SpanKind.CLIENT,
                parent_context=orchestrator_span.traceparent,
            )
            await sim.mock_tracer.set_attribute(board_span, "operation", "move_card")
            await sim.mock_tracer.end_span(board_span)

            await sim.mock_tracer.end_span(orchestrator_span)

            # Verify trace hierarchy
            sim.assert_span_exists("workflow_orchestration")
            sim.assert_span_exists("board_operation")
            sim.assert_span_kind("workflow_orchestration", SpanKind.INTERNAL)
            sim.assert_span_kind("board_operation", SpanKind.CLIENT)
            sim.assert_span_attribute("workflow_orchestration", "workflow_id", "workflow_123")
            sim.assert_span_attribute("board_operation", "operation", "move_card")

        result = await runner.run(scenario)
        assert result.success

    async def test_execution_service_trace(self):
        """Test ExecutionService operation with trace visibility."""
        config = SimulationConfig.create_fast_config("test_execution")
        runner = SimulationRunner(config)

        async def scenario(sim):
            # ExecutionService span
            execution_span = await sim.mock_tracer.start_span(
                "execution_service",
                kind=SpanKind.INTERNAL,
            )
            await sim.mock_tracer.set_attribute(execution_span, "agent_id", "agent_001")
            await sim.mock_tracer.set_attribute(execution_span, "work_item_id", "item_123")

            # Container operation (child of execution)
            container_span = await sim.mock_tracer.start_span(
                "container_execution",
                kind=SpanKind.CLIENT,
                parent_context=execution_span.traceparent,
            )
            await sim.mock_tracer.set_attribute(container_span, "exit_code", "0")
            await sim.mock_tracer.end_span(container_span)

            await sim.mock_tracer.end_span(execution_span)

            # Verify execution spans
            sim.assert_span_attribute("execution_service", "agent_id", "agent_001")
            sim.assert_span_attribute("execution_service", "work_item_id", "item_123")
            sim.assert_span_attribute("container_execution", "exit_code", "0")

        result = await runner.run(scenario)
        assert result.success

    async def test_multi_service_execution_trace(self):
        """Test trace propagation across multiple coordinating services."""
        config = SimulationConfig.create_fast_config("test_multi_service")
        runner = SimulationRunner(config)

        async def scenario(sim):
            # Root orchestration span
            root_span = await sim.mock_tracer.start_span(
                "orchestrator_execute",
                kind=SpanKind.INTERNAL,
            )

            # Scheduler span (child of orchestrator)
            scheduler_span = await sim.mock_tracer.start_span(
                "scheduler_queue_agent",
                kind=SpanKind.INTERNAL,
                parent_context=root_span.traceparent,
            )
            await sim.mock_tracer.set_attribute(scheduler_span, "queue_position", "1")
            await sim.mock_tracer.end_span(scheduler_span)

            # Executor span (also child of orchestrator)
            executor_span = await sim.mock_tracer.start_span(
                "executor_run_agent",
                kind=SpanKind.INTERNAL,
                parent_context=root_span.traceparent,
            )
            await sim.mock_tracer.set_attribute(executor_span, "duration_ms", "5000")
            await sim.mock_tracer.end_span(executor_span)

            await sim.mock_tracer.end_span(root_span)

            # Verify multi-level hierarchy
            spans = sim.mock_tracer.get_spans()
            assert len(spans) == 3
            # Find the root span and verify children
            root_span_capture = sim.mock_tracer.get_spans_by_name("orchestrator_execute")[0]
            root_id = root_span_capture.span_id

            # Both scheduler and executor are children of root
            scheduler_span_capture = sim.mock_tracer.get_spans_by_name("scheduler_queue_agent")[0]
            executor_span_capture = sim.mock_tracer.get_spans_by_name("executor_run_agent")[0]
            assert scheduler_span_capture.parent_span_id == root_id
            assert executor_span_capture.parent_span_id == root_id

        result = await runner.run(scenario)
        assert result.success

    async def test_service_adapter_handoff_trace(self):
        """Test trace propagation at service-to-adapter boundaries."""
        config = SimulationConfig.create_fast_config("test_handoff")
        runner = SimulationRunner(config)

        async def scenario(sim):
            # Service initiating an adapter call
            service_span = await sim.mock_tracer.start_span(
                "service_operation",
                kind=SpanKind.INTERNAL,
            )
            await sim.mock_tracer.set_attribute(service_span, "service", "WorkflowOrchestrator")

            # Adapter receiving the call (child of service)
            adapter_span = await sim.mock_tracer.start_span(
                "github_api_call",
                kind=SpanKind.CLIENT,
                parent_context=service_span.traceparent,
            )
            await sim.mock_tracer.set_attribute(adapter_span, "endpoint", "POST /graphql")
            await sim.mock_tracer.set_attribute(adapter_span, "status_code", "200")
            await sim.mock_tracer.end_span(adapter_span)

            await sim.mock_tracer.end_span(service_span)

            # Verify service-adapter relationship
            sim.assert_span_exists("service_operation")
            sim.assert_span_exists("github_api_call")

            # Get the spans and verify parent-child relationship
            service_span_capture = sim.mock_tracer.get_spans_by_name("service_operation")[0]
            adapter_span_capture = sim.mock_tracer.get_spans_by_name("github_api_call")[0]
            assert adapter_span_capture.parent_span_id == service_span_capture.span_id
            sim.assert_span_attribute("github_api_call", "status_code", "200")

        result = await runner.run(scenario)
        assert result.success

    async def test_repair_cycle_trace_propagation(self):
        """Test trace propagation through repair cycle with test-fix-validate loops."""
        config = SimulationConfig.create_fast_config("test_repair")
        runner = SimulationRunner(config)

        async def scenario(sim):
            # Root repair cycle span
            repair_span = await sim.mock_tracer.start_span(
                "repair_cycle",
                kind=SpanKind.INTERNAL,
            )
            await sim.mock_tracer.set_attribute(repair_span, "issue_id", "fix_001")

            # Test phase (child of repair cycle)
            test_span = await sim.mock_tracer.start_span(
                "test_phase",
                kind=SpanKind.CLIENT,
                parent_context=repair_span.traceparent,
            )
            await sim.mock_tracer.set_attribute(test_span, "test_status", "failed")
            await sim.mock_tracer.end_span(test_span)

            # Fix phase (child of repair cycle)
            fix_span = await sim.mock_tracer.start_span(
                "fix_phase",
                kind=SpanKind.CLIENT,
                parent_context=repair_span.traceparent,
            )
            await sim.mock_tracer.set_attribute(fix_span, "fix_applied", "true")
            await sim.mock_tracer.end_span(fix_span)

            # Validate phase (child of repair cycle)
            validate_span = await sim.mock_tracer.start_span(
                "validate_phase",
                kind=SpanKind.CLIENT,
                parent_context=repair_span.traceparent,
            )
            await sim.mock_tracer.set_attribute(validate_span, "validation_result", "passed")
            await sim.mock_tracer.end_span(validate_span)

            await sim.mock_tracer.end_span(repair_span)

            # Verify repair cycle hierarchy
            spans = sim.mock_tracer.get_spans()
            assert len(spans) == 4

            # Get the repair cycle span and verify all phases are its children
            repair_cycle_span = sim.mock_tracer.get_spans_by_name("repair_cycle")[0]
            repair_id = repair_cycle_span.span_id

            test_phase_span = sim.mock_tracer.get_spans_by_name("test_phase")[0]
            fix_phase_span = sim.mock_tracer.get_spans_by_name("fix_phase")[0]
            validate_phase_span = sim.mock_tracer.get_spans_by_name("validate_phase")[0]

            # All phases are children of repair cycle
            assert test_phase_span.parent_span_id == repair_id
            assert fix_phase_span.parent_span_id == repair_id
            assert validate_phase_span.parent_span_id == repair_id

        result = await runner.run(scenario)
        assert result.success

    async def test_exception_handling_in_service_trace(self):
        """Test exception propagation and error span recording."""
        config = SimulationConfig.create_fast_config("test_exception")
        runner = SimulationRunner(config)

        async def scenario(sim):
            # Service span
            service_span = await sim.mock_tracer.start_span(
                "service_with_error",
                kind=SpanKind.INTERNAL,
            )

            # Adapter call that fails
            adapter_span = await sim.mock_tracer.start_span(
                "failing_adapter_call",
                kind=SpanKind.CLIENT,
                parent_context=service_span.traceparent,
            )

            # Simulate exception
            try:
                raise ValueError("Connection failed")
            except ValueError as e:
                await sim.mock_tracer.record_exception(adapter_span, e)
                await sim.mock_tracer.end_span(adapter_span)

            # Service cleanup
            await sim.mock_tracer.end_span(service_span)

            # Verify error was recorded
            spans = sim.mock_tracer.get_spans()
            assert len(spans) == 2

            # Get the error span by name
            error_span = sim.mock_tracer.get_spans_by_name("failing_adapter_call")[0]
            assert error_span.status == SpanStatus.ERROR
            # Check that exception event was recorded
            assert len(error_span.events) > 0
            assert error_span.events[0].name == "exception"

        result = await runner.run(scenario)
        assert result.success
