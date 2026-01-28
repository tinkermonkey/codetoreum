"""Unit tests for container recovery events."""

import pytest

from codetoreum.domain.events import (
    ContainerRecoveredEvent,
    ContainerKilledEvent,
    ContainerRecoveryCompletedEvent,
    now_iso,
)

# For immutability tests
try:
    from dataclasses import FrozenInstanceError
except ImportError:
    FrozenInstanceError = AttributeError  # type: ignore


class TestContainerRecoveredEvent:
    """Test ContainerRecoveredEvent."""

    def test_create_valid_event(self):
        """Test creating a valid container recovered event."""
        timestamp = now_iso()
        event = ContainerRecoveredEvent(
            type="container_recovery.recovered",
            timestamp=timestamp,
            source="container_recovery",
            container_id="container-abc123",
            container_name="agent-run-123",
            project_id="proj-456",
            agent_id="agent-789",
            work_item_id="issue-123",
            execution_id="exec-456",
            uptime_seconds=3600.5,
            recovery_action="reconnect_with_monitoring",
        )

        assert event.container_id == "container-abc123"
        assert event.container_name == "agent-run-123"
        assert event.project_id == "proj-456"
        assert event.agent_id == "agent-789"
        assert event.work_item_id == "issue-123"
        assert event.execution_id == "exec-456"
        assert event.uptime_seconds == 3600.5
        assert event.recovery_action == "reconnect_with_monitoring"

    def test_missing_container_id(self):
        """Test that container_id is required."""
        with pytest.raises(ValueError, match="container_id"):
            ContainerRecoveredEvent(
                type="container_recovery.recovered",
                timestamp=now_iso(),
                source="container_recovery",
                container_id="",
                container_name="agent-run-123",
                project_id="proj-456",
                agent_id="agent-789",
                uptime_seconds=3600.0,
                recovery_action="reconnect_with_monitoring",
            )

    def test_missing_container_name(self):
        """Test that container_name is required."""
        with pytest.raises(ValueError, match="container_name"):
            ContainerRecoveredEvent(
                type="container_recovery.recovered",
                timestamp=now_iso(),
                source="container_recovery",
                container_id="container-abc123",
                container_name="",
                project_id="proj-456",
                agent_id="agent-789",
                uptime_seconds=3600.0,
                recovery_action="reconnect_with_monitoring",
            )

    def test_missing_project_id(self):
        """Test that project_id is required."""
        with pytest.raises(ValueError, match="project_id"):
            ContainerRecoveredEvent(
                type="container_recovery.recovered",
                timestamp=now_iso(),
                source="container_recovery",
                container_id="container-abc123",
                container_name="agent-run-123",
                project_id="",
                agent_id="agent-789",
                uptime_seconds=3600.0,
                recovery_action="reconnect_with_monitoring",
            )

    def test_missing_agent_id(self):
        """Test that agent_id is required."""
        with pytest.raises(ValueError, match="agent_id"):
            ContainerRecoveredEvent(
                type="container_recovery.recovered",
                timestamp=now_iso(),
                source="container_recovery",
                container_id="container-abc123",
                container_name="agent-run-123",
                project_id="proj-456",
                agent_id="",
                uptime_seconds=3600.0,
                recovery_action="reconnect_with_monitoring",
            )

    def test_negative_uptime(self):
        """Test that uptime_seconds must be >= 0."""
        with pytest.raises(ValueError, match="uptime_seconds"):
            ContainerRecoveredEvent(
                type="container_recovery.recovered",
                timestamp=now_iso(),
                source="container_recovery",
                container_id="container-abc123",
                container_name="agent-run-123",
                project_id="proj-456",
                agent_id="agent-789",
                uptime_seconds=-1.0,
                recovery_action="reconnect_with_monitoring",
            )

    def test_invalid_recovery_action(self):
        """Test that recovery_action must be valid."""
        with pytest.raises(ValueError, match="recovery_action"):
            ContainerRecoveredEvent(
                type="container_recovery.recovered",
                timestamp=now_iso(),
                source="container_recovery",
                container_id="container-abc123",
                container_name="agent-run-123",
                project_id="proj-456",
                agent_id="agent-789",
                uptime_seconds=3600.0,
                recovery_action="invalid_action",  # type: ignore
            )

    def test_immutability(self):
        """Test that ContainerRecoveredEvent is immutable."""
        event = ContainerRecoveredEvent(
            type="container_recovery.recovered",
            timestamp=now_iso(),
            source="container_recovery",
            container_id="container-abc123",
            container_name="agent-run-123",
            project_id="proj-456",
            agent_id="agent-789",
            uptime_seconds=3600.0,
            recovery_action="reconnect_with_monitoring",
        )

        with pytest.raises(FrozenInstanceError):
            event.container_id = "container-xyz789"  # type: ignore

    def test_serialization(self):
        """Test ContainerRecoveredEvent serialization."""
        timestamp = now_iso()
        event = ContainerRecoveredEvent(
            type="container_recovery.recovered",
            timestamp=timestamp,
            source="container_recovery",
            container_id="container-abc123",
            container_name="agent-run-123",
            project_id="proj-456",
            agent_id="agent-789",
            work_item_id="issue-123",
            execution_id="exec-456",
            uptime_seconds=3600.5,
            recovery_action="reconnect_limited",
        )

        d = event.to_dict()
        assert d["type"] == "container_recovery.recovered"
        assert d["container_id"] == "container-abc123"
        assert d["container_name"] == "agent-run-123"
        assert d["project_id"] == "proj-456"
        assert d["agent_id"] == "agent-789"
        assert d["work_item_id"] == "issue-123"
        assert d["execution_id"] == "exec-456"
        assert d["uptime_seconds"] == 3600.5
        assert d["recovery_action"] == "reconnect_limited"

    def test_deserialization(self):
        """Test ContainerRecoveredEvent deserialization."""
        timestamp = now_iso()
        d = {
            "type": "container_recovery.recovered",
            "timestamp": timestamp,
            "source": "container_recovery",
            "container_id": "container-abc123",
            "container_name": "agent-run-123",
            "project_id": "proj-456",
            "agent_id": "agent-789",
            "work_item_id": "issue-123",
            "execution_id": "exec-456",
            "uptime_seconds": 3600.5,
            "recovery_action": "reconnect_with_monitoring",
        }

        event = ContainerRecoveredEvent.from_dict(d)
        assert event.container_id == "container-abc123"
        assert event.container_name == "agent-run-123"
        assert event.project_id == "proj-456"
        assert event.agent_id == "agent-789"
        assert event.work_item_id == "issue-123"
        assert event.execution_id == "exec-456"
        assert event.uptime_seconds == 3600.5
        assert event.recovery_action == "reconnect_with_monitoring"


class TestContainerKilledEvent:
    """Test ContainerKilledEvent."""

    def test_create_valid_event(self):
        """Test creating a valid container killed event."""
        timestamp = now_iso()
        event = ContainerKilledEvent(
            type="container_recovery.killed",
            timestamp=timestamp,
            source="container_recovery",
            container_id="container-abc123",
            container_name="agent-run-123",
            project_id="proj-456",
            agent_id="agent-789",
            work_item_id="issue-123",
            kill_reason="container_timeout",
            uptime_seconds=7200.5,
            execution_marked_failed=True,
        )

        assert event.container_id == "container-abc123"
        assert event.container_name == "agent-run-123"
        assert event.project_id == "proj-456"
        assert event.agent_id == "agent-789"
        assert event.work_item_id == "issue-123"
        assert event.kill_reason == "container_timeout"
        assert event.uptime_seconds == 7200.5
        assert event.execution_marked_failed is True

    def test_optional_metadata(self):
        """Test that metadata fields are optional."""
        event = ContainerKilledEvent(
            type="container_recovery.killed",
            timestamp=now_iso(),
            source="container_recovery",
            container_id="container-abc123",
            container_name="agent-run-123",
            kill_reason="unmanaged",
            uptime_seconds=1000.0,
        )

        assert event.project_id is None
        assert event.agent_id is None
        assert event.work_item_id is None

    def test_missing_container_id(self):
        """Test that container_id is required."""
        with pytest.raises(ValueError, match="container_id"):
            ContainerKilledEvent(
                type="container_recovery.killed",
                timestamp=now_iso(),
                source="container_recovery",
                container_id="",
                container_name="agent-run-123",
                kill_reason="unmanaged",
                uptime_seconds=1000.0,
            )

    def test_missing_container_name(self):
        """Test that container_name is required."""
        with pytest.raises(ValueError, match="container_name"):
            ContainerKilledEvent(
                type="container_recovery.killed",
                timestamp=now_iso(),
                source="container_recovery",
                container_id="container-abc123",
                container_name="",
                kill_reason="unmanaged",
                uptime_seconds=1000.0,
            )

    def test_negative_uptime(self):
        """Test that uptime_seconds must be >= 0."""
        with pytest.raises(ValueError, match="uptime_seconds"):
            ContainerKilledEvent(
                type="container_recovery.killed",
                timestamp=now_iso(),
                source="container_recovery",
                container_id="container-abc123",
                container_name="agent-run-123",
                kill_reason="unmanaged",
                uptime_seconds=-1.0,
            )

    def test_invalid_kill_reason(self):
        """Test that kill_reason must be valid."""
        with pytest.raises(ValueError, match="kill_reason"):
            ContainerKilledEvent(
                type="container_recovery.killed",
                timestamp=now_iso(),
                source="container_recovery",
                container_id="container-abc123",
                container_name="agent-run-123",
                kill_reason="invalid_reason",  # type: ignore
                uptime_seconds=1000.0,
            )

    def test_all_kill_reasons(self):
        """Test all valid kill reasons."""
        valid_reasons = [
            "container_timeout",
            "agent_mismatch",
            "no_execution_found",
            "unmanaged",
            "incomplete_metadata",
        ]

        for reason in valid_reasons:
            event = ContainerKilledEvent(
                type="container_recovery.killed",
                timestamp=now_iso(),
                source="container_recovery",
                container_id="container-abc123",
                container_name="agent-run-123",
                kill_reason=reason,  # type: ignore
                uptime_seconds=1000.0,
            )
            assert event.kill_reason == reason

    def test_immutability(self):
        """Test that ContainerKilledEvent is immutable."""
        event = ContainerKilledEvent(
            type="container_recovery.killed",
            timestamp=now_iso(),
            source="container_recovery",
            container_id="container-abc123",
            container_name="agent-run-123",
            kill_reason="unmanaged",
            uptime_seconds=1000.0,
        )

        with pytest.raises(FrozenInstanceError):
            event.kill_reason = "container_timeout"  # type: ignore

    def test_serialization(self):
        """Test ContainerKilledEvent serialization."""
        timestamp = now_iso()
        event = ContainerKilledEvent(
            type="container_recovery.killed",
            timestamp=timestamp,
            source="container_recovery",
            container_id="container-abc123",
            container_name="agent-run-123",
            project_id="proj-456",
            agent_id="agent-789",
            work_item_id="issue-123",
            kill_reason="container_timeout",
            uptime_seconds=7200.5,
            execution_marked_failed=True,
        )

        d = event.to_dict()
        assert d["type"] == "container_recovery.killed"
        assert d["container_id"] == "container-abc123"
        assert d["container_name"] == "agent-run-123"
        assert d["project_id"] == "proj-456"
        assert d["agent_id"] == "agent-789"
        assert d["work_item_id"] == "issue-123"
        assert d["kill_reason"] == "container_timeout"
        assert d["uptime_seconds"] == 7200.5
        assert d["execution_marked_failed"] is True

    def test_deserialization(self):
        """Test ContainerKilledEvent deserialization."""
        timestamp = now_iso()
        d = {
            "type": "container_recovery.killed",
            "timestamp": timestamp,
            "source": "container_recovery",
            "container_id": "container-abc123",
            "container_name": "agent-run-123",
            "project_id": "proj-456",
            "agent_id": "agent-789",
            "work_item_id": "issue-123",
            "kill_reason": "container_timeout",
            "uptime_seconds": 7200.5,
            "execution_marked_failed": True,
        }

        event = ContainerKilledEvent.from_dict(d)
        assert event.container_id == "container-abc123"
        assert event.container_name == "agent-run-123"
        assert event.project_id == "proj-456"
        assert event.agent_id == "agent-789"
        assert event.work_item_id == "issue-123"
        assert event.kill_reason == "container_timeout"
        assert event.uptime_seconds == 7200.5
        assert event.execution_marked_failed is True


class TestContainerRecoveryCompletedEvent:
    """Test ContainerRecoveryCompletedEvent."""

    def test_create_valid_event(self):
        """Test creating a valid container recovery completed event."""
        timestamp = now_iso()
        started_at = now_iso()
        completed_at = now_iso()

        event = ContainerRecoveryCompletedEvent(
            type="container_recovery.completed",
            timestamp=timestamp,
            source="container_recovery",
            containers_recovered=5,
            containers_killed=2,
            errors_encountered=0,
            repair_cycles_processed=3,
            started_at=started_at,
            completed_at=completed_at,
            duration_seconds=120.5,
        )

        assert event.containers_recovered == 5
        assert event.containers_killed == 2
        assert event.errors_encountered == 0
        assert event.repair_cycles_processed == 3
        assert event.started_at == started_at
        assert event.completed_at == completed_at
        assert event.duration_seconds == 120.5

    def test_missing_started_at(self):
        """Test that started_at is required."""
        with pytest.raises(ValueError, match="started_at"):
            ContainerRecoveryCompletedEvent(
                type="container_recovery.completed",
                timestamp=now_iso(),
                source="container_recovery",
                containers_recovered=5,
                containers_killed=2,
                errors_encountered=0,
                repair_cycles_processed=3,
                started_at="",
                completed_at=now_iso(),
                duration_seconds=120.5,
            )

    def test_missing_completed_at(self):
        """Test that completed_at is required."""
        with pytest.raises(ValueError, match="completed_at"):
            ContainerRecoveryCompletedEvent(
                type="container_recovery.completed",
                timestamp=now_iso(),
                source="container_recovery",
                containers_recovered=5,
                containers_killed=2,
                errors_encountered=0,
                repair_cycles_processed=3,
                started_at=now_iso(),
                completed_at="",
                duration_seconds=120.5,
            )

    def test_negative_containers_recovered(self):
        """Test that containers_recovered must be >= 0."""
        with pytest.raises(ValueError, match="containers_recovered"):
            ContainerRecoveryCompletedEvent(
                type="container_recovery.completed",
                timestamp=now_iso(),
                source="container_recovery",
                containers_recovered=-1,
                containers_killed=2,
                errors_encountered=0,
                repair_cycles_processed=3,
                started_at=now_iso(),
                completed_at=now_iso(),
                duration_seconds=120.5,
            )

    def test_negative_containers_killed(self):
        """Test that containers_killed must be >= 0."""
        with pytest.raises(ValueError, match="containers_killed"):
            ContainerRecoveryCompletedEvent(
                type="container_recovery.completed",
                timestamp=now_iso(),
                source="container_recovery",
                containers_recovered=5,
                containers_killed=-1,
                errors_encountered=0,
                repair_cycles_processed=3,
                started_at=now_iso(),
                completed_at=now_iso(),
                duration_seconds=120.5,
            )

    def test_negative_errors_encountered(self):
        """Test that errors_encountered must be >= 0."""
        with pytest.raises(ValueError, match="errors_encountered"):
            ContainerRecoveryCompletedEvent(
                type="container_recovery.completed",
                timestamp=now_iso(),
                source="container_recovery",
                containers_recovered=5,
                containers_killed=2,
                errors_encountered=-1,
                repair_cycles_processed=3,
                started_at=now_iso(),
                completed_at=now_iso(),
                duration_seconds=120.5,
            )

    def test_negative_repair_cycles_processed(self):
        """Test that repair_cycles_processed must be >= 0."""
        with pytest.raises(ValueError, match="repair_cycles_processed"):
            ContainerRecoveryCompletedEvent(
                type="container_recovery.completed",
                timestamp=now_iso(),
                source="container_recovery",
                containers_recovered=5,
                containers_killed=2,
                errors_encountered=0,
                repair_cycles_processed=-1,
                started_at=now_iso(),
                completed_at=now_iso(),
                duration_seconds=120.5,
            )

    def test_negative_duration(self):
        """Test that duration_seconds must be >= 0."""
        with pytest.raises(ValueError, match="duration_seconds"):
            ContainerRecoveryCompletedEvent(
                type="container_recovery.completed",
                timestamp=now_iso(),
                source="container_recovery",
                containers_recovered=5,
                containers_killed=2,
                errors_encountered=0,
                repair_cycles_processed=3,
                started_at=now_iso(),
                completed_at=now_iso(),
                duration_seconds=-1.0,
            )

    def test_immutability(self):
        """Test that ContainerRecoveryCompletedEvent is immutable."""
        event = ContainerRecoveryCompletedEvent(
            type="container_recovery.completed",
            timestamp=now_iso(),
            source="container_recovery",
            containers_recovered=5,
            containers_killed=2,
            errors_encountered=0,
            repair_cycles_processed=3,
            started_at=now_iso(),
            completed_at=now_iso(),
            duration_seconds=120.5,
        )

        with pytest.raises(FrozenInstanceError):
            event.containers_recovered = 10  # type: ignore

    def test_serialization(self):
        """Test ContainerRecoveryCompletedEvent serialization."""
        timestamp = now_iso()
        started_at = now_iso()
        completed_at = now_iso()

        event = ContainerRecoveryCompletedEvent(
            type="container_recovery.completed",
            timestamp=timestamp,
            source="container_recovery",
            containers_recovered=5,
            containers_killed=2,
            errors_encountered=1,
            repair_cycles_processed=3,
            started_at=started_at,
            completed_at=completed_at,
            duration_seconds=120.5,
        )

        d = event.to_dict()
        assert d["type"] == "container_recovery.completed"
        assert d["containers_recovered"] == 5
        assert d["containers_killed"] == 2
        assert d["errors_encountered"] == 1
        assert d["repair_cycles_processed"] == 3
        assert d["started_at"] == started_at
        assert d["completed_at"] == completed_at
        assert d["duration_seconds"] == 120.5

    def test_deserialization(self):
        """Test ContainerRecoveryCompletedEvent deserialization."""
        timestamp = now_iso()
        started_at = now_iso()
        completed_at = now_iso()

        d = {
            "type": "container_recovery.completed",
            "timestamp": timestamp,
            "source": "container_recovery",
            "containers_recovered": 5,
            "containers_killed": 2,
            "errors_encountered": 1,
            "repair_cycles_processed": 3,
            "started_at": started_at,
            "completed_at": completed_at,
            "duration_seconds": 120.5,
        }

        event = ContainerRecoveryCompletedEvent.from_dict(d)
        assert event.containers_recovered == 5
        assert event.containers_killed == 2
        assert event.errors_encountered == 1
        assert event.repair_cycles_processed == 3
        assert event.started_at == started_at
        assert event.completed_at == completed_at
        assert event.duration_seconds == 120.5
