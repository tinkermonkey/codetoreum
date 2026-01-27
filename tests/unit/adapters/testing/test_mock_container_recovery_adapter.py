"""Unit tests for MockContainerRecoveryAdapter.

These tests verify:
- Container setup and retrieval
- Assessment configuration
- Action execution and tracking
- Reset functionality
"""

from datetime import datetime, timedelta, timezone

import pytest

from codetoreum.adapters.testing.mock_container_recovery_adapter import (
    MockContainerRecoveryAdapter,
)


class TestMockContainerRecoveryAdapterSetup:
    """Tests for setting up mock containers."""

    def test_add_container_basic(self):
        """Should add container with basic fields."""
        adapter = MockContainerRecoveryAdapter()

        metadata = adapter.add_container(
            container_id="abc123",
            container_name="test-container",
            project_id="proj-1",
            agent_id="agent-1",
            task_id="task-1",
        )

        assert metadata.container_id == "abc123"
        assert metadata.container_name == "test-container"
        assert metadata.project_id == "proj-1"
        assert metadata.agent_id == "agent-1"
        assert metadata.task_id == "task-1"

    def test_add_container_with_optional_fields(self):
        """Should add container with optional fields."""
        adapter = MockContainerRecoveryAdapter()

        metadata = adapter.add_container(
            container_id="abc123",
            container_name="test-container",
            project_id="proj-1",
            agent_id="agent-1",
            task_id="task-1",
            work_item_id="work-123",
            execution_id="exec-456",
        )

        assert metadata.work_item_id == "work-123"
        assert metadata.execution_id == "exec-456"

    def test_add_container_with_created_at(self):
        """Should add container with specified creation time."""
        adapter = MockContainerRecoveryAdapter()

        created_at = datetime.now(timezone.utc) - timedelta(hours=1)
        metadata = adapter.add_container(
            container_id="abc123",
            container_name="test-container",
            project_id="proj-1",
            agent_id="agent-1",
            task_id="task-1",
            created_at=created_at,
        )

        assert metadata.created_at == created_at

    def test_add_container_with_age_hours(self):
        """Should add container with age calculated in hours."""
        adapter = MockContainerRecoveryAdapter()

        before = datetime.now(timezone.utc)
        metadata = adapter.add_container(
            container_id="abc123",
            container_name="test-container",
            project_id="proj-1",
            agent_id="agent-1",
            task_id="task-1",
            age_hours=2.5,
        )
        after = datetime.now(timezone.utc)

        # Created at should be approximately 2.5 hours ago
        expected_created = before - timedelta(hours=2.5)
        delta = abs((metadata.created_at - expected_created).total_seconds())

        assert delta < 2  # Within 2 seconds


class TestMockContainerRecoveryAdapterRetrievalAndAssessment:
    """Tests for retrieving containers and assessments."""

    @pytest.mark.asyncio
    async def test_get_running_agent_containers_empty(self):
        """Should return empty list when no containers added."""
        adapter = MockContainerRecoveryAdapter()

        containers = await adapter.get_running_agent_containers()

        assert containers == []

    @pytest.mark.asyncio
    async def test_get_running_agent_containers_multiple(self):
        """Should return all added containers."""
        adapter = MockContainerRecoveryAdapter()

        adapter.add_container(
            container_id="abc123",
            container_name="container-1",
            project_id="proj-1",
            agent_id="agent-1",
            task_id="task-1",
        )

        adapter.add_container(
            container_id="def456",
            container_name="container-2",
            project_id="proj-1",
            agent_id="agent-2",
            task_id="task-2",
        )

        containers = await adapter.get_running_agent_containers()

        assert len(containers) == 2
        assert containers[0].container_id == "abc123"
        assert containers[1].container_id == "def456"

    @pytest.mark.asyncio
    async def test_assess_container_default(self):
        """Should return default assessment if none configured."""
        adapter = MockContainerRecoveryAdapter()

        metadata = adapter.add_container(
            container_id="abc123",
            container_name="test-container",
            project_id="proj-1",
            agent_id="agent-1",
            task_id="task-1",
            work_item_id="work-123",
        )

        assessment = await adapter.assess_container(metadata)

        assert assessment.action == "reconnect"
        assert assessment.reason == "default_recovery"
        assert assessment.with_monitoring is True

    @pytest.mark.asyncio
    async def test_assess_container_configured(self):
        """Should return configured assessment."""
        adapter = MockContainerRecoveryAdapter()

        adapter.add_container(
            container_id="abc123",
            container_name="test-container",
            project_id="proj-1",
            agent_id="agent-1",
            task_id="task-1",
        )

        adapter.set_assessment(
            container_id="abc123",
            action="kill",
            reason="container_timeout",
            with_monitoring=False,
        )

        metadata = adapter.containers[0]
        assessment = await adapter.assess_container(metadata)

        assert assessment.action == "kill"
        assert assessment.reason == "container_timeout"
        assert assessment.with_monitoring is False


class TestMockContainerRecoveryAdapterActionExecution:
    """Tests for action execution tracking."""

    @pytest.mark.asyncio
    async def test_execute_recovery_action_success(self):
        """Should return True for successful action execution."""
        adapter = MockContainerRecoveryAdapter()

        from codetoreum.ports.output.container_recovery import RecoveryAssessment

        assessment = RecoveryAssessment(
            container_id="abc123",
            action="reconnect",
            reason="execution_in_progress",
            with_monitoring=True,
            execution_id="exec-456",
        )

        result = await adapter.execute_recovery_action(assessment)

        assert result is True
        assert len(adapter.executed_actions) == 1
        assert adapter.executed_actions[0] == assessment

    @pytest.mark.asyncio
    async def test_execute_recovery_action_failure(self):
        """Should return False for failed action execution."""
        adapter = MockContainerRecoveryAdapter()

        from codetoreum.ports.output.container_recovery import RecoveryAssessment

        assessment = RecoveryAssessment(
            container_id="abc123",
            action="kill",
            reason="container_timeout",
            with_monitoring=False,
        )

        # Mark as failing
        adapter.set_action_failure("abc123")

        result = await adapter.execute_recovery_action(assessment)

        assert result is False
        assert len(adapter.executed_actions) == 1

    @pytest.mark.asyncio
    async def test_execute_multiple_actions_tracked(self):
        """Should track multiple executed actions."""
        adapter = MockContainerRecoveryAdapter()

        from codetoreum.ports.output.container_recovery import RecoveryAssessment

        assessment1 = RecoveryAssessment(
            container_id="abc123",
            action="reconnect",
            reason="execution_in_progress",
            with_monitoring=True,
            execution_id="exec-1",
        )

        assessment2 = RecoveryAssessment(
            container_id="def456",
            action="kill",
            reason="container_timeout",
            with_monitoring=False,
        )

        await adapter.execute_recovery_action(assessment1)
        await adapter.execute_recovery_action(assessment2)

        assert len(adapter.executed_actions) == 2
        assert adapter.executed_actions[0] == assessment1
        assert adapter.executed_actions[1] == assessment2


class TestMockContainerRecoveryAdapterRepairCycles:
    """Tests for repair cycle processing."""

    @pytest.mark.asyncio
    async def test_process_orphaned_repair_results_default(self):
        """Should return 0 repair cycles by default."""
        adapter = MockContainerRecoveryAdapter()

        count = await adapter.process_orphaned_repair_results()

        assert count == 0

    @pytest.mark.asyncio
    async def test_process_orphaned_repair_results_configured(self):
        """Should return configured repair cycle count."""
        adapter = MockContainerRecoveryAdapter()
        adapter.repair_cycles_to_process = 5

        count = await adapter.process_orphaned_repair_results()

        assert count == 5


class TestMockContainerRecoveryAdapterReset:
    """Tests for reset functionality."""

    @pytest.mark.asyncio
    async def test_reset_clears_state(self):
        """Should clear all state on reset."""
        adapter = MockContainerRecoveryAdapter()

        # Add some state
        adapter.add_container(
            container_id="abc123",
            container_name="test",
            project_id="proj-1",
            agent_id="agent-1",
            task_id="task-1",
        )

        adapter.set_assessment(
            container_id="abc123",
            action="kill",
            reason="test",
            with_monitoring=False,
        )

        adapter.set_action_failure("abc123")
        adapter.repair_cycles_to_process = 3

        from codetoreum.ports.output.container_recovery import RecoveryAssessment

        assessment = RecoveryAssessment(
            container_id="abc123",
            action="kill",
            reason="test",
            with_monitoring=False,
        )
        await adapter.execute_recovery_action(assessment)

        # Reset
        adapter.reset()

        # Verify state is cleared
        assert len(adapter.containers) == 0
        assert len(adapter.assessments) == 0
        assert len(adapter.failed_actions) == 0
        assert len(adapter.executed_actions) == 0
        assert adapter.repair_cycles_to_process == 0
