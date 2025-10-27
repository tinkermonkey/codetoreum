"""Pipeline Stage entity and value objects."""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional

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
    name: str
    workflow_id: str

    # Configuration
    stage_type: StageType
    agent_id: str
    description: str

    # Dependencies
    dependencies: List[str]
    is_parallel: bool

    # Review configuration (if stage_type == REVIEW)
    requires_review: bool
    maker_agent_id: Optional[str]
    reviewer_agent_id: Optional[str]
    max_review_iterations: int

    # Status
    status: StageStatus

    # Execution tracking
    execution_id: Optional[str]
    started_at: Optional[datetime]
    completed_at: Optional[datetime]

    # Results
    output: Optional[str]
    error_message: Optional[str]

    # Metadata
    metadata: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def create(
        cls,
        name: str,
        workflow_id: str,
        agent_id: str,
        stage_type: StageType = StageType.SEQUENTIAL,
        description: str = "",
        dependencies: Optional[List[str]] = None,
        is_parallel: bool = False,
        requires_review: bool = False,
        maker_agent_id: Optional[str] = None,
        reviewer_agent_id: Optional[str] = None,
        max_review_iterations: int = 3,
    ) -> "PipelineStage":
        """
        Create new pipeline stage.

        Args:
            name: Stage name/identifier
            workflow_id: ID of parent workflow
            agent_id: ID of agent to execute stage
            stage_type: Type of stage (default: SEQUENTIAL)
            description: Stage description (default: "")
            dependencies: List of stage names this depends on (default: [])
            is_parallel: Whether stage can run in parallel (default: False)
            requires_review: Whether stage requires review (default: False)
            maker_agent_id: ID of maker agent for review stages (default: None)
            reviewer_agent_id: ID of reviewer agent for review stages (default: None)
            max_review_iterations: Maximum review iterations (default: 3)

        Returns:
            Newly created PipelineStage instance
        """
        return cls(
            name=name,
            workflow_id=workflow_id,
            stage_type=stage_type,
            agent_id=agent_id,
            description=description,
            dependencies=dependencies or [],
            is_parallel=is_parallel,
            requires_review=requires_review,
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

    def can_start(self, completed_stages: List[str]) -> bool:
        """
        Check if stage can start based on dependencies.

        Business rules:
        - All dependencies must be completed
        - Stage must be in PENDING or READY status

        Args:
            completed_stages: List of completed stage names

        Returns:
            True if stage can start, False otherwise
        """
        if self.status not in [StageStatus.PENDING, StageStatus.READY]:
            return False

        return all(dep in completed_stages for dep in self.dependencies)

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
        self.started_at = datetime.now(timezone.utc)

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
        self.completed_at = datetime.now(timezone.utc)
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
        self.completed_at = datetime.now(timezone.utc)
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
        self.completed_at = datetime.now(timezone.utc)

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

    def get_duration_seconds(self) -> Optional[float]:
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
