"""Modern frozen dataclass Workflow domain events.

These replace the legacy CodetoreumEvent subclasses in _legacy_domain_aggregate_events.py.
All events use dot-notation type strings and typed fields.
"""

from __future__ import annotations

from dataclasses import dataclass
from uuid import uuid4

from codetoreum.domain.events.adapter_events import CodetoreumEvent


@dataclass(frozen=True)
class WorkflowCreatedEvent(CodetoreumEvent):
    """Emitted when a workflow run is created for a work item.

    Fields:
        workflow_id: Unique workflow run identifier (run_id)
        work_item_id: Work item this workflow processes
        pipeline_id: Pipeline template/config identifier
        stage_name: Initial stage name
        project_id: Project containing the work item
    """

    workflow_id: str = ""
    work_item_id: str = ""
    pipeline_id: str = ""
    stage_name: str = ""
    project_id: str = ""

    def __post_init__(self) -> None:
        super().__post_init__()
        if not self.workflow_id:
            raise ValueError("workflow_id is required")
        if not self.work_item_id:
            raise ValueError("work_item_id is required")

    def to_dict(self) -> dict:
        data = super().to_dict()
        data.update(
            {
                "workflow_id": self.workflow_id,
                "work_item_id": self.work_item_id,
                "pipeline_id": self.pipeline_id,
                "stage_name": self.stage_name,
                "project_id": self.project_id,
            }
        )
        return data

    @classmethod
    def from_dict(cls, data: dict) -> WorkflowCreatedEvent:
        return cls(
            type=data.get("type", "workflow.created"),
            timestamp=data.get("timestamp", ""),
            source=data.get("source", ""),
            correlation_id=data.get("correlation_id"),
            event_id=data.get("event_id") or str(uuid4()),
            workflow_id=data["workflow_id"],
            work_item_id=data["work_item_id"],
            pipeline_id=data.get("pipeline_id", ""),
            stage_name=data.get("stage_name", ""),
            project_id=data.get("project_id", ""),
        )


@dataclass(frozen=True)
class WorkflowStartedEvent(CodetoreumEvent):
    """Emitted when a workflow run begins execution.

    Fields:
        workflow_id: Unique workflow run identifier
        work_item_id: Work item being processed
        stage_name: Current stage name
    """

    workflow_id: str = ""
    work_item_id: str = ""
    stage_name: str = ""

    def __post_init__(self) -> None:
        super().__post_init__()
        if not self.workflow_id:
            raise ValueError("workflow_id is required")
        if not self.work_item_id:
            raise ValueError("work_item_id is required")

    def to_dict(self) -> dict:
        data = super().to_dict()
        data.update(
            {
                "workflow_id": self.workflow_id,
                "work_item_id": self.work_item_id,
                "stage_name": self.stage_name,
            }
        )
        return data

    @classmethod
    def from_dict(cls, data: dict) -> WorkflowStartedEvent:
        return cls(
            type=data.get("type", "workflow.started"),
            timestamp=data.get("timestamp", ""),
            source=data.get("source", ""),
            correlation_id=data.get("correlation_id"),
            event_id=data.get("event_id") or str(uuid4()),
            workflow_id=data["workflow_id"],
            work_item_id=data["work_item_id"],
            stage_name=data.get("stage_name", ""),
        )


@dataclass(frozen=True)
class WorkflowStageAdvancedEvent(CodetoreumEvent):
    """Emitted when a workflow advances to the next stage.

    Fields:
        workflow_id: Unique workflow run identifier
        work_item_id: Work item being processed
        from_stage: Stage transitioned from
        to_stage: Stage transitioned to
    """

    workflow_id: str = ""
    work_item_id: str = ""
    from_stage: str = ""
    to_stage: str = ""

    def __post_init__(self) -> None:
        super().__post_init__()
        if not self.workflow_id:
            raise ValueError("workflow_id is required")
        if not self.work_item_id:
            raise ValueError("work_item_id is required")

    def to_dict(self) -> dict:
        data = super().to_dict()
        data.update(
            {
                "workflow_id": self.workflow_id,
                "work_item_id": self.work_item_id,
                "from_stage": self.from_stage,
                "to_stage": self.to_stage,
            }
        )
        return data

    @classmethod
    def from_dict(cls, data: dict) -> WorkflowStageAdvancedEvent:
        return cls(
            type=data.get("type", "workflow.stage_advanced"),
            timestamp=data.get("timestamp", ""),
            source=data.get("source", ""),
            correlation_id=data.get("correlation_id"),
            event_id=data.get("event_id") or str(uuid4()),
            workflow_id=data["workflow_id"],
            work_item_id=data["work_item_id"],
            from_stage=data.get("from_stage", ""),
            to_stage=data.get("to_stage", ""),
        )


@dataclass(frozen=True)
class WorkflowCompletedEvent(CodetoreumEvent):
    """Emitted when a workflow run completes successfully.

    Fields:
        workflow_id: Unique workflow run identifier
        work_item_id: Work item that was processed
        final_stage: Last stage reached
        completed_at: ISO timestamp of completion
    """

    workflow_id: str = ""
    work_item_id: str = ""
    final_stage: str = ""
    completed_at: str = ""

    def __post_init__(self) -> None:
        super().__post_init__()
        if not self.workflow_id:
            raise ValueError("workflow_id is required")
        if not self.work_item_id:
            raise ValueError("work_item_id is required")

    def to_dict(self) -> dict:
        data = super().to_dict()
        data.update(
            {
                "workflow_id": self.workflow_id,
                "work_item_id": self.work_item_id,
                "final_stage": self.final_stage,
                "completed_at": self.completed_at,
            }
        )
        return data

    @classmethod
    def from_dict(cls, data: dict) -> WorkflowCompletedEvent:
        return cls(
            type=data.get("type", "workflow.completed"),
            timestamp=data.get("timestamp", ""),
            source=data.get("source", ""),
            correlation_id=data.get("correlation_id"),
            event_id=data.get("event_id") or str(uuid4()),
            workflow_id=data["workflow_id"],
            work_item_id=data["work_item_id"],
            final_stage=data.get("final_stage", ""),
            completed_at=data.get("completed_at", ""),
        )


@dataclass(frozen=True)
class WorkflowFailedEvent(CodetoreumEvent):
    """Emitted when a workflow run fails.

    Fields:
        workflow_id: Unique workflow run identifier
        work_item_id: Work item that was being processed
        failed_stage: Stage at which failure occurred
        reason: Human-readable failure reason
        failed_at: ISO timestamp of failure
    """

    workflow_id: str = ""
    work_item_id: str = ""
    failed_stage: str = ""
    reason: str = ""
    failed_at: str = ""

    def __post_init__(self) -> None:
        super().__post_init__()
        if not self.workflow_id:
            raise ValueError("workflow_id is required")
        if not self.work_item_id:
            raise ValueError("work_item_id is required")

    def to_dict(self) -> dict:
        data = super().to_dict()
        data.update(
            {
                "workflow_id": self.workflow_id,
                "work_item_id": self.work_item_id,
                "failed_stage": self.failed_stage,
                "reason": self.reason,
                "failed_at": self.failed_at,
            }
        )
        return data

    @classmethod
    def from_dict(cls, data: dict) -> WorkflowFailedEvent:
        return cls(
            type=data.get("type", "workflow.failed"),
            timestamp=data.get("timestamp", ""),
            source=data.get("source", ""),
            correlation_id=data.get("correlation_id"),
            event_id=data.get("event_id") or str(uuid4()),
            workflow_id=data["workflow_id"],
            work_item_id=data["work_item_id"],
            failed_stage=data.get("failed_stage", ""),
            reason=data.get("reason", ""),
            failed_at=data.get("failed_at", ""),
        )


@dataclass(frozen=True)
class WorkflowCancelledEvent(CodetoreumEvent):
    """Emitted when a workflow run is cancelled.

    Fields:
        workflow_id: Unique workflow run identifier
        work_item_id: Work item that was being processed
        cancelled_stage: Stage at which cancellation occurred
        cancelled_at: ISO timestamp of cancellation
    """

    workflow_id: str = ""
    work_item_id: str = ""
    cancelled_stage: str = ""
    cancelled_at: str = ""

    def __post_init__(self) -> None:
        super().__post_init__()
        if not self.workflow_id:
            raise ValueError("workflow_id is required")
        if not self.work_item_id:
            raise ValueError("work_item_id is required")

    def to_dict(self) -> dict:
        data = super().to_dict()
        data.update(
            {
                "workflow_id": self.workflow_id,
                "work_item_id": self.work_item_id,
                "cancelled_stage": self.cancelled_stage,
                "cancelled_at": self.cancelled_at,
            }
        )
        return data

    @classmethod
    def from_dict(cls, data: dict) -> WorkflowCancelledEvent:
        return cls(
            type=data.get("type", "workflow.cancelled"),
            timestamp=data.get("timestamp", ""),
            source=data.get("source", ""),
            correlation_id=data.get("correlation_id"),
            event_id=data.get("event_id") or str(uuid4()),
            workflow_id=data["workflow_id"],
            work_item_id=data["work_item_id"],
            cancelled_stage=data.get("cancelled_stage", ""),
            cancelled_at=data.get("cancelled_at", ""),
        )


@dataclass(frozen=True)
class WorkflowPausedEvent(CodetoreumEvent):
    """Emitted when a workflow run is paused.

    Fields:
        workflow_id: Unique workflow run identifier
        work_item_id: Work item that was being processed
        paused_stage: Stage at which pause occurred
        paused_at: ISO timestamp of pause
    """

    workflow_id: str = ""
    work_item_id: str = ""
    paused_stage: str = ""
    paused_at: str = ""

    def __post_init__(self) -> None:
        super().__post_init__()
        if not self.workflow_id:
            raise ValueError("workflow_id is required")
        if not self.work_item_id:
            raise ValueError("work_item_id is required")

    def to_dict(self) -> dict:
        data = super().to_dict()
        data.update(
            {
                "workflow_id": self.workflow_id,
                "work_item_id": self.work_item_id,
                "paused_stage": self.paused_stage,
                "paused_at": self.paused_at,
            }
        )
        return data

    @classmethod
    def from_dict(cls, data: dict) -> WorkflowPausedEvent:
        return cls(
            type=data.get("type", "workflow.paused"),
            timestamp=data.get("timestamp", ""),
            source=data.get("source", ""),
            correlation_id=data.get("correlation_id"),
            event_id=data.get("event_id") or str(uuid4()),
            workflow_id=data["workflow_id"],
            work_item_id=data["work_item_id"],
            paused_stage=data.get("paused_stage", ""),
            paused_at=data.get("paused_at", ""),
        )


@dataclass(frozen=True)
class WorkflowResumedEvent(CodetoreumEvent):
    """Emitted when a paused workflow run is resumed.

    Fields:
        workflow_id: Unique workflow run identifier
        work_item_id: Work item being processed
        resumed_stage: Stage at which resumption occurred
        resumed_at: ISO timestamp of resumption
    """

    workflow_id: str = ""
    work_item_id: str = ""
    resumed_stage: str = ""
    resumed_at: str = ""

    def __post_init__(self) -> None:
        super().__post_init__()
        if not self.workflow_id:
            raise ValueError("workflow_id is required")
        if not self.work_item_id:
            raise ValueError("work_item_id is required")

    def to_dict(self) -> dict:
        data = super().to_dict()
        data.update(
            {
                "workflow_id": self.workflow_id,
                "work_item_id": self.work_item_id,
                "resumed_stage": self.resumed_stage,
                "resumed_at": self.resumed_at,
            }
        )
        return data

    @classmethod
    def from_dict(cls, data: dict) -> WorkflowResumedEvent:
        return cls(
            type=data.get("type", "workflow.resumed"),
            timestamp=data.get("timestamp", ""),
            source=data.get("source", ""),
            correlation_id=data.get("correlation_id"),
            event_id=data.get("event_id") or str(uuid4()),
            workflow_id=data["workflow_id"],
            work_item_id=data["work_item_id"],
            resumed_stage=data.get("resumed_stage", ""),
            resumed_at=data.get("resumed_at", ""),
        )


@dataclass(frozen=True)
class WorkflowAttachedEvent(CodetoreumEvent):
    """Emitted when a workflow pipeline is attached to a work item.

    Fields:
        work_item_id: Work item receiving the workflow
        pipeline_id: Pipeline being attached
        workflow_id: Generated workflow run identifier
    """

    work_item_id: str = ""
    pipeline_id: str = ""
    workflow_id: str = ""

    def __post_init__(self) -> None:
        super().__post_init__()
        if not self.work_item_id:
            raise ValueError("work_item_id is required")

    def to_dict(self) -> dict:
        data = super().to_dict()
        data.update(
            {
                "work_item_id": self.work_item_id,
                "pipeline_id": self.pipeline_id,
                "workflow_id": self.workflow_id,
            }
        )
        return data

    @classmethod
    def from_dict(cls, data: dict) -> WorkflowAttachedEvent:
        return cls(
            type=data.get("type", "workflow.attached"),
            timestamp=data.get("timestamp", ""),
            source=data.get("source", ""),
            correlation_id=data.get("correlation_id"),
            event_id=data.get("event_id") or str(uuid4()),
            work_item_id=data["work_item_id"],
            pipeline_id=data.get("pipeline_id", ""),
            workflow_id=data.get("workflow_id", ""),
        )


@dataclass(frozen=True)
class WorkflowBranchSelectedEvent(CodetoreumEvent):
    """Emitted when a git branch is selected for a workflow run.

    Fields:
        workflow_id: Workflow run identifier
        work_item_id: Work item being processed
        branch_name: Name of the selected branch
        is_new_branch: Whether this is a newly created branch
    """

    workflow_id: str = ""
    work_item_id: str = ""
    branch_name: str = ""
    is_new_branch: bool = False

    def __post_init__(self) -> None:
        super().__post_init__()
        if not self.workflow_id:
            raise ValueError("workflow_id is required")
        if not self.work_item_id:
            raise ValueError("work_item_id is required")

    def to_dict(self) -> dict:
        data = super().to_dict()
        data.update(
            {
                "workflow_id": self.workflow_id,
                "work_item_id": self.work_item_id,
                "branch_name": self.branch_name,
                "is_new_branch": self.is_new_branch,
            }
        )
        return data

    @classmethod
    def from_dict(cls, data: dict) -> WorkflowBranchSelectedEvent:
        return cls(
            type=data.get("type", "workflow.branch_selected"),
            timestamp=data.get("timestamp", ""),
            source=data.get("source", ""),
            correlation_id=data.get("correlation_id"),
            event_id=data.get("event_id") or str(uuid4()),
            workflow_id=data["workflow_id"],
            work_item_id=data["work_item_id"],
            branch_name=data.get("branch_name", ""),
            is_new_branch=data.get("is_new_branch", False),
        )


@dataclass(frozen=True)
class WorkflowStageStatusUpdatedEvent(CodetoreumEvent):
    """Emitted when a workflow stage's status is updated.

    Fields:
        workflow_id: Workflow run identifier
        work_item_id: Work item being processed
        stage_name: Name of the stage
        old_status: Previous status value
        new_status: New status value
    """

    workflow_id: str = ""
    work_item_id: str = ""
    stage_name: str = ""
    old_status: str = ""
    new_status: str = ""

    def __post_init__(self) -> None:
        super().__post_init__()
        if not self.workflow_id:
            raise ValueError("workflow_id is required")
        if not self.work_item_id:
            raise ValueError("work_item_id is required")

    def to_dict(self) -> dict:
        data = super().to_dict()
        data.update(
            {
                "workflow_id": self.workflow_id,
                "work_item_id": self.work_item_id,
                "stage_name": self.stage_name,
                "old_status": self.old_status,
                "new_status": self.new_status,
            }
        )
        return data

    @classmethod
    def from_dict(cls, data: dict) -> WorkflowStageStatusUpdatedEvent:
        return cls(
            type=data.get("type", "workflow.stage_status_updated"),
            timestamp=data.get("timestamp", ""),
            source=data.get("source", ""),
            correlation_id=data.get("correlation_id"),
            event_id=data.get("event_id") or str(uuid4()),
            workflow_id=data["workflow_id"],
            work_item_id=data["work_item_id"],
            stage_name=data.get("stage_name", ""),
            old_status=data.get("old_status", ""),
            new_status=data.get("new_status", ""),
        )


@dataclass(frozen=True)
class PipelineStageStartedEvent(CodetoreumEvent):
    """Emitted when a pipeline stage starts."""

    pipeline_id: str = ""
    stage_id: str = ""
    stage_name: str = ""
    started_at: str = ""

    def __post_init__(self) -> None:
        super().__post_init__()
        if not self.pipeline_id:
            raise ValueError("pipeline_id is required")

    def to_dict(self) -> dict:
        d = super().to_dict()
        d.update(
            {
                "pipeline_id": self.pipeline_id,
                "stage_id": self.stage_id,
                "stage_name": self.stage_name,
                "started_at": self.started_at,
            }
        )
        return d

    @classmethod
    def from_dict(cls, data: dict) -> PipelineStageStartedEvent:
        return cls(
            type=data.get("type", "pipeline.stage.started"),
            timestamp=data.get("timestamp", ""),
            source=data.get("source", ""),
            correlation_id=data.get("correlation_id"),
            event_id=data.get("event_id") or str(uuid4()),
            pipeline_id=data.get("pipeline_id", ""),
            stage_id=data.get("stage_id", ""),
            stage_name=data.get("stage_name", ""),
            started_at=data.get("started_at", ""),
        )


@dataclass(frozen=True)
class PipelineStageCompletedEvent(CodetoreumEvent):
    """Emitted when a pipeline stage completes successfully."""

    pipeline_id: str = ""
    stage_id: str = ""
    stage_name: str = ""
    completed_at: str = ""

    def __post_init__(self) -> None:
        super().__post_init__()
        if not self.pipeline_id:
            raise ValueError("pipeline_id is required")

    def to_dict(self) -> dict:
        d = super().to_dict()
        d.update(
            {
                "pipeline_id": self.pipeline_id,
                "stage_id": self.stage_id,
                "stage_name": self.stage_name,
                "completed_at": self.completed_at,
            }
        )
        return d

    @classmethod
    def from_dict(cls, data: dict) -> PipelineStageCompletedEvent:
        return cls(
            type=data.get("type", "pipeline.stage.completed"),
            timestamp=data.get("timestamp", ""),
            source=data.get("source", ""),
            correlation_id=data.get("correlation_id"),
            event_id=data.get("event_id") or str(uuid4()),
            pipeline_id=data.get("pipeline_id", ""),
            stage_id=data.get("stage_id", ""),
            stage_name=data.get("stage_name", ""),
            completed_at=data.get("completed_at", ""),
        )


@dataclass(frozen=True)
class PipelineStageFailedEvent(CodetoreumEvent):
    """Emitted when a pipeline stage fails."""

    pipeline_id: str = ""
    stage_id: str = ""
    stage_name: str = ""
    error: str = ""

    def __post_init__(self) -> None:
        super().__post_init__()
        if not self.pipeline_id:
            raise ValueError("pipeline_id is required")

    def to_dict(self) -> dict:
        d = super().to_dict()
        d.update(
            {
                "pipeline_id": self.pipeline_id,
                "stage_id": self.stage_id,
                "stage_name": self.stage_name,
                "error": self.error,
            }
        )
        return d

    @classmethod
    def from_dict(cls, data: dict) -> PipelineStageFailedEvent:
        return cls(
            type=data.get("type", "pipeline.stage.failed"),
            timestamp=data.get("timestamp", ""),
            source=data.get("source", ""),
            correlation_id=data.get("correlation_id"),
            event_id=data.get("event_id") or str(uuid4()),
            pipeline_id=data.get("pipeline_id", ""),
            stage_id=data.get("stage_id", ""),
            stage_name=data.get("stage_name", ""),
            error=data.get("error", ""),
        )


@dataclass(frozen=True)
class PipelineCompletedEvent(CodetoreumEvent):
    """Emitted when a pipeline completes successfully."""

    pipeline_id: str = ""
    work_item_id: str = ""
    completed_stages: tuple = ()
    completed_at: str = ""

    def __post_init__(self) -> None:
        super().__post_init__()
        if not self.pipeline_id:
            raise ValueError("pipeline_id is required")
        object.__setattr__(self, "completed_stages", tuple(self.completed_stages))

    def to_dict(self) -> dict:
        d = super().to_dict()
        d.update(
            {
                "pipeline_id": self.pipeline_id,
                "work_item_id": self.work_item_id,
                "completed_stages": list(self.completed_stages),
                "completed_at": self.completed_at,
            }
        )
        return d

    @classmethod
    def from_dict(cls, data: dict) -> PipelineCompletedEvent:
        return cls(
            type=data.get("type", "pipeline.completed"),
            timestamp=data.get("timestamp", ""),
            source=data.get("source", ""),
            correlation_id=data.get("correlation_id"),
            event_id=data.get("event_id") or str(uuid4()),
            pipeline_id=data.get("pipeline_id", ""),
            work_item_id=data.get("work_item_id", ""),
            completed_stages=tuple(data.get("completed_stages", [])),
            completed_at=data.get("completed_at", ""),
        )


@dataclass(frozen=True)
class PipelineFailedEvent(CodetoreumEvent):
    """Emitted when a pipeline fails."""

    pipeline_id: str = ""
    work_item_id: str = ""
    failed_stage: str = ""
    error: str = ""
    completed_stages: tuple = ()

    def __post_init__(self) -> None:
        super().__post_init__()
        if not self.pipeline_id:
            raise ValueError("pipeline_id is required")
        object.__setattr__(self, "completed_stages", tuple(self.completed_stages))

    def to_dict(self) -> dict:
        d = super().to_dict()
        d.update(
            {
                "pipeline_id": self.pipeline_id,
                "work_item_id": self.work_item_id,
                "failed_stage": self.failed_stage,
                "error": self.error,
                "completed_stages": list(self.completed_stages),
            }
        )
        return d

    @classmethod
    def from_dict(cls, data: dict) -> PipelineFailedEvent:
        return cls(
            type=data.get("type", "pipeline.failed"),
            timestamp=data.get("timestamp", ""),
            source=data.get("source", ""),
            correlation_id=data.get("correlation_id"),
            event_id=data.get("event_id") or str(uuid4()),
            pipeline_id=data.get("pipeline_id", ""),
            work_item_id=data.get("work_item_id", ""),
            failed_stage=data.get("failed_stage", ""),
            error=data.get("error", ""),
            completed_stages=tuple(data.get("completed_stages", [])),
        )
