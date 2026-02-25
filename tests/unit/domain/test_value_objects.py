"""Unit tests for domain value objects."""

from datetime import UTC, datetime

import pytest

from codetoreum.domain.agent import AgentCapability
from codetoreum.domain.exceptions import DomainError
from codetoreum.domain.value_objects import (
    AgentId,
    ContainerConfig,
    ExecutionContext,
    ExecutionId,
    ExecutionResult,
    Requirement,
    TimeRange,
    TokenUsage,
    WorkflowId,
    WorkItemId,
)

# ============================================================================
# Type-Safe Identifier Tests
# ============================================================================


class TestWorkItemId:
    """Test WorkItemId value object."""

    def test_create_from_string(self):
        """Test creating WorkItemId from string."""
        work_item_id = WorkItemId.from_string("item-123")
        assert work_item_id.value == "item-123"
        assert str(work_item_id) == "item-123"

    def test_generate_unique_id(self):
        """Test generating unique WorkItemId."""
        id1 = WorkItemId.generate()
        id2 = WorkItemId.generate()
        assert id1.value != id2.value

    def test_empty_value_raises_error(self):
        """Test that empty value raises error."""
        with pytest.raises(DomainError, match="WorkItemId cannot be empty"):
            WorkItemId("")

    def test_equality(self):
        """Test value object equality."""
        id1 = WorkItemId.from_string("item-123")
        id2 = WorkItemId.from_string("item-123")
        id3 = WorkItemId.from_string("item-456")
        assert id1 == id2
        assert id1 != id3


class TestWorkflowId:
    """Test WorkflowId value object."""

    def test_create_from_string(self):
        """Test creating WorkflowId from string."""
        workflow_id = WorkflowId.from_string("workflow-123")
        assert workflow_id.value == "workflow-123"
        assert str(workflow_id) == "workflow-123"

    def test_generate_unique_id(self):
        """Test generating unique WorkflowId."""
        id1 = WorkflowId.generate()
        id2 = WorkflowId.generate()
        assert id1.value != id2.value

    def test_empty_value_raises_error(self):
        """Test that empty value raises error."""
        with pytest.raises(DomainError, match="WorkflowId cannot be empty"):
            WorkflowId("")


class TestAgentId:
    """Test AgentId value object."""

    def test_create_from_string(self):
        """Test creating AgentId from string."""
        agent_id = AgentId.from_string("agent-123")
        assert agent_id.value == "agent-123"
        assert str(agent_id) == "agent-123"

    def test_generate_unique_id(self):
        """Test generating unique AgentId."""
        id1 = AgentId.generate()
        id2 = AgentId.generate()
        assert id1.value != id2.value

    def test_empty_value_raises_error(self):
        """Test that empty value raises error."""
        with pytest.raises(DomainError, match="AgentId cannot be empty"):
            AgentId("")


class TestExecutionId:
    """Test ExecutionId value object."""

    def test_create_from_string(self):
        """Test creating ExecutionId from string."""
        execution_id = ExecutionId.from_string("exec-123")
        assert execution_id.value == "exec-123"
        assert str(execution_id) == "exec-123"

    def test_generate_unique_id(self):
        """Test generating unique ExecutionId."""
        id1 = ExecutionId.generate()
        id2 = ExecutionId.generate()
        assert id1.value != id2.value

    def test_empty_value_raises_error(self):
        """Test that empty value raises error."""
        with pytest.raises(DomainError, match="ExecutionId cannot be empty"):
            ExecutionId("")


# ============================================================================
# Requirement Value Object Tests
# ============================================================================


class TestRequirement:
    """Test Requirement value object."""

    def test_create_requirement(self):
        """Test creating a requirement."""
        req = Requirement(skill="python", min_proficiency=0.8)
        assert req.skill == "python"
        assert req.min_proficiency == 0.8
        assert req.is_required is True

    def test_optional_requirement(self):
        """Test creating optional requirement."""
        req = Requirement(skill="rust", min_proficiency=0.5, is_required=False)
        assert req.is_required is False

    def test_invalid_proficiency_raises_error(self):
        """Test that invalid proficiency raises error."""
        with pytest.raises(DomainError, match="Min proficiency must be between"):
            Requirement(skill="python", min_proficiency=1.5)

        with pytest.raises(DomainError, match="Min proficiency must be between"):
            Requirement(skill="python", min_proficiency=-0.1)

    def test_is_satisfied_by_capability(self):
        """Test requirement satisfaction by capability."""
        req = Requirement(skill="python", min_proficiency=0.8)
        cap_high = AgentCapability(skill="python", proficiency=0.9)
        cap_low = AgentCapability(skill="python", proficiency=0.7)
        cap_other = AgentCapability(skill="rust", proficiency=0.9)

        assert req.is_satisfied_by(cap_high)
        assert not req.is_satisfied_by(cap_low)
        assert not req.is_satisfied_by(cap_other)


# ============================================================================
# ExecutionResult Value Object Tests
# ============================================================================


class TestExecutionResult:
    """Test ExecutionResult value object."""

    def test_success_result(self):
        """Test creating successful execution result."""
        result = ExecutionResult.success_result(
            output="Task completed",
            input_tokens=1000,
            output_tokens=500,
            duration_seconds=45.2,
            modified_files=["src/main.py"],
            added_files=["tests/test_main.py"],
            session_id="session-123",
        )

        assert result.success is True
        assert result.exit_code == 0
        assert result.output == "Task completed"
        assert result.error_message is None
        assert result.input_tokens == 1000
        assert result.output_tokens == 500
        assert result.duration_seconds == 45.2
        assert result.modified_files == ["src/main.py"]
        assert result.added_files == ["tests/test_main.py"]
        assert result.deleted_files == []
        assert result.session_id == "session-123"

    def test_failure_result(self):
        """Test creating failed execution result."""
        result = ExecutionResult.failure_result(
            error_message="Compilation failed",
            exit_code=1,
            output="Error: syntax error",
            duration_seconds=12.5,
        )

        assert result.success is False
        assert result.exit_code == 1
        assert result.error_message == "Compilation failed"
        assert result.output == "Error: syntax error"
        assert result.duration_seconds == 12.5
        assert result.session_id is None

    def test_get_total_tokens(self):
        """Test getting total tokens."""
        result = ExecutionResult.success_result(
            output="Done",
            input_tokens=1000,
            output_tokens=500,
            duration_seconds=10.0,
        )
        assert result.get_total_tokens() == 1500

    def test_has_file_changes(self):
        """Test checking for file changes."""
        result_with_changes = ExecutionResult.success_result(
            output="Done",
            input_tokens=100,
            output_tokens=50,
            duration_seconds=10.0,
            modified_files=["a.py"],
        )
        result_no_changes = ExecutionResult.success_result(
            output="Done", input_tokens=100, output_tokens=50, duration_seconds=10.0
        )

        assert result_with_changes.has_file_changes()
        assert not result_no_changes.has_file_changes()

    def test_get_all_affected_files(self):
        """Test getting all affected files."""
        result = ExecutionResult.success_result(
            output="Done",
            input_tokens=100,
            output_tokens=50,
            duration_seconds=10.0,
            modified_files=["a.py", "b.py"],
            added_files=["c.py"],
            deleted_files=["d.py"],
        )

        affected = result.get_all_affected_files()
        assert set(affected) == {"a.py", "b.py", "c.py", "d.py"}

    def test_to_dict(self):
        """Test converting result to dictionary."""
        result = ExecutionResult.success_result(
            output="Done", input_tokens=100, output_tokens=50, duration_seconds=10.0
        )

        result_dict = result.to_dict()
        assert result_dict["success"] is True
        assert result_dict["exit_code"] == 0
        assert result_dict["input_tokens"] == 100
        assert result_dict["output_tokens"] == 50
        assert result_dict["total_tokens"] == 150

    def test_negative_tokens_raises_error(self):
        """Test that negative tokens raise error."""
        with pytest.raises(DomainError, match="Input tokens cannot be negative"):
            ExecutionResult.success_result(
                output="Done",
                input_tokens=-100,
                output_tokens=50,
                duration_seconds=10.0,
            )

    def test_negative_duration_raises_error(self):
        """Test that negative duration raises error."""
        with pytest.raises(DomainError, match="Duration cannot be negative"):
            ExecutionResult.success_result(
                output="Done",
                input_tokens=100,
                output_tokens=50,
                duration_seconds=-10.0,
            )


# ============================================================================
# ContainerConfig Value Object Tests
# ============================================================================


class TestContainerConfig:
    """Test ContainerConfig value object."""

    def test_create_basic_config(self):
        """Test creating basic container config."""
        config = ContainerConfig(image="python:3.11")
        assert config.image == "python:3.11"
        assert config.working_dir == "/workspace"
        assert config.user == "1000:1000"

    def test_create_full_config(self):
        """Test creating full container config."""
        config = ContainerConfig(
            image="python:3.11",
            name="test-container",
            command=["python", "main.py"],
            working_dir="/app",
            user="1001:1001",
            environment={"ENV": "test"},
            volumes={"/host/path": {"bind": "/container/path", "mode": "ro"}},
            detached=True,
        )

        assert config.image == "python:3.11"
        assert config.name == "test-container"
        assert config.command == ["python", "main.py"]
        assert config.working_dir == "/app"
        assert config.user == "1001:1001"
        assert config.environment == {"ENV": "test"}
        assert config.detached is True

    def test_empty_image_raises_error(self):
        """Test that empty image raises error."""
        with pytest.raises(DomainError, match="Container image cannot be empty"):
            ContainerConfig(image="")

    def test_invalid_volume_config_raises_error(self):
        """Test that invalid volume config raises error."""
        with pytest.raises(DomainError, match="must have 'bind'"):
            ContainerConfig(
                image="python:3.11", volumes={"/host": {"mode": "rw"}}  # Missing bind
            )

    def test_invalid_volume_mode_raises_error(self):
        """Test that invalid volume mode raises error."""
        with pytest.raises(DomainError, match="Volume mode must be"):
            ContainerConfig(
                image="python:3.11",
                volumes={"/host": {"bind": "/container", "mode": "invalid"}},
            )

    def test_to_dict(self):
        """Test converting config to dictionary."""
        config = ContainerConfig(
            image="python:3.11",
            name="test",
            environment={"KEY": "value"},
        )

        config_dict = config.to_dict()
        assert config_dict["image"] == "python:3.11"
        assert config_dict["name"] == "test"
        assert config_dict["environment"] == {"KEY": "value"}


# ============================================================================
# ExecutionContext Value Object Tests
# ============================================================================


class TestExecutionContext:
    """Test ExecutionContext value object."""

    def test_create_execution_context(self):
        """Test creating execution context."""
        context = ExecutionContext(
            work_item_id="item-123",
            workflow_id="workflow-123",
            stage_name="development",
            agent_id="agent-123",
            model="claude-sonnet-4-5",
            timeout_seconds=3600,
            workspace_type="branch",
            branch_name="feature/test",
            discussion_id=None,
            project_id="project-123",
            repository_url="https://github.com/org/repo",
            tech_stack=["python", "docker"],
            filesystem_write_allowed=True,
            can_make_commits=False,
            requires_docker=True,
            mcp_servers=["artifacts", "logging"],
            previous_session_id=None,
            metadata={"key": "value"},
        )

        assert context.work_item_id == "item-123"
        assert context.workflow_id == "workflow-123"
        assert context.agent_id == "agent-123"
        assert context.timeout_seconds == 3600
        assert context.tech_stack == ["python", "docker"]

    def test_invalid_timeout_raises_error(self):
        """Test that invalid timeout raises error."""
        with pytest.raises(DomainError, match="Timeout must be positive"):
            ExecutionContext(
                work_item_id="item-123",
                workflow_id="workflow-123",
                stage_name="dev",
                agent_id="agent-123",
                model="claude",
                timeout_seconds=0,  # Invalid
                workspace_type="branch",
                branch_name=None,
                discussion_id=None,
                project_id="proj",
                repository_url="url",
                tech_stack=[],
                filesystem_write_allowed=True,
                can_make_commits=False,
                requires_docker=False,
                mcp_servers=[],
                previous_session_id=None,
                metadata={},
            )

    def test_empty_work_item_id_raises_error(self):
        """Test that empty work item ID raises error."""
        with pytest.raises(DomainError, match="Work item ID cannot be empty"):
            ExecutionContext(
                work_item_id="",  # Invalid
                workflow_id="workflow-123",
                stage_name="dev",
                agent_id="agent-123",
                model="claude",
                timeout_seconds=3600,
                workspace_type="branch",
                branch_name=None,
                discussion_id=None,
                project_id="proj",
                repository_url="url",
                tech_stack=[],
                filesystem_write_allowed=True,
                can_make_commits=False,
                requires_docker=False,
                mcp_servers=[],
                previous_session_id=None,
                metadata={},
            )

    def test_to_dict(self):
        """Test converting context to dictionary."""
        context = ExecutionContext(
            work_item_id="item-123",
            workflow_id="workflow-123",
            stage_name="dev",
            agent_id="agent-123",
            model="claude",
            timeout_seconds=3600,
            workspace_type="branch",
            branch_name="feature",
            discussion_id=None,
            project_id="proj",
            repository_url="url",
            tech_stack=["python"],
            filesystem_write_allowed=True,
            can_make_commits=False,
            requires_docker=True,
            mcp_servers=["artifacts"],
            previous_session_id=None,
            metadata={"key": "value"},
        )

        context_dict = context.to_dict()
        assert context_dict["work_item_id"] == "item-123"
        assert context_dict["timeout_seconds"] == 3600
        assert context_dict["tech_stack"] == ["python"]


# ============================================================================
# TimeRange Value Object Tests
# ============================================================================


class TestTimeRange:
    """Test TimeRange value object."""

    def test_create_time_range(self):
        """Test creating time range."""
        start = datetime(2025, 1, 1, 12, 0, 0, tzinfo=UTC)
        end = datetime(2025, 1, 1, 13, 0, 0, tzinfo=UTC)
        time_range = TimeRange(start=start, end=end)

        assert time_range.start == start
        assert time_range.end == end

    def test_invalid_range_raises_error(self):
        """Test that invalid range raises error."""
        start = datetime(2025, 1, 1, 13, 0, 0, tzinfo=UTC)
        end = datetime(2025, 1, 1, 12, 0, 0, tzinfo=UTC)

        with pytest.raises(DomainError, match="End time must be after start time"):
            TimeRange(start=start, end=end)

    def test_duration_seconds(self):
        """Test calculating duration in seconds."""
        start = datetime(2025, 1, 1, 12, 0, 0, tzinfo=UTC)
        end = datetime(2025, 1, 1, 13, 30, 0, tzinfo=UTC)
        time_range = TimeRange(start=start, end=end)

        assert time_range.duration_seconds() == 5400  # 90 minutes

    def test_contains(self):
        """Test checking if timestamp is within range."""
        start = datetime(2025, 1, 1, 12, 0, 0, tzinfo=UTC)
        end = datetime(2025, 1, 1, 13, 0, 0, tzinfo=UTC)
        time_range = TimeRange(start=start, end=end)

        inside = datetime(2025, 1, 1, 12, 30, 0, tzinfo=UTC)
        outside = datetime(2025, 1, 1, 14, 0, 0, tzinfo=UTC)

        assert time_range.contains(inside)
        assert not time_range.contains(outside)

    def test_overlaps(self):
        """Test checking if ranges overlap."""
        range1 = TimeRange(
            start=datetime(2025, 1, 1, 12, 0, 0, tzinfo=UTC),
            end=datetime(2025, 1, 1, 13, 0, 0, tzinfo=UTC),
        )
        range2 = TimeRange(
            start=datetime(2025, 1, 1, 12, 30, 0, tzinfo=UTC),
            end=datetime(2025, 1, 1, 13, 30, 0, tzinfo=UTC),
        )
        range3 = TimeRange(
            start=datetime(2025, 1, 1, 14, 0, 0, tzinfo=UTC),
            end=datetime(2025, 1, 1, 15, 0, 0, tzinfo=UTC),
        )

        assert range1.overlaps(range2)
        assert not range1.overlaps(range3)


# ============================================================================
# TokenUsage Value Object Tests
# ============================================================================


class TestTokenUsage:
    """Test TokenUsage value object."""

    def test_create_token_usage(self):
        """Test creating token usage."""
        tokens = TokenUsage(input_tokens=1000, output_tokens=500)
        assert tokens.input_tokens == 1000
        assert tokens.output_tokens == 500
        assert tokens.total_tokens == 1500

    def test_negative_tokens_raise_error(self):
        """Test that negative tokens raise error."""
        with pytest.raises(DomainError, match="Token counts cannot be negative"):
            TokenUsage(input_tokens=-100, output_tokens=50)

        with pytest.raises(DomainError, match="Token counts cannot be negative"):
            TokenUsage(input_tokens=100, output_tokens=-50)

    def test_add_token_usage(self):
        """Test adding token usages."""
        tokens1 = TokenUsage(input_tokens=1000, output_tokens=500)
        tokens2 = TokenUsage(input_tokens=2000, output_tokens=1000)

        total = tokens1.add(tokens2)

        assert total.input_tokens == 3000
        assert total.output_tokens == 1500
        assert total.total_tokens == 4500

    def test_to_dict(self):
        """Test converting token usage to dictionary."""
        tokens = TokenUsage(input_tokens=1000, output_tokens=500)
        tokens_dict = tokens.to_dict()

        assert tokens_dict["input_tokens"] == 1000
        assert tokens_dict["output_tokens"] == 500
        assert tokens_dict["total_tokens"] == 1500

    def test_add_returns_new_instance(self):
        """Test that add returns new instance without modifying originals."""
        tokens1 = TokenUsage(input_tokens=1000, output_tokens=500)
        tokens2 = TokenUsage(input_tokens=2000, output_tokens=1000)

        total = tokens1.add(tokens2)

        # Original instances unchanged
        assert tokens1.input_tokens == 1000
        assert tokens2.input_tokens == 2000
        # New instance has sum
        assert total.input_tokens == 3000
