"""Production environment repair adapter with LLM integration.

Implements IEnvironmentRepairService by orchestrating environment rebuild and
verification operations through LLM agents. Handles both operations with independent
timeout enforcement and comprehensive event emission.

Key responsibilities:
1. Environment rebuild: Coordinate re-provisioning of dependencies and configuration
2. Environment verification: Validate that the rebuilt environment is healthy
3. Event emission: Emit 4 of 5 environment repair domain events via injected IEventEmitter
4. Timeout enforcement: Apply independent timeouts for rebuild and verification
5. Error logging: Comprehensive error logging with ErrorRegistry IDs
"""

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from codetoreum.adapters.secondary.free_form_coding_agent import (
    synthetic_agent_execution,
    synthetic_workspace_context,
)
from codetoreum.domain.coding_agent_types import InvocationMode
from codetoreum.domain.events.repair_cycle_events import (
    EnvironmentRebuildCompletedEvent,
    EnvironmentRebuildStartedEvent,
    EnvironmentVerificationCompletedEvent,
    EnvironmentVerificationStartedEvent,
)
from codetoreum.domain.repair_cycle_types import (
    EnvironmentRepairConfig,
    RebuildResult,
    RepairTestRunConfig,
    RepairTestType,
    VerificationResult,
)
from codetoreum.infrastructure.error_ids import ErrorRegistry
from codetoreum.ports.output.coding_agent import CodingAgentInvocationOptions
from codetoreum.ports.output.environment_repair_service import IEnvironmentRepairService
from codetoreum.ports.output.event_emitter import IEventEmitter, NullEventEmitter
from codetoreum.ports.output.prompt_builder import IPromptBuilder, StructuredPrompt
from codetoreum.ports.output.repair_cycle_service import RepairCycleContext

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

    from codetoreum.domain.agent import Agent
    from codetoreum.domain.work_item import WorkItem
    from codetoreum.domain.workspace_context import WorkspaceContext
    from codetoreum.infrastructure.resilience.interfaces import ICircuitBreaker
    from codetoreum.ports.output.coding_agent import (
        CodingAgentResult,
        ICodingAgent,
    )
    from codetoreum.ports.output.prompt_builder import ExecutionOutput

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class EnvironmentRepairAdapterConfig:
    """Configuration for production environment repair adapter.

    Attributes:
        max_json_parse_retries: Maximum retries for JSON parsing (default 3)
        json_parse_retry_delay_ms: Delay between retries in milliseconds (default 500)
    """

    max_json_parse_retries: int = 3
    json_parse_retry_delay_ms: int = 500

    def __post_init__(self) -> None:
        """Validate config after initialization."""
        if self.max_json_parse_retries < 1:
            msg = "max_json_parse_retries must be >= 1"
            raise ValueError(msg)
        if self.json_parse_retry_delay_ms < 0:
            msg = "json_parse_retry_delay_ms must be >= 0"
            raise ValueError(msg)


class _EnvironmentRebuildPromptBuilder(IPromptBuilder):
    """Per-call :class:`IPromptBuilder` for environment rebuild prompts.

    Closure-captures the rebuild task description text. Ignores the
    standard ``agent`` / ``work_item`` / ``prior_outputs`` arguments —
    only the supplied ``workspace_context`` is forwarded.
    """

    def __init__(self, *, task_text: str) -> None:
        self._task_text = task_text

    async def build(
        self,
        agent: Agent,
        work_item: WorkItem,
        workspace_context: WorkspaceContext,
        prior_outputs: tuple[ExecutionOutput, ...] = (),
    ) -> StructuredPrompt:
        return StructuredPrompt(
            role_description="Environment repair specialist",
            task_description=self._task_text,
            work_item=work_item,
            workspace_context=workspace_context,
            instructions=(
                "Return a JSON object describing what you did.",
                'Schema: {"success": <bool>, "actions_taken": [<str>, ...], "error": <str | null>}',
            ),
            constraints=(
                "Do not modify application source code — environment changes only.",
                "Do not commit anything to git.",
            ),
            prior_outputs=(),
        )


class _EnvironmentVerifyPromptBuilder(IPromptBuilder):
    """Per-call :class:`IPromptBuilder` for environment verification prompts."""

    def __init__(self, *, task_text: str) -> None:
        self._task_text = task_text

    async def build(
        self,
        agent: Agent,
        work_item: WorkItem,
        workspace_context: WorkspaceContext,
        prior_outputs: tuple[ExecutionOutput, ...] = (),
    ) -> StructuredPrompt:
        return StructuredPrompt(
            role_description="Environment verification specialist",
            task_description=self._task_text,
            work_item=work_item,
            workspace_context=workspace_context,
            instructions=(
                "Return a JSON object describing the verification result.",
                'Schema: {"healthy": <bool>, "checks_passed": [<str>, ...], "checks_failed": [<str>, ...]}',
            ),
            constraints=("Read-only operation — do not modify the environment.",),
            prior_outputs=(),
        )


class ProductionEnvironmentRepairAdapter(IEnvironmentRepairService):
    """Production environment repair adapter with LLM integration.

    Implements IEnvironmentRepairService by orchestrating environment rebuild and
    verification operations through LLM agents (Claude Code). Handles both operations
    with independent timeout enforcement and comprehensive event emission.

    Example:
        config = EnvironmentRepairConfig(
            env_rebuild_timeout_seconds=1200,
            env_verification_timeout_seconds=120
        )
        adapter = ProductionEnvironmentRepairAdapter(
            coding_agent_factory=lambda pb: ResilientCodingAgentDecorator(
                wrapped=FreeFormCodingAgent(prompt_builder=pb, ...),
            ),
            repair_config=config,
            event_emitter=event_emitter,
        )

        result = await adapter.rebuild_environment(
            project="my-project",
            config=test_config,
            context=context
        )
    """

    def __init__(
        self,
        coding_agent_factory: Callable[[IPromptBuilder], ICodingAgent],
        repair_config: EnvironmentRepairConfig | None = None,
        event_emitter: IEventEmitter | None = None,
        config: EnvironmentRepairAdapterConfig | None = None,
        circuit_breaker: ICircuitBreaker | None = None,
        *,
        invocation_mode: InvocationMode = InvocationMode.CONTAINERIZED,
        model: str = "claude-sonnet-4-6",
        container_image: str = "codetoreum-agent:latest",
        workspace_path: Path | None = None,
    ) -> None:
        """Initialize production environment repair adapter.

        Args:
            coding_agent_factory: Per-call factory returning a fresh
                :class:`ICodingAgent` bound to the supplied
                :class:`IPromptBuilder`. The bootstrap wires this to a
                resilience-decorated
                :class:`~codetoreum.adapters.secondary.free_form_coding_agent.FreeFormCodingAgent`.
            repair_config: Optional EnvironmentRepairConfig (uses
                defaults if not provided).
            event_emitter: Optional event emitter (uses null-object if
                not provided).
            config: Optional adapter-specific configuration (uses
                defaults if not provided).
            circuit_breaker: Optional circuit breaker for coding-agent
                call protection.
            invocation_mode: Where the coding agent runs.
            model: Model name to request.
            container_image: Docker image when running containerised.
            workspace_path: Optional workspace path the agent runs in.
        """
        if coding_agent_factory is None:
            msg = "coding_agent_factory cannot be None"
            raise ValueError(msg)
        self._coding_agent_factory = coding_agent_factory
        self.repair_config = repair_config or EnvironmentRepairConfig()
        self.event_emitter = event_emitter or NullEventEmitter()
        self.config = config or EnvironmentRepairAdapterConfig()
        self.circuit_breaker = circuit_breaker
        self._invocation_mode = invocation_mode
        self._model = model
        self._container_image = container_image
        self._workspace_path = workspace_path
        self._test_type_descriptions = {
            RepairTestType.UNIT: "unit tests",
            RepairTestType.INTEGRATION: "integration tests",
            RepairTestType.E2E: "end-to-end tests",
        }

    def _get_test_type_description(self, test_type: RepairTestType) -> str:
        """Get human-readable description for a test type, logging if unknown.

        Args:
            test_type: The test type to describe

        Returns:
            Human-readable description of the test type

        Raises:
            ValueError: If test_type is not in the known descriptions dictionary
        """
        if test_type not in self._test_type_descriptions:
            msg = f"Unknown RepairTestType {test_type!r} - this indicates RepairTestType enum was extended but prompt builders were not updated"
            logger.error(
                msg,
                extra={
                    "test_type": test_type.value if hasattr(test_type, "value") else str(test_type),
                    "error_id": ErrorRegistry.ERR_REPAIR_CYCLE_ERROR,
                },
            )
            raise ValueError(msg)
        return self._test_type_descriptions[test_type]

    def _build_environment_rebuild_prompt(self, config: RepairTestRunConfig) -> str:
        """Build prompt for LLM to rebuild the test environment.

        Args:
            config: Test run configuration

        Returns:
            Prompt for LLM agent

        Raises:
            ValueError: If test type is unknown (not in RepairTestType enum mappings)
        """
        test_type_desc = self._get_test_type_description(config.test_type)

        return f"""The test environment needs to be rebuilt. Please execute the necessary steps to:
1. Install or update dependencies (if applicable for this project type)
2. Set up required environment variables
3. Configure any necessary services or databases
4. Prepare the environment for {test_type_desc}

After completing these steps, the environment should be ready to run tests successfully.
Return a JSON response with the status of the environment rebuild."""

    def _build_environment_verify_prompt(self, config: RepairTestRunConfig) -> str:
        """Build prompt for LLM to verify the test environment.

        Args:
            config: Test run configuration

        Returns:
            Prompt for LLM agent

        Raises:
            ValueError: If test type is unknown (not in RepairTestType enum mappings)
        """
        test_type_desc = self._get_test_type_description(config.test_type)

        return f"""Please verify that the test environment is correctly configured and ready:
1. Check that all dependencies are properly installed
2. Verify environment variables are set correctly
3. Confirm that any required services are running
4. Test that the environment can support running {test_type_desc}

Return a JSON response with the verification status and any issues found."""

    async def _execute_subtask(
        self,
        *,
        purpose: str,
        prompt_builder: IPromptBuilder,
        timeout_seconds: int,
        operation: str,
        context: RepairCycleContext,
        extra_log: dict | None = None,
        error_message: str | None = None,
    ) -> CodingAgentResult:
        """Execute a free-form coding-agent call with timeout + circuit breaker.

        Builds a fresh :class:`ICodingAgent` via the injected factory,
        bound to the supplied adapter-local prompt builder. Drives a
        single short execution against a synthetic
        :class:`AgentExecution` / :class:`WorkspaceContext`.

        Args:
            purpose: Short label describing the call (e.g.
                ``"env_rebuild"``). Used in synthetic execution metadata.
            prompt_builder: Adapter-local builder owning the rendered
                prompt content.
            timeout_seconds: Hard timeout for this operation. Applied
                via the coding agent's invocation options AND via an
                outer ``asyncio.wait_for`` to guarantee bounded
                duration.
            operation: Operation name for circuit-breaker keying.
            context: Repair cycle context with workflow details.
            extra_log: Optional dict of additional logging context.
            error_message: Optional custom error message prefix.

        Returns:
            :class:`CodingAgentResult` from the coding-agent call.

        Raises:
            TimeoutError: If the call exceeds ``timeout_seconds``.
        """
        coding_agent = self._coding_agent_factory(prompt_builder)

        execution = synthetic_agent_execution(
            purpose=purpose,
            model=self._model,
        )
        workspace_context = synthetic_workspace_context(
            purpose=purpose,
            workspace_path=self._workspace_path,
        )

        mode_config: dict[str, object] = {}
        if self._invocation_mode == InvocationMode.CONTAINERIZED:
            mode_config = {"image": self._container_image}

        options = CodingAgentInvocationOptions(
            invocation_mode=self._invocation_mode,
            model=self._model,
            timeout_seconds=timeout_seconds,
            cost_limit_usd=None,
            mode_config=mode_config,
        )

        try:
            coro = (
                self.circuit_breaker.call(
                    coding_agent.execute,
                    operation,
                    execution,
                    workspace_context,
                    options,
                )
                if self.circuit_breaker
                else coding_agent.execute(execution, workspace_context, options)
            )
            return await asyncio.wait_for(coro, timeout=timeout_seconds)
        except TimeoutError as e:
            message_prefix = error_message or operation
            log_extra = {
                "workflow_run_id": context.workflow_run_id,
                "timeout_seconds": timeout_seconds,
                "error_id": ErrorRegistry.ERR_ENVIRONMENT_REPAIR_TIMEOUT,
                **(extra_log or {}),
            }
            logger.error(f"{message_prefix} timed out", extra=log_extra, exc_info=True)
            raise TimeoutError(f"{message_prefix} exceeded timeout of {timeout_seconds} seconds") from e

    def _emit_event_safely(
        self,
        event: (
            EnvironmentRebuildStartedEvent
            | EnvironmentRebuildCompletedEvent
            | EnvironmentVerificationStartedEvent
            | EnvironmentVerificationCompletedEvent
        ),
        description: str,
        workflow_run_id: str,
    ) -> None:
        """Emit a domain event with error handling.

        Wraps event emission in try/except to prevent event emission failures
        from crashing the calling operation. Logs detailed errors for diagnostics.

        Args:
            event: Domain event to emit
            description: Event description for error logging (e.g., "rebuild started")
            workflow_run_id: Workflow run ID for log context
        """
        try:
            self.event_emitter.emit(event)
        except Exception as emit_error:
            logger.error(
                f"Failed to emit {description}",
                extra={
                    "workflow_run_id": workflow_run_id,
                    "emission_error": str(emit_error),
                    "error_id": ErrorRegistry.ERR_EVENT_PUBLICATION_ERROR,
                },
                exc_info=True,
            )

    async def rebuild_environment(
        self,
        project: str,
        config: RepairTestRunConfig,
        context: RepairCycleContext,
    ) -> RebuildResult:
        """Rebuild the test environment after systemic fixes.

        Coordinates environment re-provisioning following systemic fixes,
        ensuring all dependencies are properly installed/updated and
        configuration is applied correctly.

        Args:
            project: Project identifier/name
            config: Test run configuration with timeout and other parameters
            context: Repair cycle execution context

        Returns:
            RebuildResult with success status, actions taken, duration,
            and optional error message if rebuild failed

        Raises:
            TimeoutError: When rebuild exceeds the configured timeout
            Exception: For environment-specific errors
        """
        start_time = datetime.now(UTC)
        timestamp = start_time.isoformat()

        # Emit rebuild started event with error handling
        self._emit_event_safely(
            EnvironmentRebuildStartedEvent(
                type="repair_cycle.environment_rebuild_started",
                timestamp=timestamp,
                source="production_environment_repair",
                work_item_id=context.work_item_id,
                workflow_run_id=context.workflow_run_id,
                test_type=config.test_type,
                iteration=context.iteration,
            ),
            "rebuild started event",
            context.workflow_run_id,
        )

        try:
            # Build the rebuild prompt + adapter-local prompt builder.
            prompt_text = self._build_environment_rebuild_prompt(config)
            prompt_builder = _EnvironmentRebuildPromptBuilder(task_text=prompt_text)

            result = await self._execute_subtask(
                purpose="env_rebuild",
                prompt_builder=prompt_builder,
                operation="environment_repair.rebuild_env",
                timeout_seconds=self.repair_config.env_rebuild_timeout_seconds,
                context=context,
                extra_log={
                    "project": project,
                    "test_type": config.test_type.value,
                },
                error_message="Environment rebuild",
            )

            # Calculate duration
            end_time = datetime.now(UTC)
            duration_seconds = (end_time - start_time).total_seconds()

            # Parse response
            try:
                response_data = json.loads(result.summary_text)
            except (json.JSONDecodeError, TypeError) as e:
                logger.error(
                    "Failed to parse environment rebuild response",
                    extra={
                        "workflow_run_id": context.workflow_run_id,
                        "error": str(e),
                        "error_id": ErrorRegistry.ERR_ENVIRONMENT_REPAIR_JSON_PARSE,
                    },
                    exc_info=True,
                )
                # Return gracefully degraded result instead of raising
                rebuild_result = RebuildResult(
                    success=False,
                    duration_seconds=duration_seconds,
                    actions_taken=(),
                    error=f"Failed to parse environment rebuild response: {e!s}",
                )
                # Emit rebuild completed event with parse error
                self._emit_event_safely(
                    EnvironmentRebuildCompletedEvent(
                        type="repair_cycle.environment_rebuild_completed",
                        timestamp=datetime.now(UTC).isoformat(),
                        source="production_environment_repair",
                        work_item_id=context.work_item_id,
                        workflow_run_id=context.workflow_run_id,
                        test_type=config.test_type,
                        iteration=context.iteration,
                        success=False,
                        duration_seconds=duration_seconds,
                        actions_taken=(),
                        error=rebuild_result.error,
                    ),
                    "rebuild completed event",
                    context.workflow_run_id,
                )
                return rebuild_result

            # Extract result from response
            success = response_data.get("success", False)
            actions = response_data.get("actions_taken", [])
            error_msg = response_data.get("error")

            # Ensure error message is provided when success is False (RebuildResult invariant)
            if not success and not error_msg:
                error_msg = "Unknown error (no details in response)"

            rebuild_result = RebuildResult(
                success=success,
                duration_seconds=duration_seconds,
                actions_taken=tuple(actions) if actions else (),
                error=error_msg,
            )

            # Emit rebuild completed event with error handling
            self._emit_event_safely(
                EnvironmentRebuildCompletedEvent(
                    type="repair_cycle.environment_rebuild_completed",
                    timestamp=datetime.now(UTC).isoformat(),
                    source="production_environment_repair",
                    work_item_id=context.work_item_id,
                    workflow_run_id=context.workflow_run_id,
                    test_type=config.test_type,
                    iteration=context.iteration,
                    success=rebuild_result.success,
                    duration_seconds=rebuild_result.duration_seconds,
                    actions_taken=rebuild_result.actions_taken,
                    error=rebuild_result.error,
                ),
                "rebuild completed event",
                context.workflow_run_id,
            )

            return rebuild_result

        except Exception as e:
            logger.error(
                "Environment rebuild failed with exception",
                extra={
                    "workflow_run_id": context.workflow_run_id,
                    "test_type": config.test_type.value,
                    "error": str(e),
                    "error_type": type(e).__name__,
                    "error_id": ErrorRegistry.ERR_REPAIR_CYCLE_ERROR,
                },
                exc_info=True,
            )
            # Emit rebuild completion event with error information
            end_time = datetime.now(UTC)
            final_duration = (end_time - start_time).total_seconds()
            self._emit_event_safely(
                EnvironmentRebuildCompletedEvent(
                    type="repair_cycle.environment_rebuild_completed",
                    timestamp=datetime.now(UTC).isoformat(),
                    source="production_environment_repair",
                    work_item_id=context.work_item_id,
                    workflow_run_id=context.workflow_run_id,
                    test_type=config.test_type,
                    iteration=context.iteration,
                    success=False,
                    duration_seconds=final_duration,
                    actions_taken=(),
                    error=str(e),
                ),
                "rebuild completed event",
                context.workflow_run_id,
            )
            raise

    async def verify_environment(
        self,
        project: str,
        config: RepairTestRunConfig,
        context: RepairCycleContext,
    ) -> VerificationResult:
        """Verify that the rebuilt environment is ready for testing.

        Validates that the environment is properly configured, all required
        tools and dependencies are available, and the environment is
        in a healthy state ready for test execution.

        Args:
            project: Project identifier/name
            config: Test run configuration with timeout and other parameters
            context: Repair cycle execution context

        Returns:
            VerificationResult with healthy status, passed/failed checks,
            and duration

        Raises:
            TimeoutError: When verification exceeds the configured timeout
            Exception: For environment-specific errors
        """
        start_time = datetime.now(UTC)
        timestamp = start_time.isoformat()

        # Emit verification started event with error handling
        self._emit_event_safely(
            EnvironmentVerificationStartedEvent(
                type="repair_cycle.environment_verification_started",
                timestamp=timestamp,
                source="production_environment_repair",
                work_item_id=context.work_item_id,
                workflow_run_id=context.workflow_run_id,
                test_type=config.test_type,
                iteration=context.iteration,
            ),
            "verification started event",
            context.workflow_run_id,
        )

        try:
            # Build the verification prompt + adapter-local prompt builder.
            prompt_text = self._build_environment_verify_prompt(config)
            prompt_builder = _EnvironmentVerifyPromptBuilder(task_text=prompt_text)

            result = await self._execute_subtask(
                purpose="env_verification",
                prompt_builder=prompt_builder,
                operation="environment_repair.verify_env",
                timeout_seconds=self.repair_config.env_verification_timeout_seconds,
                context=context,
                extra_log={
                    "project": project,
                    "test_type": config.test_type.value,
                },
                error_message="Environment verification",
            )

            # Calculate duration
            end_time = datetime.now(UTC)
            duration_seconds = (end_time - start_time).total_seconds()

            # Parse response
            try:
                response_data = json.loads(result.summary_text)
            except (json.JSONDecodeError, TypeError) as e:
                logger.error(
                    "Failed to parse environment verification response",
                    extra={
                        "workflow_run_id": context.workflow_run_id,
                        "error": str(e),
                        "error_id": ErrorRegistry.ERR_ENVIRONMENT_REPAIR_JSON_PARSE,
                    },
                    exc_info=True,
                )
                # Return gracefully degraded result instead of raising
                verification_result = VerificationResult(
                    healthy=False,
                    checks_passed=(),
                    checks_failed=("parsing_response",),
                    duration_seconds=duration_seconds,
                )
                # Emit verification completed event with parse error
                self._emit_event_safely(
                    EnvironmentVerificationCompletedEvent(
                        type="repair_cycle.environment_verification_completed",
                        timestamp=datetime.now(UTC).isoformat(),
                        source="production_environment_repair",
                        work_item_id=context.work_item_id,
                        workflow_run_id=context.workflow_run_id,
                        test_type=config.test_type,
                        iteration=context.iteration,
                        healthy=False,
                        checks_passed=(),
                        checks_failed=verification_result.checks_failed,
                        duration_seconds=duration_seconds,
                    ),
                    "verification completed event",
                    context.workflow_run_id,
                )
                return verification_result

            # Extract result from response
            healthy = response_data.get("healthy", False)
            checks_passed = response_data.get("checks_passed", [])
            checks_failed = response_data.get("checks_failed", [])

            # Ensure unhealthy states have evidence: if healthy=False but checks_failed is empty,
            # add a default failure reason for audit trail consistency
            if not healthy and not checks_failed:
                checks_failed = ["verification_failed"]

            verification_result = VerificationResult(
                healthy=healthy,
                checks_passed=tuple(checks_passed) if checks_passed else (),
                checks_failed=tuple(checks_failed),
                duration_seconds=duration_seconds,
            )

            # Emit verification completed event with error handling
            self._emit_event_safely(
                EnvironmentVerificationCompletedEvent(
                    type="repair_cycle.environment_verification_completed",
                    timestamp=datetime.now(UTC).isoformat(),
                    source="production_environment_repair",
                    work_item_id=context.work_item_id,
                    workflow_run_id=context.workflow_run_id,
                    test_type=config.test_type,
                    iteration=context.iteration,
                    healthy=verification_result.healthy,
                    checks_passed=verification_result.checks_passed,
                    checks_failed=verification_result.checks_failed,
                    duration_seconds=verification_result.duration_seconds,
                ),
                "verification completed event",
                context.workflow_run_id,
            )

            return verification_result

        except Exception as e:
            logger.error(
                "Environment verification failed with exception",
                extra={
                    "workflow_run_id": context.workflow_run_id,
                    "test_type": config.test_type.value,
                    "error": str(e),
                    "error_type": type(e).__name__,
                    "error_id": ErrorRegistry.ERR_REPAIR_CYCLE_ERROR,
                },
                exc_info=True,
            )
            # Emit verification completion event with error information
            end_time = datetime.now(UTC)
            final_duration = (end_time - start_time).total_seconds()
            self._emit_event_safely(
                EnvironmentVerificationCompletedEvent(
                    type="repair_cycle.environment_verification_completed",
                    timestamp=datetime.now(UTC).isoformat(),
                    source="production_environment_repair",
                    work_item_id=context.work_item_id,
                    workflow_run_id=context.workflow_run_id,
                    test_type=config.test_type,
                    iteration=context.iteration,
                    healthy=False,
                    checks_passed=(),
                    checks_failed=("timeout",) if isinstance(e, TimeoutError) else ("exception",),
                    duration_seconds=final_duration,
                ),
                "verification completed event",
                context.workflow_run_id,
            )
            raise
