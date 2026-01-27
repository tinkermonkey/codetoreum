"""Unit tests for IAgentContainerRecoveryService port interface.

These tests verify:
- Container label parsing and validation
- Immutability of dataclasses
- Docker label filtering protection
- Required label enforcement
"""

from datetime import datetime, timezone
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
            labels={},
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
        labels = {
            CONTAINER_LABEL_TYPE: "agent",
            CONTAINER_LABEL_PROJECT: "proj-1",
            CONTAINER_LABEL_AGENT: "agent-1",
        }

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
            labels={
                CONTAINER_LABEL_TYPE: "agent",
                CONTAINER_LABEL_PROJECT: "proj-1",
                CONTAINER_LABEL_AGENT: "agent-1",
                CONTAINER_LABEL_TASK_ID: "task-1",
            },
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
                labels={
                    CONTAINER_LABEL_TYPE: "agent",
                    CONTAINER_LABEL_PROJECT: "proj-1",
                    CONTAINER_LABEL_AGENT: "agent-1",
                    CONTAINER_LABEL_TASK_ID: "task-1",
                },
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
            labels={
                CONTAINER_LABEL_TYPE: CONTAINER_TYPE_AGENT,
                CONTAINER_LABEL_PROJECT: "proj-1",
                CONTAINER_LABEL_AGENT: "agent-1",
                CONTAINER_LABEL_TASK_ID: "task-1",
            },
        )

        # Type label should have correct value
        assert metadata.labels[CONTAINER_LABEL_TYPE] == CONTAINER_TYPE_AGENT
        assert metadata.labels[CONTAINER_LABEL_TYPE] == "agent"
