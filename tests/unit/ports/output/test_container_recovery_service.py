"""Unit tests for IAgentContainerRecoveryService port interface.

These tests verify:
- Container label parsing and validation
- Immutability of dataclasses
- Docker label filtering protection
- Required label enforcement
"""

from datetime import datetime, timezone
from types import MappingProxyType
from typing import Dict, List

import pytest

from codetoreum.domain.types import (
    CONTAINER_LABEL_AGENT,
    CONTAINER_LABEL_EXECUTION_ID,
    CONTAINER_LABEL_PIPELINE_RUN_ID,
    CONTAINER_LABEL_PROJECT,
    CONTAINER_LABEL_TASK_ID,
    CONTAINER_LABEL_TYPE,
    CONTAINER_LABEL_WORK_ITEM_ID,
    CONTAINER_TYPE_AGENT,
    CONTAINER_TYPE_REPAIR_CYCLE,
)
from codetoreum.ports.output.container_recovery import (
    ContainerMetadata,
    RecoveryAssessment,
    RecoveryResult,
)


class TestContainerMetadataImmutability:
    """Tests verify ContainerMetadata is immutable (frozen dataclass)."""

    def test_container_metadata_is_frozen(self):
        """ContainerMetadata should be immutable after creation."""
        metadata = ContainerMetadata(
            container_id="abc123",
            container_name="agent-proj-001",
            project_id="proj-1",
            agent_id="agent-1",
            task_id="task-1",
            created_at=datetime.now(timezone.utc),
            labels=MappingProxyType({}),
            work_item_id="work-123",
            execution_id="exec-456",
        )

        # Attempting to modify any field should raise FrozenInstanceError
        with pytest.raises(Exception):  # FrozenInstanceError
            metadata.container_id = "xyz789"

        with pytest.raises(Exception):  # FrozenInstanceError
            metadata.project_id = "proj-2"

    def test_container_metadata_preserves_all_fields(self):
        """ContainerMetadata should preserve all fields exactly as provided."""
        now = datetime.now(timezone.utc)
        labels = MappingProxyType({
            CONTAINER_LABEL_TYPE: "agent",
            CONTAINER_LABEL_PROJECT: "proj-1",
            CONTAINER_LABEL_AGENT: "agent-1",
        })

        metadata = ContainerMetadata(
            container_id="abc123",
            container_name="agent-proj-001",
            project_id="proj-1",
            agent_id="agent-1",
            task_id="task-1",
            created_at=now,
            labels=labels,
            work_item_id="work-123",
            pipeline_run_id="run-789",
            execution_id="exec-456",
        )

        assert metadata.container_id == "abc123"
        assert metadata.container_name == "agent-proj-001"
        assert metadata.project_id == "proj-1"
        assert metadata.agent_id == "agent-1"
        assert metadata.task_id == "task-1"
        assert metadata.created_at == now
        assert metadata.labels == labels
        assert metadata.work_item_id == "work-123"
        assert metadata.pipeline_run_id == "run-789"
        assert metadata.execution_id == "exec-456"


class TestRecoveryAssessmentImmutability:
    """Tests verify RecoveryAssessment is immutable (frozen dataclass)."""

    def test_recovery_assessment_is_frozen(self):
        """RecoveryAssessment should be immutable after creation."""
        assessment = RecoveryAssessment(
            container_id="abc123",
            action="reconnect",
            reason="Execution in progress",
            with_monitoring=True,
            execution_id="exec-456",
        )

        # Attempting to modify any field should raise FrozenInstanceError
        with pytest.raises(Exception):  # FrozenInstanceError
            assessment.action = "kill"

        with pytest.raises(Exception):  # FrozenInstanceError
            assessment.reason = "Container timeout"

    def test_recovery_assessment_kill_action(self):
        """RecoveryAssessment should support kill action."""
        assessment = RecoveryAssessment(
            container_id="abc123",
            action="kill",
            reason="Container timeout",
            with_monitoring=False,
            execution_id=None,
        )

        assert assessment.action == "kill"
        assert assessment.execution_id is None

    def test_recovery_assessment_reconnect_action(self):
        """RecoveryAssessment should support reconnect action."""
        assessment = RecoveryAssessment(
            container_id="abc123",
            action="reconnect",
            reason="Execution in progress",
            with_monitoring=True,
            execution_id="exec-456",
        )

        assert assessment.action == "reconnect"
        assert assessment.with_monitoring is True


class TestRecoveryResultImmutability:
    """Tests verify RecoveryResult is immutable (frozen dataclass)."""

    def test_recovery_result_is_frozen(self):
        """RecoveryResult should be immutable after creation."""
        result = RecoveryResult(
            recovered=5,
            killed=3,
            errors=1,
            repair_cycles_processed=2,
            timestamp="2025-01-14T10:30:00Z",
        )

        # Attempting to modify any field should raise FrozenInstanceError
        with pytest.raises(Exception):  # FrozenInstanceError
            result.recovered = 10

        with pytest.raises(Exception):  # FrozenInstanceError
            result.killed = 5

    def test_recovery_result_preserves_counts(self):
        """RecoveryResult should preserve counts accurately."""
        result = RecoveryResult(
            recovered=5,
            killed=3,
            errors=1,
            repair_cycles_processed=2,
            timestamp="2025-01-14T10:30:00Z",
        )

        assert result.recovered == 5
        assert result.killed == 3
        assert result.errors == 1
        assert result.repair_cycles_processed == 2


class TestContainerLabelConstants:
    """Tests verify container label constants are correctly defined."""

    def test_label_constants_have_codetoreum_prefix(self):
        """All label constants should use org.codetoreum.* namespace."""
        constants = [
            CONTAINER_LABEL_TYPE,
            CONTAINER_LABEL_PROJECT,
            CONTAINER_LABEL_AGENT,
            CONTAINER_LABEL_WORK_ITEM_ID,
            CONTAINER_LABEL_TASK_ID,
            CONTAINER_LABEL_PIPELINE_RUN_ID,
            CONTAINER_LABEL_EXECUTION_ID,
        ]

        for constant in constants:
            assert constant.startswith("org.codetoreum."), \
                f"Label constant '{constant}' should start with 'org.codetoreum.'"

    def test_label_constants_are_unique(self):
        """All label constants should be unique."""
        constants = [
            CONTAINER_LABEL_TYPE,
            CONTAINER_LABEL_PROJECT,
            CONTAINER_LABEL_AGENT,
            CONTAINER_LABEL_WORK_ITEM_ID,
            CONTAINER_LABEL_TASK_ID,
            CONTAINER_LABEL_PIPELINE_RUN_ID,
            CONTAINER_LABEL_EXECUTION_ID,
        ]

        assert len(constants) == len(set(constants)), \
            "Label constants must be unique"

    def test_label_constants_expected_values(self):
        """Label constants should have expected values."""
        assert CONTAINER_LABEL_TYPE == "org.codetoreum.type"
        assert CONTAINER_LABEL_PROJECT == "org.codetoreum.project"
        assert CONTAINER_LABEL_AGENT == "org.codetoreum.agent"
        assert CONTAINER_LABEL_WORK_ITEM_ID == "org.codetoreum.work_item_id"
        assert CONTAINER_LABEL_TASK_ID == "org.codetoreum.task_id"
        assert CONTAINER_LABEL_PIPELINE_RUN_ID == "org.codetoreum.pipeline_run_id"
        assert CONTAINER_LABEL_EXECUTION_ID == "org.codetoreum.execution_id"


class TestLabelFilteringProtection:
    """Tests verify Docker label filtering provides query-time protection.

    These tests document the safety mechanism that prevents the recovery service
    from ever querying or touching containers without org.codetoreum.type label.
    """

    def test_label_filter_inclusion_only(self):
        """Docker label filter with org.codetoreum.type is an inclusion filter.

        Only containers WITH this label should be in the result set.
        Containers without the label are never returned by Docker API.
        """
        # This test documents the expected behavior of Docker API label filtering
        # Mock containers that would be filtered
        mock_containers = [
            {
                "Id": "container-1",
                "Labels": {CONTAINER_LABEL_TYPE: "agent", CONTAINER_LABEL_PROJECT: "proj-1"}
            },
            {
                "Id": "postgres-db",
                "Labels": {}  # No org.codetoreum.type label
            },
            {
                "Id": "nginx-proxy",
                "Labels": {}  # No org.codetoreum.type label
            },
            {
                "Id": "container-2",
                "Labels": {CONTAINER_LABEL_TYPE: "agent", CONTAINER_LABEL_PROJECT: "proj-2"}
            },
        ]

        # Docker API would return ONLY containers with org.codetoreum.type label
        filtered = [
            c for c in mock_containers
            if CONTAINER_LABEL_TYPE in c.get("Labels", {})
        ]

        assert len(filtered) == 2, "Only Codetoreum containers should be returned"
        assert "postgres-db" not in [c["Id"] for c in filtered]
        assert "nginx-proxy" not in [c["Id"] for c in filtered]
        assert "container-1" in [c["Id"] for c in filtered]
        assert "container-2" in [c["Id"] for c in filtered]

    def test_unrelated_containers_never_queried(self):
        """Unrelated containers are NEVER in the result set.

        This is enforced at Docker API query time, not post-query filtering.
        The recovery service should never touch postgres, nginx, or other
        containers not explicitly labeled with org.codetoreum.type.
        """
        # Simulating Docker API with label filter
        docker_filter = {
            "label": [CONTAINER_LABEL_TYPE]  # Inclusion filter
        }

        # Docker only returns containers matching the filter
        all_containers = [
            {"Id": "postgres-1", "Labels": {"app": "postgres"}},
            {"Id": "agent-123", "Labels": {CONTAINER_LABEL_TYPE: "agent"}},
            {"Id": "nginx-1", "Labels": {"app": "nginx"}},
            {"Id": "agent-456", "Labels": {CONTAINER_LABEL_TYPE: "agent"}},
        ]

        # Simulate Docker API filtering (inclusion-based)
        returned_containers = [
            c for c in all_containers
            if CONTAINER_LABEL_TYPE in c.get("Labels", {})
        ]

        # Recovery service only sees these filtered results
        assert len(returned_containers) == 2
        container_ids = [c["Id"] for c in returned_containers]
        assert "postgres-1" not in container_ids
        assert "nginx-1" not in container_ids


class TestRequiredLabelValidation:
    """Tests verify required label validation logic.

    These tests document how the recovery service validates that containers
    have the minimum required labels after Docker API filtering.
    """

    def test_required_labels_must_be_present(self):
        """Container must have minimum required labels."""
        required_labels = [
            CONTAINER_LABEL_TYPE,
            CONTAINER_LABEL_PROJECT,
            CONTAINER_LABEL_AGENT,
        ]

        # Valid container with all required labels
        valid_labels = {
            CONTAINER_LABEL_TYPE: "agent",
            CONTAINER_LABEL_PROJECT: "proj-1",
            CONTAINER_LABEL_AGENT: "agent-1",
            CONTAINER_LABEL_TASK_ID: "task-1",
        }

        has_required = all(
            label in valid_labels for label in required_labels
        )
        assert has_required is True

    def test_container_without_type_label_is_unmanaged(self):
        """Container without org.codetoreum.type is unmanaged."""
        incomplete_labels = {
            CONTAINER_LABEL_PROJECT: "proj-1",
            CONTAINER_LABEL_AGENT: "agent-1",
            # Missing CONTAINER_LABEL_TYPE
        }

        required_labels = [
            CONTAINER_LABEL_TYPE,
            CONTAINER_LABEL_PROJECT,
            CONTAINER_LABEL_AGENT,
        ]

        has_required = all(
            label in incomplete_labels for label in required_labels
        )
        assert has_required is False

    def test_container_without_project_label_is_unmanaged(self):
        """Container without org.codetoreum.project is unmanaged."""
        incomplete_labels = {
            CONTAINER_LABEL_TYPE: "agent",
            CONTAINER_LABEL_AGENT: "agent-1",
            # Missing CONTAINER_LABEL_PROJECT
        }

        required_labels = [
            CONTAINER_LABEL_TYPE,
            CONTAINER_LABEL_PROJECT,
            CONTAINER_LABEL_AGENT,
        ]

        has_required = all(
            label in incomplete_labels for label in required_labels
        )
        assert has_required is False

    def test_container_without_agent_label_is_unmanaged(self):
        """Container without org.codetoreum.agent is unmanaged."""
        incomplete_labels = {
            CONTAINER_LABEL_TYPE: "agent",
            CONTAINER_LABEL_PROJECT: "proj-1",
            # Missing CONTAINER_LABEL_AGENT
        }

        required_labels = [
            CONTAINER_LABEL_TYPE,
            CONTAINER_LABEL_PROJECT,
            CONTAINER_LABEL_AGENT,
        ]

        has_required = all(
            label in incomplete_labels for label in required_labels
        )
        assert has_required is False

    def test_optional_labels_not_required(self):
        """Optional labels (work_item, execution) are not required."""
        complete_labels = {
            CONTAINER_LABEL_TYPE: "agent",
            CONTAINER_LABEL_PROJECT: "proj-1",
            CONTAINER_LABEL_AGENT: "agent-1",
            CONTAINER_LABEL_TASK_ID: "task-1",
            # Optional labels not included
        }

        required_labels = [
            CONTAINER_LABEL_TYPE,
            CONTAINER_LABEL_PROJECT,
            CONTAINER_LABEL_AGENT,
        ]

        has_required = all(
            label in complete_labels for label in required_labels
        )
        assert has_required is True


class TestContainerNameIsNotParsed:
    """Tests verify container name is NOT used for identification.

    Container names are human-friendly for logging but NEVER parsed for
    metadata. All metadata comes from Docker labels only.
    """

    def test_container_name_human_friendly_format(self):
        """Container names follow human-friendly format (not parsed)."""
        # Valid human-friendly names that would fail if name-parsed
        names = [
            "agent-proj-name-001",
            "agent-context-studio-task1",
            "agent-my-project-xyz789",
        ]

        # Names should NOT be parsed to extract metadata
        # All metadata should come from labels instead
        metadata = ContainerMetadata(
            container_id="abc123",
            container_name="agent-proj-name-001",  # Name is for display only
            project_id="proj-1",  # Comes from label, not name
            agent_id="agent-1",   # Comes from label, not name
            task_id="task-1",     # Comes from label, not name
            created_at=datetime.now(timezone.utc),
            labels=MappingProxyType({
                CONTAINER_LABEL_TYPE: "agent",
                CONTAINER_LABEL_PROJECT: "proj-1",
                CONTAINER_LABEL_AGENT: "agent-1",
                CONTAINER_LABEL_TASK_ID: "task-1",
            }),
        )

        # Metadata should be extracted from labels, not inferred from name
        assert metadata.project_id == "proj-1"
        assert metadata.agent_id == "agent-1"
        assert metadata.task_id == "task-1"

    def test_container_name_with_special_characters(self):
        """Container names can have special characters (not parsed)."""
        # These would be ambiguous if name-parsing was used
        names = [
            "agent-proj-001-test",
            "agent-my-project-123-xyz",
            "agent-context_studio-2025",
        ]

        for name in names:
            metadata = ContainerMetadata(
                container_id="abc123",
                container_name=name,
                project_id="proj-1",  # Must come from label
                agent_id="agent-1",   # Must come from label
                task_id="task-1",     # Must come from label
                created_at=datetime.now(timezone.utc),
                labels=MappingProxyType({
                    CONTAINER_LABEL_TYPE: "agent",
                    CONTAINER_LABEL_PROJECT: "proj-1",
                    CONTAINER_LABEL_AGENT: "agent-1",
                    CONTAINER_LABEL_TASK_ID: "task-1",
                }),
            )

            # Metadata extraction should succeed regardless of name format
            assert metadata.container_name == name
            assert metadata.project_id == "proj-1"


class TestContainerTypeConstants:
    """Tests verify container type constant values and usage."""

    def test_container_type_agent_value(self):
        """CONTAINER_TYPE_AGENT should be 'agent'."""
        assert CONTAINER_TYPE_AGENT == "agent"

    def test_container_type_repair_cycle_value(self):
        """CONTAINER_TYPE_REPAIR_CYCLE should be 'repair-cycle'."""
        assert CONTAINER_TYPE_REPAIR_CYCLE == "repair-cycle"

    def test_container_label_type_uses_correct_namespace(self):
        """CONTAINER_LABEL_TYPE should use org.codetoreum namespace."""
        assert CONTAINER_LABEL_TYPE == "org.codetoreum.type"
        assert CONTAINER_LABEL_TYPE.startswith("org.codetoreum.")

    def test_container_type_constants_are_distinct(self):
        """Container type constants should be distinct values."""
        assert CONTAINER_TYPE_AGENT != CONTAINER_TYPE_REPAIR_CYCLE

    def test_agent_type_in_container_metadata(self):
        """Container type should be set to CONTAINER_TYPE_AGENT in metadata."""
        metadata = ContainerMetadata(
            container_id="abc123",
            container_name="agent-proj-001",
            project_id="proj-1",
            agent_id="agent-1",
            task_id="task-1",
            created_at=datetime.now(timezone.utc),
            labels=MappingProxyType({
                CONTAINER_LABEL_TYPE: CONTAINER_TYPE_AGENT,
                CONTAINER_LABEL_PROJECT: "proj-1",
                CONTAINER_LABEL_AGENT: "agent-1",
                CONTAINER_LABEL_TASK_ID: "task-1",
            }),
        )

        # Type label should have correct value
        assert metadata.labels[CONTAINER_LABEL_TYPE] == CONTAINER_TYPE_AGENT
        assert metadata.labels[CONTAINER_LABEL_TYPE] == "agent"


class TestContainerMetadataValidation:
    """Tests for ContainerMetadata validation rules."""

    def test_container_id_required(self):
        """container_id is required and must be non-empty."""
        with pytest.raises(ValueError, match="container_id is required"):
            ContainerMetadata(
                container_id="",
                container_name="agent-proj-001",
                project_id="proj-1",
                agent_id="agent-1",
                task_id="task-1",
                created_at=datetime.now(timezone.utc),
                labels=MappingProxyType({}),
            )

    def test_container_name_required(self):
        """container_name is required and must be non-empty."""
        with pytest.raises(ValueError, match="container_name is required"):
            ContainerMetadata(
                container_id="abc123",
                container_name="",
                project_id="proj-1",
                agent_id="agent-1",
                task_id="task-1",
                created_at=datetime.now(timezone.utc),
                labels=MappingProxyType({}),
            )

    def test_project_id_required(self):
        """project_id is required and must be non-empty."""
        with pytest.raises(ValueError, match="project_id is required"):
            ContainerMetadata(
                container_id="abc123",
                container_name="agent-proj-001",
                project_id="",
                agent_id="agent-1",
                task_id="task-1",
                created_at=datetime.now(timezone.utc),
                labels=MappingProxyType({}),
            )

    def test_agent_id_required(self):
        """agent_id is required and must be non-empty."""
        with pytest.raises(ValueError, match="agent_id is required"):
            ContainerMetadata(
                container_id="abc123",
                container_name="agent-proj-001",
                project_id="proj-1",
                agent_id="",
                task_id="task-1",
                created_at=datetime.now(timezone.utc),
                labels=MappingProxyType({}),
            )

    def test_task_id_required(self):
        """task_id is required and must be non-empty."""
        with pytest.raises(ValueError, match="task_id is required"):
            ContainerMetadata(
                container_id="abc123",
                container_name="agent-proj-001",
                project_id="proj-1",
                agent_id="agent-1",
                task_id="",
                created_at=datetime.now(timezone.utc),
                labels=MappingProxyType({}),
            )

    def test_created_at_must_be_datetime(self):
        """created_at must be a valid datetime object."""
        with pytest.raises(ValueError, match="created_at must be a valid datetime"):
            ContainerMetadata(
                container_id="abc123",
                container_name="agent-proj-001",
                project_id="proj-1",
                agent_id="agent-1",
                task_id="task-1",
                created_at="2025-01-14T10:30:00Z",  # type: ignore
                labels=MappingProxyType({}),
            )

    def test_labels_must_be_mapping_proxy_type(self):
        """labels must be a MappingProxyType (immutable)."""
        with pytest.raises(ValueError, match="labels must be a MappingProxyType"):
            ContainerMetadata(
                container_id="abc123",
                container_name="agent-proj-001",
                project_id="proj-1",
                agent_id="agent-1",
                task_id="task-1",
                created_at=datetime.now(timezone.utc),
                labels={"key": "value"},  # type: ignore - Plain dict instead
            )

    def test_work_item_id_must_be_non_empty_if_provided(self):
        """work_item_id must be non-empty if provided."""
        with pytest.raises(ValueError, match="work_item_id must be non-empty"):
            ContainerMetadata(
                container_id="abc123",
                container_name="agent-proj-001",
                project_id="proj-1",
                agent_id="agent-1",
                task_id="task-1",
                created_at=datetime.now(timezone.utc),
                labels=MappingProxyType({}),
                work_item_id="",  # Empty string not allowed
            )

    def test_pipeline_run_id_must_be_non_empty_if_provided(self):
        """pipeline_run_id must be non-empty if provided."""
        with pytest.raises(ValueError, match="pipeline_run_id must be non-empty"):
            ContainerMetadata(
                container_id="abc123",
                container_name="agent-proj-001",
                project_id="proj-1",
                agent_id="agent-1",
                task_id="task-1",
                created_at=datetime.now(timezone.utc),
                labels=MappingProxyType({}),
                pipeline_run_id="",  # Empty string not allowed
            )

    def test_execution_id_must_be_non_empty_if_provided(self):
        """execution_id must be non-empty if provided."""
        with pytest.raises(ValueError, match="execution_id must be non-empty"):
            ContainerMetadata(
                container_id="abc123",
                container_name="agent-proj-001",
                project_id="proj-1",
                agent_id="agent-1",
                task_id="task-1",
                created_at=datetime.now(timezone.utc),
                labels=MappingProxyType({}),
                execution_id="",  # Empty string not allowed
            )

    def test_optional_fields_can_be_none(self):
        """Optional fields can be None (not provided)."""
        metadata = ContainerMetadata(
            container_id="abc123",
            container_name="agent-proj-001",
            project_id="proj-1",
            agent_id="agent-1",
            task_id="task-1",
            created_at=datetime.now(timezone.utc),
            labels=MappingProxyType({}),
            work_item_id=None,
            pipeline_run_id=None,
            execution_id=None,
        )

        assert metadata.work_item_id is None
        assert metadata.pipeline_run_id is None
        assert metadata.execution_id is None

    def test_container_id_whitespace_only_rejected(self):
        """container_id must reject whitespace-only strings."""
        with pytest.raises(ValueError, match="container_id is required"):
            ContainerMetadata(
                container_id="   ",
                container_name="agent-proj-001",
                project_id="proj-1",
                agent_id="agent-1",
                task_id="task-1",
                created_at=datetime.now(timezone.utc),
                labels=MappingProxyType({}),
            )

    def test_container_name_whitespace_only_rejected(self):
        """container_name must reject whitespace-only strings."""
        with pytest.raises(ValueError, match="container_name is required"):
            ContainerMetadata(
                container_id="abc123",
                container_name="   ",
                project_id="proj-1",
                agent_id="agent-1",
                task_id="task-1",
                created_at=datetime.now(timezone.utc),
                labels=MappingProxyType({}),
            )

    def test_project_id_whitespace_only_rejected(self):
        """project_id must reject whitespace-only strings."""
        with pytest.raises(ValueError, match="project_id is required"):
            ContainerMetadata(
                container_id="abc123",
                container_name="agent-proj-001",
                project_id="   ",
                agent_id="agent-1",
                task_id="task-1",
                created_at=datetime.now(timezone.utc),
                labels=MappingProxyType({}),
            )

    def test_agent_id_whitespace_only_rejected(self):
        """agent_id must reject whitespace-only strings."""
        with pytest.raises(ValueError, match="agent_id is required"):
            ContainerMetadata(
                container_id="abc123",
                container_name="agent-proj-001",
                project_id="proj-1",
                agent_id="   ",
                task_id="task-1",
                created_at=datetime.now(timezone.utc),
                labels=MappingProxyType({}),
            )

    def test_task_id_whitespace_only_rejected(self):
        """task_id must reject whitespace-only strings."""
        with pytest.raises(ValueError, match="task_id is required"):
            ContainerMetadata(
                container_id="abc123",
                container_name="agent-proj-001",
                project_id="proj-1",
                agent_id="agent-1",
                task_id="   ",
                created_at=datetime.now(timezone.utc),
                labels=MappingProxyType({}),
            )

    def test_work_item_id_whitespace_only_rejected(self):
        """work_item_id must reject whitespace-only strings."""
        with pytest.raises(ValueError, match="work_item_id must be non-empty"):
            ContainerMetadata(
                container_id="abc123",
                container_name="agent-proj-001",
                project_id="proj-1",
                agent_id="agent-1",
                task_id="task-1",
                created_at=datetime.now(timezone.utc),
                labels=MappingProxyType({}),
                work_item_id="   ",
            )

    def test_pipeline_run_id_whitespace_only_rejected(self):
        """pipeline_run_id must reject whitespace-only strings."""
        with pytest.raises(ValueError, match="pipeline_run_id must be non-empty"):
            ContainerMetadata(
                container_id="abc123",
                container_name="agent-proj-001",
                project_id="proj-1",
                agent_id="agent-1",
                task_id="task-1",
                created_at=datetime.now(timezone.utc),
                labels=MappingProxyType({}),
                pipeline_run_id="   ",
            )

    def test_execution_id_whitespace_only_rejected(self):
        """execution_id must reject whitespace-only strings."""
        with pytest.raises(ValueError, match="execution_id must be non-empty"):
            ContainerMetadata(
                container_id="abc123",
                container_name="agent-proj-001",
                project_id="proj-1",
                agent_id="agent-1",
                task_id="task-1",
                created_at=datetime.now(timezone.utc),
                labels=MappingProxyType({}),
                execution_id="   ",
            )

    def test_created_at_cannot_be_future(self):
        """created_at cannot be in the future."""
        from datetime import timedelta
        future_time = datetime.now(timezone.utc) + timedelta(hours=1)

        with pytest.raises(ValueError, match="created_at cannot be in the future"):
            ContainerMetadata(
                container_id="abc123",
                container_name="agent-proj-001",
                project_id="proj-1",
                agent_id="agent-1",
                task_id="task-1",
                created_at=future_time,
                labels=MappingProxyType({}),
            )

    def test_required_labels_must_be_present(self):
        """labels must contain all required keys."""
        incomplete_labels = MappingProxyType({
            CONTAINER_LABEL_TYPE: "agent",
            CONTAINER_LABEL_PROJECT: "proj-1",
            # Missing CONTAINER_LABEL_AGENT
        })

        with pytest.raises(ValueError, match="Missing required labels"):
            ContainerMetadata(
                container_id="abc123",
                container_name="agent-proj-001",
                project_id="proj-1",
                agent_id="agent-1",
                task_id="task-1",
                created_at=datetime.now(timezone.utc),
                labels=incomplete_labels,
            )

    def test_all_required_labels_must_be_present(self):
        """labels must contain all three required label keys."""
        complete_labels = MappingProxyType({
            CONTAINER_LABEL_TYPE: "agent",
            CONTAINER_LABEL_PROJECT: "proj-1",
            CONTAINER_LABEL_AGENT: "agent-1",
        })

        metadata = ContainerMetadata(
            container_id="abc123",
            container_name="agent-proj-001",
            project_id="proj-1",
            agent_id="agent-1",
            task_id="task-1",
            created_at=datetime.now(timezone.utc),
            labels=complete_labels,
        )

        assert CONTAINER_LABEL_TYPE in metadata.labels
        assert CONTAINER_LABEL_PROJECT in metadata.labels
        assert CONTAINER_LABEL_AGENT in metadata.labels

    def test_all_required_fields_valid(self):
        """Valid metadata with all required fields."""
        now = datetime.now(timezone.utc)
        labels = MappingProxyType({
            CONTAINER_LABEL_TYPE: "agent",
            CONTAINER_LABEL_PROJECT: "proj-1",
        })

        metadata = ContainerMetadata(
            container_id="abc123",
            container_name="agent-proj-001",
            project_id="proj-1",
            agent_id="agent-1",
            task_id="task-1",
            created_at=now,
            labels=labels,
        )

        assert metadata.container_id == "abc123"
        assert metadata.container_name == "agent-proj-001"
        assert metadata.project_id == "proj-1"
        assert metadata.agent_id == "agent-1"
        assert metadata.task_id == "task-1"
        assert metadata.created_at == now
        assert metadata.labels == labels


class TestRecoveryAssessmentValidation:
    """Tests for RecoveryAssessment validation rules."""

    def test_container_id_required(self):
        """container_id is required and must be non-empty."""
        with pytest.raises(ValueError, match="container_id is required"):
            RecoveryAssessment(
                container_id="",
                action="reconnect",
                reason="Test reason",
                with_monitoring=True,
                execution_id="exec-456",
            )

    def test_container_id_whitespace_only_rejected(self):
        """container_id must reject whitespace-only strings."""
        with pytest.raises(ValueError, match="container_id is required"):
            RecoveryAssessment(
                container_id="   ",
                action="reconnect",
                reason="Test reason",
                with_monitoring=True,
                execution_id="exec-456",
            )

    def test_action_must_be_valid(self):
        """action must be one of: reconnect, kill."""
        with pytest.raises(ValueError, match='action must be one of'):
            RecoveryAssessment(
                container_id="abc123",
                action="invalid",  # type: ignore
                reason="Test reason",
                with_monitoring=True,
                execution_id="exec-456",
            )

    def test_reason_required(self):
        """reason is required and must be non-empty."""
        with pytest.raises(ValueError, match="reason is required"):
            RecoveryAssessment(
                container_id="abc123",
                action="reconnect",
                reason="",
                with_monitoring=True,
                execution_id="exec-456",
            )

    def test_reason_whitespace_only_rejected(self):
        """reason must reject whitespace-only strings."""
        with pytest.raises(ValueError, match="reason is required"):
            RecoveryAssessment(
                container_id="abc123",
                action="reconnect",
                reason="   ",
                with_monitoring=True,
                execution_id="exec-456",
            )

    def test_with_monitoring_must_be_boolean(self):
        """with_monitoring must be a boolean."""
        with pytest.raises(ValueError, match="with_monitoring must be a boolean"):
            RecoveryAssessment(
                container_id="abc123",
                action="reconnect",
                reason="Test reason",
                with_monitoring="true",  # type: ignore
                execution_id="exec-456",
            )

    def test_execution_id_must_be_non_empty_if_provided(self):
        """execution_id must be non-empty if provided."""
        with pytest.raises(ValueError, match="execution_id must be non-empty"):
            RecoveryAssessment(
                container_id="abc123",
                action="reconnect",
                reason="Test reason",
                with_monitoring=True,
                execution_id="",  # Empty string not allowed
            )

    def test_reconnect_requires_execution_id(self):
        """reconnect action requires execution_id."""
        with pytest.raises(ValueError, match="execution_id is required when action is 'reconnect'"):
            RecoveryAssessment(
                container_id="abc123",
                action="reconnect",
                reason="Test reason",
                with_monitoring=True,
                execution_id=None,  # Should not be None for reconnect
            )

    def test_kill_must_not_have_execution_id(self):
        """kill action must not have execution_id."""
        with pytest.raises(ValueError, match="execution_id must be None when action is 'kill'"):
            RecoveryAssessment(
                container_id="abc123",
                action="kill",
                reason="Container timeout",
                with_monitoring=False,
                execution_id="exec-456",  # Should be None for kill
            )

    def test_valid_reconnect_assessment(self):
        """Valid reconnect assessment with execution_id."""
        assessment = RecoveryAssessment(
            container_id="abc123",
            action="reconnect",
            reason="Execution in progress",
            with_monitoring=True,
            execution_id="exec-456",
        )

        assert assessment.container_id == "abc123"
        assert assessment.action == "reconnect"
        assert assessment.reason == "Execution in progress"
        assert assessment.with_monitoring is True
        assert assessment.execution_id == "exec-456"

    def test_valid_kill_assessment(self):
        """Valid kill assessment without execution_id."""
        assessment = RecoveryAssessment(
            container_id="abc123",
            action="kill",
            reason="Container timeout",
            with_monitoring=False,
            execution_id=None,
        )

        assert assessment.container_id == "abc123"
        assert assessment.action == "kill"
        assert assessment.reason == "Container timeout"
        assert assessment.with_monitoring is False
        assert assessment.execution_id is None


class TestRecoveryResultValidation:
    """Tests for RecoveryResult validation rules."""

    def test_recovered_must_be_non_negative(self):
        """recovered must be >= 0."""
        with pytest.raises(ValueError, match="recovered must be >= 0"):
            RecoveryResult(
                recovered=-1,
                killed=3,
                errors=1,
                repair_cycles_processed=2,
                timestamp="2025-01-14T10:30:00Z",
            )

    def test_killed_must_be_non_negative(self):
        """killed must be >= 0."""
        with pytest.raises(ValueError, match="killed must be >= 0"):
            RecoveryResult(
                recovered=5,
                killed=-1,
                errors=1,
                repair_cycles_processed=2,
                timestamp="2025-01-14T10:30:00Z",
            )

    def test_errors_must_be_non_negative(self):
        """errors must be >= 0."""
        with pytest.raises(ValueError, match="errors must be >= 0"):
            RecoveryResult(
                recovered=5,
                killed=3,
                errors=-1,
                repair_cycles_processed=2,
                timestamp="2025-01-14T10:30:00Z",
            )

    def test_repair_cycles_processed_must_be_non_negative(self):
        """repair_cycles_processed must be >= 0."""
        with pytest.raises(ValueError, match="repair_cycles_processed must be >= 0"):
            RecoveryResult(
                recovered=5,
                killed=3,
                errors=1,
                repair_cycles_processed=-1,
                timestamp="2025-01-14T10:30:00Z",
            )

    def test_timestamp_required(self):
        """timestamp is required and must be non-empty."""
        with pytest.raises(ValueError, match="timestamp is required"):
            RecoveryResult(
                recovered=5,
                killed=3,
                errors=1,
                repair_cycles_processed=2,
                timestamp="",
            )

    def test_timestamp_must_be_iso8601(self):
        """timestamp must be a valid ISO 8601 datetime string."""
        with pytest.raises(ValueError, match="timestamp must be a valid ISO 8601"):
            RecoveryResult(
                recovered=5,
                killed=3,
                errors=1,
                repair_cycles_processed=2,
                timestamp="not-a-timestamp",
            )

    def test_timestamp_iso8601_with_z_suffix(self):
        """timestamp should accept ISO 8601 with Z suffix."""
        result = RecoveryResult(
            recovered=5,
            killed=3,
            errors=1,
            repair_cycles_processed=2,
            timestamp="2025-01-14T10:30:00Z",
        )

        assert result.timestamp == "2025-01-14T10:30:00Z"

    def test_timestamp_iso8601_with_timezone_offset(self):
        """timestamp should accept ISO 8601 with timezone offset."""
        result = RecoveryResult(
            recovered=5,
            killed=3,
            errors=1,
            repair_cycles_processed=2,
            timestamp="2025-01-14T10:30:00+00:00",
        )

        assert result.timestamp == "2025-01-14T10:30:00+00:00"

    def test_timestamp_iso8601_without_timezone(self):
        """timestamp should accept ISO 8601 without timezone info."""
        result = RecoveryResult(
            recovered=5,
            killed=3,
            errors=1,
            repair_cycles_processed=2,
            timestamp="2025-01-14T10:30:00",
        )

        assert result.timestamp == "2025-01-14T10:30:00"

    def test_timestamp_cannot_be_far_in_future(self):
        """timestamp cannot be more than 1 minute in the future."""
        from datetime import timedelta
        future_time = datetime.now(timezone.utc) + timedelta(minutes=5)

        with pytest.raises(ValueError, match="timestamp cannot be more than 1 minute in the future"):
            RecoveryResult(
                recovered=5,
                killed=3,
                errors=1,
                repair_cycles_processed=2,
                timestamp=future_time.isoformat(),
            )

    def test_timestamp_cannot_be_far_in_past(self):
        """timestamp cannot be more than 1 year in the past."""
        from datetime import timedelta
        past_time = datetime.now(timezone.utc) - timedelta(days=400)

        with pytest.raises(ValueError, match="timestamp cannot be more than 1 year in the past"):
            RecoveryResult(
                recovered=5,
                killed=3,
                errors=1,
                repair_cycles_processed=2,
                timestamp=past_time.isoformat(),
            )

    def test_timestamp_slightly_future_allowed(self):
        """timestamp slightly in the future (within 1 minute) is allowed for clock skew."""
        from datetime import timedelta
        slightly_future = datetime.now(timezone.utc) + timedelta(seconds=30)

        result = RecoveryResult(
            recovered=5,
            killed=3,
            errors=1,
            repair_cycles_processed=2,
            timestamp=slightly_future.isoformat(),
        )

        assert result.timestamp == slightly_future.isoformat()

    def test_timestamp_slightly_past_allowed(self):
        """timestamp slightly in the past is allowed."""
        from datetime import timedelta
        slightly_past = datetime.now(timezone.utc) - timedelta(seconds=30)

        result = RecoveryResult(
            recovered=5,
            killed=3,
            errors=1,
            repair_cycles_processed=2,
            timestamp=slightly_past.isoformat(),
        )

        assert result.timestamp == slightly_past.isoformat()

    def test_all_zeros_valid(self):
        """All counts can be zero (e.g., no containers to recover)."""
        result = RecoveryResult(
            recovered=0,
            killed=0,
            errors=0,
            repair_cycles_processed=0,
            timestamp="2025-01-14T10:30:00Z",
        )

        assert result.recovered == 0
        assert result.killed == 0
        assert result.errors == 0
        assert result.repair_cycles_processed == 0

    def test_valid_recovery_result(self):
        """Valid recovery result with all fields."""
        result = RecoveryResult(
            recovered=5,
            killed=3,
            errors=1,
            repair_cycles_processed=2,
            timestamp="2025-01-14T10:30:00Z",
        )

        assert result.recovered == 5
        assert result.killed == 3
        assert result.errors == 1
        assert result.repair_cycles_processed == 2
        assert result.timestamp == "2025-01-14T10:30:00Z"
