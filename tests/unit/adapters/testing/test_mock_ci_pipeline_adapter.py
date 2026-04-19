"""Unit tests for MockCIPipelineAdapter."""

import pytest

from codetoreum.adapters.testing import CapturingMockEventEmitter, MockCIPipelineAdapter
from codetoreum.domain.events.ci_pipeline_events import (
    CIPipelineStatusCheckedEvent,
    CIRunCompletedEvent,
    CIRunStartedEvent,
)
from codetoreum.infrastructure.simulation.simulation_clock import SimulationClock
from codetoreum.ports.output.ci_pipeline_service import CICheckStatus


class TestMockCIPipelineAdapterConfiguration:
    """Test configuration API methods."""

    async def test_set_pr_ci_passing(self) -> None:
        """Test configuring PR with passing CI status."""
        adapter = MockCIPipelineAdapter()
        adapter.set_pr_ci_passing("pr-123")

        status = await adapter.get_pr_ci_status("pr-123", "proj-1")

        assert status.pr_id == "pr-123"
        assert status.status == CICheckStatus.PASSED
        assert all(r.status == CICheckStatus.PASSED for r in status.check_results)

    async def test_set_pr_ci_failing(self) -> None:
        """Test configuring PR with failing CI status."""
        adapter = MockCIPipelineAdapter()
        adapter.set_pr_ci_failing("pr-123", failure_count=2)

        status = await adapter.get_pr_ci_status("pr-123", "proj-1")

        assert status.pr_id == "pr-123"
        assert status.status == CICheckStatus.FAILED
        failed_results = [r for r in status.check_results if r.status == CICheckStatus.FAILED]
        assert len(failed_results) == 2

    async def test_set_pr_ci_pending(self) -> None:
        """Test configuring PR with pending CI status."""
        adapter = MockCIPipelineAdapter()
        adapter.set_pr_ci_pending("pr-123", pending_count=3)

        status = await adapter.get_pr_ci_status("pr-123", "proj-1")

        assert status.pr_id == "pr-123"
        assert status.status == CICheckStatus.PENDING
        pending_results = [r for r in status.check_results if r.status == CICheckStatus.PENDING]
        assert len(pending_results) == 3

    async def test_set_ci_run_passing(self) -> None:
        """Test configuring project with passing CI run results."""
        adapter = MockCIPipelineAdapter()
        adapter.set_ci_run_passing("proj-1")

        result = await adapter.run_ci_checks("proj-1", "/workspace")

        assert result.failed == 0
        assert result.passed == 1
        assert len(result.failures) == 0

    async def test_set_ci_run_failing(self) -> None:
        """Test configuring project with failing CI run results."""
        adapter = MockCIPipelineAdapter()
        failures = ["lint: line too long", "tests: timeout"]
        adapter.set_ci_run_failing("proj-1", failures)

        result = await adapter.run_ci_checks("proj-1", "/workspace")

        assert result.failed == 2
        assert result.passed == 0
        assert result.failures == ("lint: line too long", "tests: timeout")


class TestMockCIPipelineAdapterDefaultBehavior:
    """Test default behavior when no configuration is set."""

    async def test_default_pr_ci_passing(self) -> None:
        """Test unconfigured PR defaults to passing status."""
        adapter = MockCIPipelineAdapter()

        status = await adapter.get_pr_ci_status("pr-unconfigured", "proj-1")

        assert status.pr_id == "pr-unconfigured"
        assert status.status == CICheckStatus.PASSED
        assert all(r.status == CICheckStatus.PASSED for r in status.check_results)

    async def test_default_ci_run_passing(self) -> None:
        """Test unconfigured project defaults to passing CI run results."""
        adapter = MockCIPipelineAdapter()

        result = await adapter.run_ci_checks("proj-unconfigured", "/workspace")

        assert result.failed == 0
        assert result.passed == 1
        assert len(result.failures) == 0


class TestMockCIPipelineAdapterAssertions:
    """Test assertion helper methods."""

    async def test_assert_pr_ci_checked_success(self) -> None:
        """Test assertion passes when PR CI status is checked."""
        adapter = MockCIPipelineAdapter()
        await adapter.get_pr_ci_status("pr-123", "proj-1")

        # Should not raise
        adapter.assert_pr_ci_checked("pr-123")

    async def test_assert_pr_ci_checked_failure(self) -> None:
        """Test assertion fails when PR CI status was never checked."""
        adapter = MockCIPipelineAdapter()

        with pytest.raises(AssertionError) as exc_info:
            adapter.assert_pr_ci_checked("pr-123")

        assert "Expected PR pr-123 CI status to have been checked" in str(exc_info.value)

    async def test_assert_ci_run_executed_success(self) -> None:
        """Test assertion passes when CI run is executed."""
        adapter = MockCIPipelineAdapter()
        await adapter.run_ci_checks("proj-1", "/workspace")

        # Should not raise
        adapter.assert_ci_run_executed("proj-1")

    async def test_assert_ci_run_executed_failure(self) -> None:
        """Test assertion fails when CI run was never executed."""
        adapter = MockCIPipelineAdapter()

        with pytest.raises(AssertionError) as exc_info:
            adapter.assert_ci_run_executed("proj-1")

        assert "Expected CI run to have been executed for project proj-1" in str(exc_info.value)

    async def test_assert_no_failures_success(self) -> None:
        """Test assertion passes when PR has no failures configured."""
        adapter = MockCIPipelineAdapter()
        adapter.set_pr_ci_passing("pr-123")

        # Should not raise
        adapter.assert_no_failures("pr-123")

    async def test_assert_no_failures_with_unconfigured_pr(self) -> None:
        """Test assertion passes when PR is unconfigured (defaults to passing)."""
        adapter = MockCIPipelineAdapter()

        # Should not raise - unconfigured PRs default to passing
        adapter.assert_no_failures("pr-unconfigured")

    async def test_assert_no_failures_failure(self) -> None:
        """Test assertion fails when PR has failures configured."""
        adapter = MockCIPipelineAdapter()
        adapter.set_pr_ci_failing("pr-123", failure_count=2)

        with pytest.raises(AssertionError) as exc_info:
            adapter.assert_no_failures("pr-123")

        assert "Expected PR pr-123 to have no failures" in str(exc_info.value)
        assert "2 checks are failing" in str(exc_info.value)


class TestMockCIPipelineAdapterEventEmission:
    """Test event emission functionality."""

    async def test_emit_pipeline_status_checked_event(self) -> None:
        """Test CIPipelineStatusCheckedEvent is emitted."""
        emitter = CapturingMockEventEmitter()
        adapter = MockCIPipelineAdapter(event_emitter=emitter)
        adapter.set_pr_ci_failing("pr-123", failure_count=2)

        await adapter.get_pr_ci_status("pr-123", "proj-1")

        events = emitter.get_events_by_type("ci.pipeline_status_checked")
        assert len(events) == 1

        event = events[0]
        assert isinstance(event, CIPipelineStatusCheckedEvent)
        assert event.pr_id == "pr-123"
        assert event.project_id == "proj-1"
        assert event.status == "failed"
        assert event.failed_count == 2

    async def test_emit_ci_run_started_event(self) -> None:
        """Test CIRunStartedEvent is emitted."""
        emitter = CapturingMockEventEmitter()
        adapter = MockCIPipelineAdapter(event_emitter=emitter)

        await adapter.run_ci_checks("proj-1", "/workspace", timeout_seconds=600)

        events = emitter.get_events_by_type("ci.run_started")
        assert len(events) == 1

        event = events[0]
        assert isinstance(event, CIRunStartedEvent)
        assert event.project_id == "proj-1"
        assert event.working_directory == "/workspace"
        assert event.timeout_seconds == 600

    async def test_emit_ci_run_completed_event(self) -> None:
        """Test CIRunCompletedEvent is emitted."""
        emitter = CapturingMockEventEmitter()
        adapter = MockCIPipelineAdapter(event_emitter=emitter)
        adapter.set_ci_run_failing("proj-1", ["lint: error"])

        await adapter.run_ci_checks("proj-1", "/workspace")

        events = emitter.get_events_by_type("ci.run_completed")
        assert len(events) == 1

        event = events[0]
        assert isinstance(event, CIRunCompletedEvent)
        assert event.project_id == "proj-1"
        assert event.passed == 0
        assert event.failed == 1

    async def test_emit_events_have_timestamp(self) -> None:
        """Test all emitted events have timestamps."""
        emitter = CapturingMockEventEmitter()
        adapter = MockCIPipelineAdapter(event_emitter=emitter)

        await adapter.get_pr_ci_status("pr-123", "proj-1")

        event = emitter.get_events_by_type("ci.pipeline_status_checked")[0]
        assert event.timestamp
        assert len(event.timestamp) > 0

    async def test_emit_events_have_source(self) -> None:
        """Test all emitted events have 'mock' source."""
        emitter = CapturingMockEventEmitter()
        adapter = MockCIPipelineAdapter(event_emitter=emitter)

        await adapter.get_pr_ci_status("pr-123", "proj-1")
        await adapter.run_ci_checks("proj-1", "/workspace")

        events = emitter.get_events()
        for event in events:
            assert event.source == "mock"


class TestMockCIPipelineAdapterMonitoring:
    """Test monitoring lifecycle (IMonitoredService)."""

    async def test_start_monitoring(self) -> None:
        """Test start_monitoring sets active status."""
        from codetoreum.ports.output.monitoring import MonitoringConfig, MonitoringState

        adapter = MockCIPipelineAdapter()
        config = MonitoringConfig(project_id="proj-1")

        await adapter.start_monitoring("proj-1", config)
        status = await adapter.get_monitoring_status("proj-1")

        assert status.state == MonitoringState.ACTIVE
        assert status.project_id == "proj-1"

    async def test_stop_monitoring(self) -> None:
        """Test stop_monitoring sets stopped status."""
        from codetoreum.ports.output.monitoring import MonitoringConfig, MonitoringState

        adapter = MockCIPipelineAdapter()
        config = MonitoringConfig(project_id="proj-1")

        await adapter.start_monitoring("proj-1", config)
        await adapter.stop_monitoring("proj-1")
        status = await adapter.get_monitoring_status("proj-1")

        assert status.state == MonitoringState.STOPPED
        assert status.project_id == "proj-1"

    async def test_get_monitoring_status_inactive_by_default(self) -> None:
        """Test unmonitored project returns stopped status."""
        from codetoreum.ports.output.monitoring import MonitoringState

        adapter = MockCIPipelineAdapter()
        status = await adapter.get_monitoring_status("proj-unmonitored")

        assert status.state == MonitoringState.STOPPED
        assert status.project_id == "proj-unmonitored"


class TestMockCIPipelineAdapterSimulationClock:
    """Test SimulationClock integration."""

    async def test_uses_simulation_clock_for_timestamps(self) -> None:
        """Test adapter uses SimulationClock for timestamps when provided."""
        from datetime import UTC, datetime, timedelta

        clock = SimulationClock(speed_multiplier=100.0)
        start_time = datetime(2025, 1, 1, 12, 0, 0, tzinfo=UTC)
        clock.start_at(start_time)

        emitter = CapturingMockEventEmitter()
        adapter = MockCIPipelineAdapter(event_emitter=emitter, clock=clock)

        await adapter.get_pr_ci_status("pr-123", "proj-1")

        event = emitter.get_events_by_type("ci.pipeline_status_checked")[0]
        assert event.timestamp == start_time.isoformat()

    async def test_falls_back_to_wall_clock_without_simulation_clock(self) -> None:
        """Test adapter uses wall clock when SimulationClock not provided."""
        from datetime import UTC, datetime

        emitter = CapturingMockEventEmitter()
        adapter = MockCIPipelineAdapter(event_emitter=emitter, clock=None)

        before = datetime.now(UTC).isoformat()
        await adapter.get_pr_ci_status("pr-123", "proj-1")
        after = datetime.now(UTC).isoformat()

        event = emitter.get_events_by_type("ci.pipeline_status_checked")[0]
        # Timestamp should be between before and after
        assert before <= event.timestamp <= after


class TestMockCIPipelineAdapterTestHelpers:
    """Test helper methods for testing."""

    async def test_clear_removes_all_state(self) -> None:
        """Test clear() removes all configuration and call history."""
        adapter = MockCIPipelineAdapter()
        adapter.set_pr_ci_failing("pr-123", failure_count=1)
        await adapter.get_pr_ci_status("pr-123", "proj-1")
        await adapter.run_ci_checks("proj-1", "/workspace")

        # Before clear, confirm history is populated
        assert len(adapter.get_pr_ci_calls()) > 0
        assert len(adapter.get_ci_run_calls()) > 0

        adapter.clear()

        # After clear, call history should be cleared
        assert adapter.get_pr_ci_calls() == []
        assert adapter.get_ci_run_calls() == []

        # After clear, PR should be unconfigured (defaults to passing)
        status = await adapter.get_pr_ci_status("pr-123", "proj-1")
        assert status.status == CICheckStatus.PASSED

    async def test_get_pr_ci_calls(self) -> None:
        """Test get_pr_ci_calls returns checked PR IDs."""
        adapter = MockCIPipelineAdapter()

        await adapter.get_pr_ci_status("pr-1", "proj-1")
        await adapter.get_pr_ci_status("pr-2", "proj-1")
        await adapter.get_pr_ci_status("pr-1", "proj-1")  # Second check of same PR

        calls = adapter.get_pr_ci_calls()
        assert "pr-1" in calls
        assert "pr-2" in calls

    async def test_get_ci_run_calls(self) -> None:
        """Test get_ci_run_calls returns project IDs that had runs."""
        adapter = MockCIPipelineAdapter()

        await adapter.run_ci_checks("proj-1", "/workspace")
        await adapter.run_ci_checks("proj-2", "/workspace")
        await adapter.run_ci_checks("proj-1", "/workspace")  # Second run of same project

        calls = adapter.get_ci_run_calls()
        assert "proj-1" in calls
        assert "proj-2" in calls


class TestMockCIPipelineAdapterIntegration:
    """Integration tests combining multiple features."""

    async def test_full_workflow_pr_failing_ci(self) -> None:
        """Test complete workflow with failing PR CI."""
        emitter = CapturingMockEventEmitter()
        adapter = MockCIPipelineAdapter(event_emitter=emitter)

        # Configure failing PR
        adapter.set_pr_ci_failing("pr-123", failure_count=1)

        # Check status
        status = await adapter.get_pr_ci_status("pr-123", "proj-1")
        assert status.status == CICheckStatus.FAILED

        # Verify interaction
        adapter.assert_pr_ci_checked("pr-123")

        # Verify assertion for no failures fails
        with pytest.raises(AssertionError):
            adapter.assert_no_failures("pr-123")

        # Verify events emitted
        events = emitter.get_events_by_type("ci.pipeline_status_checked")
        assert len(events) == 1

    async def test_full_workflow_ci_run_with_failures(self) -> None:
        """Test complete workflow with CI run failures."""
        emitter = CapturingMockEventEmitter()
        adapter = MockCIPipelineAdapter(event_emitter=emitter)

        # Configure failing CI run
        failures = ["lint: error", "tests: failed"]
        adapter.set_ci_run_failing("proj-1", failures)

        # Run CI
        result = await adapter.run_ci_checks("proj-1", "/workspace", timeout_seconds=300)

        assert result.failed == 2
        assert result.failures == ("lint: error", "tests: failed")

        # Verify interaction
        adapter.assert_ci_run_executed("proj-1")

        # Verify events emitted (started and completed)
        started_events = emitter.get_events_by_type("ci.run_started")
        completed_events = emitter.get_events_by_type("ci.run_completed")
        assert len(started_events) == 1
        assert len(completed_events) == 1

        # Verify completed event has correct failure count
        completed_event = completed_events[0]
        assert completed_event.failed == 2
        assert completed_event.passed == 0

    async def test_multiple_prs_and_projects(self) -> None:
        """Test handling multiple PRs and projects independently."""
        adapter = MockCIPipelineAdapter()

        # Configure different PRs differently
        adapter.set_pr_ci_passing("pr-1")
        adapter.set_pr_ci_failing("pr-2", failure_count=1)

        # Configure different projects differently
        adapter.set_ci_run_passing("proj-1")
        adapter.set_ci_run_failing("proj-2", ["error"])

        # Verify PR statuses
        status1 = await adapter.get_pr_ci_status("pr-1", "proj-1")
        status2 = await adapter.get_pr_ci_status("pr-2", "proj-1")

        assert status1.status == CICheckStatus.PASSED
        assert status2.status == CICheckStatus.FAILED

        # Verify CI run results
        result1 = await adapter.run_ci_checks("proj-1", "/workspace")
        result2 = await adapter.run_ci_checks("proj-2", "/workspace")

        assert result1.failed == 0
        assert result2.failed == 1

        # Verify call tracking is independent
        adapter.assert_pr_ci_checked("pr-1")
        adapter.assert_pr_ci_checked("pr-2")
        adapter.assert_ci_run_executed("proj-1")
        adapter.assert_ci_run_executed("proj-2")
