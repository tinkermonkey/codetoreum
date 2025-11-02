"""Workflow aggregate root and value objects."""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional
from uuid import uuid4

from codetoreum.domain.events import (
    DomainEvent,
    WorkflowCancelled,
    WorkflowCompleted,
    WorkflowCreated,
    WorkflowFailed,
    WorkflowPaused,
    WorkflowResumed,
    WorkflowStageAdvanced,
    WorkflowStageStatusUpdated,
    WorkflowStarted,
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
    stages: List[PipelineStage]
    current_stage_index: int
    completed_stages: List[str]

    # Execution tracking
    started_at: Optional[datetime]
    completed_at: Optional[datetime]
    paused_at: Optional[datetime]

    # Metadata
    metadata: Dict[str, Any]

    # Timestamps
    created_at: datetime
    updated_at: datetime

    # Event tracking
    _events: List[DomainEvent] = field(default_factory=list, init=False, repr=False)
    _version: int = field(default=0, init=False, repr=False)
    _skip_validation: bool = field(default=False, init=False, repr=False)

    def __post_init__(self):
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
            raise DomainError("Workflow must have at least one stage")

        if self._count_parallel_stages() > MAX_PARALLEL_STAGES:
            raise DomainError(f"Cannot exceed {MAX_PARALLEL_STAGES} parallel stages")

        if self._has_circular_dependencies():
            raise DomainError("Workflow has circular stage dependencies")

        if not self._all_dependencies_satisfied():
            raise DomainError("Not all stage dependencies are satisfied")

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
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )

        # Set workflow_id on all stages
        for stage in workflow.stages:
            stage.workflow_id = workflow.id

        event = WorkflowCreated(
            aggregate_id=workflow.id,
            payload={
                "work_item_id": work_item_id,
                "template_id": template.id,
                "project_id": project_id,
                "stage_count": len(workflow.stages),
            },
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
            raise DomainError(f"Cannot start workflow in status {self.status.value}")

        if not self.stages:
            raise DomainError("Cannot start workflow with no stages")

        self.status = WorkflowStatus.RUNNING
        self.started_at = datetime.now(timezone.utc)
        self.updated_at = self.started_at
        self._version += 1

        event = WorkflowStarted(
            aggregate_id=self.id,
            payload={
                "started_at": self.started_at.isoformat(),
                "work_item_id": self.work_item_id,
                "first_stage": self.stages[0].name,
            },
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
            raise DomainError("Cannot advance non-running workflow")

        current_stage = self.get_current_stage()
        if not current_stage.is_completed():
            raise DomainError("Cannot advance: current stage not completed")

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
        self.updated_at = datetime.now(timezone.utc)
        self._version += 1

        event = WorkflowStageAdvanced(
            aggregate_id=self.id,
            payload={
                "from_stage": old_stage,
                "to_stage": new_stage,
                "stage_index": self.current_stage_index,
                "advanced_at": self.updated_at.isoformat(),
            },
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
            raise DomainError(
                f"Cannot complete workflow in status {self.status.value}"
            )

        # Verify all stages completed
        for stage in self.stages:
            if not stage.is_completed():
                raise DomainError(
                    f"Cannot complete: stage {stage.name} not completed"
                )

        self.status = WorkflowStatus.COMPLETED
        self.completed_at = datetime.now(timezone.utc)
        self.updated_at = self.completed_at
        self._version += 1

        event = WorkflowCompleted(
            aggregate_id=self.id,
            payload={
                "completed_at": self.completed_at.isoformat(),
                "work_item_id": self.work_item_id,
                "duration_seconds": (self.completed_at - self.started_at).total_seconds(),
            },
        )
        self._add_event(event)

    def fail(self, reason: str, failed_stage: Optional[str] = None) -> None:
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
            raise DomainError(
                f"Cannot fail workflow in terminal status {self.status.value}"
            )

        self.status = WorkflowStatus.FAILED
        self.updated_at = datetime.now(timezone.utc)
        self._version += 1

        event = WorkflowFailed(
            aggregate_id=self.id,
            payload={
                "failed_at": self.updated_at.isoformat(),
                "reason": reason,
                "failed_stage": failed_stage or self.get_current_stage().name,
                "completed_stages": self.completed_stages,
            },
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
            raise DomainError("Can only pause running workflows")

        self.status = WorkflowStatus.PAUSED
        self.paused_at = datetime.now(timezone.utc)
        self.updated_at = self.paused_at
        self._version += 1

        event = WorkflowPaused(
            aggregate_id=self.id,
            payload={
                "paused_at": self.paused_at.isoformat(),
                "reason": reason,
                "current_stage": self.get_current_stage().name,
            },
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
            raise DomainError("Can only resume paused workflows")

        self.status = WorkflowStatus.RUNNING
        self.updated_at = datetime.now(timezone.utc)
        self._version += 1

        event = WorkflowResumed(
            aggregate_id=self.id,
            payload={
                "resumed_at": self.updated_at.isoformat(),
                "current_stage": self.get_current_stage().name,
            },
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
            raise DomainError(
                f"Cannot cancel workflow in terminal status {self.status.value}"
            )

        self.status = WorkflowStatus.CANCELLED
        self.updated_at = datetime.now(timezone.utc)
        self._version += 1

        event = WorkflowCancelled(
            aggregate_id=self.id,
            payload={
                "cancelled_at": self.updated_at.isoformat(),
                "reason": reason,
                "completed_stages": self.completed_stages,
            },
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
            raise DomainError("Invalid stage index")
        return self.stages[self.current_stage_index]

    def get_stage_by_name(self, name: str) -> Optional[PipelineStage]:
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
            raise DomainError(f"Stage {stage_name} not found")

        old_status = stage.status.value
        stage.update_status(status)
        self.updated_at = datetime.now(timezone.utc)
        self._version += 1

        event = WorkflowStageStatusUpdated(
            aggregate_id=self.id,
            payload={
                "stage_name": stage_name,
                "old_status": old_status,
                "new_status": status,
                "updated_at": self.updated_at.isoformat(),
            },
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

    def get_duration_seconds(self) -> Optional[int]:
        """
        Get workflow duration in seconds.

        Returns:
            Duration in seconds, or None if not started
        """
        if not self.started_at:
            return None

        end_time = self.completed_at or datetime.now(timezone.utc)
        return int((end_time - self.started_at).total_seconds())

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
    def _add_event(self, event: DomainEvent) -> None:
        """
        Add event to pending events list.

        Args:
            event: Domain event to add
        """
        self._events.append(event)

    def get_pending_events(self) -> List[DomainEvent]:
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
    def from_events(cls, events: List[DomainEvent]) -> "Workflow":
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
            raise DomainError("Cannot reconstruct workflow from empty event stream")

        first_event = events[0]
        if not isinstance(first_event, WorkflowCreated):
            raise DomainError("First event must be WorkflowCreated")

        # This is simplified - actual implementation would need to
        # reconstruct stages from template or events
        payload = first_event.payload

        # Create workflow with validation skipped (stages will be empty during reconstruction)
        workflow = cls._create_without_validation(
            id=first_event.aggregate_id,
            work_item_id=payload["work_item_id"],
            template_id=payload["template_id"],
            project_id=payload["project_id"],
            status=WorkflowStatus.PENDING,
            stages=[],  # Would be reconstructed from template or stored in events
            current_stage_index=0,
            completed_stages=[],
            started_at=None,
            completed_at=None,
            paused_at=None,
            metadata={},
            created_at=first_event.occurred_at,
            updated_at=first_event.occurred_at,
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
        stages: List[PipelineStage],
        current_stage_index: int,
        completed_stages: List[str],
        started_at: Optional[datetime],
        completed_at: Optional[datetime],
        paused_at: Optional[datetime],
        metadata: Dict[str, Any],
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

    def _apply_event(self, event: DomainEvent) -> None:
        """
        Apply event to update state.

        Args:
            event: Domain event to apply
        """
        if isinstance(event, WorkflowStarted):
            self.status = WorkflowStatus.RUNNING
            self.started_at = event.occurred_at

        elif isinstance(event, WorkflowStageAdvanced):
            self.current_stage_index = event.payload["stage_index"]
            # Reconstruct completed stages from previous + current
            old_stage = event.payload["from_stage"]
            if old_stage not in self.completed_stages:
                self.completed_stages.append(old_stage)

        elif isinstance(event, WorkflowCompleted):
            self.status = WorkflowStatus.COMPLETED
            self.completed_at = event.occurred_at

        elif isinstance(event, WorkflowFailed):
            self.status = WorkflowStatus.FAILED

        elif isinstance(event, WorkflowPaused):
            self.status = WorkflowStatus.PAUSED
            self.paused_at = event.occurred_at

        elif isinstance(event, WorkflowResumed):
            self.status = WorkflowStatus.RUNNING

        elif isinstance(event, WorkflowCancelled):
            self.status = WorkflowStatus.CANCELLED

        self.updated_at = event.occurred_at
