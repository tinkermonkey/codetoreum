"""Unit tests for ExecutionService container label building.

Tests verify that ExecutionService correctly builds Docker labels for containers
according to the container recovery service requirements.
"""

from datetime import UTC, datetime

import pytest

from codetoreum.application.execution_service import ExecutionService
from codetoreum.domain.agent_execution import AgentExecution
from codetoreum.domain.types import (
    CONTAINER_LABEL_AGENT,
    CONTAINER_LABEL_EXECUTION_ID,
    CONTAINER_LABEL_PROJECT,
    CONTAINER_LABEL_TASK_ID,
    CONTAINER_LABEL_TYPE,
    CONTAINER_LABEL_WORK_ITEM_ID,
    CONTAINER_LABEL_WORKFLOW_RUN_ID,
)
from codetoreum.domain.value_objects import ExecutionContext


class MockEventStore:
    """Mock event store for testing."""

    async def append(self, event) -> None:
        """Append event to store."""


class MockLLMProvider:
    """Mock LLM provider for testing."""


class MockContainer:
    """Mock container adapter for testing."""


class MockStorage:
    """Mock storage adapter for testing."""


class TestExecutionServiceLabelBuilding:
    """Tests for ExecutionService container label building.

    Note on test isolation: These unit tests instantiate AgentExecution directly
    rather than using AgentExecution.create() factory. This is intentional because:
    1. We're testing the label building logic in isolation
    2. The factory creates full persistent state with validation
    3. Direct instantiation is appropriate for unit testing a single method
    4. These tests verify label building, not AgentExecution creation logic
    """

    def setup_method(self):
        """Setup test fixtures."""
        self.event_store = MockEventStore()
        self.llm_provider = MockLLMProvider()
        self.container = MockContainer()
        self.storage = MockStorage()

        self.service = ExecutionService(
            llm_provider=self.llm_provider,
            container=self.container,
            event_store=self.event_store,
            storage=self.storage,
        )

        # Shared execution and context fixtures (can be overridden per test)
        self.execution = AgentExecution(
            id="exec-123",
            agent_id="agent-1",
            work_item_id="work-item-456",
            workflow_id="workflow-789",
            stage_name="analyze",
            status=None,
            prompt="Test prompt",
            model="claude-opus",
            session_id=None,
            container_name="agent-proj-001",
            container_id=None,
            output=None,
            error_message=None,
            exit_code=None,
            input_tokens=0,
            output_tokens=0,
            duration_seconds=None,
            initialized_at=datetime.now(UTC),
            started_at=None,
            completed_at=None,
            metadata={},
        )

        self.context = ExecutionContext(
            work_item_id="work-item-456",
            workflow_id="workflow-789",
            stage_name="analyze",
            agent_id="agent-1",
            model="claude-opus",
            timeout_seconds=300,
            workspace_type="issue",
            branch_name="feature/issue-456",
            discussion_id=None,
            project_id="proj-1",
            repository_url="https://github.com/test/repo",
            tech_stack=("python", "fastapi"),
            filesystem_write_allowed=True,
            can_make_commits=True,
            requires_docker=False,
            mcp_servers=(),
            previous_session_id=None,
            metadata={},
        )

    def test_build_container_labels_includes_all_required_labels(self):
        """Container labels should include all required labels."""
        labels = self.service._build_container_labels(self.execution, self.context)

        # All required labels should be present
        assert CONTAINER_LABEL_TYPE in labels
        assert CONTAINER_LABEL_PROJECT in labels
        assert CONTAINER_LABEL_AGENT in labels
        assert CONTAINER_LABEL_WORK_ITEM_ID in labels
        assert CONTAINER_LABEL_TASK_ID in labels
        assert CONTAINER_LABEL_WORKFLOW_RUN_ID in labels
        assert CONTAINER_LABEL_EXECUTION_ID in labels

    def test_build_container_labels_values_match_execution_context(self):
        """Container label values should match execution and context data."""
        labels = self.service._build_container_labels(self.execution, self.context)

        # Label values should match source data
        assert labels[CONTAINER_LABEL_TYPE] == "agent"
        assert labels[CONTAINER_LABEL_PROJECT] == "proj-1"
        assert labels[CONTAINER_LABEL_AGENT] == "agent-1"
        assert labels[CONTAINER_LABEL_WORK_ITEM_ID] == "work-item-456"
        assert labels[CONTAINER_LABEL_TASK_ID] == "exec-123"
        assert labels[CONTAINER_LABEL_WORKFLOW_RUN_ID] == "workflow-789"
        assert labels[CONTAINER_LABEL_EXECUTION_ID] == "exec-123"

    def test_build_container_labels_returns_dict(self):
        """Container labels should be a dict."""
        labels = self.service._build_container_labels(self.execution, self.context)

        assert isinstance(labels, dict)
        assert all(isinstance(k, str) for k in labels.keys())
        assert all(isinstance(v, str) for v in labels.values())

    def test_build_container_labels_label_count(self):
        """Container labels should include exactly 7 labels."""
        labels = self.service._build_container_labels(self.execution, self.context)

        # Should have exactly 7 labels
        assert len(labels) == 7
