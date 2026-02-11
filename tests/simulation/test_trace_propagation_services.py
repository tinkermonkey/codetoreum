"""Simulation tests for trace propagation across application services.

Tests trace context propagation through application layer services like
WorkflowOrchestrator, ExecutionService, AgentScheduler, etc. to verify
end-to-end tracing across service boundaries.

Test scenarios:
1. Trace propagation through workflow orchestration
2. Trace propagation through execution service
3. Trace propagation across multiple service calls
4. Trace context in service-to-adapter handoffs
"""

import pytest
from datetime import timedelta

from codetoreum.infrastructure.simulation import (
    SimulationConfig,
    SimulationRunner,
    SpanKind,
)


@pytest.mark.asyncio
async def test_workflow_orchestration_trace():
    """Test trace propagation through workflow orchestration."""
    config = SimulationConfig.create_fast_config(
        scenario_name="workflow_orchestration_trace",
        speed_multiplier=100.0,
    )

    runner = SimulationRunner(config)

    async def scenario(sim: SimulationRunner):
        # Root: workflow orchestration handler
        orchestrator_span = sim.mock_tracer.start_span(
            "WorkflowOrchestrator.handle_card_movement",
            kind=SpanKind.INTERNAL,
        )

        try:
            orchestrator_span.set_attribute("work_item_id", "item-123")
            orchestrator_span.set_attribute("from_column", "Todo")
            orchestrator_span.set_attribute("to_column", "In Progress")

            # Child 1: Schedule agent
            schedule_span = sim.mock_tracer.start_span(
                "AgentScheduler.queue_execution",
                kind=SpanKind.INTERNAL,
                parent_span_id=orchestrator_span.span_id,
                trace_id=orchestrator_span.trace_id,
            )
            schedule_span.set_attribute("agent_id", "code-generator")
            schedule_span.set_attribute("queue_position", 1)
            sim.mock_tracer.end_span(schedule_span)

            # Child 2: Execute agent
            exec_span = sim.mock_tracer.start_span(
                "ExecutionService.execute_with_llm",
                kind=SpanKind.INTERNAL,
                parent_span_id=orchestrator_span.span_id,
                trace_id=orchestrator_span.trace_id,
            )
            exec_span.set_attribute("agent_id", "code-generator")
            exec_span.set_attribute("mode", "single_turn")

            # Grandchild: LLM call
            llm_span = sim.mock_tracer.start_span(
                "llm.chat_completion",
                kind=SpanKind.CLIENT,
                parent_span_id=exec_span.span_id,
                trace_id=orchestrator_span.trace_id,
            )
            llm_span.set_attribute("model", "claude-opus-4-6")
            sim.mock_tracer.end_span(llm_span)

            sim.mock_tracer.end_span(exec_span)

            # Child 3: Update board
            update_span = sim.mock_tracer.start_span(
                "BoardAdapter.move_card",
                kind=SpanKind.CLIENT,
                parent_span_id=orchestrator_span.span_id,
                trace_id=orchestrator_span.trace_id,
            )
            update_span.set_attribute("work_item_id", "item-123")
            update_span.set_attribute("to_column", "In Review")
            sim.mock_tracer.end_span(update_span)

        finally:
            sim.mock_tracer.end_span(orchestrator_span)

        # Verify trace structure
        sim.assert_span_exists("WorkflowOrchestrator.handle_card_movement")
        sim.assert_span_exists("AgentScheduler.queue_execution")
        sim.assert_span_exists("ExecutionService.execute_with_llm")
        sim.assert_span_exists("llm.chat_completion")
        sim.assert_span_exists("BoardAdapter.move_card")

    result = await runner.run(scenario)
    assert result.success, f"Scenario failed: {result.errors}"
    assert result.spans_captured == 5

    # Verify all in same trace
    spans = runner.mock_tracer.get_spans()
    trace_ids = set(s.trace_id for s in spans)
    assert len(trace_ids) == 1


@pytest.mark.asyncio
async def test_execution_service_trace():
    """Test trace propagation through execution service."""
    config = SimulationConfig.create_fast_config(
        scenario_name="execution_service_trace",
        speed_multiplier=100.0,
    )

    runner = SimulationRunner(config)

    async def scenario(sim: SimulationRunner):
        # Root: execution service
        exec_service_span = sim.mock_tracer.start_span(
            "ExecutionService.execute",
            kind=SpanKind.INTERNAL,
        )

        try:
            exec_service_span.set_attribute("execution_id", "exec-789")
            exec_service_span.set_attribute("agent_id", "test-runner")

            # Create workspace
            workspace_span = sim.mock_tracer.start_span(
                "WorkspaceRouter.mount_workspace",
                kind=SpanKind.INTERNAL,
                parent_span_id=exec_service_span.span_id,
                trace_id=exec_service_span.trace_id,
            )
            workspace_span.set_attribute("workspace_id", "ws-001")
            sim.mock_tracer.end_span(workspace_span)

            # Choose execution mode
            if True:  # execute_with_container in this path
                # Container execution
                container_span = sim.mock_tracer.start_span(
                    "ExecutionService.execute_with_container",
                    kind=SpanKind.INTERNAL,
                    parent_span_id=exec_service_span.span_id,
                    trace_id=exec_service_span.trace_id,
                )

                # Container operations
                run_span = sim.mock_tracer.start_span(
                    "ContainerAdapter.run",
                    kind=SpanKind.CLIENT,
                    parent_span_id=container_span.span_id,
                    trace_id=exec_service_span.trace_id,
                )
                run_span.set_attribute("image", "python:3.11")
                run_span.set_attribute("exit_code", 0)
                sim.mock_tracer.end_span(run_span)

                sim.mock_tracer.end_span(container_span)

            # Collect results
            results_span = sim.mock_tracer.start_span(
                "ExecutionService.collect_results",
                kind=SpanKind.INTERNAL,
                parent_span_id=exec_service_span.span_id,
                trace_id=exec_service_span.trace_id,
            )
            results_span.set_attribute("output_size_bytes", 4096)
            sim.mock_tracer.end_span(results_span)

        finally:
            sim.mock_tracer.end_span(exec_service_span)

        # Verify execution flow
        sim.assert_span_exists("ExecutionService.execute")
        sim.assert_span_exists("WorkspaceRouter.mount_workspace")
        sim.assert_span_exists("ExecutionService.execute_with_container")
        sim.assert_span_exists("ContainerAdapter.run")
        sim.assert_span_exists("ExecutionService.collect_results")

    result = await runner.run(scenario)
    assert result.success, f"Scenario failed: {result.errors}"


@pytest.mark.asyncio
async def test_multi_service_execution_trace():
    """Test trace propagation across multiple service calls."""
    config = SimulationConfig.create_fast_config(
        scenario_name="multi_service_trace",
        speed_multiplier=100.0,
    )

    runner = SimulationRunner(config)

    async def scenario(sim: SimulationRunner):
        # Root: event handler
        event_handler_span = sim.mock_tracer.start_span(
            "EventHandler.handle_event",
            kind=SpanKind.INTERNAL,
        )

        try:
            event_handler_span.set_attribute("event_type", "ReviewCycleCompleted")
            event_handler_span.set_attribute("review_id", "rev-456")

            # Service 1: ReviewService
            review_service_span = sim.mock_tracer.start_span(
                "ReviewService.process_review",
                kind=SpanKind.INTERNAL,
                parent_span_id=event_handler_span.span_id,
                trace_id=event_handler_span.trace_id,
            )
            review_service_span.set_attribute("decision", "approved")
            sim.mock_tracer.end_span(review_service_span)

            # Service 2: WorkflowOrchestrator
            workflow_span = sim.mock_tracer.start_span(
                "WorkflowOrchestrator.advance_workflow",
                kind=SpanKind.INTERNAL,
                parent_span_id=event_handler_span.span_id,
                trace_id=event_handler_span.trace_id,
            )
            workflow_span.set_attribute("new_stage", "Testing")

            # Nested: AgentScheduler
            scheduler_span = sim.mock_tracer.start_span(
                "AgentScheduler.queue_execution",
                kind=SpanKind.INTERNAL,
                parent_span_id=workflow_span.span_id,
                trace_id=event_handler_span.trace_id,
            )
            scheduler_span.set_attribute("agent_id", "test-runner")
            sim.mock_tracer.end_span(scheduler_span)

            sim.mock_tracer.end_span(workflow_span)

            # Service 3: Notification
            notification_span = sim.mock_tracer.start_span(
                "NotificationService.notify",
                kind=SpanKind.INTERNAL,
                parent_span_id=event_handler_span.span_id,
                trace_id=event_handler_span.trace_id,
            )
            notification_span.set_attribute("recipient", "team@example.com")
            notification_span.set_attribute("template", "review_approved")
            sim.mock_tracer.end_span(notification_span)

        finally:
            sim.mock_tracer.end_span(event_handler_span)

        # All should be in same trace
        spans = sim.mock_tracer.get_spans()
        trace_ids = set(s.trace_id for s in spans)
        sim.assert_true(
            len(trace_ids) == 1,
            "single_trace",
            "All services should be in same trace",
        )

    result = await runner.run(scenario)
    assert result.success, f"Scenario failed: {result.errors}"


@pytest.mark.asyncio
async def test_service_adapter_handoff_trace():
    """Test trace context handoff between services and adapters."""
    config = SimulationConfig.create_fast_config(
        scenario_name="service_adapter_handoff",
        speed_multiplier=100.0,
    )

    runner = SimulationRunner(config)

    async def scenario(sim: SimulationRunner):
        # Service layer
        service_span = sim.mock_tracer.start_span(
            "GitRepositoryService.push_changes",
            kind=SpanKind.INTERNAL,
        )

        try:
            service_span.set_attribute("branch", "feature/auth")
            service_span.set_attribute("commit_count", 3)

            # Adapter layer: Git operations
            git_span = sim.mock_tracer.start_span(
                "GitRepositoryAdapter.push",
                kind=SpanKind.CLIENT,
                parent_span_id=service_span.span_id,
                trace_id=service_span.trace_id,
            )

            # Low-level operations
            for i in range(3):
                op_span = sim.mock_tracer.start_span(
                    f"git.push.chunk_{i}",
                    kind=SpanKind.CLIENT,
                    parent_span_id=git_span.span_id,
                    trace_id=service_span.trace_id,
                )
                op_span.set_attribute("size_bytes", 1024 * (i + 1))
                sim.mock_tracer.end_span(op_span)

            git_span.set_attribute("total_pushed", 6144)
            sim.mock_tracer.end_span(git_span)

        finally:
            sim.mock_tracer.end_span(service_span)

        # Verify handoff chain
        spans = sim.mock_tracer.get_spans()
        assert len(spans) == 5  # service + adapter + 3 chunks

    result = await runner.run(scenario)
    assert result.success, f"Scenario failed: {result.errors}"


@pytest.mark.asyncio
async def test_repair_cycle_trace_propagation():
    """Test trace propagation through repair cycle operations."""
    config = SimulationConfig.create_fast_config(
        scenario_name="repair_cycle_trace",
        speed_multiplier=100.0,
    )

    runner = SimulationRunner(config)

    async def scenario(sim: SimulationRunner):
        # Root: repair cycle initiation
        repair_span = sim.mock_tracer.start_span(
            "RepairCycleOrchestrator.start_repair",
            kind=SpanKind.INTERNAL,
        )

        try:
            repair_span.set_attribute("execution_id", "exec-001")
            repair_span.set_attribute("max_iterations", 3)

            # Iteration 1: Test
            test_span = sim.mock_tracer.start_span(
                "RepairCycle.run_tests",
                kind=SpanKind.INTERNAL,
                parent_span_id=repair_span.span_id,
                trace_id=repair_span.trace_id,
            )
            test_span.set_attribute("iteration", 1)
            test_span.set_attribute("passed", 8)
            test_span.set_attribute("failed", 2)
            sim.mock_tracer.end_span(test_span)

            # Iteration 2: Fix
            fix_span = sim.mock_tracer.start_span(
                "RepairCycle.generate_fix",
                kind=SpanKind.INTERNAL,
                parent_span_id=repair_span.span_id,
                trace_id=repair_span.trace_id,
            )
            fix_span.set_attribute("iteration", 2)
            fix_span.set_attribute("target_tests", ["test_auth", "test_login"])

            # Nested: LLM call for fix generation
            llm_span = sim.mock_tracer.start_span(
                "llm.generate_code_fix",
                kind=SpanKind.CLIENT,
                parent_span_id=fix_span.span_id,
                trace_id=repair_span.trace_id,
            )
            llm_span.set_attribute("context_lines", 50)
            sim.mock_tracer.end_span(llm_span)

            sim.mock_tracer.end_span(fix_span)

            # Iteration 2 continued: Validate
            validate_span = sim.mock_tracer.start_span(
                "RepairCycle.run_tests",
                kind=SpanKind.INTERNAL,
                parent_span_id=repair_span.span_id,
                trace_id=repair_span.trace_id,
            )
            validate_span.set_attribute("iteration", 2)
            validate_span.set_attribute("passed", 10)
            validate_span.set_attribute("failed", 0)
            sim.mock_tracer.end_span(validate_span)

        finally:
            sim.mock_tracer.end_span(repair_span)

        # Verify repair cycle trace structure
        sim.assert_span_exists("RepairCycleOrchestrator.start_repair")
        repair_spans = sim.mock_tracer.get_spans_by_name("RepairCycle.run_tests")
        assert len(repair_spans) == 2, "Should have test runs for iteration 1 and 2"

    result = await runner.run(scenario)
    assert result.success, f"Scenario failed: {result.errors}"


@pytest.mark.asyncio
async def test_exception_handling_in_service_trace():
    """Test trace recording when services encounter exceptions."""
    config = SimulationConfig.create_fast_config(
        scenario_name="exception_trace",
        speed_multiplier=100.0,
    )

    runner = SimulationRunner(config)

    async def scenario(sim: SimulationRunner):
        from codetoreum.infrastructure.simulation.mock_tracer import SpanStatus

        # Service operation that encounters error
        service_span = sim.mock_tracer.start_span(
            "WorkflowOrchestrator.advance_stage",
            kind=SpanKind.INTERNAL,
        )

        try:
            # Successful operations
            schedule_span = sim.mock_tracer.start_span(
                "AgentScheduler.queue",
                kind=SpanKind.INTERNAL,
                parent_span_id=service_span.span_id,
                trace_id=service_span.trace_id,
            )
            schedule_span.set_status(SpanStatus.OK)
            sim.mock_tracer.end_span(schedule_span)

            # Failed operation
            exec_span = sim.mock_tracer.start_span(
                "ExecutionService.execute",
                kind=SpanKind.INTERNAL,
                parent_span_id=service_span.span_id,
                trace_id=service_span.trace_id,
            )
            exec_span.set_status(SpanStatus.ERROR)
            exec_span.add_event("exception", {
                "type": "ContainerError",
                "message": "Container startup timeout",
            })
            sim.mock_tracer.end_span(exec_span)

            service_span.set_status(SpanStatus.ERROR)
            service_span.add_event("workflow_failed", {
                "reason": "execution_error",
                "retry_count": 1,
            })

        finally:
            sim.mock_tracer.end_span(service_span)

        # Verify error recording
        spans = sim.mock_tracer.get_spans()
        error_spans = [s for s in spans if s.status.value == "ERROR"]
        assert len(error_spans) == 2  # service + execution

    result = await runner.run(scenario)
    assert result.success, f"Scenario failed: {result.errors}"
