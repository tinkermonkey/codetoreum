"""Production LLM-based systemic analysis adapter.

Implements ISystemicAnalysisService by delegating failure classification to the LLM
agent using the existing systemic_analysis sub-task infrastructure.

This adapter analyzes test failures and classifies their root causes using Claude Code,
enabling the repair cycle to dispatch to the correct handling strategy (code fix,
environment rebuild, dependency fix, or transient retry).

Architecture:
- Async factory injection for agent-based LLM provider resolution
- Factory resolves providers by agent name (e.g., "systemic_analysis")
- Prompt construction with comprehensive context (failures, prior attempts, iteration)
- JSON parsing with fallback to CODE_DEFECT classification on parse errors
- No event emission (caller's responsibility)
- Comprehensive error logging with no silent failures
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Callable, Coroutine
    from typing import Any, Protocol

    from codetoreum.ports.output.llm_types import ExecutionContext, ExecutionResult

    class _LLMProviderLike(Protocol):
        """Duck-typed interface for the prompt-execution call sites.

        The historical ``ILLMProvider`` port retired in Phase D5; this
        adapter still needs a callable that takes a prompt+context and
        returns an ``ExecutionResult``. Until the systemic-analysis
        adapter migrates to ``ICodingAgent``, it relies on the duck type
        below."""

        async def execute(self, prompt: str, context: ExecutionContext | None = ...) -> ExecutionResult: ...

    AgentLLMFactory = Callable[[str], Coroutine[Any, Any, _LLMProviderLike]]

from codetoreum.domain.repair_cycle_types import (
    AnalysisContext,
    FailureClassification,
    RepairTestFailure,
    SystemicAnalysisResult,
)
from codetoreum.infrastructure.error_ids import ErrorRegistry
from codetoreum.ports.output.systemic_analysis_service import ISystemicAnalysisService

logger = logging.getLogger(__name__)


class LLMSystemicAnalysisAdapter(ISystemicAnalysisService):
    """Production systemic analysis adapter using LLM for classification.

    Analyzes test failures by delegating to Claude Code via the LLM provider factory,
    constructing rich context prompts that include failure details, prior fix
    attempts, and iteration count.

    Example:
        adapter = LLMSystemicAnalysisAdapter(llm_factory=lambda agent_name: provider_coro)
        result = await adapter.analyze(failures, context)
    """

    def __init__(self, llm_factory: AgentLLMFactory, timeout_seconds: int = 300) -> None:
        """Initialize production systemic analysis adapter.

        Args:
            llm_factory: Factory callable that takes agent name (str) and returns coroutine
                        resolving to configured ILLMProvider instance
            timeout_seconds: Timeout for LLM execution in seconds (default 300)

        Raises:
            ValueError: If llm_factory is None or timeout_seconds is invalid
        """
        if llm_factory is None:
            msg = "llm_factory cannot be None"
            raise ValueError(msg)
        if timeout_seconds <= 0:
            msg = "timeout_seconds must be > 0"
            raise ValueError(msg)
        self._llm_factory = llm_factory
        self._timeout_seconds = timeout_seconds
        self._logger = logging.getLogger(__name__)

    async def analyze(
        self,
        failures: list[RepairTestFailure],
        context: AnalysisContext,
    ) -> SystemicAnalysisResult:
        """Classify test failures by analyzing with LLM.

        Constructs a comprehensive prompt including failure messages, affected files,
        iteration count, and prior fix attempts. Sends to LLM for classification and
        parses the JSON response.

        Args:
            failures: List of test failures to classify.
            context: Context including work item id, iteration count,
                     and prior fix attempt history.

        Returns:
            SystemicAnalysisResult with classification, confidence, reasoning,
            affected files, and recommended action.

        Raises:
            TimeoutError: If LLM execution exceeds timeout
            ConnectionError: If LLM provider is unreachable
            Exception: Other LLM provider failures (propagated for caller fallback)

        Note:
            Response parsing errors (json.JSONDecodeError, ValueError, KeyError) are
            caught internally and result in a CODE_DEFECT fallback response rather than
            propagating to the caller.
        """
        prompt = self._build_prompt(failures, context)

        # Create execution context with timeout and agent specialization metadata
        from codetoreum.ports.output.llm_types import ExecutionContext as ExecutionContextImpl

        execution_context = ExecutionContextImpl(
            timeout_seconds=self._timeout_seconds,
            metadata={
                "subtask_name": "systemic_analysis",
                "workflow_run_id": context.workflow_run_id,
                "work_item_id": context.work_item_id,
                "iteration": context.iteration,
            },
        )

        response = await self._execute_llm_with_timeout(prompt, execution_context, context)
        try:
            return self._parse_response(response.content, context)
        except (json.JSONDecodeError, ValueError, KeyError) as e:
            # Parse error: response received but couldn't parse/validate it
            # Fall back to CODE_DEFECT for malformed responses
            self._logger.error(
                "Failed to parse systemic analysis response, defaulting to code_defect",
                extra={
                    "workflow_run_id": context.workflow_run_id,
                    "work_item_id": context.work_item_id,
                    "iteration": context.iteration,
                    "error": str(e),
                    "error_id": ErrorRegistry.ERR_REPAIR_CYCLE_ERROR,
                },
                exc_info=True,
            )
            return SystemicAnalysisResult(
                classification=FailureClassification.CODE_DEFECT,
                confidence=0.0,
                reasoning=f"Parse failure: {e}",
                affected_files=(),
                recommended_action="Fix code defects",
                cross_cutting=False,
            )

    def _build_prompt(
        self,
        failures: list[RepairTestFailure],
        context: AnalysisContext,
    ) -> str:
        """Build comprehensive prompt for LLM systemic analysis.

        Includes:
        - Iteration count (for escalation context)
        - Work item ID (for reference)
        - Prior fix attempts (to avoid re-analyzing same issues)
        - Test failure details (file, test name, message)

        Args:
            failures: List of test failures
            context: Analysis context with iteration and prior attempts

        Returns:
            Formatted prompt for LLM
        """
        failure_lines = "\n".join(f"- {f.file}::{f.test}: {f.message}" for f in failures)
        prior_attempts = "\n".join(context.prior_fix_attempts) if context.prior_fix_attempts else "None"

        return f"""Analyze the following test failures and classify the root cause.

Iteration: {context.iteration}
Work item: {context.work_item_id}
Prior fix attempts:
{prior_attempts}

Test failures:
{failure_lines}

Respond with JSON only (no markdown, no additional text):
{{
  "classification": "<code_defect|environment_issue|transient_failure|dependency_issue|configuration_issue>",
  "confidence": <0.0-1.0>,
  "reasoning": "<explanation>",
  "affected_files": ["<file1>", ...],
  "recommended_action": "<action>",
  "cross_cutting": <true|false>
}}

Field definitions:
- classification: The root cause category of the failures
- confidence: Your confidence in the classification (0.0-1.0)
- reasoning: Explanation of why you chose this classification
- affected_files: List of files involved in the failures
- recommended_action: What action should be taken to fix this issue
- cross_cutting: Set to true if the identified root cause is a single change that propagates failures across multiple files simultaneously (e.g., renamed method, changed interface contract, modified base class, API contract change, schema migration, shared import path change). Set to false when failures in different files are independent and can be fixed in isolation."""

    async def _execute_llm_with_timeout(
        self,
        prompt: str,
        execution_context: ExecutionContext,
        analysis_context: AnalysisContext,
    ) -> ExecutionResult:
        """Execute LLM with timeout protection.

        Wraps the LLM execution with asyncio timeout to prevent classification
        calls from hanging indefinitely.

        Args:
            prompt: Prompt to send to LLM
            execution_context: Execution context with timeout and metadata
            analysis_context: Analysis context for logging

        Returns:
            LLM response object

        Raises:
            TimeoutError: If execution exceeds timeout
            Exception: Any exception raised by the LLM provider
        """
        try:
            llm_provider = await self._llm_factory("systemic_analysis")
            return await asyncio.wait_for(
                llm_provider.execute(prompt, context=execution_context),
                timeout=execution_context.timeout_seconds,
            )
        except TimeoutError as e:
            self._logger.error(
                "LLM systemic analysis execution timed out",
                extra={
                    "workflow_run_id": analysis_context.workflow_run_id,
                    "work_item_id": analysis_context.work_item_id,
                    "iteration": analysis_context.iteration,
                    "timeout_seconds": execution_context.timeout_seconds,
                    "error_id": ErrorRegistry.ERR_REPAIR_CYCLE_ERROR,
                },
                exc_info=True,
            )
            raise TimeoutError(
                f"Systemic analysis classification exceeded {execution_context.timeout_seconds}s timeout"
            ) from e

    def _parse_response(
        self,
        response_text: str,
        context: AnalysisContext,
    ) -> SystemicAnalysisResult:
        """Parse LLM response into SystemicAnalysisResult.

        Strips markdown code fences from response and extracts JSON.
        Validates JSON structure and enum values. On parse error or invalid enum,
        raises exception that will be caught by analyze() for fallback handling.

        Args:
            response_text: Raw LLM response text (may contain markdown fences)
            context: Analysis context for logging

        Returns:
            Parsed SystemicAnalysisResult

        Raises:
            json.JSONDecodeError: If response is not valid JSON
            ValueError: If classification value is not a valid FailureClassification
            KeyError: If required JSON fields are missing
        """
        # Extract JSON from markdown code fences or plain response
        json_text = self._extract_json_from_response(response_text, context)

        # Parse JSON (may raise json.JSONDecodeError)
        data = json.loads(json_text)

        # Validate classification enum (may raise ValueError)
        classification_str = data["classification"]
        try:
            classification = FailureClassification(classification_str)
        except ValueError as e:
            self._logger.warning(
                "Unknown classification value: %s",
                classification_str,
                extra={
                    "workflow_run_id": context.workflow_run_id,
                    "work_item_id": context.work_item_id,
                    "iteration": context.iteration,
                },
                exc_info=True,
            )
            raise ValueError(f"Invalid classification value: {classification_str}") from e

        # Extract and validate confidence
        confidence = float(data["confidence"])
        if not 0.0 <= confidence <= 1.0:
            msg = f"Confidence must be between 0.0 and 1.0, got {confidence}"
            raise ValueError(msg)

        # Extract cross_cutting - optional field, defaults to False (backward-compatible)
        cross_cutting = bool(data.get("cross_cutting", False))

        # Build result
        return SystemicAnalysisResult(
            classification=classification,
            confidence=confidence,
            reasoning=data["reasoning"],
            affected_files=tuple(data.get("affected_files", [])),
            recommended_action=data["recommended_action"],
            cross_cutting=cross_cutting,
        )

    def _extract_json_from_response(
        self,
        response_text: str,
        context: AnalysisContext,
    ) -> str:
        """Extract JSON from response, stripping markdown code fences.

        Attempts to extract JSON from markdown code blocks (```json ... ```),
        falling back to finding JSON object in response if no fences found.

        Uses depth-tracking to find matching braces, avoiding greedy matching
        that would capture trailing braces from commentary.

        Args:
            response_text: Raw response text from LLM
            context: Analysis context for logging

        Returns:
            JSON string ready for parsing

        Raises:
            ValueError: If no valid JSON found in response
        """
        # Try to extract JSON from markdown code fence first
        # Pattern: ```json ... ``` or ``` ... ```
        json_match = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", response_text, re.DOTALL)
        if json_match:
            json_text = json_match.group(1).strip()
            self._logger.debug(
                "Extracted JSON from markdown code fence",
                extra={
                    "workflow_run_id": context.workflow_run_id,
                    "work_item_id": context.work_item_id,
                },
            )
            return json_text

        # Fallback: find JSON object by tracking brace depth
        # This avoids greedy matching (r"\{.*\}") which captures from first { to last }
        json_text = self._find_json_by_depth(response_text)
        if json_text:
            self._logger.debug(
                "Extracted JSON object from response using depth tracking",
                extra={
                    "workflow_run_id": context.workflow_run_id,
                    "work_item_id": context.work_item_id,
                },
            )
            return json_text

        # No JSON found
        msg = f"No JSON found in LLM response: {response_text[:200]}"
        raise ValueError(msg)

    def _find_json_by_depth(self, response_text: str) -> str | None:
        """Find JSON object by tracking brace depth.

        Locates the first opening brace and finds its matching closing brace
        by tracking depth. This prevents capturing trailing braces from
        commentary that would be included by greedy matching.

        Args:
            response_text: Text to search for JSON object

        Returns:
            JSON string if found, None otherwise
        """
        # Find the first opening brace
        start_idx = response_text.find("{")
        if start_idx == -1:
            return None

        # Track brace depth from the opening brace
        depth = 0
        in_string = False
        escape_next = False

        for idx in range(start_idx, len(response_text)):
            char = response_text[idx]

            # Handle string boundaries and escape sequences
            if escape_next:
                escape_next = False
                continue
            if char == "\\":
                escape_next = True
                continue
            if char == '"':
                in_string = not in_string
                continue

            # Only count braces outside strings
            if not in_string:
                if char == "{":
                    depth += 1
                elif char == "}":
                    depth -= 1
                    if depth == 0:
                        # Found matching closing brace
                        return response_text[start_idx : idx + 1]

        # Unmatched braces
        return None
