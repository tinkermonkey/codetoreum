"""Pipeline Manager application service."""

import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import TYPE_CHECKING, Any, cast

from codetoreum.domain.agent import Agent, AgentCapability, AgentType
from codetoreum.domain.coding_agent_types import AgentInvocationConfig, InvocationMode
from codetoreum.domain.events.workflow_events import (
    PipelineCompletedEvent,
    PipelineFailedEvent,
    PipelineStageCompletedEvent,
    PipelineStageFailedEvent,
    PipelineStageStartedEvent,
)
from codetoreum.domain.pipeline_stage import PipelineStage, StageStatus
from codetoreum.domain.value_objects import ExecutionContext as ExecutionContextVO
from codetoreum.domain.work_item import WorkItem, WorkItemPriority, WorkItemStatus
from codetoreum.domain.workflow import Workflow
from codetoreum.ports.output import IEventStore

if TYPE_CHECKING:
    from codetoreum.application.execution_service import ExecutionService

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
        execution_service: "ExecutionService | None" = None,
        checkpoint_store: Any | None = None,
    ):
        """
        Initialize PipelineManager.

        Args:
            event_store: Event store port for emitting events
            execution_service: Execution service for running agent stages
            checkpoint_store: Optional checkpoint storage (Redis, file system, etc.)
        """
        self.event_store = event_store
        self.execution_service = execution_service
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
            await self.event_store.append(getattr(event, "pipeline_id", None) or event.event_id, [event])
        except Exception as e:
            self._logger.error(
                f"Failed to emit event {type(event).__name__}: {e}",
                exc_info=True,
                extra={"error_id": "ERR_PIPELINE_EVENT_EMIT_FAILURE"},
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
                    self._logger.info(f"Resuming from checkpoint: completed={len(checkpoint.completed_stages)}")
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
                    self._logger.info(f"Stage {stage.name} waiting for dependencies: {stage.dependencies}")
                    continue

                # Execute stage
                stage_result = await self.execute_stage(stage, context, workflow_id=pipeline_id)

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
                        self._logger.warning(f"Parallel stage {stage.name} failed, continuing")
                        continue
                    # For sequential stages, stop pipeline and cleanup
                    self._logger.error(
                        f"Sequential stage {stage.name} failed, stopping pipeline",
                        extra={"error_id": "ERR_PIPELINE_SEQUENTIAL_STAGE_FAILURE"},
                    )
                    # Cleanup partial state
                    await self._cleanup_failed_pipeline(pipeline_id, context, completed_stages, failed_stages)
                    message = f"Stage {stage.name} failed: {stage_result.error}"
                    raise Exception(message)

            # All stages completed
            duration = (datetime.now(UTC) - start_time).total_seconds()

            # Emit completion event
            await self._emit_pipeline_completed(pipeline_id, workflow, completed_stages, outputs, duration)

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
                extra={"error_id": "ERR_PIPELINE_EXECUTION_FAILURE"},
            )

            # Emit failure event
            await self._emit_pipeline_failed(pipeline_id, workflow, str(e), completed_stages, failed_stages)

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

        Executes a stage by delegating to the execution service for agent-based stages.
        Updates stage status and emits domain events for each lifecycle transition.

        Args:
            stage: Pipeline stage to execute
            context: Execution context (project, work item, etc.)
            workflow_id: Optional workflow ID for event correlation

        Returns:
            StageResult: Result of stage execution

        Raises:
            ValueError: If stage configuration is invalid or execution service not available
        """
        self._logger.info(
            f"Executing stage: stage={stage.name}, type={stage.stage_type.value}, status={stage.status.value}"
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
            await self._emit_stage_started(stage, workflow_id or stage.workflow_id, context)

            # If no execution service, skip actual execution (for testing/simulation)
            if not self.execution_service:
                self._logger.warning(f"No execution service configured for stage {stage.name}, skipping execution")
                output = f"Simulated output from stage {stage.name}"
                stage.complete(output)

                duration = (datetime.now(UTC) - start_time).total_seconds()
                await self._emit_stage_completed(stage, workflow_id or stage.workflow_id, output, duration)

                return StageResult(
                    success=True,
                    stage_name=stage.name,
                    output=output,
                    error=None,
                    duration_seconds=duration,
                    metadata={
                        "execution_id": execution_id,
                        "stage_type": stage.stage_type.value,
                        "simulated": True,
                    },
                )

            # Get agent ID from stage configuration
            agent_id = stage.agent_config.get("agent_id")
            if not agent_id:
                raise ValueError(f"Stage {stage.name} missing required 'agent_id' in agent_config")

            # Build agent and work item for execution (minimal required data)
            # TODO: In production, these should be retrieved from repositories instead of
            # constructing inline from configuration. This is a placeholder for initial implementation.
            # Create agent capabilities
            capabilities_config = stage.agent_config.get("capabilities", {})
            if not capabilities_config:
                # Default capability if none specified
                capabilities_config = {"general": {"proficiency": 1.0, "description": "General capability"}}

            capabilities = {}
            for skill_name, skill_config in capabilities_config.items():
                if isinstance(skill_config, dict):
                    proficiency = skill_config.get("proficiency", 1.0)
                    description = skill_config.get("description")
                else:
                    proficiency = 1.0
                    description = None

                capabilities[skill_name] = AgentCapability(
                    skill=skill_name,
                    proficiency=proficiency,
                    description=description,
                )

            agent = Agent.create(
                name=stage.agent_config.get("agent_name", agent_id),
                display_name=stage.agent_config.get("agent_display_name", agent_id),
                agent_type=AgentType[stage.agent_config.get("agent_type", "SPECIALIZED").upper()],
                role_description=stage.agent_config.get("agent_description", f"Agent for stage {stage.name}"),
                capabilities=capabilities,
                invocation=AgentInvocationConfig(
                    mode=InvocationMode.CONTAINERIZED,
                    model=stage.agent_config.get("model", "claude-opus"),
                    timeout_seconds=stage.agent_config.get("timeout_seconds", 3600),
                    mode_config={"image": "codetoreum-agent:latest"},
                ),
                max_retries=stage.agent_config.get("max_retries", 3),
            )

            work_item_id = context.get("work_item_id")
            if not work_item_id:
                raise ValueError("Execution context missing required 'work_item_id'")

            project_id = context.get("project_id")
            if not project_id:
                raise ValueError("Execution context missing required 'project_id'")

            # Create work item with required fields
            work_item = WorkItem(
                id=work_item_id,
                project_id=project_id,
                title=context.get("work_item_title", f"Work item {work_item_id}"),
                description=context.get("work_item_description", ""),
                status=WorkItemStatus.IN_PROGRESS,
                priority=WorkItemPriority.MEDIUM,
                labels=[],
                external_id=None,
                external_url=None,
                assigned_agent_id=stage.agent_config.get("agent_id"),
                assigned_at=datetime.now(UTC),
                current_workflow_id=workflow_id or stage.workflow_id,
                current_stage=stage.name,
                created_at=datetime.now(UTC),
                updated_at=datetime.now(UTC),
                completed_at=None,
            )

            # Build prompt from context
            prompt = context.get(f"{stage.name}_prompt") or f"Execute stage {stage.name}"

            # Create execution
            execution = await self.execution_service.create_execution(
                agent=agent,
                work_item=work_item,
                workflow_id=workflow_id or stage.workflow_id,
                stage_name=stage.name,
                prompt=prompt,
            )

            # Build execution context
            exec_context = ExecutionContextVO(
                work_item_id=work_item_id,
                workflow_id=workflow_id or stage.workflow_id,
                stage_name=stage.name,
                agent_id=agent_id,
                model=stage.agent_config.get("model", "claude-opus"),
                timeout_seconds=stage.agent_config.get("timeout_seconds", 3600),
                workspace_type="container",
                branch_name=None,
                discussion_id=None,
                project_id=context.get("project_id", ""),
                repository_url=context.get("repository_url", ""),
            )

            # Start execution
            start_result = await self.execution_service.start_execution(
                execution=execution,
                context=exec_context,
            )

            if not start_result.success:
                raise Exception(f"Failed to start execution: {start_result.error}")

            # PipelineManager has no live production wiring (every
            # bootstrap constructs it with ``execution_service=None`` and
            # only the simulated branch above runs). The old call site
            # invoked the retired ``ExecutionService.execute_with_llm``
            # which Phase D5 removed. Any caller that wants real agent
            # execution from PipelineManager must migrate to the new
            # ``ExecutionService.execute()`` path; that migration is
            # tracked separately from this redesign.
            raise NotImplementedError(
                "PipelineManager.execute_stage no longer supports direct agent execution. "
                "The legacy ExecutionService.execute_with_llm path retired in Phase D5. "
                "Use WorkflowOrchestrator + ExecutionServiceAgentExecutor for real agent runs."
            )

        except Exception as e:
            duration = (datetime.now(UTC) - start_time).total_seconds()
            self._logger.error(
                f"Stage execution failed: stage={stage.name}, error={e}",
                exc_info=True,
                extra={"error_id": "ERR_PIPELINE_STAGE_EXECUTION_FAILURE"},
            )

            # Mark stage as failed
            stage.fail(str(e))

            # Emit stage failed event
            await self._emit_stage_failed(stage, workflow_id or stage.workflow_id, str(e), duration)

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

    async def checkpoint(self, pipeline_id: str, checkpoint: PipelineCheckpoint) -> None:
        """
        Save pipeline checkpoint for recovery.

        Args:
            pipeline_id: Pipeline identifier
            checkpoint: Checkpoint data to save

        Raises:
            StorageError: If checkpoint save fails
        """
        self._logger.debug(
            f"Checkpointing pipeline: pipeline_id={pipeline_id}, completed={len(checkpoint.completed_stages)}"
        )

        if self.checkpoint_store:
            try:
                await self.checkpoint_store.save_checkpoint(pipeline_id, checkpoint)
            except Exception as e:
                self._logger.error(
                    f"Failed to save checkpoint: {e}",
                    exc_info=True,
                    extra={"error_id": "ERR_PIPELINE_CHECKPOINT_SAVE_FAILURE"},
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
                checkpoint = cast(
                    "PipelineCheckpoint | None",
                    await self.checkpoint_store.load_checkpoint(pipeline_id),
                )
                if checkpoint:
                    self._logger.info(f"Recovered checkpoint: completed={len(checkpoint.completed_stages)}")
                    return checkpoint
                self._logger.info("No checkpoint found")
                return None
            except Exception as e:
                self._logger.error(
                    f"Failed to recover checkpoint: {e}",
                    exc_info=True,
                    extra={"error_id": "ERR_PIPELINE_CHECKPOINT_RECOVER_FAILURE"},
                )
                return None
        else:
            self._logger.debug("No checkpoint store configured")
            return None

    # ========================================================================
    # Event Emission
    # ========================================================================

    async def _emit_stage_started(self, stage: PipelineStage, workflow_id: str, context: dict[str, Any]) -> None:
        """Emit stage started event."""
        event = PipelineStageStartedEvent(
            type="pipeline.stage.started",
            timestamp=datetime.now(UTC).isoformat(),
            source="pipeline_manager",
            pipeline_id=workflow_id,
            stage_id=stage.id if hasattr(stage, "id") else "",
            stage_name=stage.name,
            started_at=datetime.now(UTC).isoformat(),
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
        event = PipelineStageCompletedEvent(
            type="pipeline.stage.completed",
            timestamp=datetime.now(UTC).isoformat(),
            source="pipeline_manager",
            pipeline_id=workflow_id,
            stage_id=stage.id if hasattr(stage, "id") else "",
            stage_name=stage.name,
            completed_at=datetime.now(UTC).isoformat(),
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
        event = PipelineStageFailedEvent(
            type="pipeline.stage.failed",
            timestamp=datetime.now(UTC).isoformat(),
            source="pipeline_manager",
            pipeline_id=workflow_id,
            stage_id=stage.id if hasattr(stage, "id") else "",
            stage_name=stage.name,
            error=error,
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
        event = PipelineCompletedEvent(
            type="pipeline.completed",
            timestamp=datetime.now(UTC).isoformat(),
            source="pipeline_manager",
            pipeline_id=pipeline_id,
            work_item_id=workflow.id,
            completed_stages=tuple(completed_stages),
            completed_at=datetime.now(UTC).isoformat(),
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
        event = PipelineFailedEvent(
            type="pipeline.failed",
            timestamp=datetime.now(UTC).isoformat(),
            source="pipeline_manager",
            pipeline_id=pipeline_id,
            work_item_id=workflow.id,
            error=error,
            completed_stages=tuple(completed_stages),
            failed_stage=failed_stages[0] if failed_stages else "",
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
                extra={"error_id": "ERR_PIPELINE_CLEANUP_FAILURE"},
            )
