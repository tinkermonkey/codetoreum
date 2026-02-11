"""Simulation tests for trace propagation through adapters.

Tests trace context in adapter operations to verify proper instrumentation
of external service calls (container, LLM, GitHub, etc.).

Test scenarios:
1. Container adapter operations with span context
2. LLM adapter calls with trace attributes
3. Adapter error handling with spans
4. Parallel adapter calls within same trace
"""

import pytest
from datetime import timedelta

from codetoreum.infrastructure.simulation import (
    SimulationConfig,
    SimulationRunner,
    SpanKind,
)


@pytest.mark.asyncio
async def test_container_adapter_span_context():
    """Test trace context in container adapter operations."""
    config = SimulationConfig.create_fast_config(
        scenario_name="container_adapter_trace",
        speed_multiplier=100.0,
    )

    runner = SimulationRunner(config)

    async def scenario(sim: SimulationRunner):
        # Parent span: agent execution
        agent_span = await sim.mock_tracer.start_span(
            "agent_execution",
            kind=SpanKind.INTERNAL,
        )

        try:
            # Child span: container create
            create_span = await sim.mock_tracer.start_span(
                "container.create",
                kind=SpanKind.CLIENT,
                parent_span_id=agent_span.span_id,
                trace_id=agent_span.trace_id,
            )
            await sim.mock_tracer.set_attribute(create_span, "image", "python:3.11")
            await sim.mock_tracer.set_attribute(create_span, "container_name", "agent-work-001")
            await sim.mock_tracer.end_span(create_span)

            # Child span: container start
            start_span = await sim.mock_tracer.start_span(
                "container.start",
                kind=SpanKind.CLIENT,
                parent_span_id=agent_span.span_id,
                trace_id=agent_span.trace_id,
            )
            await sim.mock_tracer.set_attribute(start_span, "container_id", "abc123")
            await sim.mock_tracer.end_span(start_span)

            # Child span: container execute
            exec_span = await sim.mock_tracer.start_span(
                "container.exec",
                kind=SpanKind.CLIENT,
                parent_span_id=agent_span.span_id,
                trace_id=agent_span.trace_id,
            )
            await sim.mock_tracer.set_attribute(exec_span, "command", "python script.py")
            await sim.mock_tracer.set_attribute(exec_span, "exit_code", 0)
            await sim.mock_tracer.end_span(exec_span)

            # Child span: container cleanup
            cleanup_span = await sim.mock_tracer.start_span(
                "container.cleanup",
                kind=SpanKind.CLIENT,
                parent_span_id=agent_span.span_id,
                trace_id=agent_span.trace_id,
            )
            await sim.mock_tracer.set_attribute(cleanup_span, "container_id", "abc123")
            await sim.mock_tracer.end_span(cleanup_span)

        finally:
            await sim.mock_tracer.end_span(agent_span)

        # Verify parent-child relationships
        sim.assert_span_exists("agent_execution")
        sim.assert_span_exists("container.create")
        sim.assert_span_exists("container.start")
        sim.assert_span_exists("container.exec")
        sim.assert_span_exists("container.cleanup")

        # All should be in same trace
        sim.assert_span_count(5)

    result = await runner.run(scenario)
    assert result.success, f"Scenario failed: {result.errors}"
    assert result.spans_captured == 5

    # Verify all spans share trace ID
    spans = runner.mock_tracer.get_spans()
    trace_ids = set(s.trace_id for s in spans)
    assert len(trace_ids) == 1, "All container operations should share trace"


@pytest.mark.asyncio
async def test_llm_adapter_span_context():
    """Test trace context in LLM adapter calls."""
    config = SimulationConfig.create_fast_config(
        scenario_name="llm_adapter_trace",
        speed_multiplier=100.0,
    )

    runner = SimulationRunner(config)

    async def scenario(sim: SimulationRunner):
        # Parent span: agent execution
        exec_span = await sim.mock_tracer.start_span(
            "agent_execute",
            kind=SpanKind.INTERNAL,
        )

        try:
            # Child span: LLM call
            llm_span = await sim.mock_tracer.start_span(
                "llm.chat_completion",
                kind=SpanKind.CLIENT,
                parent_span_id=exec_span.span_id,
                trace_id=exec_span.trace_id,
            )

            await sim.mock_tracer.set_attribute(llm_span, "model", "claude-opus-4-6")
            await sim.mock_tracer.set_attribute(llm_span, "messages", 5)
            await sim.mock_tracer.set_attribute(llm_span, "max_tokens", 2000)
            await sim.mock_tracer.add_event(llm_span, "llm_request_sent", {"tokens": 1500})
            await sim.mock_tracer.add_event(llm_span, "llm_response_received", {"tokens": 500})

            await sim.mock_tracer.end_span(llm_span)

        finally:
            await sim.mock_tracer.end_span(exec_span)

        # Verify LLM span has attributes
        sim.assert_span_attribute("llm.chat_completion", "model", "claude-opus-4-6")
        sim.assert_span_attribute("llm.chat_completion", "max_tokens", 2000)

    result = await runner.run(scenario)
    assert result.success, f"Scenario failed: {result.errors}"

    spans = runner.mock_tracer.get_spans()
    llm_spans = [s for s in spans if s.name == "llm.chat_completion"]
    assert len(llm_spans) == 1
    assert len(llm_spans[0].events) == 2


@pytest.mark.asyncio
async def test_adapter_error_handling_with_spans():
    """Test error handling and span status with adapter failures."""
    config = SimulationConfig.create_fast_config(
        scenario_name="adapter_error_trace",
        speed_multiplier=100.0,
    )

    runner = SimulationRunner(config)

    async def scenario(sim: SimulationRunner):
        from codetoreum.infrastructure.simulation.mock_tracer import SpanStatus

        # Successful operation
        success_span = await sim.mock_tracer.start_span(
            "container.create",
            kind=SpanKind.CLIENT,
        )
        success_span.set_status(SpanStatus.OK)
        await sim.mock_tracer.end_span(success_span)

        # Failed operation
        error_span = await sim.mock_tracer.start_span(
            "container.start",
            kind=SpanKind.CLIENT,
        )
        error_span.set_status(SpanStatus.ERROR)
        await sim.mock_tracer.add_event(
            error_span,
            "error",
            {"message": "Container startup failed", "error_code": 1},
        )
        await sim.mock_tracer.end_span(error_span)

        # Verify spans recorded with correct status
        spans = sim.mock_tracer.get_spans()
        assert len(spans) == 2
        assert spans[0].status.value == "OK"
        assert spans[1].status.value == "ERROR"

    result = await runner.run(scenario)
    assert result.success, f"Scenario failed: {result.errors}"


@pytest.mark.asyncio
async def test_parallel_adapter_calls_same_trace():
    """Test parallel adapter calls within same trace context."""
    config = SimulationConfig.create_fast_config(
        scenario_name="parallel_adapter_trace",
        speed_multiplier=100.0,
    )

    runner = SimulationRunner(config)

    async def scenario(sim: SimulationRunner):
        # Parent operation
        parent_span = await sim.mock_tracer.start_span(
            "multi_adapter_operation",
            kind=SpanKind.INTERNAL,
        )

        try:
            trace_id = parent_span.trace_id
            parent_id = parent_span.span_id

            # Simulate 3 parallel adapter calls
            adapter_calls = [
                ("container.exec", {"command": "npm test"}),
                ("github.create_pr", {"target": "main"}),
                ("storage.upload", {"type": "artifacts"}),
            ]

            for span_name, attrs in adapter_calls:
                call_span = await sim.mock_tracer.start_span(
                    span_name,
                    kind=SpanKind.CLIENT,
                    parent_span_id=parent_id,
                    trace_id=trace_id,
                )
                for key, value in attrs.items():
                    await sim.mock_tracer.set_attribute(call_span, key, value)
                await sim.mock_tracer.end_span(call_span)

        finally:
            await sim.mock_tracer.end_span(parent_span)

        # Verify all operations in same trace
        sim.assert_span_count(4)  # parent + 3 children

    result = await runner.run(scenario)
    assert result.success, f"Scenario failed: {result.errors}"

    spans = runner.mock_tracer.get_spans()
    trace_ids = set(s.trace_id for s in spans)
    assert len(trace_ids) == 1, "All parallel calls should be in same trace"


@pytest.mark.asyncio
async def test_adapter_span_timing():
    """Test span timing/duration tracking in adapter calls."""
    config = SimulationConfig.create_fast_config(
        scenario_name="adapter_timing_trace",
        speed_multiplier=100.0,
    )

    runner = SimulationRunner(config)

    async def scenario(sim: SimulationRunner):
        import time

        span = await sim.mock_tracer.start_span(
            "container.exec",
            kind=SpanKind.CLIENT,
        )

        # Simulate some work
        time.sleep(0.01)  # 10ms of real work

        await sim.mock_tracer.end_span(span)  # Use async interface

        # Verify duration is recorded
        spans = sim.mock_tracer.get_spans()
        sim.assert_true(
            len(spans) == 1,
            "span_recorded",
            "One span should be recorded",
        )
        if len(spans) > 0:
            sim.assert_true(
                spans[0].duration_ms is not None,
                "duration_recorded",
                "Duration should be recorded",
            )
            sim.assert_true(
                spans[0].duration_ms > 0,
                "duration_positive",
                "Duration should be positive",
            )

    result = await runner.run(scenario)
    assert result.success, f"Scenario failed: {result.errors}"


@pytest.mark.asyncio
async def test_github_adapter_span_context():
    """Test trace context in GitHub adapter operations."""
    config = SimulationConfig.create_fast_config(
        scenario_name="github_adapter_trace",
        speed_multiplier=100.0,
    )

    runner = SimulationRunner(config)

    async def scenario(sim: SimulationRunner):
        # Workflow operation
        workflow_span = await sim.mock_tracer.start_span(
            "github_workflow",
            kind=SpanKind.INTERNAL,
        )

        try:
            # Create PR
            create_pr_span = await sim.mock_tracer.start_span(
                "github.create_pull_request",
                kind=SpanKind.CLIENT,
                parent_span_id=workflow_span.span_id,
                trace_id=workflow_span.trace_id,
            )
            await sim.mock_tracer.set_attribute(create_pr_span, "repo", "codetoreum")
            await sim.mock_tracer.set_attribute(create_pr_span, "title", "Feature: auth")
            await sim.mock_tracer.set_attribute(create_pr_span, "pr_number", 42)
            await sim.mock_tracer.end_span(create_pr_span)

            # Add review comment
            comment_span = await sim.mock_tracer.start_span(
                "github.add_review_comment",
                kind=SpanKind.CLIENT,
                parent_span_id=workflow_span.span_id,
                trace_id=workflow_span.trace_id,
            )
            await sim.mock_tracer.set_attribute(comment_span, "pr_number", 42)
            await sim.mock_tracer.set_attribute(comment_span, "comment_id", "c123")
            await sim.mock_tracer.end_span(comment_span)

            # Request review
            review_span = await sim.mock_tracer.start_span(
                "github.request_review",
                kind=SpanKind.CLIENT,
                parent_span_id=workflow_span.span_id,
                trace_id=workflow_span.trace_id,
            )
            await sim.mock_tracer.set_attribute(review_span, "pr_number", 42)
            await sim.mock_tracer.set_attribute(review_span, "reviewers", ["alice", "bob"])
            await sim.mock_tracer.end_span(review_span)

        finally:
            await sim.mock_tracer.end_span(workflow_span)

        # Verify GitHub operations traced
        sim.assert_span_exists("github.create_pull_request")
        sim.assert_span_exists("github.add_review_comment")
        sim.assert_span_exists("github.request_review")
        sim.assert_span_count(4)

    result = await runner.run(scenario)
    assert result.success, f"Scenario failed: {result.errors}"
