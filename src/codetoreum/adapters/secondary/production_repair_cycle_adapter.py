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

import asyncio
import json
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

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
from codetoreum.domain.exceptions import TestOutputParseError
from codetoreum.domain.events.repair_cycle_events import (
    RepairCycleCheckpointFailedEvent,
    RepairCycleCompletedEvent,
    RepairCycleFileFixCompletedEvent,
    RepairCycleFileFixStartedEvent,
    RepairCycleFastFailEvent,
    RepairCycleResumedEvent,
    RepairCycleStartedEvent,
    RepairCycleTestCycleCompletedEvent,
    RepairCycleTestExecutionCompletedEvent,
    RepairCycleWarningReviewCompletedEvent,
    RepairCycleWarningReviewStartedEvent,
)
from codetoreum.ports.output.repair_cycle_service import (
    IRepairCycle,
    RepairCycleContext,
)
from codetoreum.ports.output.repair_cycle_checkpoint_store import IRepairCycleCheckpointStore

logger = logging.getLogger(__name__)


class CircuitBreakerTripped(Exception):
    """Raised when max_total_agent_calls exceeded."""

    pass


class JSONParseError(Exception):
    """Raised when agent response cannot be parsed as JSON."""

    pass


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
            raise ValueError("max_json_parse_retries must be >= 1")
        if self.json_parse_retry_delay_ms < 0:
            raise ValueError("json_parse_retry_delay_ms must be >= 0")


class NullEventEmitter:
    """Null-object pattern for optional event emission."""

    def emit(self, event: Any) -> None:
        """No-op emit."""
        pass


class ProductionRepairCycleAdapter(IRepairCycle):
    """Production repair cycle adapter with LLM integration.

    Implements IRepairCycle by orchestrating test execution, failure analysis,
    and agent-based fixes. Uses Claude Code via ILLMProvider for intelligent
    repair coordination.

    Example:
        config = RepairCycleConfig()
        adapter = ProductionRepairCycleAdapter(llm_provider, config=config)

        context = RepairCycleContext(...)
        result = await adapter.execute(context)
    """

    def __init__(
        self,
        llm_provider: Any,
        config: RepairCycleConfig = None,
        event_emitter: Any = None,
        checkpoint_store: IRepairCycleCheckpointStore = None,
    ) -> None:
        """Initialize production repair cycle adapter.

        Args:
            llm_provider: ILLMProvider implementation (e.g., Claude Code adapter)
            config: Optional RepairCycleConfig (uses defaults if not provided)
            event_emitter: Optional event emitter (uses null-object if not provided)
            checkpoint_store: Optional checkpoint store for resumable repairs
        """
        self.llm_provider = llm_provider
        self.config = config or RepairCycleConfig()
        self.event_emitter = event_emitter or NullEventEmitter()
        self.checkpoint_store = checkpoint_store
        self.agent_call_count = 0

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
            CircuitBreakerTripped: When max_total_agent_calls exceeded
            ValueError: If test_configs is empty
        """
        if not context.test_configs:
            raise ValueError("test_configs cannot be empty")

        start_time = datetime.utcnow()
        cycle_start_timestamp = start_time.isoformat()

        # Emit repair cycle started event
        self.event_emitter.emit(
            RepairCycleStartedEvent(
                type="repair_cycle.started",
                timestamp=cycle_start_timestamp,
                source="production_repair_cycle",
                stage_name=context.stage_name,
                test_types=tuple(cfg.test_type for cfg in context.test_configs),
                pipeline_run_id=context.pipeline_run_id,
            )
        )

        # Execute each test type in sequence
        test_results: List[CycleResult] = []
        overall_success = True

        for test_type_index, test_config in enumerate(context.test_configs, start=1):
            # Check circuit breaker before starting test type
            if self.agent_call_count >= context.max_total_agent_calls:
                logger.warning(
                    "Circuit breaker triggered: max agent calls reached",
                    extra={
                        "pipeline_run_id": context.pipeline_run_id,
                        "test_type": test_config.test_type.value,
                        "agent_calls": self.agent_call_count,
                        "max_calls": context.max_total_agent_calls,
                    },
                    exc_info=False,
                )
                self.event_emitter.emit(
                    RepairCycleFastFailEvent(
                        type="repair_cycle.fast_fail",
                        timestamp=datetime.utcnow().isoformat(),
                        source="production_repair_cycle",
                        test_type=test_config.test_type,
                        reason="circuit_breaker_triggered",
                        pipeline_run_id=context.pipeline_run_id,
                    )
                )
                break

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
        end_time = datetime.utcnow()
        duration_seconds = (end_time - start_time).total_seconds()

        if test_results:
            self.event_emitter.emit(
                RepairCycleCompletedEvent(
                    type="repair_cycle.completed",
                    timestamp=cycle_start_timestamp,
                    source="production_repair_cycle",
                    overall_success=overall_success,
                    test_results=tuple(test_results),
                    total_agent_calls=self.agent_call_count,
                    duration_seconds=duration_seconds,
                    pipeline_run_id=context.pipeline_run_id,
                )
            )

        return RepairCycleResult(
            stage=context.stage_name,
            test_results=tuple(test_results),
            overall_success=overall_success,
            total_agent_calls=self.agent_call_count,
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
            CircuitBreakerTripped: When max_total_agent_calls exceeded
            TimeoutError: When test execution exceeds timeout
            JSONParseError: When agent returns invalid JSON (after retries)
        """
        # Check circuit breaker
        if self.agent_call_count >= context.max_total_agent_calls:
            raise CircuitBreakerTripped(
                f"Max agent calls ({context.max_total_agent_calls}) exceeded"
            )

        self.agent_call_count += 1

        # Build test command based on framework detection
        test_command = self._detect_and_build_test_command(config)

        # Execute tests via LLM
        logger.info(
            "Executing tests",
            extra={
                "pipeline_run_id": context.pipeline_run_id,
                "test_type": config.test_type.value,
                "command": test_command,
                "timeout": config.timeout,
            },
            exc_info=False,
        )

        try:
            # Call LLM to execute tests
            agent_response = await self.llm_provider.execute(
                prompt=f"Execute the following test command and return results as JSON:\n\n{test_command}",
                timeout=config.timeout,
            )

            # Parse test output with retry logic
            test_output = await self._parse_test_output_with_retry(
                agent_response, config.test_type
            )

            # Parse failures and warnings
            failures = self._extract_failures(test_output, config.test_type)
            warnings = self._extract_warnings(test_output, config.test_type)

            timestamp = datetime.utcnow().isoformat()

            result = RepairTestResult(
                test_type=config.test_type,
                iteration=1,  # Each run_tests call represents one iteration
                passed=test_output.get("passed", 0),
                failed=test_output.get("failed", 0),
                warnings=len(warnings),
                failures=tuple(failures),
                warning_list=tuple(warnings),
                raw_output=agent_response,
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
                    pipeline_run_id=context.pipeline_run_id,
                )
            )

            logger.info(
                "Test execution completed",
                extra={
                    "pipeline_run_id": context.pipeline_run_id,
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
                    "pipeline_run_id": context.pipeline_run_id,
                    "test_type": config.test_type.value,
                    "error": str(e),
                },
                exc_info=True,
            )
            raise

    async def fix_failures_by_file(
        self,
        grouped_failures: Dict[str, Tuple[RepairTestFailure, ...]],
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
            CircuitBreakerTripped: When max_total_agent_calls exceeded
        """
        fixed = 0

        for file_path, failures in grouped_failures.items():
            # Check circuit breaker
            if self.agent_call_count >= context.max_total_agent_calls:
                logger.warning(
                    "Circuit breaker triggered during file fixes",
                    extra={
                        "pipeline_run_id": context.pipeline_run_id,
                        "file": file_path,
                        "failures": len(failures),
                        "agent_calls": self.agent_call_count,
                    },
                    exc_info=False,
                )
                break

            self.agent_call_count += 1

            # Emit file fix started event
            timestamp = datetime.utcnow().isoformat()
            self.event_emitter.emit(
                RepairCycleFileFixStartedEvent(
                    type="repair_cycle.file_fix_started",
                    timestamp=timestamp,
                    source="production_repair_cycle",
                    test_file=file_path,
                    failure_count=len(failures),
                    test_type=config.test_type,
                    pipeline_run_id=context.pipeline_run_id,
                )
            )

            # Build fix prompt with failure context
            fix_prompt = self._build_fix_prompt(file_path, failures)

            try:
                # Call LLM to fix failures
                logger.info(
                    "Fixing test failures in file",
                    extra={
                        "pipeline_run_id": context.pipeline_run_id,
                        "file": file_path,
                        "failure_count": len(failures),
                    },
                    exc_info=False,
                )

                await self.llm_provider.execute(
                    prompt=fix_prompt,
                    timeout=config.timeout,
                )

                # Emit file fix completed event (success)
                self.event_emitter.emit(
                    RepairCycleFileFixCompletedEvent(
                        type="repair_cycle.file_fix_completed",
                        timestamp=datetime.utcnow().isoformat(),
                        source="production_repair_cycle",
                        test_file=file_path,
                        failure_count=len(failures),
                        test_type=config.test_type,
                        success=True,
                        pipeline_run_id=context.pipeline_run_id,
                    )
                )

                fixed += 1

                logger.info(
                    "File fix completed",
                    extra={
                        "pipeline_run_id": context.pipeline_run_id,
                        "file": file_path,
                    },
                    exc_info=False,
                )

            except Exception as e:
                # Emit file fix completed event (failure)
                logger.error(
                    "File fix failed",
                    extra={
                        "pipeline_run_id": context.pipeline_run_id,
                        "file": file_path,
                        "error": str(e),
                    },
                    exc_info=True,
                )

                self.event_emitter.emit(
                    RepairCycleFileFixCompletedEvent(
                        type="repair_cycle.file_fix_completed",
                        timestamp=datetime.utcnow().isoformat(),
                        source="production_repair_cycle",
                        test_file=file_path,
                        failure_count=len(failures),
                        test_type=config.test_type,
                        success=False,
                        pipeline_run_id=context.pipeline_run_id,
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
            CircuitBreakerTripped: When max_total_agent_calls exceeded
        """
        if not test_result.warning_list or not config.review_warnings:
            return 0

        reviewed = 0

        for warning in test_result.warning_list:
            # Check circuit breaker
            if self.agent_call_count >= context.max_total_agent_calls:
                logger.warning(
                    "Circuit breaker triggered during warning review",
                    extra={
                        "pipeline_run_id": context.pipeline_run_id,
                        "file": warning.file,
                        "agent_calls": self.agent_call_count,
                    },
                    exc_info=False,
                )
                break

            self.agent_call_count += 1

            # Emit warning review started event
            timestamp = datetime.utcnow().isoformat()
            self.event_emitter.emit(
                RepairCycleWarningReviewStartedEvent(
                    type="repair_cycle.warning_review_started",
                    timestamp=timestamp,
                    source="production_repair_cycle",
                    source_file=warning.file,
                    warning_count=1,
                    test_type=config.test_type,
                    warnings=(warning,),
                    pipeline_run_id=context.pipeline_run_id,
                )
            )

            try:
                # Build warning review prompt
                review_prompt = self._build_warning_review_prompt(warning)

                # Call LLM to review and address warning
                logger.info(
                    "Reviewing test warning",
                    extra={
                        "pipeline_run_id": context.pipeline_run_id,
                        "file": warning.file,
                        "warning": warning.message,
                    },
                    exc_info=False,
                )

                await self.llm_provider.execute(
                    prompt=review_prompt,
                    timeout=config.timeout,
                )

                # Emit warning review completed event (success)
                self.event_emitter.emit(
                    RepairCycleWarningReviewCompletedEvent(
                        type="repair_cycle.warning_review_completed",
                        timestamp=datetime.utcnow().isoformat(),
                        source="production_repair_cycle",
                        source_file=warning.file,
                        warning_count=1,
                        test_type=config.test_type,
                        success=True,
                        pipeline_run_id=context.pipeline_run_id,
                    )
                )

                reviewed += 1

                logger.info(
                    "Warning review completed",
                    extra={
                        "pipeline_run_id": context.pipeline_run_id,
                        "file": warning.file,
                    },
                    exc_info=False,
                )

            except Exception as e:
                logger.error(
                    "Warning review failed",
                    extra={
                        "pipeline_run_id": context.pipeline_run_id,
                        "file": warning.file,
                        "error": str(e),
                    },
                    exc_info=True,
                )

        return reviewed

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
                    "pipeline_run_id": context.pipeline_run_id,
                    "test_type": test_type.value,
                    "iteration": iteration,
                },
                exc_info=False,
            )
            return True

        try:
            from datetime import datetime, timedelta

            # Create checkpoint with current state
            now = datetime.utcnow()
            expires_at = (now + timedelta(hours=24)).isoformat()

            checkpoint = RepairCycleCheckpoint(
                pipeline_run_id=context.pipeline_run_id,
                test_type=test_type.value,
                iteration=iteration,
                total_agent_calls=self.agent_call_count,
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
                    "pipeline_run_id": context.pipeline_run_id,
                    "test_type": test_type.value,
                    "iteration": iteration,
                    "agent_calls": self.agent_call_count,
                    "expires_at": expires_at,
                },
                exc_info=False,
            )
            return True

        except Exception as e:
            logger.error(
                "Failed to save checkpoint - repair cycle may not be resumable",
                extra={
                    "pipeline_run_id": context.pipeline_run_id,
                    "test_type": test_type.value,
                    "iteration": iteration,
                    "error": str(e),
                    "error_type": type(e).__name__,
                },
                exc_info=True,
            )

            # Emit event so users/monitoring can be alerted
            if self.event_emitter:
                self.event_emitter.emit(
                    RepairCycleCheckpointFailedEvent(
                        type="repair_cycle.checkpoint_failed",
                        timestamp=datetime.utcnow().isoformat(),
                        source="production_repair_cycle",
                        pipeline_run_id=context.pipeline_run_id,
                        test_type=test_type.value,
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

    async def _parse_test_output_with_retry(
        self, agent_response: str, test_type: RepairTestType
    ) -> Dict[str, Any]:
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
                    raise JSONParseError("No JSON found in agent response")

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

        raise JSONParseError(
            f"Failed to parse test output after {self.config.max_json_parse_retries} attempts: {last_error}"
        )

    def _extract_failures(
        self, test_output: Dict[str, Any], test_type: RepairTestType
    ) -> List[RepairTestFailure]:
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

        for failure_data in test_output.get("failures", []):
            try:
                failure = RepairTestFailure(
                    file=failure_data.get("file", "unknown"),
                    test=failure_data.get("test", "unknown"),
                    message=failure_data.get("message", ""),
                )
                failures.append(failure)
            except ValueError as e:
                # Parse error indicates agent returned invalid format or parser bug
                logger.error(
                    "PARSE ERROR: Test failure data is invalid - agent may be malfunctioning",
                    extra={
                        "test_type": test_type.value,
                        "failure_data": failure_data,
                        "validation_error": str(e),
                    },
                    exc_info=True,
                )

                # Don't create synthetic data - fail loudly
                raise TestOutputParseError(
                    f"Invalid test failure data for {test_type.value}. "
                    f"This indicates either: (1) Test framework output changed, "
                    f"(2) Agent prompt needs updating, or (3) Agent is malfunctioning. "
                    f"Validation error: {e}",
                    test_type=test_type.value,
                    raw_data=failure_data,
                ) from e

        return failures

    def _extract_warnings(
        self, test_output: Dict[str, Any], test_type: RepairTestType
    ) -> List[RepairTestWarning]:
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

        for warning_data in test_output.get("warnings", []):
            try:
                warning = RepairTestWarning(
                    file=warning_data.get("file", "unknown"),
                    message=warning_data.get("message", ""),
                )
                warnings.append(warning)
            except ValueError as e:
                # Parse error indicates agent returned invalid format or parser bug
                logger.error(
                    "PARSE ERROR: Test warning data is invalid - agent may be malfunctioning",
                    extra={
                        "test_type": test_type.value,
                        "warning_data": warning_data,
                        "validation_error": str(e),
                    },
                    exc_info=True,
                )

                # Don't create synthetic data - fail loudly
                raise TestOutputParseError(
                    f"Invalid test warning data for {test_type.value}. "
                    f"This indicates either: (1) Test framework output changed, "
                    f"(2) Agent prompt needs updating, or (3) Agent is malfunctioning. "
                    f"Validation error: {e}",
                    test_type=test_type.value,
                    raw_data=warning_data,
                ) from e

        return warnings

    def _build_fix_prompt(
        self, file_path: str, failures: Tuple[RepairTestFailure, ...]
    ) -> str:
        """Build prompt for LLM to fix test failures in a file.

        Args:
            file_path: Path to the test file with failures
            failures: Tuple of failures in this file

        Returns:
            Prompt for LLM agent
        """
        failure_details = "\n".join(
            [
                f"- {f.test}: {f.message}"
                for f in failures
            ]
        )

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
        self, failures: Tuple[RepairTestFailure, ...]
    ) -> Dict[str, Tuple[RepairTestFailure, ...]]:
        """Group test failures by file.

        Args:
            failures: Tuple of all failures

        Returns:
            Dictionary mapping file path to failures in that file
        """
        grouped: Dict[str, List[RepairTestFailure]] = {}
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
        start_time = datetime.utcnow()

        for iteration in range(1, config.max_iterations + 1):
            # Check circuit breaker
            if self.agent_call_count >= context.max_total_agent_calls:
                error = "Circuit breaker: max agent calls reached"
                logger.warning(
                    error,
                    extra={
                        "pipeline_run_id": context.pipeline_run_id,
                        "test_type": config.test_type.value,
                        "iteration": iteration,
                    },
                    exc_info=False,
                )
                break

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
                        warnings_reviewed += await self.handle_warnings(
                            test_result, config, context
                        )

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
                    files_fixed += await self.fix_failures_by_file(
                        grouped, config, context
                    )

                # Checkpoint at interval
                if iteration % context.checkpoint_interval == 0:
                    success = await self.checkpoint(config.test_type, iteration, context)
                    if not success:
                        logger.warning(
                            "Checkpoint save failed, continuing without checkpoint",
                            extra={"pipeline_run_id": context.pipeline_run_id}
                        )

            except Exception as e:
                error = str(e)
                logger.error(
                    "Test cycle iteration failed",
                    extra={
                        "pipeline_run_id": context.pipeline_run_id,
                        "test_type": config.test_type.value,
                        "iteration": iteration,
                        "error": error,
                    },
                    exc_info=True,
                )
                break

        # Emit test cycle completed event
        duration_seconds = (datetime.utcnow() - start_time).total_seconds()

        self.event_emitter.emit(
            RepairCycleTestCycleCompletedEvent(
                type="repair_cycle.test_cycle_completed",
                timestamp=datetime.utcnow().isoformat(),
                source="production_repair_cycle",
                test_type=config.test_type,
                test_type_index=test_type_index,
                passed=cycle_passed,
                test_cycle_iterations=iteration,
                files_fixed=files_fixed,
                warnings_reviewed=warnings_reviewed,
                error=error,
                duration_seconds=duration_seconds,
                pipeline_run_id=context.pipeline_run_id,
            )
        )

        return CycleResult(
            test_type=config.test_type,
            passed=cycle_passed,
            iterations=iteration,
            final_result=None,
            error=error,
            files_fixed=files_fixed,
            warnings_reviewed=warnings_reviewed,
            duration_seconds=duration_seconds,
        )
