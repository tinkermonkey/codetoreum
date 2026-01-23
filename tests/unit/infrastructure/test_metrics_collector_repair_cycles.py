"""Unit tests for repair cycle metrics collection."""

import asyncio
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from codetoreum.domain.events import DomainEvent
from codetoreum.domain.events.repair_cycle_events import (
    RepairCycleStartedEvent,
    RepairCycleTestExecutionCompletedEvent,
    RepairCycleFileFixCompletedEvent,
    RepairCycleWarningReviewCompletedEvent,
    RepairCycleFastFailEvent,
    RepairCycleCompletedEvent,
)
from codetoreum.infrastructure.event_bus import EventBus
from codetoreum.infrastructure.event_types import EventTypes
from codetoreum.infrastructure.metrics_collector import MetricsCollector


def _now_iso():
    """Get current time in ISO 8601 format."""
    return datetime.now(timezone.utc).isoformat()


@pytest.mark.asyncio
class TestRepairCycleMetricsCollection:
    """Tests for repair cycle metrics collection in MetricsCollector."""

    @pytest.fixture
    def event_bus(self):
        """Create an event bus."""
        return EventBus()

    @pytest.fixture
    def metrics_collector(self, event_bus):
        """Create a metrics collector with event bus."""
        return MetricsCollector(event_bus=event_bus)

    @pytest.fixture
    def repair_cycle_started_event(self):
        """Create a repair cycle started event."""
        return RepairCycleStartedEvent(
            type="repair_cycle.started",
            timestamp=_now_iso(),
            source="test",
            pipeline_run_id="run-123",
            stage_name="code_review",
            agent_name="reviewer",
        )

    @pytest.fixture
    def repair_cycle_test_execution_event(self):
        """Create a repair cycle test execution event."""
        return RepairCycleTestExecutionCompletedEvent(
            type="repair_cycle.test_execution_completed",
            timestamp=_now_iso(),
            source="test",
            pipeline_run_id="run-123",
            test_type="unit",
            iteration=1,
            passed_count=5,
            failed_count=2,
            warnings_count=1,
        )

    @pytest.fixture
    def repair_cycle_file_fix_event(self):
        """Create a repair cycle file fix completed event."""
        return RepairCycleFileFixCompletedEvent(
            type="repair_cycle.file_fix_completed",
            timestamp=_now_iso(),
            source="test",
            pipeline_run_id="run-123",
            file_path="src/main.py",
            fixed=True,
            iterations_used=2,
        )

    @pytest.fixture
    def repair_cycle_warning_review_event(self):
        """Create a repair cycle warning review event."""
        return RepairCycleWarningReviewCompletedEvent(
            type="repair_cycle.warning_review_completed",
            timestamp=_now_iso(),
            source="test",
            pipeline_run_id="run-123",
            test_type="integration",
            warnings_reviewed=3,
        )

    @pytest.fixture
    def repair_cycle_fast_fail_event(self):
        """Create a repair cycle fast-fail event."""
        return RepairCycleFastFailEvent(
            type="repair_cycle.fast_fail",
            timestamp=_now_iso(),
            source="test",
            pipeline_run_id="run-123",
            reason="max_iterations",
            test_type="unit",
            iteration=3,
        )

    @pytest.fixture
    def repair_cycle_completed_event(self):
        """Create a repair cycle completed event."""
        return RepairCycleCompletedEvent(
            type="repair_cycle.completed",
            timestamp=_now_iso(),
            source="test",
            pipeline_run_id="run-123",
            stage_name="code_review",
            overall_success=True,
            total_iterations=3,
            total_agent_calls=2,
            duration_seconds=45.5,
        )

    async def test_repair_cycle_started_metric(self, event_bus, metrics_collector, repair_cycle_started_event):
        """Test repair cycle started metric collection."""
        await event_bus.publish(repair_cycle_started_event)
        await asyncio.sleep(0.1)  # Allow async handler to process

        metrics = metrics_collector.get_metrics()
        assert metrics["repair_cycles_started"] == 1

    async def test_repair_cycle_test_execution_metric(
        self, event_bus, metrics_collector, repair_cycle_test_execution_event
    ):
        """Test repair cycle test execution metric collection."""
        await event_bus.publish(repair_cycle_test_execution_event)
        await asyncio.sleep(0.1)

        metrics = metrics_collector.get_metrics()
        assert metrics["repair_cycle_test_executions"]["unit"] == 1

    async def test_repair_cycle_file_fix_metric(
        self, event_bus, metrics_collector, repair_cycle_file_fix_event
    ):
        """Test repair cycle file fix metric collection."""
        await event_bus.publish(repair_cycle_file_fix_event)
        await asyncio.sleep(0.1)

        metrics = metrics_collector.get_metrics()
        assert metrics["repair_cycle_file_fixes"]["src/main.py"] == 1

    async def test_repair_cycle_warning_review_metric(
        self, event_bus, metrics_collector, repair_cycle_warning_review_event
    ):
        """Test repair cycle warning review metric collection."""
        await event_bus.publish(repair_cycle_warning_review_event)
        await asyncio.sleep(0.1)

        metrics = metrics_collector.get_metrics()
        assert metrics["repair_cycle_warnings_reviewed"] == 3

    async def test_repair_cycle_fast_fail_metric(
        self, event_bus, metrics_collector, repair_cycle_fast_fail_event
    ):
        """Test repair cycle fast-fail metric collection."""
        await event_bus.publish(repair_cycle_fast_fail_event)
        await asyncio.sleep(0.1)

        metrics = metrics_collector.get_metrics()
        assert metrics["repair_cycles_fast_failed"] == 1

    async def test_repair_cycle_completed_successful_metric(
        self, event_bus, metrics_collector, repair_cycle_completed_event
    ):
        """Test repair cycle completed metric for successful cycles."""
        await event_bus.publish(repair_cycle_completed_event)
        await asyncio.sleep(0.1)

        metrics = metrics_collector.get_metrics()
        assert metrics["repair_cycles_completed"] == 1
        assert metrics["repair_cycles_successful"] == 1
        assert metrics["repair_cycles_failed"] == 0
        assert metrics["avg_repair_cycle_duration_seconds"] == 45.5
        assert metrics["avg_repair_cycle_agent_calls"] == 2

    async def test_repair_cycle_completed_failed_metric(self, event_bus, metrics_collector):
        """Test repair cycle completed metric for failed cycles."""
        failed_event = RepairCycleCompletedEvent(
            pipeline_run_id="run-456",
            stage_name="code_review",
            overall_success=False,
            total_iterations=5,
            total_agent_calls=5,
            duration_seconds=120.0,
        )

        await event_bus.publish(failed_event)
        await asyncio.sleep(0.1)

        metrics = metrics_collector.get_metrics()
        assert metrics["repair_cycles_completed"] == 1
        assert metrics["repair_cycles_successful"] == 0
        assert metrics["repair_cycles_failed"] == 1

    async def test_repair_cycle_success_rate_calculation(self, event_bus, metrics_collector):
        """Test repair cycle success rate calculation."""
        # Publish 3 successful cycles
        for i in range(3):
            event = RepairCycleCompletedEvent(
                pipeline_run_id=f"run-{i}",
                stage_name="code_review",
                overall_success=True,
                total_iterations=2,
                total_agent_calls=1,
                duration_seconds=30.0,
            )
            await event_bus.publish(event)
            await asyncio.sleep(0.05)

        # Publish 1 failed cycle
        failed_event = RepairCycleCompletedEvent(
            pipeline_run_id="run-failed",
            stage_name="code_review",
            overall_success=False,
            total_iterations=5,
            total_agent_calls=5,
            duration_seconds=120.0,
        )
        await event_bus.publish(failed_event)
        await asyncio.sleep(0.1)

        metrics = metrics_collector.get_metrics()
        assert metrics["repair_cycles_completed"] == 4
        assert metrics["repair_cycles_successful"] == 3
        assert metrics["repair_cycles_failed"] == 1
        # Success rate should be 75%
        assert metrics["repair_cycle_success_rate_percent"] == 75.0

    async def test_repair_cycle_duration_averaging(self, event_bus, metrics_collector):
        """Test repair cycle duration averaging."""
        durations = [30.0, 45.0, 60.0]

        for i, duration in enumerate(durations):
            event = RepairCycleCompletedEvent(
                pipeline_run_id=f"run-{i}",
                stage_name="code_review",
                overall_success=True,
                total_iterations=2,
                total_agent_calls=1,
                duration_seconds=duration,
            )
            await event_bus.publish(event)
            await asyncio.sleep(0.05)

        metrics = metrics_collector.get_metrics()
        expected_avg = sum(durations) / len(durations)
        assert metrics["avg_repair_cycle_duration_seconds"] == expected_avg

    async def test_reset_repair_cycle_metrics(self, event_bus, metrics_collector, repair_cycle_started_event):
        """Test resetting repair cycle metrics."""
        await event_bus.publish(repair_cycle_started_event)
        await asyncio.sleep(0.1)

        metrics = metrics_collector.get_metrics()
        assert metrics["repair_cycles_started"] == 1

        # Reset metrics
        metrics_collector.reset_metrics()
        metrics = metrics_collector.get_metrics()

        assert metrics["repair_cycles_started"] == 0
        assert metrics["repair_cycles_completed"] == 0
        assert metrics["repair_cycles_successful"] == 0
        assert metrics["repair_cycles_failed"] == 0
        assert metrics["repair_cycles_fast_failed"] == 0
        assert metrics["repair_cycle_success_rate_percent"] is None
        assert metrics["avg_repair_cycle_duration_seconds"] is None
        assert metrics["avg_repair_cycle_agent_calls"] is None

    async def test_multiple_test_types_tracking(self, event_bus, metrics_collector):
        """Test tracking multiple test types in repair cycles."""
        test_types = ["unit", "integration", "e2e"]

        for test_type in test_types:
            event = RepairCycleTestExecutionCompletedEvent(
                pipeline_run_id="run-123",
                test_type=test_type,
                iteration=1,
                passed_count=10,
                failed_count=0,
                warnings_count=0,
            )
            await event_bus.publish(event)
            await asyncio.sleep(0.05)

        metrics = metrics_collector.get_metrics()
        assert metrics["repair_cycle_test_executions"]["unit"] == 1
        assert metrics["repair_cycle_test_executions"]["integration"] == 1
        assert metrics["repair_cycle_test_executions"]["e2e"] == 1

    async def test_multiple_files_fixed_tracking(self, event_bus, metrics_collector):
        """Test tracking multiple files fixed in repair cycles."""
        files = ["src/main.py", "src/utils.py", "tests/test_main.py"]

        for file_path in files:
            event = RepairCycleFileFixCompletedEvent(
                pipeline_run_id="run-123",
                file_path=file_path,
                fixed=True,
                iterations_used=1,
            )
            await event_bus.publish(event)
            await asyncio.sleep(0.05)

        metrics = metrics_collector.get_metrics()
        for file_path in files:
            assert metrics["repair_cycle_file_fixes"][file_path] == 1

    async def test_event_handler_error_handling(self, event_bus, metrics_collector):
        """Test that metrics collector handles event handler errors gracefully."""
        # Create an event with missing required fields by calling from_dict with empty payload
        try:
            bad_event = RepairCycleStartedEvent.from_dict({})
        except ValueError:
            # This is expected - the event requires pipeline_run_id, stage_name, agent_name
            # Instead, let's test with a malformed event type
            bad_event = MagicMock(spec=DomainEvent)
            bad_event.event_type = "unknown.event"
            # Publishing unknown event types should not cause errors in metrics collector
            await event_bus.publish(bad_event)
            await asyncio.sleep(0.1)
            # Errors should not be incremented for unknown event types,
            # only for handled event types that fail
            return

        # This should not raise an error for missing fields on validation
        await event_bus.publish(bad_event)
        await asyncio.sleep(0.1)

    async def test_end_to_end_repair_cycle_metrics(self, event_bus, metrics_collector):
        """Test end-to-end repair cycle metrics collection."""
        # Start cycle
        start_event = RepairCycleStartedEvent(
            pipeline_run_id="run-123",
            stage_name="code_review",
            agent_name="reviewer",
        )
        await event_bus.publish(start_event)
        await asyncio.sleep(0.05)

        # Test execution
        test_event = RepairCycleTestExecutionCompletedEvent(
            pipeline_run_id="run-123",
            test_type="unit",
            iteration=1,
            passed_count=5,
            failed_count=2,
            warnings_count=0,
        )
        await event_bus.publish(test_event)
        await asyncio.sleep(0.05)

        # File fix
        file_fix_event = RepairCycleFileFixCompletedEvent(
            pipeline_run_id="run-123",
            file_path="src/main.py",
            fixed=True,
            iterations_used=1,
        )
        await event_bus.publish(file_fix_event)
        await asyncio.sleep(0.05)

        # Completion
        completion_event = RepairCycleCompletedEvent(
            pipeline_run_id="run-123",
            stage_name="code_review",
            overall_success=True,
            total_iterations=1,
            total_agent_calls=1,
            duration_seconds=42.0,
        )
        await event_bus.publish(completion_event)
        await asyncio.sleep(0.1)

        metrics = metrics_collector.get_metrics()

        # Verify all metrics are collected
        assert metrics["repair_cycles_started"] == 1
        assert metrics["repair_cycles_completed"] == 1
        assert metrics["repair_cycles_successful"] == 1
        assert metrics["repair_cycle_test_executions"]["unit"] == 1
        assert metrics["repair_cycle_file_fixes"]["src/main.py"] == 1
        assert metrics["avg_repair_cycle_duration_seconds"] == 42.0
        assert metrics["avg_repair_cycle_agent_calls"] == 1.0
