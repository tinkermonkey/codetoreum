"""Production environment repair adapter with LLM integration.

Implements IEnvironmentRepairService by orchestrating environment rebuild and
verification operations through LLM agents. Handles both operations with independent
timeout enforcement and comprehensive event emission.

Key responsibilities:
1. Environment rebuild: Coordinate re-provisioning of dependencies and configuration
2. Environment verification: Validate that the rebuilt environment is healthy
3. Event emission: Emit all 4 domain events via injected IEventEmitter
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

if TYPE_CHECKING:
    from codetoreum.infrastructure.resilience.interfaces import ICircuitBreaker
    from codetoreum.ports.output.llm_provider import AgentLLMFactory, ExecutionResult, ILLMProvider

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
from codetoreum.ports.output.environment_repair_service import IEnvironmentRepairService
from codetoreum.ports.output.event_emitter import IEventEmitter, NullEventEmitter
from codetoreum.ports.output.repair_cycle_service import RepairCycleContext

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
            llm_factory=lambda agent_name: llm_provider,
            repair_config=config,
            event_emitter=event_emitter
        )

        result = await adapter.rebuild_environment(
            project="my-project",
            config=test_config,
            context=context
        )
    """

    def __init__(
        self,
        llm_factory: AgentLLMFactory,
        repair_config: EnvironmentRepairConfig | None = None,
        event_emitter: IEventEmitter | None = None,
        config: EnvironmentRepairAdapterConfig | None = None,
        circuit_breaker: ICircuitBreaker | None = None,
    ) -> None:
        """Initialize production environment repair adapter.

        Args:
            llm_factory: Async factory callable that takes agent name and returns configured ILLMProvider
            repair_config: Optional EnvironmentRepairConfig (uses defaults if not provided)
            event_emitter: Optional event emitter (uses null-object if not provided)
            config: Optional adapter-specific configuration (uses defaults if not provided)
            circuit_breaker: Optional circuit breaker for LLM call protection
        """
        self._llm_factory = llm_factory
        self.repair_config = repair_config or EnvironmentRepairConfig()
        self.event_emitter = event_emitter or NullEventEmitter()
        self.config = config or EnvironmentRepairAdapterConfig()
        self.circuit_breaker = circuit_breaker

    def _build_environment_rebuild_prompt(self, config: RepairTestRunConfig) -> str:
        """Build prompt for LLM to rebuild the test environment.

        Args:
            config: Test run configuration

        Returns:
            Prompt for LLM agent
        """
        test_type_desc = {
            RepairTestType.UNIT: "unit tests",
            RepairTestType.INTEGRATION: "integration tests",
            RepairTestType.E2E: "end-to-end tests",
        }.get(config.test_type, "tests")

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
        """
        test_type_desc = {
            RepairTestType.UNIT: "unit tests",
            RepairTestType.INTEGRATION: "integration tests",
            RepairTestType.E2E: "end-to-end tests",
        }.get(config.test_type, "tests")

        return f"""Please verify that the test environment is correctly configured and ready:
1. Check that all dependencies are properly installed
2. Verify environment variables are set correctly
3. Confirm that any required services are running
4. Test that the environment can support running {test_type_desc}

Return a JSON response with the verification status and any issues found."""

    async def _execute_llm_with_timeout(
        self,
        llm: ILLMProvider,
        prompt: str,
        operation: str,
        timeout_seconds: int,
        context: RepairCycleContext,
        extra_log: dict | None = None,
        error_message: str | None = None,
    ) -> ExecutionResult:
        """Execute an LLM call with timeout and optional circuit breaker.

        Centralizes timeout enforcement and error handling for all LLM calls,
        ensuring consistent timeout application and logging.

        Args:
            llm: LLM provider to execute
            prompt: Prompt to send to the LLM
            operation: Operation name for circuit breaker (e.g., "repair_cycle.rebuild_env")
            timeout_seconds: Timeout in seconds for this operation
            context: Repair cycle context with workflow details
            extra_log: Optional dict of additional logging context
            error_message: Optional custom error message prefix

        Returns:
            ExecutionResult from the LLM call

        Raises:
            TimeoutError: If the LLM call exceeds the configured timeout
        """
        try:
            coro = (
                self.circuit_breaker.call(llm.execute, operation, prompt=prompt)
                if self.circuit_breaker
                else llm.execute(prompt=prompt)
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
            # Get LLM for environment rebuild task
            llm, agent_name = await self._get_llm_for_subtask("env_rebuild", context)

            # Build and execute rebuild prompt
            prompt = self._build_environment_rebuild_prompt(config)
            result = await self._execute_llm_with_timeout(
                llm=llm,
                prompt=prompt,
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
                response_data = json.loads(result.content) if isinstance(result.content, str) else result.content
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
            # Get LLM for environment verification task
            llm, agent_name = await self._get_llm_for_subtask("env_verification", context)

            # Build and execute verification prompt
            prompt = self._build_environment_verify_prompt(config)
            result = await self._execute_llm_with_timeout(
                llm=llm,
                prompt=prompt,
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
                response_data = json.loads(result.content) if isinstance(result.content, str) else result.content
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

            verification_result = VerificationResult(
                healthy=healthy,
                checks_passed=tuple(checks_passed) if checks_passed else (),
                checks_failed=tuple(checks_failed) if checks_failed else (),
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

    async def _get_llm_for_subtask(self, sub_task: str, context: RepairCycleContext) -> tuple[ILLMProvider, str]:
        """Resolve the appropriate agent for a sub-task and return its LLM provider.

        Args:
            sub_task: Sub-task key (e.g., "env_rebuild", "env_verification")
            context: Repair cycle context with agent configuration

        Returns:
            Tuple of (ILLMProvider instance, resolved agent name)
        """
        agent_name = (
            context.agent_config.resolve_agent(sub_task, context.agent_name)
            if context.agent_config
            else context.agent_name
        )
        return await self._llm_factory(agent_name), agent_name
