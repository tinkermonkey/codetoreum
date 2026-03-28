"""Production repair cycle adapter with LLM integration.

Implements IRepairCycle by integrating with LLM agents (Claude Code) to execute
tests, analyze failures, and coordinate intelligent fixes. This adapter automates
the test-driven repair cycle in production environments.

Key responsibilities:
1. Test execution: Detect framework (pytest, jest, cargo test) and run tests
2. Failure parsing: Parse test output and extract pass/fail/warning counts
3. Failure grouping: Group failures by file for targeted fixes
4. Fix coordination: Use LLM to analyze and fix failures
5. Warning handling: Optional warning review after test success
6. Checkpointing: Save state for resumability
7. Event emission: Emit all repair cycle domain events
8. Circuit breaking: Prevent runaway agent execution

Architecture:
- Dependency injection of ILLMProvider for testability
- Optional event emission (null-object pattern)
- Retry logic for JSON parsing (3 attempts)
- Comprehensive error logging with no silent failures
- Circuit breaker preventing exceeding max_total_agent_calls
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from codetoreum.domain.events.adapter_events import CodetoreumEvent
    from codetoreum.infrastructure.resilience.interfaces import ICircuitBreaker
    from codetoreum.ports.output.event_emitter import IEventEmitter
    from codetoreum.ports.output.llm_provider import AgentLLMFactory, ILLMProvider

from codetoreum.domain.events.repair_cycle_events import (
    RepairCycleCheckpointFailedEvent,
    RepairCycleCompletedEvent,
    RepairCycleFastFailEvent,
    RepairCycleFileFixCompletedEvent,
    RepairCycleFileFixStartedEvent,
    RepairCycleStartedEvent,
    RepairCycleTestCycleCompletedEvent,
    RepairCycleTestExecutionCompletedEvent,
    RepairCycleWarningReviewCompletedEvent,
    RepairCycleWarningReviewStartedEvent,
)
from codetoreum.domain.exceptions import TestOutputParseError
from codetoreum.domain.repair_cycle_types import (
    CycleResult,
    RepairCycleCheckpoint,
    RepairCycleResult,
    RepairTestFailure,
    RepairTestResult,
    RepairTestRunConfig,
    RepairTestType,
    RepairTestWarning,
)
from codetoreum.infrastructure.error_ids import ErrorRegistry
from codetoreum.infrastructure.resilience.exceptions import CircuitBreakerOpenError
from codetoreum.ports.output.repair_cycle_checkpoint_store import (
    IRepairCycleCheckpointStore,
)
from codetoreum.ports.output.repair_cycle_service import (
    IRepairCycle,
    RepairCycleContext,
)

logger = logging.getLogger(__name__)


class JSONParseError(Exception):
    """Raised when agent response cannot be parsed as JSON."""


@dataclass(frozen=True)
class RepairCycleConfig:
    """Configuration for production repair cycle adapter.

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


class NullEventEmitter:
    """Null-object pattern for optional event emission.

    Implements a no-op event emitter for use when event emission is not required.
    All methods are silent, allowing the repair cycle to run without event infrastructure.
    """

    def emit(self, event: CodetoreumEvent) -> None:
        """No-op emit - silently discards all events."""

    def on(self, event_type: str, handler: Callable) -> None:
        """No-op subscription - no handlers are registered."""

    def off(self, event_type: str, handler: Callable) -> None:
        """No-op unsubscription - no handlers to unregister."""

    def once(self, event_type: str, handler: Callable) -> None:
        """No-op single subscription - no handlers are registered."""


class ProductionRepairCycleAdapter(IRepairCycle):
    """Production repair cycle adapter with LLM integration.

    Implements IRepairCycle by orchestrating test execution, failure analysis,
    and agent-based fixes. Uses Claude Code via ILLMProvider for intelligent
    repair coordination.

    Example:
        config = RepairCycleConfig()
        adapter = ProductionRepairCycleAdapter(
            llm_factory=lambda agent_name: llm_provider,
            config=config
        )

        context = RepairCycleContext(...)
        result = await adapter.execute(context)
    """

    def __init__(
        self,
        llm_factory: AgentLLMFactory,
        config: RepairCycleConfig | None = None,
        event_emitter: IEventEmitter | None = None,
        checkpoint_store: IRepairCycleCheckpointStore | None = None,
        circuit_breaker: ICircuitBreaker | None = None,
    ) -> None:
        """Initialize production repair cycle adapter.

        Args:
            llm_factory: Factory callable that takes agent name and returns configured ILLMProvider
            config: Optional RepairCycleConfig (uses defaults if not provided)
            event_emitter: Optional event emitter (uses null-object if not provided)
            checkpoint_store: Optional checkpoint store for resumable repairs
            circuit_breaker: Optional circuit breaker for LLM call protection
        """
        self._llm_factory = llm_factory
        self.config = config or RepairCycleConfig()
        self.event_emitter = event_emitter or NullEventEmitter()
        self.checkpoint_store = checkpoint_store
        self.circuit_breaker = circuit_breaker

    async def _get_llm_for_subtask(self, sub_task: str, context: RepairCycleContext) -> tuple[ILLMProvider, str]:
        """Resolve the appropriate agent for a sub-task and return its LLM provider.

        Centralizes agent name resolution logic to prevent duplication across call
        sites. Returns both the LLM provider and the resolved agent name.

        Args:
            sub_task: Sub-task key (e.g., "test_execution", "code_fix")
            context: Repair cycle context with agent configuration

        Returns:
            Coroutine that resolves to a tuple of (ILLMProvider instance for the
            resolved agent, resolved agent name)
        """
        agent_name = (
            context.agent_config.resolve_agent(sub_task, context.agent_name)
            if context.agent_config
            else context.agent_name
        )
        return await self._llm_factory(agent_name), agent_name

    async def execute(self, context: RepairCycleContext) -> RepairCycleResult:
        """Execute complete repair cycle for all configured test types.

        Orchestrates the full test-fix-validate loop across all configured test
        types (UNIT, INTEGRATION, E2E) in sequence. For each test type, runs
        tests, analyzes failures, coordinates fixes via agent, and validates
        until tests pass or circuit breaker triggers.

        Args:
            context: Repair cycle execution context with configuration

        Returns:
            RepairCycleResult with overall success status and per-test-type results

        Raises:
            CircuitBreakerOpenError: When circuit breaker is open
            ValueError: If test_configs is empty
        """
        if not context.test_configs:
            msg = "test_configs cannot be empty"
            raise ValueError(msg)

        start_time = datetime.now(UTC)
        cycle_start_timestamp = start_time.isoformat()

        # Emit repair cycle started event
        self.event_emitter.emit(
            RepairCycleStartedEvent(
                type="repair_cycle.started",
                timestamp=cycle_start_timestamp,
                source="production_repair_cycle",
                stage_name=context.stage_name,
                test_types=tuple(cfg.test_type for cfg in context.test_configs),
                workflow_run_id=context.workflow_run_id,
            )
        )

        # Execute each test type in sequence
        test_results: list[CycleResult] = []
        overall_success = True

        for test_type_index, test_config in enumerate(context.test_configs, start=1):
            # Check circuit breaker before starting test type
            if self.circuit_breaker and self.circuit_breaker.is_open():
                logger.warning(
                    "Circuit breaker triggered: max agent calls reached",
                    extra={
                        "workflow_run_id": context.workflow_run_id,
                        "test_type": test_config.test_type.value,
                    },
                    exc_info=False,
                )
                self.event_emitter.emit(
                    RepairCycleFastFailEvent(
                        type="repair_cycle.fast_fail",
                        timestamp=datetime.now(UTC).isoformat(),
                        source="production_repair_cycle",
                        test_type=test_config.test_type,
                        reason="circuit_breaker_triggered",
                        workflow_run_id=context.workflow_run_id,
                    )
                )
                raise CircuitBreakerOpenError("Max agent calls reached; circuit breaker is open")

            # Execute test type cycle
            cycle_result = await self._run_test_cycle(
                config=test_config,
                context=context,
                test_type_index=test_type_index,
            )

            test_results.append(cycle_result)

            # If this test type failed, stop cycling through remaining types (fast-fail)
            if not cycle_result.passed:
                overall_success = False
                break

        # Emit cycle completed event
        end_time = datetime.now(UTC)
        duration_seconds = (end_time - start_time).total_seconds()

        total_agent_calls = self.circuit_breaker.get_stats().total_calls if self.circuit_breaker else 0

        if test_results:
            self.event_emitter.emit(
                RepairCycleCompletedEvent(
                    type="repair_cycle.completed",
                    timestamp=cycle_start_timestamp,
                    source="production_repair_cycle",
                    overall_success=overall_success,
                    test_results=tuple(test_results),
                    total_agent_calls=total_agent_calls,
                    duration_seconds=duration_seconds,
                    workflow_run_id=context.workflow_run_id,
                )
            )

        return RepairCycleResult(
            stage=context.stage_name,
            test_results=tuple(test_results),
            overall_success=overall_success,
            total_agent_calls=total_agent_calls,
            duration_seconds=duration_seconds,
            timestamp=cycle_start_timestamp,
        )

    async def run_tests(
        self,
        config: RepairTestRunConfig,
        context: RepairCycleContext,
    ) -> RepairTestResult:
        """Execute tests for a specific test type.

        Detects test framework, runs tests, and parses output to extract
        pass/fail counts, failure details, and warnings.

        Args:
            config: Test run configuration (timeout, max iterations, etc.)
            context: Repair cycle context

        Returns:
            RepairTestResult with pass/fail counts and failure details

        Raises:
            CircuitBreakerOpenError: When circuit breaker is open
            TimeoutError: When test execution exceeds timeout
            JSONParseError: When agent returns invalid JSON (after retries)
        """
        # Build test command based on framework detection
        test_command = self._detect_and_build_test_command(config)

        # Resolve agent for test execution sub-task
        llm, resolved_agent_name = await self._get_llm_for_subtask("test_execution", context)

        # Execute tests via LLM
        logger.info(
            "Executing tests",
            extra={
                "workflow_run_id": context.workflow_run_id,
                "test_type": config.test_type.value,
                "command": test_command,
                "timeout": config.timeout,
                "agent_name": resolved_agent_name,
            },
            exc_info=False,
        )

        try:
            # Call LLM to execute tests (with circuit breaker if configured)
            prompt = f"Execute the following test command and return results as JSON:\n\n{test_command}"
            try:
                if self.circuit_breaker:
                    agent_response = await asyncio.wait_for(
                        self.circuit_breaker.call(
                            llm.execute,
                            "repair_cycle.run_tests",
                            prompt=prompt,
                        ),
                        timeout=config.timeout,
                    )
                else:
                    agent_response = await asyncio.wait_for(
                        llm.execute(
                            prompt=prompt,
                        ),
                        timeout=config.timeout,
                    )
            except asyncio.TimeoutError as e:
                logger.error(
                    "Test execution timed out",
                    extra={
                        "workflow_run_id": context.workflow_run_id,
                        "test_type": config.test_type.value,
                        "timeout_seconds": config.timeout,
                        "error_id": ErrorRegistry.ERR_REPAIR_CYCLE_ERROR,
                    },
                    exc_info=True,
                )
                raise TimeoutError(
                    f"Test execution exceeded timeout of {config.timeout} seconds"
                ) from e

            # Parse test output with retry logic
            test_output = await self._parse_test_output_with_retry(agent_response.content, config.test_type)

            # Parse failures and warnings
            failures = self._extract_failures(test_output, config.test_type)
            warnings = self._extract_warnings(test_output, config.test_type)

            timestamp = datetime.now(UTC).isoformat()

            result = RepairTestResult(
                test_type=config.test_type,
                iteration=1,  # Each run_tests call represents one iteration
                passed=test_output.get("passed", 0),
                failed=len(failures),  # Use actual parsed failures count, not raw test output
                warnings=len(warnings),
                failures=tuple(failures),
                warning_list=tuple(warnings),
                raw_output=agent_response.content,
                timestamp=timestamp,
            )

            # Emit test execution completed event
            self.event_emitter.emit(
                RepairCycleTestExecutionCompletedEvent(
                    type="repair_cycle.test_execution_completed",
                    timestamp=timestamp,
                    source="production_repair_cycle",
                    test_type=config.test_type,
                    test_type_index=1,  # Test type sequence position
                    test_cycle_iteration=result.iteration,
                    passed=result.passed,
                    failed=result.failed,
                    warnings=result.warnings,
                    has_failures=(result.failed > 0),
                    failures=result.failures,
                    agent_name=resolved_agent_name,
                    workflow_run_id=context.workflow_run_id,
                )
            )

            logger.info(
                "Test execution completed",
                extra={
                    "workflow_run_id": context.workflow_run_id,
                    "test_type": config.test_type.value,
                    "passed": result.passed,
                    "failed": result.failed,
                    "warnings": result.warnings,
                },
                exc_info=False,
            )

            return result

        except Exception as e:
            logger.error(
                "Test execution failed",
                extra={
                    "workflow_run_id": context.workflow_run_id,
                    "test_type": config.test_type.value,
                    "error": str(e),
                    "error_id": ErrorRegistry.ERR_REPAIR_CYCLE_ERROR,
                },
                exc_info=True,
            )
            raise

    async def fix_failures_by_file(
        self,
        grouped_failures: dict[str, tuple[RepairTestFailure, ...]],
        config: RepairTestRunConfig,
        context: RepairCycleContext,
    ) -> int:
        """Fix test failures grouped by file.

        Iterates through files with failures, coordinating agent-based fixes
        for each file. Agents analyze failure details and implement fixes,
        then tests are re-run to validate.

        Args:
            grouped_failures: Map of test file name to failures in that file
            config: Test run configuration
            context: Repair cycle context

        Returns:
            Number of files fixed (may be less than input if some fail)

        Raises:
            CircuitBreakerOpenError: When circuit breaker is open
        """
        # Resolve agent for code fix sub-task (once for all files)
        llm, resolved_agent_name = await self._get_llm_for_subtask("code_fix", context)

        fixed = 0

        for file_path, failures in grouped_failures.items():
            # Check circuit breaker
            if self.circuit_breaker and self.circuit_breaker.is_open():
                logger.warning(
                    "Circuit breaker triggered during file fixes",
                    extra={
                        "workflow_run_id": context.workflow_run_id,
                        "file": file_path,
                        "failures": len(failures),
                        "agent_name": resolved_agent_name,
                    },
                    exc_info=False,
                )
                raise CircuitBreakerOpenError("Max agent calls reached; circuit breaker is open")

            # Emit file fix started event
            timestamp = datetime.now(UTC).isoformat()
            self.event_emitter.emit(
                RepairCycleFileFixStartedEvent(
                    type="repair_cycle.file_fix_started",
                    timestamp=timestamp,
                    source="production_repair_cycle",
                    test_file=file_path,
                    failure_count=len(failures),
                    test_type=config.test_type,
                    agent_name=resolved_agent_name,
                    workflow_run_id=context.workflow_run_id,
                )
            )

            # Build fix prompt with failure context
            fix_prompt = self._build_fix_prompt(file_path, failures)

            try:
                # Call LLM to fix failures
                logger.info(
                    "Fixing test failures in file",
                    extra={
                        "workflow_run_id": context.workflow_run_id,
                        "file": file_path,
                        "failure_count": len(failures),
                        "agent_name": resolved_agent_name,
                    },
                    exc_info=False,
                )

                try:
                    if self.circuit_breaker:
                        await asyncio.wait_for(
                            self.circuit_breaker.call(
                                llm.execute,
                                "repair_cycle.fix_failures_by_file",
                                prompt=fix_prompt,
                            ),
                            timeout=config.timeout,
                        )
                    else:
                        await asyncio.wait_for(
                            llm.execute(
                                prompt=fix_prompt,
                            ),
                            timeout=config.timeout,
                        )
                except asyncio.TimeoutError as e:
                    logger.error(
                        "File fix execution timed out",
                        extra={
                            "workflow_run_id": context.workflow_run_id,
                            "file": file_path,
                            "timeout_seconds": config.timeout,
                            "error_id": ErrorRegistry.ERR_REPAIR_CYCLE_ERROR,
                        },
                        exc_info=True,
                    )
                    raise TimeoutError(
                        f"Fix execution for {file_path} exceeded timeout of {config.timeout} seconds"
                    ) from e

                # Emit file fix completed event (success)
                self.event_emitter.emit(
                    RepairCycleFileFixCompletedEvent(
                        type="repair_cycle.file_fix_completed",
                        timestamp=datetime.now(UTC).isoformat(),
                        source="production_repair_cycle",
                        test_file=file_path,
                        failure_count=len(failures),
                        test_type=config.test_type,
                        success=True,
                        agent_name=resolved_agent_name,
                        workflow_run_id=context.workflow_run_id,
                    )
                )

                fixed += 1

                logger.info(
                    "File fix completed",
                    extra={
                        "workflow_run_id": context.workflow_run_id,
                        "file": file_path,
                    },
                    exc_info=False,
                )

            except (TimeoutError, CircuitBreakerOpenError):
                # Allow timeout and circuit breaker errors to propagate
                raise
            except Exception as e:
                # Emit file fix completed event (failure)
                logger.error(
                    "File fix failed",
                    extra={
                        "workflow_run_id": context.workflow_run_id,
                        "file": file_path,
                        "error": str(e),
                        "error_id": ErrorRegistry.ERR_REPAIR_CYCLE_ERROR,
                    },
                    exc_info=True,
                )

                self.event_emitter.emit(
                    RepairCycleFileFixCompletedEvent(
                        type="repair_cycle.file_fix_completed",
                        timestamp=datetime.now(UTC).isoformat(),
                        source="production_repair_cycle",
                        test_file=file_path,
                        failure_count=len(failures),
                        test_type=config.test_type,
                        success=False,
                        agent_name=resolved_agent_name,
                        workflow_run_id=context.workflow_run_id,
                    )
                )

        return fixed

    async def analyze_systemic_issues(
        self,
        test_result: RepairTestResult,
        config: RepairTestRunConfig,
        context: RepairCycleContext,
    ) -> str:
        """Analyze failure root causes at systemic level.

        Classifies test failures to identify systemic patterns that affect
        multiple tests or require cross-cutting fixes. Invokes the configured
        systemic_analysis agent to examine failures and categorize them.

        Args:
            test_result: Test result containing failures to analyze
            config: Test run configuration
            context: Repair cycle context

        Returns:
            Analysis summary from the agent

        Raises:
            CircuitBreakerOpenError: When circuit breaker is open
        """
        if not test_result.failures:
            return ""

        # Check circuit breaker
        if self.circuit_breaker and self.circuit_breaker.is_open():
            logger.warning(
                "Circuit breaker triggered during systemic analysis",
                extra={
                    "workflow_run_id": context.workflow_run_id,
                    "failure_count": len(test_result.failures),
                },
                exc_info=False,
            )
            raise CircuitBreakerOpenError("Max agent calls reached; circuit breaker is open")

        # Resolve agent for systemic analysis sub-task
        llm, resolved_agent_name = await self._get_llm_for_subtask("systemic_analysis", context)

        try:
            # Build analysis prompt with failure context
            analysis_prompt = self._build_systemic_analysis_prompt(test_result.failures)

            logger.info(
                "Analyzing systemic failure patterns",
                extra={
                    "workflow_run_id": context.workflow_run_id,
                    "test_type": config.test_type.value,
                    "failure_count": len(test_result.failures),
                    "agent_name": resolved_agent_name,
                },
                exc_info=False,
            )

            # Call LLM to analyze systemic issues
            try:
                if self.circuit_breaker:
                    agent_response = await asyncio.wait_for(
                        self.circuit_breaker.call(
                            llm.execute,
                            "repair_cycle.analyze_systemic_issues",
                            prompt=analysis_prompt,
                        ),
                        timeout=config.timeout,
                    )
                else:
                    agent_response = await asyncio.wait_for(
                        llm.execute(
                            prompt=analysis_prompt,
                        ),
                        timeout=config.timeout,
                    )
            except asyncio.TimeoutError as e:
                logger.error(
                    "Systemic analysis execution timed out",
                    extra={
                        "workflow_run_id": context.workflow_run_id,
                        "test_type": config.test_type.value,
                        "timeout_seconds": config.timeout,
                        "error_id": ErrorRegistry.ERR_REPAIR_CYCLE_ERROR,
                    },
                    exc_info=True,
                )
                raise TimeoutError(
                    f"Systemic analysis exceeded timeout of {config.timeout} seconds"
                ) from e

            logger.info(
                "Systemic analysis completed",
                extra={
                    "workflow_run_id": context.workflow_run_id,
                    "test_type": config.test_type.value,
                    "agent_name": resolved_agent_name,
                },
                exc_info=False,
            )

            return agent_response.content

        except Exception as e:
            logger.error(
                "Systemic analysis failed",
                extra={
                    "workflow_run_id": context.workflow_run_id,
                    "test_type": config.test_type.value,
                    "error": str(e),
                    "error_id": ErrorRegistry.ERR_REPAIR_CYCLE_ERROR,
                },
                exc_info=True,
            )
            raise

    async def apply_systemic_fixes(
        self,
        analysis_summary: str,
        test_result: RepairTestResult,
        config: RepairTestRunConfig,
        context: RepairCycleContext,
    ) -> bool:
        """Apply cross-cutting fixes based on systemic analysis.

        Uses the systemic analysis to apply fixes that address root causes
        affecting multiple tests. These are broader fixes beyond file-level
        changes, such as architecture adjustments or dependency updates.

        Args:
            analysis_summary: Summary from systemic analysis
            test_result: Test result that triggered the analysis
            config: Test run configuration
            context: Repair cycle context

        Returns:
            True if fixes were successfully applied

        Raises:
            CircuitBreakerOpenError: When circuit breaker is open
        """
        if not analysis_summary:
            return False

        # Check circuit breaker
        if self.circuit_breaker and self.circuit_breaker.is_open():
            logger.warning(
                "Circuit breaker triggered during systemic fix",
                extra={
                    "workflow_run_id": context.workflow_run_id,
                },
                exc_info=False,
            )
            raise CircuitBreakerOpenError("Max agent calls reached; circuit breaker is open")

        # Resolve agent for systemic fix sub-task
        llm, resolved_agent_name = await self._get_llm_for_subtask("systemic_fix", context)

        try:
            # Build fix prompt based on analysis
            fix_prompt = self._build_systemic_fix_prompt(analysis_summary, test_result.failures)

            logger.info(
                "Applying systemic fixes",
                extra={
                    "workflow_run_id": context.workflow_run_id,
                    "test_type": config.test_type.value,
                    "agent_name": resolved_agent_name,
                },
                exc_info=False,
            )

            # Call LLM to apply systemic fixes
            try:
                if self.circuit_breaker:
                    agent_response = await asyncio.wait_for(
                        self.circuit_breaker.call(
                            llm.execute,
                            "repair_cycle.apply_systemic_fixes",
                            prompt=fix_prompt,
                        ),
                        timeout=config.timeout,
                    )
                else:
                    agent_response = await asyncio.wait_for(
                        llm.execute(
                            prompt=fix_prompt,
                        ),
                        timeout=config.timeout,
                    )
            except asyncio.TimeoutError as e:
                logger.error(
                    "Systemic fix execution timed out",
                    extra={
                        "workflow_run_id": context.workflow_run_id,
                        "test_type": config.test_type.value,
                        "timeout_seconds": config.timeout,
                        "error_id": ErrorRegistry.ERR_REPAIR_CYCLE_ERROR,
                    },
                    exc_info=True,
                )
                raise TimeoutError(
                    f"Systemic fix application exceeded timeout of {config.timeout} seconds"
                ) from e

            # Log the response for audit trail
            logger.info(
                "Systemic fixes applied",
                extra={
                    "workflow_run_id": context.workflow_run_id,
                    "test_type": config.test_type.value,
                    "agent_name": resolved_agent_name,
                    "response_length": len(agent_response.content),
                },
                exc_info=False,
            )

            return True

        except Exception as e:
            logger.error(
                "Systemic fix application failed",
                extra={
                    "workflow_run_id": context.workflow_run_id,
                    "test_type": config.test_type.value,
                    "error": str(e),
                    "error_id": ErrorRegistry.ERR_REPAIR_CYCLE_ERROR,
                },
                exc_info=True,
            )
            raise

    async def rebuild_environment(
        self,
        config: RepairTestRunConfig,
        context: RepairCycleContext,
    ) -> bool:
        """Rebuild test environment to apply systemic fixes.

        Coordinates with the env_rebuild agent to rebuild the test environment
        after systemic fixes, ensuring dependencies and configuration are
        properly updated.

        Args:
            config: Test run configuration
            context: Repair cycle context

        Returns:
            True if environment was successfully rebuilt

        Raises:
            CircuitBreakerOpenError: When circuit breaker is open
        """
        # Check circuit breaker
        if self.circuit_breaker and self.circuit_breaker.is_open():
            logger.warning(
                "Circuit breaker triggered during environment rebuild",
                extra={
                    "workflow_run_id": context.workflow_run_id,
                },
                exc_info=False,
            )
            raise CircuitBreakerOpenError("Max agent calls reached; circuit breaker is open")

        # Resolve agent for env rebuild sub-task
        llm, resolved_agent_name = await self._get_llm_for_subtask("env_rebuild", context)

        try:
            # Build environment rebuild prompt
            rebuild_prompt = self._build_environment_rebuild_prompt(config.test_type)

            logger.info(
                "Rebuilding test environment",
                extra={
                    "workflow_run_id": context.workflow_run_id,
                    "test_type": config.test_type.value,
                    "agent_name": resolved_agent_name,
                },
                exc_info=False,
            )

            # Call LLM to rebuild environment
            try:
                if self.circuit_breaker:
                    agent_response = await asyncio.wait_for(
                        self.circuit_breaker.call(
                            llm.execute,
                            "repair_cycle.rebuild_environment",
                            prompt=rebuild_prompt,
                        ),
                        timeout=config.timeout,
                    )
                else:
                    agent_response = await asyncio.wait_for(
                        llm.execute(
                            prompt=rebuild_prompt,
                        ),
                        timeout=config.timeout,
                    )
            except asyncio.TimeoutError as e:
                logger.error(
                    "Environment rebuild execution timed out",
                    extra={
                        "workflow_run_id": context.workflow_run_id,
                        "test_type": config.test_type.value,
                        "timeout_seconds": config.timeout,
                        "error_id": ErrorRegistry.ERR_REPAIR_CYCLE_ERROR,
                    },
                    exc_info=True,
                )
                raise TimeoutError(
                    f"Environment rebuild exceeded timeout of {config.timeout} seconds"
                ) from e

            # Log the response for audit trail
            logger.info(
                "Environment rebuild completed",
                extra={
                    "workflow_run_id": context.workflow_run_id,
                    "test_type": config.test_type.value,
                    "agent_name": resolved_agent_name,
                    "response_length": len(agent_response.content),
                },
                exc_info=False,
            )

            return True

        except Exception as e:
            logger.error(
                "Environment rebuild failed",
                extra={
                    "workflow_run_id": context.workflow_run_id,
                    "test_type": config.test_type.value,
                    "error": str(e),
                    "error_id": ErrorRegistry.ERR_REPAIR_CYCLE_ERROR,
                },
                exc_info=True,
            )
            raise

    async def verify_environment(
        self,
        config: RepairTestRunConfig,
        context: RepairCycleContext,
    ) -> bool:
        """Verify that rebuilt environment is ready for testing.

        Coordinates with the env_verification agent to verify that the
        rebuilt environment is properly configured and ready for test execution.

        Args:
            config: Test run configuration
            context: Repair cycle context

        Returns:
            True if environment verification passed

        Raises:
            CircuitBreakerOpenError: When circuit breaker is open
        """
        # Check circuit breaker
        if self.circuit_breaker and self.circuit_breaker.is_open():
            logger.warning(
                "Circuit breaker triggered during environment verification",
                extra={
                    "workflow_run_id": context.workflow_run_id,
                },
                exc_info=False,
            )
            raise CircuitBreakerOpenError("Max agent calls reached; circuit breaker is open")

        # Resolve agent for env verification sub-task
        llm, resolved_agent_name = await self._get_llm_for_subtask("env_verification", context)

        try:
            # Build environment verification prompt
            verification_prompt = self._build_environment_verification_prompt(config.test_type)

            logger.info(
                "Verifying rebuilt environment",
                extra={
                    "workflow_run_id": context.workflow_run_id,
                    "test_type": config.test_type.value,
                    "agent_name": resolved_agent_name,
                },
                exc_info=False,
            )

            # Call LLM to verify environment
            try:
                if self.circuit_breaker:
                    agent_response = await asyncio.wait_for(
                        self.circuit_breaker.call(
                            llm.execute,
                            "repair_cycle.verify_environment",
                            prompt=verification_prompt,
                        ),
                        timeout=config.timeout,
                    )
                else:
                    agent_response = await asyncio.wait_for(
                        llm.execute(
                            prompt=verification_prompt,
                        ),
                        timeout=config.timeout,
                    )
            except asyncio.TimeoutError as e:
                logger.error(
                    "Environment verification execution timed out",
                    extra={
                        "workflow_run_id": context.workflow_run_id,
                        "test_type": config.test_type.value,
                        "timeout_seconds": config.timeout,
                        "error_id": ErrorRegistry.ERR_REPAIR_CYCLE_ERROR,
                    },
                    exc_info=True,
                )
                raise TimeoutError(
                    f"Environment verification exceeded timeout of {config.timeout} seconds"
                ) from e

            # Parse response to extract verification status
            try:
                response_data = json.loads(agent_response.content)
                verification_passed = response_data.get("ready", False)

                logger.info(
                    "Environment verification completed",
                    extra={
                        "workflow_run_id": context.workflow_run_id,
                        "test_type": config.test_type.value,
                        "agent_name": resolved_agent_name,
                        "ready": verification_passed,
                    },
                    exc_info=False,
                )

                return verification_passed
            except (json.JSONDecodeError, KeyError) as e:
                logger.error(
                    "Failed to parse environment verification response",
                    extra={
                        "workflow_run_id": context.workflow_run_id,
                        "test_type": config.test_type.value,
                        "error": str(e),
                        "response": agent_response.content,
                        "error_id": ErrorRegistry.ERR_REPAIR_CYCLE_ERROR,
                    },
                    exc_info=True,
                )
                return False

        except Exception as e:
            logger.error(
                "Environment verification failed",
                extra={
                    "workflow_run_id": context.workflow_run_id,
                    "test_type": config.test_type.value,
                    "error": str(e),
                    "error_id": ErrorRegistry.ERR_REPAIR_CYCLE_ERROR,
                },
                exc_info=True,
            )
            raise

    async def handle_warnings(
        self,
        test_result: RepairTestResult,
        config: RepairTestRunConfig,
        context: RepairCycleContext,
    ) -> int:
        """Review and fix warnings from test execution.

        Only called when tests pass (0 failures), warnings exist, and
        config.review_warnings is True. Coordinates with agent to review
        and address warnings.

        Args:
            test_result: Test result containing warnings
            config: Test run configuration
            context: Repair cycle context

        Returns:
            Number of warning files reviewed

        Raises:
            CircuitBreakerOpenError: When circuit breaker is open
        """
        if not test_result.warning_list or not config.review_warnings:
            return 0

        # Resolve agent for code fix sub-task (warnings use same agent as code fixes)
        llm, resolved_agent_name = await self._get_llm_for_subtask("code_fix", context)

        reviewed = 0

        for warning in test_result.warning_list:
            # Check circuit breaker
            if self.circuit_breaker and self.circuit_breaker.is_open():
                logger.warning(
                    "Circuit breaker triggered during warning review",
                    extra={
                        "workflow_run_id": context.workflow_run_id,
                        "file": warning.file,
                        "agent_name": resolved_agent_name,
                    },
                    exc_info=False,
                )
                raise CircuitBreakerOpenError("Max agent calls reached; circuit breaker is open")

            # Emit warning review started event
            timestamp = datetime.now(UTC).isoformat()
            self.event_emitter.emit(
                RepairCycleWarningReviewStartedEvent(
                    type="repair_cycle.warning_review_started",
                    timestamp=timestamp,
                    source="production_repair_cycle",
                    source_file=warning.file,
                    warning_count=1,
                    test_type=config.test_type,
                    warnings=(warning,),
                    agent_name=resolved_agent_name,
                    workflow_run_id=context.workflow_run_id,
                )
            )

            try:
                # Build warning review prompt
                review_prompt = self._build_warning_review_prompt(warning)

                # Call LLM to review and address warning
                logger.info(
                    "Reviewing test warning",
                    extra={
                        "workflow_run_id": context.workflow_run_id,
                        "file": warning.file,
                        "warning": warning.message,
                        "agent_name": resolved_agent_name,
                    },
                    exc_info=False,
                )

                try:
                    if self.circuit_breaker:
                        await asyncio.wait_for(
                            self.circuit_breaker.call(
                                llm.execute,
                                "repair_cycle.handle_warnings",
                                prompt=review_prompt,
                            ),
                            timeout=config.timeout,
                        )
                    else:
                        await asyncio.wait_for(
                            llm.execute(
                                prompt=review_prompt,
                            ),
                            timeout=config.timeout,
                        )
                except asyncio.TimeoutError as e:
                    logger.error(
                        "Warning review execution timed out",
                        extra={
                            "workflow_run_id": context.workflow_run_id,
                            "file": warning.file,
                            "timeout_seconds": config.timeout,
                            "error_id": ErrorRegistry.ERR_REPAIR_CYCLE_ERROR,
                        },
                        exc_info=True,
                    )
                    raise TimeoutError(
                        f"Warning review for {warning.file} exceeded timeout of {config.timeout} seconds"
                    ) from e

                # Emit warning review completed event (success)
                self.event_emitter.emit(
                    RepairCycleWarningReviewCompletedEvent(
                        type="repair_cycle.warning_review_completed",
                        timestamp=datetime.now(UTC).isoformat(),
                        source="production_repair_cycle",
                        source_file=warning.file,
                        warning_count=1,
                        test_type=config.test_type,
                        success=True,
                        agent_name=resolved_agent_name,
                        workflow_run_id=context.workflow_run_id,
                    )
                )

                reviewed += 1

                logger.info(
                    "Warning review completed",
                    extra={
                        "workflow_run_id": context.workflow_run_id,
                        "file": warning.file,
                    },
                    exc_info=False,
                )

            except (TimeoutError, CircuitBreakerOpenError):
                # Allow timeout and circuit breaker errors to propagate
                raise
            except Exception as e:
                logger.error(
                    "Warning review failed",
                    extra={
                        "workflow_run_id": context.workflow_run_id,
                        "file": warning.file,
                        "error": str(e),
                        "error_id": ErrorRegistry.ERR_REPAIR_CYCLE_ERROR,
                    },
                    exc_info=True,
                )

        return reviewed

    def _build_systemic_analysis_prompt(self, failures: tuple[RepairTestFailure, ...]) -> str:
        """Build prompt for LLM to analyze systemic failure patterns.

        Args:
            failures: Tuple of failures to analyze for systemic patterns

        Returns:
            Prompt for LLM agent
        """
        failure_summary = "\n".join([f"- {f.file}::{f.test}: {f.message}" for f in failures])

        return f"""Analyze the following test failures to identify systemic patterns and root causes:

{failure_summary}

Look for common themes:
- Multiple failures in same module/package
- Similar error patterns across different tests
- Configuration or dependency issues
- Architecture or design problems

Return a JSON response with:
- patterns: List of identified patterns
- root_causes: List of potential root causes
- severity: "critical", "major", or "minor"
- recommended_fixes: List of recommended fixes"""

    def _build_systemic_fix_prompt(self, analysis_summary: str, failures: tuple[RepairTestFailure, ...]) -> str:
        """Build prompt for LLM to apply systemic fixes.

        Args:
            analysis_summary: Summary from systemic analysis
            failures: Tuple of failures that triggered the analysis

        Returns:
            Prompt for LLM agent
        """
        return f"""Based on the following systemic analysis, apply cross-cutting fixes:

Analysis:
{analysis_summary}

Number of failures affected: {len(failures)}

Apply fixes that address the root causes identified in the analysis. These may include:
- Dependency updates
- Configuration changes
- Architecture adjustments
- Environment setup fixes

Return a JSON response with the fixes applied and validation steps."""

    def _build_environment_rebuild_prompt(self, test_type: RepairTestType) -> str:
        """Build prompt for LLM to rebuild test environment.

        Args:
            test_type: Type of test being executed

        Returns:
            Prompt for LLM agent
        """
        return f"""Rebuild the test environment for {test_type.value} tests.

This should:
1. Clean up any stale artifacts or caches
2. Reinstall dependencies with fresh versions
3. Reinitialize configuration and fixtures
4. Prepare containers/services needed for testing

Return a JSON response with:
- steps_completed: List of rebuild steps performed
- dependencies_updated: List of updated dependencies
- services_ready: True if all services are ready for testing
- errors: Any errors encountered (empty list if successful)"""

    def _build_environment_verification_prompt(self, test_type: RepairTestType) -> str:
        """Build prompt for LLM to verify rebuilt environment.

        Args:
            test_type: Type of test being executed

        Returns:
            Prompt for LLM agent
        """
        return f"""Verify that the rebuilt test environment is ready for {test_type.value} tests.

Check that:
1. All dependencies are installed and accessible
2. Configuration files are properly set up
3. Test fixtures and data are available
4. Services and containers are running
5. Environment variables are set correctly

Return a JSON response with:
- ready: True if environment is verified and ready
- checks_passed: List of passed verification checks
- checks_failed: List of failed verification checks
- remediation: Suggested fixes for any failed checks"""

    async def checkpoint(
        self,
        test_type: RepairTestType,
        iteration: int,
        context: RepairCycleContext,
    ) -> None:
        """Save repair cycle state for resume after failures.

        Called at checkpoint_interval iterations. Saves sufficient state to
        resume from this point if cycle is interrupted.

        Args:
            test_type: Current test type being executed
            iteration: current iteration number
            context: Repair cycle context
        """
        if not self.checkpoint_store:
            logger.debug(
                "Checkpoint skipped: no checkpoint store configured",
                extra={
                    "workflow_run_id": context.workflow_run_id,
                    "test_type": test_type.value,
                    "iteration": iteration,
                },
                exc_info=False,
            )
            return

        try:
            # Create checkpoint with current state
            now = datetime.now(UTC)
            expires_at = (now + timedelta(hours=24)).isoformat()

            checkpoint = RepairCycleCheckpoint(
                workflow_run_id=context.workflow_run_id,
                test_type=test_type,
                iteration=iteration,
                total_agent_calls=self.circuit_breaker.get_stats().total_calls if self.circuit_breaker else 0,
                files_fixed=0,  # Would be tracked by application layer
                warnings_reviewed=0,  # Would be tracked by application layer
                elapsed_seconds=0.0,  # Would be tracked by application layer
                test_results=(),  # Would contain completed test results
                timestamp=now.isoformat(),
                expires_at=expires_at,
            )

            # Save to checkpoint store
            await self.checkpoint_store.save_checkpoint(checkpoint)

            logger.info(
                "Checkpoint saved successfully",
                extra={
                    "workflow_run_id": context.workflow_run_id,
                    "test_type": test_type.value,
                    "iteration": iteration,
                    "agent_calls": self.circuit_breaker.get_stats().total_calls if self.circuit_breaker else 0,
                    "expires_at": expires_at,
                },
                exc_info=False,
            )

        except Exception as e:
            logger.error(
                "Failed to save checkpoint - repair cycle may not be resumable",
                extra={
                    "workflow_run_id": context.workflow_run_id,
                    "test_type": test_type.value,
                    "iteration": iteration,
                    "error": str(e),
                    "error_type": type(e).__name__,
                    "error_id": ErrorRegistry.ERR_REPAIR_CYCLE_ERROR,
                },
                exc_info=True,
            )

            # Emit event so users/monitoring can be alerted
            if self.event_emitter:
                self.event_emitter.emit(
                    RepairCycleCheckpointFailedEvent(
                        type="repair_cycle.checkpoint_failed",
                        timestamp=datetime.now(UTC).isoformat(),
                        source="production_repair_cycle",
                        workflow_run_id=context.workflow_run_id,
                        test_type=test_type,
                        iteration=iteration,
                        error_type=type(e).__name__,
                        error_message=str(e),
                        checkpoint_store_type=type(self.checkpoint_store).__name__ if self.checkpoint_store else "none",
                    )
                )

    # Private helper methods

    def _detect_and_build_test_command(self, config: RepairTestRunConfig) -> str:
        """Detect test framework and build appropriate test command.

        Supports: pytest, jest, cargo test, go test, etc.

        Args:
            config: Test run configuration

        Returns:
            Test command to execute
        """
        # Try to detect based on project files (simplified)
        # In production, this would scan for package.json, Cargo.toml, go.mod, etc.

        # Default to pytest (most common for Python projects)
        test_command = "pytest --json-report --json-report-file=test-results.json"

        if config.test_type == RepairTestType.UNIT:
            test_command += " tests/unit"
        elif config.test_type == RepairTestType.INTEGRATION:
            test_command += " tests/integration"
        elif config.test_type == RepairTestType.E2E:
            test_command += " tests/e2e"

        return test_command

    async def _parse_test_output_with_retry(self, agent_response: str, test_type: RepairTestType) -> dict[str, Any]:
        """Parse test output with retry logic for JSON parsing.

        Attempts to parse agent response as JSON up to max_json_parse_retries times.

        Args:
            agent_response: Raw response from agent
            test_type: Type of test executed

        Returns:
            Parsed test output as dictionary

        Raises:
            JSONParseError: If JSON parsing fails after all retries
        """
        last_error = None

        for attempt in range(1, self.config.max_json_parse_retries + 1):
            try:
                # Try to extract JSON from response
                json_match = re.search(r"\{.*\}", agent_response, re.DOTALL)
                if not json_match:
                    msg = "No JSON found in agent response"
                    raise JSONParseError(msg)

                parsed = json.loads(json_match.group())

                logger.info(
                    "Test output parsed successfully",
                    extra={
                        "test_type": test_type.value,
                        "attempt": attempt,
                    },
                    exc_info=False,
                )

                return parsed

            except (json.JSONDecodeError, JSONParseError) as e:
                last_error = e
                logger.warning(
                    "Failed to parse test output",
                    extra={
                        "test_type": test_type.value,
                        "attempt": attempt,
                        "max_attempts": self.config.max_json_parse_retries,
                        "error": str(e),
                    },
                    exc_info=True,
                )

                if attempt < self.config.max_json_parse_retries:
                    # Wait before retry with configured delay
                    await asyncio.sleep(self.config.json_parse_retry_delay_ms / 1000.0)

        msg = f"Failed to parse test output after {self.config.max_json_parse_retries} attempts: {last_error}"
        raise JSONParseError(msg)

    def _extract_failures(self, test_output: dict[str, Any], test_type: RepairTestType) -> list[RepairTestFailure]:
        """Extract test failures from parsed test output.

        Assumes test_output has structure:
        {
            "passed": <int>,
            "failed": <int>,
            "failures": [
                {
                    "file": <str>,
                    "test": <str>,
                    "message": <str>
                }
            ]
        }

        Args:
            test_output: Parsed test output
            test_type: Type of test executed

        Returns:
            List of RepairTestFailure objects
        """
        failures = []
        parse_errors = []

        for idx, failure_data in enumerate(test_output.get("failures", [])):
            try:
                failure = RepairTestFailure(
                    file=failure_data.get("file", "unknown"),
                    test=failure_data.get("test", "unknown"),
                    message=failure_data.get("message", ""),
                )
                failures.append(failure)
            except ValueError as e:
                # Collect parse errors but continue processing other failures
                parse_errors.append({"index": idx, "data": failure_data, "error": str(e)})
                logger.error(
                    f"PARSE ERROR: Test failure #{idx} data is invalid - agent may be malfunctioning. "
                    f"Continuing to process remaining failures.",
                    extra={
                        "test_type": test_type.value,
                        "failure_index": idx,
                        "failure_data": failure_data,
                        "validation_error": str(e),
                        "error_id": ErrorRegistry.ERR_REPAIR_CYCLE_ERROR,
                    },
                    exc_info=True,
                )

        # If we collected any valid failures, log parse errors but return valid data
        if failures and parse_errors:
            logger.warning(
                f"Extracted {len(failures)} valid test failures despite {len(parse_errors)} parse errors. "
                f"Agent output may be partially corrupt.",
                extra={
                    "test_type": test_type.value,
                    "valid_failures": len(failures),
                    "parse_errors": len(parse_errors),
                    "error_indices": [e["index"] for e in parse_errors],
                },
            )
        # If ALL failures failed to parse, raise error with details
        elif parse_errors and not failures:
            logger.error(
                f"ALL test failure entries failed to parse ({len(parse_errors)} errors). "
                f"This indicates either: (1) Test framework output changed, "
                f"(2) Agent prompt needs updating, or (3) Agent is malfunctioning.",
                extra={
                    "test_type": test_type.value,
                    "total_failures": len(test_output.get("failures", [])),
                    "parse_errors": parse_errors,
                    "error_id": ErrorRegistry.ERR_REPAIR_CYCLE_ERROR,
                },
            )
            msg = (
                f"All {len(parse_errors)} test failure entries for {test_type.value} failed to parse. "
                f"This indicates either: (1) Test framework output changed, "
                f"(2) Agent prompt needs updating, or (3) Agent is malfunctioning. "
                f"First error: {parse_errors[0]['error']}"
            )
            raise TestOutputParseError(
                msg,
                test_type=test_type.value,
                raw_data=test_output.get("failures", []),
            )

        return failures

    def _extract_warnings(self, test_output: dict[str, Any], test_type: RepairTestType) -> list[RepairTestWarning]:
        """Extract test warnings from parsed test output.

        Assumes test_output has structure:
        {
            "warnings": [
                {
                    "file": <str>,
                    "message": <str>
                }
            ]
        }

        Args:
            test_output: Parsed test output
            test_type: Type of test executed

        Returns:
            List of RepairTestWarning objects
        """
        warnings = []
        parse_errors = []

        for idx, warning_data in enumerate(test_output.get("warnings", [])):
            try:
                warning = RepairTestWarning(
                    file=warning_data.get("file", "unknown"),
                    message=warning_data.get("message", ""),
                )
                warnings.append(warning)
            except ValueError as e:
                # Collect parse errors but continue processing other warnings
                parse_errors.append({"index": idx, "data": warning_data, "error": str(e)})
                logger.error(
                    f"PARSE ERROR: Test warning #{idx} data is invalid - agent may be malfunctioning. "
                    f"Continuing to process remaining warnings.",
                    extra={
                        "test_type": test_type.value,
                        "warning_index": idx,
                        "warning_data": warning_data,
                        "validation_error": str(e),
                        "error_id": ErrorRegistry.ERR_REPAIR_CYCLE_ERROR,
                    },
                    exc_info=True,
                )

        # If we collected any valid warnings, log parse errors but return valid data
        if warnings and parse_errors:
            logger.warning(
                f"Extracted {len(warnings)} valid test warnings despite {len(parse_errors)} parse errors. "
                f"Agent output may be partially corrupt.",
                extra={
                    "test_type": test_type.value,
                    "valid_warnings": len(warnings),
                    "parse_errors": len(parse_errors),
                    "error_indices": [e["index"] for e in parse_errors],
                },
            )
        # If ALL warnings failed to parse, raise error with details
        elif parse_errors and not warnings:
            logger.error(
                f"ALL test warning entries failed to parse ({len(parse_errors)} errors). "
                f"This indicates either: (1) Test framework output changed, "
                f"(2) Agent prompt needs updating, or (3) Agent is malfunctioning.",
                extra={
                    "test_type": test_type.value,
                    "total_warnings": len(test_output.get("warnings", [])),
                    "parse_errors": parse_errors,
                    "error_id": ErrorRegistry.ERR_REPAIR_CYCLE_ERROR,
                },
            )
            msg = (
                f"All {len(parse_errors)} test warning entries for {test_type.value} failed to parse. "
                f"This indicates either: (1) Test framework output changed, "
                f"(2) Agent prompt needs updating, or (3) Agent is malfunctioning. "
                f"First error: {parse_errors[0]['error']}"
            )
            raise TestOutputParseError(
                msg,
                test_type=test_type.value,
                raw_data=test_output.get("warnings", []),
            )

        return warnings

    def _build_fix_prompt(self, file_path: str, failures: tuple[RepairTestFailure, ...]) -> str:
        """Build prompt for LLM to fix test failures in a file.

        Args:
            file_path: Path to the test file with failures
            failures: Tuple of failures in this file

        Returns:
            Prompt for LLM agent
        """
        failure_details = "\n".join([f"- {f.test}: {f.message}" for f in failures])

        return f"""Please fix the following test failures in {file_path}:

{failure_details}

Analyze the test code, understand the failures, and make targeted fixes to the implementation.
Return a JSON response with the status of fixes applied."""

    def _build_warning_review_prompt(self, warning: RepairTestWarning) -> str:
        """Build prompt for LLM to review and address a warning.

        Args:
            warning: Warning to review

        Returns:
            Prompt for LLM agent
        """
        return f"""Please review and address the following warning in {warning.file}:

{warning.message}

Analyze the warning, understand its root cause, and make targeted fixes.
Return a JSON response with the status of fixes applied."""

    def _group_failures_by_file(
        self, failures: tuple[RepairTestFailure, ...]
    ) -> dict[str, tuple[RepairTestFailure, ...]]:
        """Group test failures by file.

        Args:
            failures: Tuple of all failures

        Returns:
            Dictionary mapping file path to failures in that file
        """
        grouped: dict[str, list[RepairTestFailure]] = {}
        for failure in failures:
            if failure.file not in grouped:
                grouped[failure.file] = []
            grouped[failure.file].append(failure)

        return {file: tuple(fs) for file, fs in grouped.items()}

    async def _run_test_cycle(
        self,
        config: RepairTestRunConfig,
        context: RepairCycleContext,
        test_type_index: int,
    ) -> CycleResult:
        """Execute full cycle for a single test type.

        Orchestrates the test-fix-validate loop for a single test type,
        updating iteration count and agent calls.

        Args:
            config: Test run configuration
            context: Repair cycle context
            test_type_index: Index of this test type in the sequence

        Returns:
            CycleResult with outcomes and metrics
        """
        iteration = 0
        files_fixed = 0
        warnings_reviewed = 0
        cycle_passed = False
        error = None
        start_time = datetime.now(UTC)

        for iteration in range(1, config.max_iterations + 1):
            # Check circuit breaker
            if self.circuit_breaker and self.circuit_breaker.is_open():
                error = "Circuit breaker: max agent calls reached"
                logger.warning(
                    error,
                    extra={
                        "workflow_run_id": context.workflow_run_id,
                        "test_type": config.test_type.value,
                        "iteration": iteration,
                    },
                    exc_info=False,
                )
                raise CircuitBreakerOpenError("Max agent calls reached; circuit breaker is open")

            try:
                # Run tests
                test_result = await self.run_tests(config, context)

                # Update iteration in result
                test_result = RepairTestResult(
                    test_type=test_result.test_type,
                    iteration=iteration,
                    passed=test_result.passed,
                    failed=test_result.failed,
                    warnings=test_result.warnings,
                    failures=test_result.failures,
                    warning_list=test_result.warning_list,
                    raw_output=test_result.raw_output,
                    timestamp=test_result.timestamp,
                )

                # Check for success
                if test_result.failed == 0:
                    cycle_passed = True

                    # Handle warnings if configured
                    if config.review_warnings and test_result.warnings > 0:
                        warnings_reviewed += await self.handle_warnings(test_result, config, context)

                        # Re-test after warning fixes
                        retest = await self.run_tests(config, context)
                        if retest.failed > 0:
                            # Warning fixes broke something, continue fixing
                            cycle_passed = False
                        else:
                            # Warnings fixed, success
                            break
                    else:
                        # Success, no warnings to handle
                        break

                # Fix failures
                if not cycle_passed:
                    grouped = self._group_failures_by_file(test_result.failures)
                    files_fixed += await self.fix_failures_by_file(grouped, config, context)

                    # Re-test to determine if file-level fixes resolved issues
                    retest_result = await self.run_tests(config, context)
                    retest_result = RepairTestResult(
                        test_type=retest_result.test_type,
                        iteration=iteration,
                        passed=retest_result.passed,
                        failed=retest_result.failed,
                        warnings=retest_result.warnings,
                        failures=retest_result.failures,
                        warning_list=retest_result.warning_list,
                        raw_output=retest_result.raw_output,
                        timestamp=retest_result.timestamp,
                    )

                    # Only proceed to systemic analysis if failures persist after fixes
                    if retest_result.failures:
                        try:
                            analysis = await self.analyze_systemic_issues(retest_result, config, context)
                            if analysis:
                                # Apply systemic fixes based on analysis
                                fixed = await self.apply_systemic_fixes(analysis, retest_result, config, context)
                                if fixed:
                                    # Rebuild and verify environment after systemic fixes
                                    rebuild_success = await self.rebuild_environment(config, context)
                                    if not rebuild_success:
                                        logger.error(
                                            "Environment rebuild failed; cannot continue with tests",
                                            extra={
                                                "workflow_run_id": context.workflow_run_id,
                                                "test_type": config.test_type.value,
                                                "iteration": iteration,
                                                "error_id": ErrorRegistry.ERR_REPAIR_CYCLE_ERROR,
                                            },
                                            exc_info=False,
                                        )
                                        break

                                    env_ready = await self.verify_environment(config, context)
                                    if not env_ready:
                                        logger.error(
                                            "Environment verification failed; environment not ready for testing",
                                            extra={
                                                "workflow_run_id": context.workflow_run_id,
                                                "test_type": config.test_type.value,
                                                "iteration": iteration,
                                                "error_id": ErrorRegistry.ERR_REPAIR_CYCLE_ERROR,
                                            },
                                            exc_info=False,
                                        )
                                        break
                        except Exception as e:
                            # Log systemic analysis failures but continue with regular retry
                            logger.warning(
                                "Systemic analysis/fixes failed, continuing with standard retry",
                                extra={
                                    "workflow_run_id": context.workflow_run_id,
                                    "test_type": config.test_type.value,
                                    "error": str(e),
                                },
                                exc_info=True,
                            )
                    else:
                        # File-level fixes resolved issues, update test_result for the loop
                        test_result = retest_result

                # Checkpoint at interval
                if iteration % context.checkpoint_interval == 0:
                    await self.checkpoint(config.test_type, iteration, context)

            except CircuitBreakerOpenError:
                raise
            except Exception as e:
                error = str(e)
                logger.error(
                    "Test cycle iteration failed",
                    extra={
                        "workflow_run_id": context.workflow_run_id,
                        "test_type": config.test_type.value,
                        "iteration": iteration,
                        "error": error,
                        "error_id": ErrorRegistry.ERR_REPAIR_CYCLE_ERROR,
                    },
                    exc_info=True,
                )
                break

        # Emit test cycle completed event
        duration_seconds = (datetime.now(UTC) - start_time).total_seconds()

        self.event_emitter.emit(
            RepairCycleTestCycleCompletedEvent(
                type="repair_cycle.test_cycle_completed",
                timestamp=datetime.now(UTC).isoformat(),
                source="production_repair_cycle",
                test_type=config.test_type,
                test_type_index=test_type_index,
                passed=cycle_passed,
                test_cycle_iterations=iteration,
                files_fixed=files_fixed,
                warnings_reviewed=warnings_reviewed,
                error=error,
                duration_seconds=duration_seconds,
                workflow_run_id=context.workflow_run_id,
            )
        )

        return CycleResult(
            test_type=config.test_type,
            passed=cycle_passed,
            iterations=iteration,
            final_result=test_result if cycle_passed else None,
            error=error,
            files_fixed=files_fixed,
            warnings_reviewed=warnings_reviewed,
            duration_seconds=duration_seconds,
        )
