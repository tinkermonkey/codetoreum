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
- Factory injection of ILLMProvider for flexible provider selection
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
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from codetoreum.domain.events.adapter_events import CodetoreumEvent
    from codetoreum.infrastructure.resilience.interfaces import ICircuitBreaker
    from codetoreum.ports.output.event_emitter import IEventEmitter
    from codetoreum.ports.output.llm_provider import AgentLLMFactory, ExecutionResult, ILLMProvider

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
    SystemicAnalysisCompletedEvent,
    SystemicAnalysisStartedEvent,
)
from codetoreum.domain.exceptions import TestOutputParseError
from codetoreum.domain.repair_cycle_types import (
    AnalysisContext,
    CycleResult,
    FailureClassification,
    RepairCycleCheckpoint,
    RepairCycleResult,
    RepairTestFailure,
    RepairTestResult,
    RepairTestRunConfig,
    RepairTestType,
    RepairTestWarning,
    SystemicAnalysisResult,
    SystemicFixResult,
)
from codetoreum.infrastructure.error_ids import ErrorRegistry
from codetoreum.infrastructure.resilience.exceptions import CircuitBreakerOpenError
from codetoreum.ports.output.event_emitter import IEventEmitter
from codetoreum.ports.output.repair_cycle_checkpoint_store import (
    IRepairCycleCheckpointStore,
)
from codetoreum.ports.output.repair_cycle_service import (
    IRepairCycle,
    RepairCycleContext,
)
from codetoreum.ports.output.systemic_analysis_service import ISystemicAnalysisService

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


class NullEventEmitter(IEventEmitter):
    """Null-object pattern for optional event emission.

    Implements IEventEmitter with no-op methods for use when event emission is not required.
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
        systemic_analysis_service: ISystemicAnalysisService | None = None,
    ) -> None:
        """Initialize production repair cycle adapter.

        Args:
            llm_factory: Factory callable that takes agent name and returns configured ILLMProvider
            config: Optional RepairCycleConfig (uses defaults if not provided)
            event_emitter: Optional event emitter (uses null-object if not provided)
            checkpoint_store: Optional checkpoint store for resumable repairs
            circuit_breaker: Optional circuit breaker for LLM call protection
            systemic_analysis_service: Optional systemic analysis service for failure classification
        """
        self._llm_factory = llm_factory
        self.config = config or RepairCycleConfig()
        self.event_emitter = event_emitter or NullEventEmitter()
        self.checkpoint_store = checkpoint_store
        self.circuit_breaker = circuit_breaker
        self._systemic_analysis_service = systemic_analysis_service

    @property
    def systemic_analysis_service(self) -> ISystemicAnalysisService | None:
        """Get the systemic analysis service."""
        return self._systemic_analysis_service

    @systemic_analysis_service.setter
    def systemic_analysis_service(self, service: ISystemicAnalysisService | None) -> None:
        """Set the systemic analysis service."""
        self._systemic_analysis_service = service

        # Tracking state for checkpoint resumption
        self._files_fixed = 0  # Number of files fixed in current cycle
        self._warnings_reviewed = 0  # Number of warnings reviewed in current cycle
        self._elapsed_time = 0.0  # Total time spent in current cycle (seconds)
        self._cycle_results: list[CycleResult] = []  # Accumulated test results

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

    async def _execute_llm_with_timeout(
        self,
        llm: ILLMProvider,
        prompt: str,
        operation: str,
        config: RepairTestRunConfig,
        context: RepairCycleContext,
        extra_log: dict | None = None,
        error_message: str | None = None,
    ) -> ExecutionResult:
        """Execute an LLM call with timeout and optional circuit breaker.

        Centralizes timeout enforcement and error handling for all LLM calls,
        ensuring consistent timeout application and logging across the adapter.

        Args:
            llm: LLM provider to execute
            prompt: Prompt to send to the LLM
            operation: Operation name for circuit breaker (e.g., "repair_cycle.run_tests")
            config: Test run configuration containing timeout value
            context: Repair cycle context with workflow details
            extra_log: Optional dict of additional logging context
            error_message: Optional custom error message prefix (defaults to operation name)

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
            return await asyncio.wait_for(coro, timeout=config.timeout)
        except TimeoutError as e:
            message_prefix = error_message or operation
            log_extra = {
                "workflow_run_id": context.workflow_run_id,
                "timeout_seconds": config.timeout,
                "error_id": ErrorRegistry.ERR_REPAIR_CYCLE_ERROR,
                **(extra_log or {}),
            }
            logger.error(f"{message_prefix} timed out", extra=log_extra, exc_info=True)
            raise TimeoutError(f"{message_prefix} exceeded timeout of {config.timeout} seconds") from e

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
            agent_response = await self._execute_llm_with_timeout(
                llm=llm,
                prompt=prompt,
                operation="repair_cycle.run_tests",
                config=config,
                context=context,
                extra_log={"test_type": config.test_type.value},
                error_message="Test execution",
            )

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
        fixed = 0

        # Resolve agent for code fix sub-task
        llm, resolved_agent_name = await self._get_llm_for_subtask("code_fix", context)

        for file_path, failures in grouped_failures.items():
            # Check circuit breaker
            if self.circuit_breaker and self.circuit_breaker.is_open():
                logger.warning(
                    "Circuit breaker triggered during file fixes",
                    extra={
                        "workflow_run_id": context.workflow_run_id,
                        "file": file_path,
                        "failures": len(failures),
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
                    },
                    exc_info=False,
                )

                await self._execute_llm_with_timeout(
                    llm=llm,
                    prompt=fix_prompt,
                    operation="repair_cycle.fix_failures_by_file",
                    config=config,
                    context=context,
                    extra_log={"file": file_path},
                    error_message=f"Fix execution for {file_path}",
                )

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

        reviewed = 0

        # Resolve agent for warning review sub-task (uses code_fix agent)
        llm, resolved_agent_name = await self._get_llm_for_subtask("code_fix", context)

        for warning in test_result.warning_list:
            # Check circuit breaker
            if self.circuit_breaker and self.circuit_breaker.is_open():
                logger.warning(
                    "Circuit breaker triggered during warning review",
                    extra={
                        "workflow_run_id": context.workflow_run_id,
                        "file": warning.file,
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
                    },
                    exc_info=False,
                )

                await self._execute_llm_with_timeout(
                    llm=llm,
                    prompt=review_prompt,
                    operation="repair_cycle.handle_warnings",
                    config=config,
                    context=context,
                    extra_log={"file": warning.file},
                    error_message=f"Warning review for {warning.file}",
                )

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

    async def fix_failures_systemically(
        self,
        failures: tuple[RepairTestFailure, ...],
        analysis_result: SystemicAnalysisResult,
        config: RepairTestRunConfig,
        context: RepairCycleContext,
    ) -> SystemicFixResult:
        """Apply a coordinated holistic fix addressing the root cause across all affected files.

        Issues a single agent invocation presenting all failures together with the root cause
        context from systemic analysis. This is the primary contract for cross-cutting fixes
        that affect multiple files with a shared root cause.

        Args:
            failures: Immutable tuple of test failures to address
            analysis_result: Systemic analysis result with root cause and affected files
            config: Test run configuration
            context: Repair cycle context

        Returns:
            SystemicFixResult indicating whether the holistic fix succeeded and which
            files were modified

        Raises:
            CircuitBreakerOpenError: When circuit breaker is open
        """
        start_time = time.time()

        # Circuit breaker check
        if self.circuit_breaker and self.circuit_breaker.is_open():
            logger.error(
                "Circuit breaker open; cannot apply systemic fixes",
                extra={
                    "workflow_run_id": context.workflow_run_id,
                    "work_item_id": context.work_item_id,
                    "error_id": ErrorRegistry.ERR_REPAIR_CYCLE_CIRCUIT_BREAKER_OPEN,
                },
                exc_info=False,
            )
            raise CircuitBreakerOpenError("Circuit breaker is open")

        try:
            logger.info(
                "Starting systemic fix for cross-cutting root cause",
                extra={
                    "workflow_run_id": context.workflow_run_id,
                    "work_item_id": context.work_item_id,
                    "failure_count": len(failures),
                    "classification": analysis_result.classification.value,
                    "affected_files": ",".join(analysis_result.affected_files),
                },
                exc_info=False,
            )

            # Get LLM provider for the fix agent
            llm_provider, resolved_agent_name = await self._get_llm_for_subtask("systemic_fix", context)

            # Build prompt with failure details and root cause context
            failures_summary = "\n".join([
                f"- {f.file}::{f.test}: {f.message}"
                for f in failures
            ])

            prompt = f"""You are a specialized repair agent addressing a cross-cutting root cause issue.

## Root Cause Analysis
**Classification**: {analysis_result.classification.value}
**Confidence**: {analysis_result.confidence:.1%}
**Reasoning**: {analysis_result.reasoning}
**Recommended Action**: {analysis_result.recommended_action}

## Affected Files
{', '.join(analysis_result.affected_files)}

## All Failures to Address
{failures_summary}

## Your Task
Apply a holistic fix that addresses the root cause across all affected files. This may involve:
- Updating dependencies or configuration
- Fixing shared interfaces or contracts
- Updating build/environment configuration
- Or other systemic changes

After making changes:
1. Summarize what root cause you addressed
2. List all files you modified
3. Explain how your changes fix all the failures above

Respond with JSON:
{{
    "root_cause_addressed": "description of what was fixed",
    "files_modified": ["file1", "file2", ...],
    "explanation": "how this addresses all failures"
}}
"""

            # Execute LLM call
            execution_result = await self._execute_llm_with_timeout(
                llm=llm_provider,
                prompt=prompt,
                operation="repair_cycle.fix_failures_systemically",
                config=config,
                context=context,
                error_message="Systemic fix execution",
            )

            if not execution_result.success:
                logger.error(
                    "Systemic fix agent execution failed",
                    extra={
                        "workflow_run_id": context.workflow_run_id,
                        "work_item_id": context.work_item_id,
                        "error": execution_result.error or "Unknown error",
                        "error_id": ErrorRegistry.ERR_REPAIR_CYCLE_ERROR,
                    },
                    exc_info=False,
                )
                duration_seconds = time.time() - start_time
                return SystemicFixResult(
                    success=False,
                    files_modified=(),
                    root_cause_addressed="",
                    duration_seconds=duration_seconds,
                )

            # Parse agent response
            try:
                response_json = json.loads(execution_result.output or "{}")
                files_modified = tuple(response_json.get("files_modified", []))
                root_cause_addressed = response_json.get("root_cause_addressed", "")

                duration_seconds = time.time() - start_time
                result = SystemicFixResult(
                    success=True,
                    files_modified=files_modified,
                    root_cause_addressed=root_cause_addressed,
                    duration_seconds=duration_seconds,
                )

                logger.info(
                    "Systemic fix completed successfully",
                    extra={
                        "workflow_run_id": context.workflow_run_id,
                        "work_item_id": context.work_item_id,
                        "files_modified_count": len(files_modified),
                        "duration_seconds": duration_seconds,
                    },
                    exc_info=False,
                )

                return result

            except (json.JSONDecodeError, KeyError, TypeError) as e:
                logger.error(
                    "Failed to parse systemic fix response",
                    extra={
                        "workflow_run_id": context.workflow_run_id,
                        "work_item_id": context.work_item_id,
                        "error": str(e),
                        "error_id": ErrorRegistry.ERR_REPAIR_CYCLE_ERROR,
                    },
                    exc_info=True,
                )
                duration_seconds = time.time() - start_time
                return SystemicFixResult(
                    success=False,
                    files_modified=(),
                    root_cause_addressed="",
                    duration_seconds=duration_seconds,
                )

        except Exception as e:
            logger.error(
                "Unexpected error in systemic fix",
                extra={
                    "workflow_run_id": context.workflow_run_id,
                    "work_item_id": context.work_item_id,
                    "error": str(e),
                    "error_type": type(e).__name__,
                    "error_id": ErrorRegistry.ERR_REPAIR_CYCLE_ERROR,
                },
                exc_info=True,
            )
            duration_seconds = time.time() - start_time
            return SystemicFixResult(
                success=False,
                files_modified=(),
                root_cause_addressed="",
                duration_seconds=duration_seconds,
            )

    async def checkpoint(
        self,
        test_type: RepairTestType,
        iteration: int,
        context: RepairCycleContext,
    ) -> bool:
        """Save repair cycle state for resume after failures.

        Called at checkpoint_interval iterations. Saves sufficient state to
        resume from this point if cycle is interrupted.

        Args:
            test_type: Current test type being executed
            iteration: current iteration number
            context: Repair cycle context

        Returns:
            bool: True if checkpoint saved successfully, False otherwise
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
            return True

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
            return True

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

            return False

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
        """Parse test output from agent response.

        Attempts to extract and parse JSON from the agent response. Unlike transient network errors,
        JSON parsing and regex extraction are deterministic operations—if parsing fails on the first
        attempt, retrying the exact same input will always fail identically. Therefore, no retry logic
        is needed; failures are due to invalid input and should fail fast.

        Args:
            agent_response: Raw response from agent
            test_type: Type of test executed

        Returns:
            Parsed test output as dictionary

        Raises:
            JSONParseError: If JSON cannot be extracted or parsed from the response
        """
        try:
            # Try to extract JSON from response
            json_match = re.search(r"\{.*\}", agent_response, re.DOTALL)
            if not json_match:
                msg = "No JSON found in agent response"
                raise JSONParseError(msg) from None

            parsed = json.loads(json_match.group())

            logger.info(
                "Test output parsed successfully",
                extra={
                    "test_type": test_type.value,
                },
                exc_info=False,
            )

            return parsed

        except json.JSONDecodeError as e:
            logger.error(
                "Failed to parse test output",
                extra={
                    "test_type": test_type.value,
                    "error_type": type(e).__name__,
                    "error": str(e),
                },
                exc_info=True,
            )
            raise JSONParseError(f"Failed to parse test output: {e}") from e

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

    async def _execute_llm_prompt(
        self,
        prompt: str,
        operation_name: str,
        config: RepairTestRunConfig,
        context: RepairCycleContext,
    ) -> dict[str, Any]:
        """Execute an LLM prompt and return the parsed response.

        Abstracts the common pattern of circuit-breaker-protected LLM execution
        with response capture and error handling. Inspects the response to
        distinguish success from failure.

        Args:
            prompt: The prompt to send to the LLM
            operation_name: Name of the operation (used in logging and circuit breaker)
            config: Test run configuration
            context: Repair cycle context

        Returns:
            Parsed LLM response as a dictionary

        Raises:
            Exception: If LLM execution fails or response indicates failure
        """
        try:
            logger.info(
                f"Executing LLM operation: {operation_name}",
                extra={
                    "workflow_run_id": context.workflow_run_id,
                    "test_type": config.test_type.value,
                    "operation": operation_name,
                },
                exc_info=False,
            )

            llm, _ = await self._get_llm_for_subtask(operation_name, context)
            result = await self._execute_llm_with_timeout(
                llm=llm,
                prompt=prompt,
                operation=f"repair_cycle.{operation_name}",
                config=config,
                context=context,
                error_message=f"LLM operation {operation_name}",
            )
            response = result.content

            # Parse response if it's a string (JSON)
            if isinstance(response, str):
                try:
                    response = json.loads(response)
                except json.JSONDecodeError:
                    # If not valid JSON, treat as plain response
                    response = {"status": "success", "response": response}

            # Check for failure indicators in response
            if isinstance(response, dict):
                status = response.get("status", "").lower()
                if status in ("failed", "error", "failure"):
                    error_msg = response.get("error", response.get("message", "Unknown error"))
                    raise ValueError(f"LLM operation returned failure status: {error_msg}")

            logger.info(
                f"LLM operation completed: {operation_name}",
                extra={
                    "workflow_run_id": context.workflow_run_id,
                    "operation": operation_name,
                    "response_keys": list(response.keys()) if isinstance(response, dict) else "non-dict",
                },
                exc_info=False,
            )
            return response if isinstance(response, dict) else {"response": response}

        except Exception as e:
            logger.error(
                f"LLM operation failed: {operation_name}",
                extra={
                    "workflow_run_id": context.workflow_run_id,
                    "operation": operation_name,
                    "error": str(e),
                    "error_id": ErrorRegistry.ERR_REPAIR_CYCLE_ERROR,
                },
                exc_info=True,
            )
            raise

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

    async def _apply_dependency_fix(
        self,
        reasoning: str,
        test_result: RepairTestResult,
        config: RepairTestRunConfig,
        context: RepairCycleContext,
    ) -> bool:
        """Apply fixes for dependency-related issues.

        Routes dependency issue fixes through the LLM to identify and resolve
        missing or incompatible dependencies.

        Args:
            reasoning: Classification reasoning from systemic analysis
            test_result: Test result that triggered this fix
            config: Test run configuration
            context: Repair cycle context

        Returns:
            True if dependency fixes were applied, False otherwise
        """
        try:
            prompt = self._build_dependency_fix_prompt(reasoning, test_result)
            await self._execute_llm_prompt(prompt, "apply_dependency_fix", config, context)
            return True
        except Exception as e:
            logger.error(
                "Dependency fix failed",
                extra={
                    "workflow_run_id": context.workflow_run_id,
                    "error": str(e),
                    "error_type": type(e).__name__,
                    "error_id": ErrorRegistry.ERR_REPAIR_CYCLE_ERROR,
                },
                exc_info=True,
            )
            return False

    async def _apply_configuration_fix(
        self,
        reasoning: str,
        test_result: RepairTestResult,
        config: RepairTestRunConfig,
        context: RepairCycleContext,
    ) -> bool:
        """Apply fixes for configuration-related issues.

        Routes configuration issue fixes through the LLM to identify and resolve
        configuration problems or missing environment setup.

        Args:
            reasoning: Classification reasoning from systemic analysis
            test_result: Test result that triggered this fix
            config: Test run configuration
            context: Repair cycle context

        Returns:
            True if configuration fixes were applied, False otherwise
        """
        try:
            prompt = self._build_configuration_fix_prompt(reasoning, test_result)
            await self._execute_llm_prompt(prompt, "apply_configuration_fix", config, context)
            return True
        except Exception as e:
            logger.error(
                "Configuration fix failed",
                extra={
                    "workflow_run_id": context.workflow_run_id,
                    "error": str(e),
                    "error_type": type(e).__name__,
                    "error_id": ErrorRegistry.ERR_REPAIR_CYCLE_ERROR,
                },
                exc_info=True,
            )
            return False

    def _build_dependency_fix_prompt(self, reasoning: str, test_result: RepairTestResult) -> str:
        """Build prompt for LLM to fix dependency issues.

        Args:
            reasoning: Classification reasoning from systemic analysis
            test_result: Test result containing failure details

        Returns:
            Prompt for LLM agent
        """
        failure_details = "\n".join([f"- {f.file}::{f.test}: {f.message}" for f in test_result.failures])

        return f"""The failures are classified as DEPENDENCY_ISSUE based on the following analysis:

Reasoning: {reasoning}

Test failures:
{failure_details}

Please identify and resolve the missing or incompatible dependencies. This may involve:
1. Installing missing packages
2. Updating dependency versions
3. Removing conflicting dependencies
4. Updating package manifests (package.json, requirements.txt, Cargo.toml, etc.)

Return a JSON response with the status of dependency fixes applied."""

    def _build_configuration_fix_prompt(self, reasoning: str, test_result: RepairTestResult) -> str:
        """Build prompt for LLM to fix configuration issues.

        Args:
            reasoning: Classification reasoning from systemic analysis
            test_result: Test result containing failure details

        Returns:
            Prompt for LLM agent
        """
        failure_details = "\n".join([f"- {f.file}::{f.test}: {f.message}" for f in test_result.failures])

        return f"""The failures are classified as CONFIGURATION_ISSUE based on the following analysis:

Reasoning: {reasoning}

Test failures:
{failure_details}

Please identify and resolve the configuration problems. This may involve:
1. Adding or modifying environment variables
2. Creating or updating configuration files
3. Adjusting service configurations
4. Setting up required credentials or API keys
5. Configuring test fixtures or test databases

Return a JSON response with the status of configuration fixes applied."""

    async def rebuild_environment(
        self,
        config: RepairTestRunConfig,
        context: RepairCycleContext,
    ) -> bool:
        """Rebuild the test environment.

        Coordinates with the LLM provider to identify and execute steps needed
        to rebuild the environment (e.g., dependency installation, configuration setup).

        Args:
            config: Test run configuration
            context: Repair cycle context

        Returns:
            True if environment rebuild succeeded, False otherwise
        """
        try:
            rebuild_prompt = self._build_environment_rebuild_prompt(config)
            await self._execute_llm_prompt(rebuild_prompt, "rebuild_environment", config, context)
            return True
        except Exception as e:
            logger.error(
                "Environment rebuild failed",
                extra={
                    "workflow_run_id": context.workflow_run_id,
                    "test_type": config.test_type.value,
                    "error": str(e),
                    "error_type": type(e).__name__,
                    "error_id": ErrorRegistry.ERR_REPAIR_CYCLE_ERROR,
                },
                exc_info=True,
            )
            return False

    async def verify_environment(
        self,
        config: RepairTestRunConfig,
        context: RepairCycleContext,
    ) -> bool:
        """Verify the test environment is correctly set up.

        Executes verification steps to confirm the environment rebuild was successful.

        Args:
            config: Test run configuration
            context: Repair cycle context

        Returns:
            True if environment verification succeeded, False otherwise
        """
        try:
            verify_prompt = self._build_environment_verify_prompt(config)
            await self._execute_llm_prompt(verify_prompt, "verify_environment", config, context)
            return True
        except Exception as e:
            logger.error(
                "Environment verification failed",
                extra={
                    "workflow_run_id": context.workflow_run_id,
                    "test_type": config.test_type.value,
                    "error": str(e),
                    "error_type": type(e).__name__,
                    "error_id": ErrorRegistry.ERR_REPAIR_CYCLE_ERROR,
                },
                exc_info=True,
            )
            return False

    async def apply_systemic_fixes(
        self,
        classification: FailureClassification,
        reasoning: str,
        test_result: RepairTestResult,
        config: RepairTestRunConfig,
        context: RepairCycleContext,
    ) -> bool:
        """Apply systemic fixes for DEPENDENCY_ISSUE or CONFIGURATION_ISSUE.

        Coordinates with the LLM provider to identify and implement fixes for
        systemic issues like dependency problems or configuration errors.
        Routes to differentiated fix strategies based on classification.

        Args:
            classification: The systemic failure classification from analysis
            reasoning: Classification reasoning from systemic analysis
            test_result: Test result that triggered this fix
            config: Test run configuration
            context: Repair cycle context

        Returns:
            True if systemic fixes were applied, False otherwise
        """
        try:
            if classification == FailureClassification.DEPENDENCY_ISSUE:
                return await self._apply_dependency_fix(reasoning, test_result, config, context)
            if classification == FailureClassification.CONFIGURATION_ISSUE:
                return await self._apply_configuration_fix(reasoning, test_result, config, context)
            # Fallback to dependency fix if classification is unknown
            logger.warning(
                "Unknown systemic fix classification; defaulting to dependency fix",
                extra={
                    "workflow_run_id": context.workflow_run_id,
                    "classification": classification.value if classification else "none",
                },
                exc_info=False,
            )
            return await self._apply_dependency_fix(reasoning, test_result, config, context)

        except Exception as e:
            # Safety net for unexpected exceptions in routing logic. Inner fix methods
            # catch and log their own exceptions, so this handler primarily catches
            # errors from classification checks or unexpected routing failures.
            logger.error(
                "Unexpected error in systemic fix routing",
                extra={
                    "workflow_run_id": context.workflow_run_id,
                    "error": str(e),
                    "error_type": type(e).__name__,
                    "error_id": ErrorRegistry.ERR_REPAIR_CYCLE_ERROR,
                },
                exc_info=True,
            )
            return False

    async def analyze_systemic_issues(
        self,
        failures: tuple[RepairTestFailure, ...],
    ) -> str:
        """Analyze systemic issues in test failures.

        Backward-compatible method that delegates to ISystemicAnalysisService
        for failure classification. Returns the reasoning string from the
        analysis result.

        Args:
            failures: Tuple of test failures to analyze

        Returns:
            Reasoning string from the systemic analysis result

        Raises:
            ValueError: If no systemic analysis service is configured
        """
        if self._systemic_analysis_service is None:
            msg = "Cannot analyze systemic issues: ISystemicAnalysisService is not configured"
            raise ValueError(msg)

        # Create a minimal AnalysisContext for the analysis
        # Note: work_item_id, iteration, and workflow_run_id would ideally come from caller context,
        # but for backward compatibility, we use placeholder values.
        analysis_context = AnalysisContext(
            work_item_id="unknown",
            iteration=0,
            workflow_run_id="unknown",
            prior_fix_attempts=(),
            prior_classifications=(),
        )

        result = await self._systemic_analysis_service.analyze(list(failures), analysis_context)
        return result.reasoning

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
        prior_fix_attempts: list[str] = []  # Track descriptions of fix attempts
        prior_classifications: list[SystemicAnalysisResult] = []  # Track prior SystemicAnalysisResult objects
        consecutive_transient_failures = 0  # Track consecutive TRANSIENT_FAILURE classifications
        max_consecutive_transient = 2  # Escalate after 2 consecutive transient failures

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

                # Fix failures or perform classification-based dispatch
                if not cycle_passed:
                    if self._systemic_analysis_service is not None:
                        # Perform systemic analysis and dispatch based on classification
                        analysis_context = AnalysisContext(
                            work_item_id=context.work_item_id,
                            iteration=iteration,
                            workflow_run_id=context.workflow_run_id,
                            prior_fix_attempts=tuple(prior_fix_attempts),
                            prior_classifications=tuple(prior_classifications),
                        )
                        self.event_emitter.emit(
                            SystemicAnalysisStartedEvent(
                                type="repair_cycle.systemic_analysis_started",
                                timestamp=datetime.now(UTC).isoformat(),
                                source="production_repair_cycle",
                                work_item_id=context.work_item_id,
                                workflow_run_id=context.workflow_run_id,
                                failure_count=len(test_result.failures),
                            )
                        )
                        try:
                            classification = await self._systemic_analysis_service.analyze(
                                list(test_result.failures), analysis_context
                            )
                            self.event_emitter.emit(
                                SystemicAnalysisCompletedEvent(
                                    type="repair_cycle.systemic_analysis_completed",
                                    timestamp=datetime.now(UTC).isoformat(),
                                    source="production_repair_cycle",
                                    classification=classification.classification.value,
                                    confidence=classification.confidence,
                                    reasoning=classification.reasoning,
                                    recommended_action=classification.recommended_action,
                                    work_item_id=context.work_item_id,
                                    workflow_run_id=context.workflow_run_id,
                                    failure_count=len(test_result.failures),
                                )
                            )

                            # Track this classification for escalation support in future iterations
                            prior_classifications.append(classification)

                            if classification.classification == FailureClassification.CODE_DEFECT:
                                consecutive_transient_failures = 0  # Reset counter
                                grouped = self._group_failures_by_file(test_result.failures)
                                files_fixed += await self.fix_failures_by_file(grouped, config, context)
                                prior_fix_attempts.append(
                                    f"Iteration {iteration}: CODE_DEFECT classified, applied file-level fixes"
                                )
                            elif classification.classification == FailureClassification.ENVIRONMENT_ISSUE:
                                consecutive_transient_failures = 0  # Reset counter
                                rebuild_success = await self.rebuild_environment(config, context)
                                if rebuild_success:
                                    await self.verify_environment(config, context)
                                prior_fix_attempts.append(
                                    f"Iteration {iteration}: ENVIRONMENT_ISSUE classified, rebuilt and verified environment"
                                )
                            elif classification.classification == FailureClassification.TRANSIENT_FAILURE:
                                consecutive_transient_failures += 1
                                if consecutive_transient_failures > max_consecutive_transient:
                                    # Escalate: treat as code defect after repeated transient failures
                                    logger.warning(
                                        f"Escalating TRANSIENT_FAILURE after {consecutive_transient_failures} consecutive occurrences",
                                        extra={
                                            "workflow_run_id": context.workflow_run_id,
                                            "iteration": iteration,
                                            "consecutive_transient_count": consecutive_transient_failures,
                                        },
                                        exc_info=False,
                                    )
                                    grouped = self._group_failures_by_file(test_result.failures)
                                    files_fixed += await self.fix_failures_by_file(grouped, config, context)
                                    prior_fix_attempts.append(
                                        f"Iteration {iteration}: TRANSIENT_FAILURE escalated to CODE_DEFECT (after {consecutive_transient_failures} consecutive), applied file-level fixes"
                                    )
                                    consecutive_transient_failures = 0  # Reset counter after escalation
                                else:
                                    prior_fix_attempts.append(
                                        f"Iteration {iteration}: TRANSIENT_FAILURE classified, retrying without fix (consecutive count: {consecutive_transient_failures})"
                                    )
                            elif classification.classification in (
                                FailureClassification.DEPENDENCY_ISSUE,
                                FailureClassification.CONFIGURATION_ISSUE,
                            ):
                                consecutive_transient_failures = 0  # Reset counter
                                fix_success = await self.apply_systemic_fixes(
                                    classification.classification,
                                    classification.reasoning,
                                    test_result,
                                    config,
                                    context,
                                )
                                status = "applied" if fix_success else "attempted but failed"
                                prior_fix_attempts.append(
                                    f"Iteration {iteration}: {classification.classification.value} classified, {status} systemic fixes"
                                )
                        except Exception as e:
                            # Classifier failure: emit failed event and fall back to existing behavior
                            error_msg = str(e)
                            logger.warning(
                                "Systemic analysis failed; falling back to fix_failures_by_file()",
                                extra={
                                    "workflow_run_id": context.workflow_run_id,
                                    "iteration": iteration,
                                    "error": error_msg,
                                },
                                exc_info=True,
                            )
                            # Emit failed completion event to close out the started event
                            self.event_emitter.emit(
                                SystemicAnalysisCompletedEvent(
                                    type="repair_cycle.systemic_analysis_completed",
                                    timestamp=datetime.now(UTC).isoformat(),
                                    source="production_repair_cycle",
                                    classification=FailureClassification.CODE_DEFECT.value,
                                    confidence=0.0,  # Zero confidence indicates failure
                                    reasoning=f"Analysis failed with error: {error_msg}",
                                    recommended_action="Fell back to fix_failures_by_file() due to analysis error",
                                    work_item_id=context.work_item_id,
                                    workflow_run_id=context.workflow_run_id,
                                    failure_count=len(test_result.failures),
                                )
                            )
                            grouped = self._group_failures_by_file(test_result.failures)
                            files_fixed += await self.fix_failures_by_file(grouped, config, context)
                    else:
                        # Backward-compatible fallback: no classifier injected
                        grouped = self._group_failures_by_file(test_result.failures)
                        files_fixed += await self.fix_failures_by_file(grouped, config, context)

                # Checkpoint at interval
                if iteration % context.checkpoint_interval == 0:
                    success = await self.checkpoint(config.test_type, iteration, context)
                    if not success:
                        logger.warning(
                            "Checkpoint save failed, continuing without checkpoint",
                            extra={"workflow_run_id": context.workflow_run_id},
                        )

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
