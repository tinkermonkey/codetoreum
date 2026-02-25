"""Pipeline Stage entity and value objects."""

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import Any

from codetoreum.domain.exceptions import DomainError


class StageStatus(Enum):
    """Status enumeration for pipeline stages."""

    PENDING = "pending"
    READY = "ready"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


class StageType(Enum):
    """Type of pipeline stage."""

    SEQUENTIAL = "sequential"
    PARALLEL = "parallel"
    REVIEW = "review"


@dataclass
class PipelineStage:
    """
    Pipeline Stage entity.

    Represents a stage in a workflow pipeline with dependencies and execution tracking.
    """

    # Identity
    id: str
    name: str
    workflow_id: str

    # Configuration
    stage_type: StageType
    agent_config: dict[str, Any]
    description: str

    # Dependencies
    dependencies: list[str]
    is_parallel: bool

    # Review configuration (if stage_type == REVIEW)
    maker_agent_id: str | None
    reviewer_agent_id: str | None
    max_review_iterations: int

    # Status
    status: StageStatus

    # Execution tracking
    execution_id: str | None
    started_at: datetime | None
    completed_at: datetime | None

    # Results
    output: str | None
    error_message: str | None

    # Metadata
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def create(
        cls,
        name: str,
        workflow_id: str,
        agent_config: dict[str, Any],
        stage_type: StageType = StageType.SEQUENTIAL,
        description: str = "",
        dependencies: list[str] | None = None,
        is_parallel: bool = False,
        maker_agent_id: str | None = None,
        reviewer_agent_id: str | None = None,
        max_review_iterations: int = 3,
        id: str | None = None,
    ) -> "PipelineStage":
        """
        Create new pipeline stage.

        Args:
            name: Stage name/identifier
            workflow_id: ID of parent workflow
            agent_config: Configuration for agent execution (agent_id, capabilities, etc.)
            stage_type: Type of stage (default: SEQUENTIAL)
            description: Stage description (default: "")
            dependencies: List of stage names this depends on (default: [])
            is_parallel: Whether stage can run in parallel (default: False)
            maker_agent_id: ID of maker agent for review stages (default: None)
            reviewer_agent_id: ID of reviewer agent for review stages (default: None)
            max_review_iterations: Maximum review iterations (default: 3)
            id: Stage ID (auto-generated if not provided)

        Returns:
            Newly created PipelineStage instance

        Raises:
            DomainError: If review stage is missing required agents
        """
        from uuid import uuid4

        # Validate review stages
        if stage_type == StageType.REVIEW:
            if not maker_agent_id or not reviewer_agent_id:
                raise DomainError("Review stages require both maker and reviewer agents")
            if maker_agent_id == reviewer_agent_id:
                raise DomainError("Review stages must have different maker and reviewer agents")

        return cls(
            id=id or str(uuid4()),
            name=name,
            workflow_id=workflow_id,
            stage_type=stage_type,
            agent_config=agent_config,
            description=description,
            dependencies=dependencies or [],
            is_parallel=is_parallel,
            maker_agent_id=maker_agent_id,
            reviewer_agent_id=reviewer_agent_id,
            max_review_iterations=max_review_iterations,
            status=StageStatus.PENDING,
            execution_id=None,
            started_at=None,
            completed_at=None,
            output=None,
            error_message=None,
            metadata={},
        )

    def can_enter(self, completed_stages: list[str]) -> bool:
        """
        Check if stage entry conditions are met.

        Business rules:
        - All dependencies must be completed
        - Stage must be in PENDING or READY status

        Args:
            completed_stages: List of completed stage names

        Returns:
            True if stage entry conditions are met, False otherwise
        """
        if self.status not in [StageStatus.PENDING, StageStatus.READY]:
            return False

        return all(dep in completed_stages for dep in self.dependencies)

    def get_agent_for_execution(self) -> dict[str, Any]:
        """
        Get agent configuration for execution.

        Returns appropriate agent config based on stage type:
        - SEQUENTIAL/PARALLEL: Return agent_config
        - REVIEW: Return maker_agent configuration

        Returns:
            Agent configuration dictionary with agent_id and other settings

        Raises:
            DomainError: If review stage is missing maker agent
        """
        if self.stage_type == StageType.REVIEW:
            if not self.maker_agent_id:
                raise DomainError(f"Review stage {self.name} is missing maker agent")
            return {
                **self.agent_config,
                "agent_id": self.maker_agent_id,
                "stage_type": "review_maker",
            }

        return self.agent_config

    def mark_ready(self) -> None:
        """
        Mark stage as ready to execute.

        Raises:
            DomainError: If stage is not in PENDING status
        """
        if self.status != StageStatus.PENDING:
            raise DomainError(
                f"Cannot mark ready: stage in status {self.status.value}"
            )

        self.status = StageStatus.READY

    def start(self, execution_id: str) -> None:
        """
        Start stage execution.

        Args:
            execution_id: ID of the execution

        Raises:
            DomainError: If stage is not in READY status
        """
        if self.status != StageStatus.READY:
            raise DomainError(
                f"Cannot start: stage not ready (status: {self.status.value})"
            )

        self.status = StageStatus.RUNNING
        self.execution_id = execution_id
        self.started_at = datetime.now(UTC)

    def complete(self, output: str) -> None:
        """
        Complete stage successfully.

        Args:
            output: Stage output/result

        Raises:
            DomainError: If stage is not in RUNNING status
        """
        if self.status != StageStatus.RUNNING:
            raise DomainError("Cannot complete: stage not running")

        self.status = StageStatus.COMPLETED
        self.completed_at = datetime.now(UTC)
        self.output = output

    def fail(self, error_message: str) -> None:
        """
        Mark stage as failed.

        Args:
            error_message: Error message describing the failure

        Raises:
            DomainError: If stage is not in READY or RUNNING status
        """
        if self.status not in [StageStatus.READY, StageStatus.RUNNING]:
            raise DomainError(f"Cannot fail: invalid status {self.status.value}")

        self.status = StageStatus.FAILED
        self.completed_at = datetime.now(UTC)
        self.error_message = error_message

    def skip(self, reason: str) -> None:
        """
        Skip stage execution.

        Args:
            reason: Reason for skipping

        Raises:
            DomainError: If stage is not in PENDING status
        """
        if self.status != StageStatus.PENDING:
            raise DomainError(f"Cannot skip: stage in status {self.status.value}")

        self.status = StageStatus.SKIPPED
        self.metadata["skip_reason"] = reason
        self.completed_at = datetime.now(UTC)

    def is_completed(self) -> bool:
        """
        Check if stage completed successfully.

        Returns:
            True if status is COMPLETED
        """
        return self.status == StageStatus.COMPLETED

    def is_failed(self) -> bool:
        """
        Check if stage failed.

        Returns:
            True if status is FAILED
        """
        return self.status == StageStatus.FAILED

    def is_terminal(self) -> bool:
        """
        Check if stage is in terminal state.

        Returns:
            True if status is COMPLETED, FAILED, or SKIPPED
        """
        return self.status in [
            StageStatus.COMPLETED,
            StageStatus.FAILED,
            StageStatus.SKIPPED,
        ]

    def get_duration_seconds(self) -> float | None:
        """
        Get stage duration in seconds.

        Returns:
            Duration in seconds, or None if not yet started or completed
        """
        if not self.started_at or not self.completed_at:
            return None
        return (self.completed_at - self.started_at).total_seconds()

    def update_status(self, status: str) -> None:
        """
        Update stage status (for workflow use).

        Args:
            status: New status value

        Raises:
            ValueError: If status is not a valid StageStatus value
        """
        self.status = StageStatus(status)
