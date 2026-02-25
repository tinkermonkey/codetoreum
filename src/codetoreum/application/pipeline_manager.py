"""Pipeline Manager application service."""

import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import Any, cast

from codetoreum.domain.events import (
    PipelineCompleted,
    PipelineFailed,
    PipelineStageCompleted,
    PipelineStageFailed,
    PipelineStageStarted,
)
from codetoreum.domain.pipeline_stage import PipelineStage, StageStatus
from codetoreum.domain.workflow import Workflow
from codetoreum.ports.output import IEventStore

logger = logging.getLogger(__name__)


# ============================================================================
# Data Models
# ============================================================================


class PipelineStatus(Enum):
    """Status of pipeline execution."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class StageOutput:
    """Typed output from a pipeline stage."""

    stage_name: str
    success: bool
    data: Any  # Stage-specific output data
    artifacts: dict[str, str] = field(default_factory=dict)  # artifact_name -> path
    metrics: dict[str, float] = field(default_factory=dict)  # metric_name -> value
    error: str | None = None
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for context propagation."""
        return {
            "stage_name": self.stage_name,
            "success": self.success,
            "data": self.data,
            "artifacts": self.artifacts,
            "metrics": self.metrics,
            "error": self.error,
            "timestamp": self.timestamp.isoformat(),
        }


@dataclass
class PipelineCheckpoint:
    """Pipeline checkpoint for recovery."""

    pipeline_id: str
    current_stage: str | None
    completed_stages: list[str]
    failed_stages: list[str]
    status: PipelineStatus
    context: dict[str, Any]
    timestamp: datetime
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class PipelineResult:
    """Result of pipeline execution."""

    success: bool
    status: PipelineStatus
    completed_stages: list[str]
    failed_stages: list[str]
    outputs: dict[str, Any]  # stage_name -> output
    errors: dict[str, str]  # stage_name -> error
    duration_seconds: float
    metadata: dict[str, Any]


@dataclass
class StageResult:
    """Result of stage execution."""

    success: bool
    stage_name: str
    output: str | None
    error: str | None
    duration_seconds: float
    metadata: dict[str, Any]


# ============================================================================
# Service
# ============================================================================


class PipelineManager:
    """
    Pipeline Manager application service.

    Manages pipeline execution, stage coordination, and state checkpointing.

    This service is responsible for:
    - Executing multi-stage pipelines
    - Coordinating stage transitions based on dependencies
    - Handling stage dependencies and parallel execution
    - State checkpointing and recovery from failures
    - Emitting pipeline lifecycle events
    - Propagating context through pipeline stages
    """

    def __init__(
        self,
        event_store: IEventStore,
        checkpoint_store: Any | None = None,
    ):
        """
        Initialize PipelineManager.

        Args:
            event_store: Event store port for emitting events
            checkpoint_store: Optional checkpoint storage (Redis, file system, etc.)
        """
        self.event_store = event_store
        self.checkpoint_store = checkpoint_store
        self._logger = logging.getLogger(f"{__name__}.PipelineManager")

    async def _emit_event_safely(self, event: Any) -> None:
        """
        Emit event to event store with error handling.

        Logs failures but doesn't break main flow.

        Args:
            event: Event to emit
        """
        try:
            # Use aggregate_id as stream_id and wrap event in a list
            await self.event_store.append(event.aggregate_id, [event])
        except Exception as e:
            self._logger.error(
                f"Failed to emit event {type(event).__name__}: {e}",
                exc_info=True,
                extra={"error_id": "ERR_PIPELINE_EVENT_EMIT_FAILURE"}
            )

    # ========================================================================
    # Public API
    # ========================================================================

    async def execute_pipeline(
        self,
        workflow: Workflow,
        context: dict[str, Any],
        resume_from_checkpoint: bool = False,
    ) -> PipelineResult:
        """
        Execute complete pipeline.

        Executes all stages in the workflow respecting dependencies and
        execution order. Supports checkpointing and recovery.

        Args:
            workflow: Workflow containing pipeline stages
            context: Execution context (project, work item, etc.)
            resume_from_checkpoint: Whether to resume from last checkpoint

        Returns:
            PipelineResult: Result of pipeline execution

        Raises:
            ValueError: If workflow is invalid
        """
        pipeline_id = workflow.id
        self._logger.info(
            f"Starting pipeline execution: pipeline_id={pipeline_id}, "
            f"stages={len(workflow.stages)}, "
            f"resume={resume_from_checkpoint}"
        )

        start_time = datetime.now(UTC)

        # Initialize tracking
        completed_stages = []
        failed_stages = []
        outputs = {}
        errors = {}

        try:
            # Check for checkpoint if resuming
            if resume_from_checkpoint:
                checkpoint = await self.recover(pipeline_id)
                if checkpoint:
                    self._logger.info(
                        f"Resuming from checkpoint: "
                        f"completed={len(checkpoint.completed_stages)}"
                    )
                    completed_stages = checkpoint.completed_stages
                    failed_stages = checkpoint.failed_stages
                    context = {**context, **checkpoint.context}

            # Execute stages sequentially (respecting dependencies)
            for stage in workflow.stages:
                # Skip if already completed
                if stage.name in completed_stages:
                    self._logger.info(f"Skipping completed stage: {stage.name}")
                    continue

                # Check if stage can execute
                if not stage.can_enter(completed_stages):
                    self._logger.info(
                        f"Stage {stage.name} waiting for dependencies: "
                        f"{stage.dependencies}"
                    )
                    continue

                # Execute stage
                stage_result = await self.execute_stage(
                    stage, context, workflow_id=pipeline_id
                )

                # Track result
                if stage_result.success:
                    completed_stages.append(stage.name)
                    outputs[stage.name] = stage_result.output

                    # Create typed output for context propagation
                    stage_output = StageOutput(
                        stage_name=stage.name,
                        success=True,
                        data=stage_result.output,
                        artifacts={},
                        metrics={"duration_seconds": stage_result.duration_seconds},
                    )

                    # Propagate output to context for next stages
                    context[f"{stage.name}_output"] = stage_output.to_dict()
                else:
                    failed_stages.append(stage.name)
                    errors[stage.name] = stage_result.error or "Unknown error"

                    # Store error in context for debugging
                    stage_output = StageOutput(
                        stage_name=stage.name,
                        success=False,
                        data=None,
                        error=stage_result.error,
                        metrics={"duration_seconds": stage_result.duration_seconds},
                    )
                    context[f"{stage.name}_output"] = stage_output.to_dict()

                # Checkpoint after each stage
                await self.checkpoint(
                    pipeline_id,
                    PipelineCheckpoint(
                        pipeline_id=pipeline_id,
                        current_stage=stage.name,
                        completed_stages=completed_stages,
                        failed_stages=failed_stages,
                        status=PipelineStatus.RUNNING,
                        context=context,
                        timestamp=datetime.now(UTC),
                        metadata={
                            "last_stage": stage.name,
                            "stage_result": stage_result.success,
                        },
                    ),
                )

                # Handle stage failure
                if not stage_result.success:
                    if stage.is_parallel:
                        # For parallel stages, continue to other stages
                        self._logger.warning(
                            f"Parallel stage {stage.name} failed, continuing"
                        )
                        continue
                    # For sequential stages, stop pipeline and cleanup
                    self._logger.error(
                        f"Sequential stage {stage.name} failed, stopping pipeline",
                        extra={"error_id": "ERR_PIPELINE_SEQUENTIAL_STAGE_FAILURE"}
                    )
                    # Cleanup partial state
                    await self._cleanup_failed_pipeline(
                        pipeline_id, context, completed_stages, failed_stages
                    )
                    message = f"Stage {stage.name} failed: {stage_result.error}"
                    raise Exception(message)

            # All stages completed
            duration = (datetime.now(UTC) - start_time).total_seconds()

            # Emit completion event
            await self._emit_pipeline_completed(
                pipeline_id, workflow, completed_stages, outputs, duration
            )

            return PipelineResult(
                success=True,
                status=PipelineStatus.COMPLETED,
                completed_stages=completed_stages,
                failed_stages=failed_stages,
                outputs=outputs,
                errors=errors,
                duration_seconds=duration,
                metadata={
                    "workflow_id": pipeline_id,
                    "total_stages": len(workflow.stages),
                },
            )

        except Exception as e:
            duration = (datetime.now(UTC) - start_time).total_seconds()
            self._logger.error(
                f"Pipeline execution failed: {e}",
                exc_info=True,
                extra={"error_id": "ERR_PIPELINE_EXECUTION_FAILURE"}
            )

            # Emit failure event
            await self._emit_pipeline_failed(
                pipeline_id, workflow, str(e), completed_stages, failed_stages
            )

            return PipelineResult(
                success=False,
                status=PipelineStatus.FAILED,
                completed_stages=completed_stages,
                failed_stages=failed_stages,
                outputs=outputs,
                errors=errors,
                duration_seconds=duration,
                metadata={
                    "workflow_id": pipeline_id,
                    "error": str(e),
                },
            )

    async def execute_stage(
        self,
        stage: PipelineStage,
        context: dict[str, Any],
        workflow_id: str | None = None,
    ) -> StageResult:
        """
        Execute single pipeline stage.

        Args:
            stage: Pipeline stage to execute
            context: Execution context
            workflow_id: Optional workflow ID for event correlation

        Returns:
            StageResult: Result of stage execution

        Raises:
            ValueError: If stage configuration is invalid
        """
        self._logger.info(
            f"Executing stage: stage={stage.name}, "
            f"type={stage.stage_type.value}, "
            f"status={stage.status.value}"
        )

        start_time = datetime.now(UTC)

        try:
            # Mark stage as ready if pending
            if stage.status == StageStatus.PENDING:
                stage.mark_ready()

            # Start stage
            execution_id = f"exec-{stage.id}-{int(start_time.timestamp())}"
            stage.start(execution_id)

            # Emit stage started event
            await self._emit_stage_started(
                stage, workflow_id or stage.workflow_id, context
            )

            # TODO: This is where we'd call the actual agent execution service
            # For now, we'll simulate execution
            self._logger.info(
                f"Stage {stage.name} execution would happen here "
                f"(agent_config={stage.agent_config})"
            )

            # Simulate successful execution
            output = f"Output from stage {stage.name}"
            stage.complete(output)

            duration = (datetime.now(UTC) - start_time).total_seconds()

            # Emit stage completed event
            await self._emit_stage_completed(
                stage, workflow_id or stage.workflow_id, output, duration
            )

            return StageResult(
                success=True,
                stage_name=stage.name,
                output=output,
                error=None,
                duration_seconds=duration,
                metadata={
                    "execution_id": execution_id,
                    "stage_type": stage.stage_type.value,
                },
            )

        except Exception as e:
            duration = (datetime.now(UTC) - start_time).total_seconds()
            self._logger.error(
                f"Stage execution failed: stage={stage.name}, error={e}",
                exc_info=True,
                extra={"error_id": "ERR_PIPELINE_STAGE_EXECUTION_FAILURE"}
            )

            # Mark stage as failed
            stage.fail(str(e))

            # Emit stage failed event
            await self._emit_stage_failed(
                stage, workflow_id or stage.workflow_id, str(e), duration
            )

            return StageResult(
                success=False,
                stage_name=stage.name,
                output=None,
                error=str(e),
                duration_seconds=duration,
                metadata={
                    "stage_type": stage.stage_type.value,
                },
            )

    async def checkpoint(
        self, pipeline_id: str, checkpoint: PipelineCheckpoint
    ) -> None:
        """
        Save pipeline checkpoint for recovery.

        Args:
            pipeline_id: Pipeline identifier
            checkpoint: Checkpoint data to save

        Raises:
            StorageError: If checkpoint save fails
        """
        self._logger.debug(
            f"Checkpointing pipeline: pipeline_id={pipeline_id}, "
            f"completed={len(checkpoint.completed_stages)}"
        )

        if self.checkpoint_store:
            try:
                await self.checkpoint_store.save_checkpoint(pipeline_id, checkpoint)
            except Exception as e:
                self._logger.error(
                    f"Failed to save checkpoint: {e}",
                    exc_info=True,
                    extra={"error_id": "ERR_PIPELINE_CHECKPOINT_SAVE_FAILURE"}
                )
                # Don't fail pipeline if checkpoint fails
        else:
            self._logger.debug("No checkpoint store configured, skipping")

    async def recover(self, pipeline_id: str) -> PipelineCheckpoint | None:
        """
        Recover pipeline from checkpoint.

        Args:
            pipeline_id: Pipeline identifier

        Returns:
            Optional[PipelineCheckpoint]: Checkpoint data if found, None otherwise

        Raises:
            StorageError: If checkpoint retrieval fails
        """
        self._logger.info(f"Attempting to recover pipeline: pipeline_id={pipeline_id}")

        if self.checkpoint_store:
            try:
                checkpoint = cast("PipelineCheckpoint | None", await self.checkpoint_store.load_checkpoint(pipeline_id))
                if checkpoint:
                    self._logger.info(
                        f"Recovered checkpoint: completed={len(checkpoint.completed_stages)}"
                    )
                    return checkpoint
                self._logger.info("No checkpoint found")
                return None
            except Exception as e:
                self._logger.error(
                    f"Failed to recover checkpoint: {e}",
                    exc_info=True,
                    extra={"error_id": "ERR_PIPELINE_CHECKPOINT_RECOVER_FAILURE"}
                )
                return None
        else:
            self._logger.debug("No checkpoint store configured")
            return None

    # ========================================================================
    # Event Emission
    # ========================================================================

    async def _emit_stage_started(
        self, stage: PipelineStage, workflow_id: str, context: dict[str, Any]
    ) -> None:
        """Emit stage started event."""
        event = PipelineStageStarted(
            aggregate_id=workflow_id,
            pipeline_id=workflow_id,
            stage_name=stage.name,
            stage_type=stage.stage_type.value,
            agent_config=stage.agent_config,
            execution_id=stage.execution_id or "",
            timestamp=datetime.now(UTC),
        )
        await self._emit_event_safely(event)

    async def _emit_stage_completed(
        self,
        stage: PipelineStage,
        workflow_id: str,
        output: str,
        duration_seconds: float,
    ) -> None:
        """Emit stage completed event."""
        event = PipelineStageCompleted(
            aggregate_id=workflow_id,
            pipeline_id=workflow_id,
            stage_name=stage.name,
            execution_id=stage.execution_id or "",
            output=output,
            duration_seconds=duration_seconds,
            timestamp=datetime.now(UTC),
        )
        await self._emit_event_safely(event)

    async def _emit_stage_failed(
        self,
        stage: PipelineStage,
        workflow_id: str,
        error: str,
        duration_seconds: float,
    ) -> None:
        """Emit stage failed event."""
        event = PipelineStageFailed(
            aggregate_id=workflow_id,
            pipeline_id=workflow_id,
            stage_name=stage.name,
            execution_id=stage.execution_id or "",
            error=error,
            duration_seconds=duration_seconds,
            timestamp=datetime.now(UTC),
        )
        await self._emit_event_safely(event)

    async def _emit_pipeline_completed(
        self,
        pipeline_id: str,
        workflow: Workflow,
        completed_stages: list[str],
        outputs: dict[str, Any],
        duration_seconds: float,
    ) -> None:
        """Emit pipeline completed event."""
        event = PipelineCompleted(
            aggregate_id=pipeline_id,
            pipeline_id=pipeline_id,
            workflow_id=workflow.id,
            completed_stages=completed_stages,
            outputs=outputs,
            duration_seconds=duration_seconds,
            timestamp=datetime.now(UTC),
        )
        await self._emit_event_safely(event)

    async def _emit_pipeline_failed(
        self,
        pipeline_id: str,
        workflow: Workflow,
        error: str,
        completed_stages: list[str],
        failed_stages: list[str],
    ) -> None:
        """Emit pipeline failed event."""
        event = PipelineFailed(
            aggregate_id=pipeline_id,
            pipeline_id=pipeline_id,
            workflow_id=workflow.id,
            error=error,
            completed_stages=completed_stages,
            failed_stages=failed_stages,
            timestamp=datetime.now(UTC),
        )
        await self._emit_event_safely(event)

    async def _cleanup_failed_pipeline(
        self,
        pipeline_id: str,
        context: dict[str, Any],
        completed_stages: list[str],
        failed_stages: list[str],
    ) -> None:
        """
        Cleanup resources and partial state from failed pipeline.

        Args:
            pipeline_id: Pipeline identifier
            context: Pipeline execution context
            completed_stages: List of successfully completed stages
            failed_stages: List of failed stages
        """
        self._logger.info(
            f"Cleaning up failed pipeline: pipeline_id={pipeline_id}, "
            f"completed={len(completed_stages)}, failed={len(failed_stages)}"
        )

        try:
            # Clear stage outputs from context to prevent stale data
            for stage_name in completed_stages + failed_stages:
                output_key = f"{stage_name}_output"
                context.pop(output_key, None)

            # TODO: Add rollback logic for specific stages if needed
            # This could include:
            # - Deleting temporary files
            # - Rolling back database changes
            # - Cleaning up container resources

            self._logger.info(f"Cleanup completed for pipeline {pipeline_id}")

        except Exception as e:
            self._logger.error(
                f"Error during pipeline cleanup: {e}",
                exc_info=True,
                extra={"error_id": "ERR_PIPELINE_CLEANUP_FAILURE"}
            )
