"""Workflow aggregate root and value objects."""

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import TYPE_CHECKING, Any
from uuid import uuid4

if TYPE_CHECKING:
    from codetoreum.domain.workflow_template import WorkflowTemplate

from codetoreum.domain.events.workflow_events import (
    WorkflowCancelledEvent,
    WorkflowCompletedEvent,
    WorkflowCreatedEvent,
    WorkflowFailedEvent,
    WorkflowPausedEvent,
    WorkflowResumedEvent,
    WorkflowStageAdvancedEvent,
    WorkflowStageStatusUpdatedEvent,
    WorkflowStartedEvent,
)
from codetoreum.domain.exceptions import DomainError
from codetoreum.domain.pipeline_stage import PipelineStage

# Constants
MAX_PARALLEL_STAGES = 10


class WorkflowStatus(Enum):
    """Status enumeration for workflows."""

    PENDING = "pending"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class Workflow:
    """
    Workflow aggregate root.

    Orchestrates execution of work items through pipeline stages.
    Maintains consistency boundary for workflow execution.
    """

    # Identity
    id: str
    work_item_id: str
    template_id: str
    project_id: str

    # Status
    status: WorkflowStatus

    # Stage tracking
    stages: list[PipelineStage]
    current_stage_index: int
    completed_stages: list[str]

    # Execution tracking
    started_at: datetime | None
    completed_at: datetime | None
    paused_at: datetime | None

    # Metadata
    metadata: dict[str, Any]

    # Timestamps
    created_at: datetime
    updated_at: datetime

    # Event tracking
    _events: list = field(default_factory=list, init=False, repr=False)
    _version: int = field(default=0, init=False, repr=False)
    _skip_validation: bool = field(default=False, init=False, repr=False)

    def __post_init__(self) -> None:
        """Validate invariants after initialization."""
        if not self._skip_validation:
            self._validate_invariants()

    def _validate_invariants(self) -> None:
        """
        Validate domain invariants.

        Invariants:
        - Must have at least one stage
        - Cannot exceed maximum parallel stages
        - Stage dependencies must not create cycles
        - All dependencies must be satisfied
        """
        if len(self.stages) < 1:
            msg = "Workflow must have at least one stage"
            raise DomainError(msg)

        if self._count_parallel_stages() > MAX_PARALLEL_STAGES:
            msg = f"Cannot exceed {MAX_PARALLEL_STAGES} parallel stages"
            raise DomainError(msg)

        if self._has_circular_dependencies():
            msg = "Workflow has circular stage dependencies"
            raise DomainError(msg)

        if not self._all_dependencies_satisfied():
            msg = "Not all stage dependencies are satisfied"
            raise DomainError(msg)

    @classmethod
    def create(
        cls,
        work_item_id: str,
        template: "WorkflowTemplate",
        project_id: str,
    ) -> "Workflow":
        """
        Factory method to create a new workflow from template.

        Args:
            work_item_id: ID of the work item
            template: WorkflowTemplate to instantiate
            project_id: ID of the project

        Returns:
            Newly created Workflow instance

        Emits: WorkflowCreated event
        """
        workflow = cls(
            id=str(uuid4()),
            work_item_id=work_item_id,
            template_id=template.id,
            project_id=project_id,
            status=WorkflowStatus.PENDING,
            stages=template.build_stages(),
            current_stage_index=0,
            completed_stages=[],
            started_at=None,
            completed_at=None,
            paused_at=None,
            metadata={},
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )

        # Set workflow_id on all stages
        for stage in workflow.stages:
            stage.workflow_id = workflow.id

        event = WorkflowCreatedEvent(
            type="workflow.created",
            timestamp=datetime.now(UTC).isoformat(),
            source="workflow",
            workflow_id=workflow.id,
            work_item_id=work_item_id,
            pipeline_id=template.id,
            stage_name=workflow.stages[0].name if workflow.stages else "",
            project_id=project_id,
        )
        workflow._add_event(event)

        return workflow

    # Lifecycle methods
    def start(self) -> None:
        """
        Start workflow execution.

        Business rules:
        - Must be in PENDING status
        - Must have at least one stage

        Raises:
            DomainError: If workflow is not in PENDING status or has no stages

        Emits: WorkflowStarted event
        """
        if self.status != WorkflowStatus.PENDING:
            msg = f"Cannot start workflow in status {self.status.value}"
            raise DomainError(msg)

        if not self.stages:
            msg = "Cannot start workflow with no stages"
            raise DomainError(msg)

        self.status = WorkflowStatus.RUNNING
        self.started_at = datetime.now(UTC)
        self.updated_at = self.started_at
        self._version += 1

        event = WorkflowStartedEvent(
            type="workflow.started",
            timestamp=self.started_at.isoformat(),
            source="workflow",
            workflow_id=self.id,
            work_item_id=self.work_item_id,
            stage_name=self.stages[0].name,
        )
        self._add_event(event)

    def advance_to_next_stage(self) -> None:
        """
        Advance workflow to next stage.

        Business rules:
        - Current stage must be completed
        - Must have remaining stages

        Raises:
            DomainError: If workflow is not running or current stage not completed

        Emits: WorkflowStageAdvanced event (or WorkflowCompleted if last stage)
        """
        if self.status != WorkflowStatus.RUNNING:
            msg = "Cannot advance non-running workflow"
            raise DomainError(msg)

        current_stage = self.get_current_stage()
        if not current_stage.is_completed():
            msg = "Cannot advance: current stage not completed"
            raise DomainError(msg)

        # Mark current stage as completed
        self.completed_stages.append(current_stage.name)

        # Check if workflow is complete
        if self.current_stage_index >= len(self.stages) - 1:
            self.complete()
            return

        # Move to next stage
        old_stage = current_stage.name
        self.current_stage_index += 1
        new_stage = self.get_current_stage().name
        self.updated_at = datetime.now(UTC)
        self._version += 1

        event = WorkflowStageAdvancedEvent(
            type="workflow.stage_advanced",
            timestamp=self.updated_at.isoformat(),
            source="workflow",
            workflow_id=self.id,
            work_item_id=self.work_item_id,
            from_stage=old_stage,
            to_stage=new_stage,
        )
        self._add_event(event)

    def complete(self) -> None:
        """
        Mark workflow as completed.

        Business rules:
        - Must be running
        - All stages must be completed

        Raises:
            DomainError: If workflow is not running or stages not completed

        Emits: WorkflowCompleted event
        """
        if self.status != WorkflowStatus.RUNNING:
            msg = f"Cannot complete workflow in status {self.status.value}"
            raise DomainError(msg)

        # Verify all stages completed
        for stage in self.stages:
            if not stage.is_completed():
                msg = f"Cannot complete: stage {stage.name} not completed"
                raise DomainError(msg)

        self.status = WorkflowStatus.COMPLETED
        self.completed_at = datetime.now(UTC)
        self.updated_at = self.completed_at
        self._version += 1

        event = WorkflowCompletedEvent(
            type="workflow.completed",
            timestamp=self.completed_at.isoformat(),
            source="workflow",
            workflow_id=self.id,
            work_item_id=self.work_item_id,
            final_stage=self.completed_stages[-1] if self.completed_stages else "",
            completed_at=self.completed_at.isoformat(),
        )
        self._add_event(event)

    def fail(self, reason: str, failed_stage: str | None = None) -> None:
        """
        Mark workflow as failed.

        Args:
            reason: Reason for failure
            failed_stage: Name of stage that failed (optional)

        Raises:
            DomainError: If workflow is already in terminal status

        Emits: WorkflowFailed event
        """
        if self.status in [WorkflowStatus.COMPLETED, WorkflowStatus.CANCELLED]:
            msg = f"Cannot fail workflow in terminal status {self.status.value}"
            raise DomainError(msg)

        self.status = WorkflowStatus.FAILED
        self.updated_at = datetime.now(UTC)
        self._version += 1

        event = WorkflowFailedEvent(
            type="workflow.failed",
            timestamp=self.updated_at.isoformat(),
            source="workflow",
            workflow_id=self.id,
            work_item_id=self.work_item_id,
            failed_stage=failed_stage or self.get_current_stage().name,
            reason=reason,
            failed_at=self.updated_at.isoformat(),
        )
        self._add_event(event)

    def pause(self, reason: str) -> None:
        """
        Pause workflow execution.

        Args:
            reason: Reason for pausing

        Raises:
            DomainError: If workflow is not running

        Emits: WorkflowPaused event
        """
        if self.status != WorkflowStatus.RUNNING:
            msg = "Can only pause running workflows"
            raise DomainError(msg)

        self.status = WorkflowStatus.PAUSED
        self.paused_at = datetime.now(UTC)
        self.updated_at = self.paused_at
        self._version += 1

        event = WorkflowPausedEvent(
            type="workflow.paused",
            timestamp=self.paused_at.isoformat(),
            source="workflow",
            workflow_id=self.id,
            work_item_id=self.work_item_id,
            paused_stage=self.get_current_stage().name,
            paused_at=self.paused_at.isoformat(),
        )
        self._add_event(event)

    def resume(self) -> None:
        """
        Resume paused workflow.

        Raises:
            DomainError: If workflow is not paused

        Emits: WorkflowResumed event
        """
        if self.status != WorkflowStatus.PAUSED:
            msg = "Can only resume paused workflows"
            raise DomainError(msg)

        self.status = WorkflowStatus.RUNNING
        self.updated_at = datetime.now(UTC)
        self._version += 1

        event = WorkflowResumedEvent(
            type="workflow.resumed",
            timestamp=self.updated_at.isoformat(),
            source="workflow",
            workflow_id=self.id,
            work_item_id=self.work_item_id,
            resumed_stage=self.get_current_stage().name,
            resumed_at=self.updated_at.isoformat(),
        )
        self._add_event(event)

    def cancel(self, reason: str) -> None:
        """
        Cancel workflow execution.

        Args:
            reason: Reason for cancellation

        Raises:
            DomainError: If workflow is already in terminal status

        Emits: WorkflowCancelled event
        """
        if self.status in [WorkflowStatus.COMPLETED, WorkflowStatus.FAILED]:
            msg = f"Cannot cancel workflow in terminal status {self.status.value}"
            raise DomainError(msg)

        self.status = WorkflowStatus.CANCELLED
        self.updated_at = datetime.now(UTC)
        self._version += 1

        event = WorkflowCancelledEvent(
            type="workflow.cancelled",
            timestamp=self.updated_at.isoformat(),
            source="workflow",
            workflow_id=self.id,
            work_item_id=self.work_item_id,
            cancelled_stage=self.get_current_stage().name if self.stages else "",
            cancelled_at=self.updated_at.isoformat(),
        )
        self._add_event(event)

    # Stage management
    def get_current_stage(self) -> PipelineStage:
        """
        Get the current pipeline stage.

        Returns:
            Current PipelineStage

        Raises:
            DomainError: If stage index is invalid
        """
        if self.current_stage_index >= len(self.stages):
            msg = "Invalid stage index"
            raise DomainError(msg)
        return self.stages[self.current_stage_index]

    def get_stage_by_name(self, name: str) -> PipelineStage | None:
        """
        Get stage by name.

        Args:
            name: Stage name to search for

        Returns:
            PipelineStage if found, None otherwise
        """
        for stage in self.stages:
            if stage.name == name:
                return stage
        return None

    def update_stage_status(self, stage_name: str, status: str) -> None:
        """
        Update status of a specific stage.

        Args:
            stage_name: Name of stage to update
            status: New status value

        Raises:
            DomainError: If stage not found

        Emits: WorkflowStageStatusUpdated event
        """
        stage = self.get_stage_by_name(stage_name)
        if not stage:
            msg = f"Stage {stage_name} not found"
            raise DomainError(msg)

        old_status = stage.status.value
        stage.update_status(status)
        self.updated_at = datetime.now(UTC)
        self._version += 1

        event = WorkflowStageStatusUpdatedEvent(
            type="workflow.stage_status_updated",
            timestamp=self.updated_at.isoformat(),
            source="workflow",
            workflow_id=self.id,
            work_item_id=self.work_item_id,
            stage_name=stage_name,
            old_status=old_status,
            new_status=status,
        )
        self._add_event(event)

    # Query methods
    def is_completed(self) -> bool:
        """
        Check if workflow is completed.

        Returns:
            True if status is COMPLETED
        """
        return self.status == WorkflowStatus.COMPLETED

    def is_failed(self) -> bool:
        """
        Check if workflow has failed.

        Returns:
            True if status is FAILED
        """
        return self.status == WorkflowStatus.FAILED

    def is_running(self) -> bool:
        """
        Check if workflow is currently running.

        Returns:
            True if status is RUNNING
        """
        return self.status == WorkflowStatus.RUNNING

    def get_progress_percentage(self) -> float:
        """
        Calculate workflow completion percentage.

        Returns:
            Progress percentage (0.0 to 100.0)
        """
        if not self.stages:
            return 0.0
        return (len(self.completed_stages) / len(self.stages)) * 100

    def get_duration_seconds(self) -> float | None:
        """
        Get workflow duration in seconds.

        Returns:
            Duration in seconds, or None if not started
        """
        if not self.started_at:
            return None

        end_time = self.completed_at or datetime.now(UTC)
        return (end_time - self.started_at).total_seconds()

    # Validation helpers
    def _count_parallel_stages(self) -> int:
        """
        Count number of parallel stages.

        Returns:
            Number of parallel stages
        """
        return sum(1 for stage in self.stages if stage.is_parallel)

    def _has_circular_dependencies(self) -> bool:
        """
        Check if stage dependencies create a cycle.

        Returns:
            True if circular dependencies exist
        """
        visited = set()
        rec_stack = set()

        def has_cycle(stage_name: str) -> bool:
            visited.add(stage_name)
            rec_stack.add(stage_name)

            stage = self.get_stage_by_name(stage_name)
            if stage:
                for dep in stage.dependencies:
                    if dep not in visited:
                        if has_cycle(dep):
                            return True
                    elif dep in rec_stack:
                        return True

            rec_stack.remove(stage_name)
            return False

        for stage in self.stages:
            if stage.name not in visited:
                if has_cycle(stage.name):
                    return True

        return False

    def _all_dependencies_satisfied(self) -> bool:
        """
        Check if all stage dependencies reference valid stages.

        Returns:
            True if all dependencies are satisfied
        """
        stage_names = {stage.name for stage in self.stages}

        for stage in self.stages:
            for dep in stage.dependencies:
                if dep not in stage_names:
                    return False

        return True

    # Event management
    def _add_event(self, event: object) -> None:
        """
        Add event to pending events list.

        Args:
            event: Domain event to add
        """
        self._events.append(event)

    def get_pending_events(self) -> list:
        """
        Get all pending events.

        Returns:
            Copy of the pending events list
        """
        return self._events.copy()

    def clear_events(self) -> None:
        """Clear pending events (after persistence)."""
        self._events.clear()

    # Event sourcing support
    @classmethod
    def from_events(cls, events: list) -> "Workflow":
        """
        Reconstruct workflow from event stream.

        Args:
            events: List of domain events to replay

        Returns:
            Reconstructed Workflow instance

        Raises:
            DomainError: If events list is empty or first event is not WorkflowCreated

        Note:
            This is a simplified implementation. A production version would need
            to reconstruct stages from template or events.
        """
        if not events:
            msg = "Cannot reconstruct workflow from empty event stream"
            raise DomainError(msg)

        first_event = events[0]
        if not isinstance(first_event, WorkflowCreatedEvent):
            msg = "First event must be WorkflowCreatedEvent"
            raise DomainError(msg)

        # This is simplified - actual implementation would need to
        # reconstruct stages from template or events
        # Create workflow with validation skipped (stages will be empty during reconstruction)
        workflow = cls._create_without_validation(
            id=first_event.workflow_id,
            work_item_id=first_event.work_item_id,
            template_id=first_event.pipeline_id,
            project_id=getattr(first_event, "project_id", ""),
            status=WorkflowStatus.PENDING,
            stages=[],  # Would be reconstructed from template or stored in events
            current_stage_index=0,
            completed_stages=[],
            started_at=None,
            completed_at=None,
            paused_at=None,
            metadata={},
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )

        # Apply subsequent events
        for event in events[1:]:
            workflow._apply_event(event)

        workflow._version = len(events)
        return workflow

    @classmethod
    def _create_without_validation(
        cls,
        id: str,
        work_item_id: str,
        template_id: str,
        project_id: str,
        status: WorkflowStatus,
        stages: list[PipelineStage],
        current_stage_index: int,
        completed_stages: list[str],
        started_at: datetime | None,
        completed_at: datetime | None,
        paused_at: datetime | None,
        metadata: dict[str, Any],
        created_at: datetime,
        updated_at: datetime,
    ) -> "Workflow":
        """
        Private constructor for event sourcing that skips invariant validation.

        Used when reconstructing workflows from events where stages may not yet be loaded.

        Args:
            All workflow properties

        Returns:
            Workflow instance with validation skipped
        """
        # Create instance without calling __init__ or __post_init__
        workflow = object.__new__(cls)
        workflow.id = id
        workflow.work_item_id = work_item_id
        workflow.template_id = template_id
        workflow.project_id = project_id
        workflow.status = status
        workflow.stages = stages
        workflow.current_stage_index = current_stage_index
        workflow.completed_stages = completed_stages
        workflow.started_at = started_at
        workflow.completed_at = completed_at
        workflow.paused_at = paused_at
        workflow.metadata = metadata
        workflow.created_at = created_at
        workflow.updated_at = updated_at
        workflow._events = []
        workflow._version = 0
        workflow._skip_validation = True
        return workflow

    def _apply_event(self, event: object) -> None:
        """
        Apply event to update state.

        Args:
            event: Domain event to apply
        """
        ts = getattr(event, "timestamp", None)
        occurred = datetime.fromisoformat(ts) if ts else datetime.now(UTC)

        if isinstance(event, WorkflowStartedEvent):
            self.status = WorkflowStatus.RUNNING
            self.started_at = occurred

        elif isinstance(event, WorkflowStageAdvancedEvent):
            # Reconstruct completed stages from previous stage
            old_stage = event.from_stage
            if old_stage not in self.completed_stages:
                self.completed_stages.append(old_stage)
            # Advance stage index
            new_stage = event.to_stage
            for idx, stage in enumerate(self.stages):
                if stage.name == new_stage:
                    self.current_stage_index = idx
                    break

        elif isinstance(event, WorkflowCompletedEvent):
            self.status = WorkflowStatus.COMPLETED
            self.completed_at = occurred

        elif isinstance(event, WorkflowFailedEvent):
            self.status = WorkflowStatus.FAILED

        elif isinstance(event, WorkflowPausedEvent):
            self.status = WorkflowStatus.PAUSED
            self.paused_at = occurred

        elif isinstance(event, WorkflowResumedEvent):
            self.status = WorkflowStatus.RUNNING

        elif isinstance(event, WorkflowCancelledEvent):
            self.status = WorkflowStatus.CANCELLED

        self.updated_at = occurred
