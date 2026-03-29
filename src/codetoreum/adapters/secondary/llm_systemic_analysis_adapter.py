"""Production LLM-based systemic analysis adapter.

Implements ISystemicAnalysisService by delegating failure classification to the LLM
agent using the existing systemic_analysis sub-task infrastructure.

This adapter analyzes test failures and classifies their root causes using Claude Code,
enabling the repair cycle to dispatch to the correct handling strategy (code fix,
environment rebuild, dependency fix, or transient retry).

Architecture:
- Dependency injection of ILLMProvider for testability
- Prompt construction with comprehensive context (failures, prior attempts, iteration)
- JSON parsing with fallback to CODE_DEFECT classification on parse errors
- No event emission (caller's responsibility)
- Comprehensive error logging with no silent failures
"""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from codetoreum.ports.output.llm_provider import ILLMProvider

from codetoreum.domain.repair_cycle_types import (
    AnalysisContext,
    FailureClassification,
    RepairTestFailure,
    SystemicAnalysisResult,
)
from codetoreum.ports.output.systemic_analysis_service import ISystemicAnalysisService

logger = logging.getLogger(__name__)


class LLMSystemicAnalysisAdapter(ISystemicAnalysisService):
    """Production systemic analysis adapter using LLM for classification.

    Analyzes test failures by delegating to Claude Code via the LLM provider,
    constructing rich context prompts that include failure details, prior fix
    attempts, and iteration count.

    Example:
        adapter = LLMSystemicAnalysisAdapter(llm_provider)
        result = await adapter.analyze(failures, context)
    """

    def __init__(self, llm_provider: ILLMProvider) -> None:
        """Initialize production systemic analysis adapter.

        Args:
            llm_provider: ILLMProvider implementation (e.g., Claude Code adapter)

        Raises:
            ValueError: If llm_provider is None
        """
        if llm_provider is None:
            msg = "llm_provider cannot be None"
            raise ValueError(msg)
        self._llm_provider = llm_provider
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
            None - always returns a result, even on parse errors (fallback to CODE_DEFECT)
        """
        try:
            prompt = self._build_prompt(failures, context)
            response = await self._llm_provider.execute(prompt)
            return self._parse_response(response.content, context)
        except Exception as e:
            self._logger.error(
                "Failed to parse systemic analysis response, defaulting to code_defect",
                extra={
                    "workflow_run_id": context.workflow_run_id,
                    "work_item_id": context.work_item_id,
                    "iteration": context.iteration,
                    "error": str(e),
                },
                exc_info=True,
            )
            return SystemicAnalysisResult(
                classification=FailureClassification.CODE_DEFECT,
                confidence=0.0,
                reasoning=f"Parse failure: {e}",
                affected_files=(),
                recommended_action="Fix code defects",
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
        failure_lines = "\n".join(
            f"- {f.file}::{f.test}: {f.message}" for f in failures
        )
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
  "recommended_action": "<action>"
}}"""

    def _parse_response(
        self,
        response_text: str,
        context: AnalysisContext,
    ) -> SystemicAnalysisResult:
        """Parse LLM response into SystemicAnalysisResult.

        Validates JSON structure and enum values. On parse error or invalid enum,
        raises exception that will be caught by analyze() for fallback handling.

        Args:
            response_text: Raw LLM response text
            context: Analysis context for logging

        Returns:
            Parsed SystemicAnalysisResult

        Raises:
            json.JSONDecodeError: If response is not valid JSON
            ValueError: If classification value is not a valid FailureClassification
            KeyError: If required JSON fields are missing
        """
        # Parse JSON (may raise json.JSONDecodeError)
        data = json.loads(response_text)

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
                exc_info=False,
            )
            raise ValueError(f"Invalid classification value: {classification_str}") from e

        # Extract and validate confidence
        confidence = float(data["confidence"])
        if not 0.0 <= confidence <= 1.0:
            msg = f"Confidence must be between 0.0 and 1.0, got {confidence}"
            raise ValueError(msg)

        # Build result
        return SystemicAnalysisResult(
            classification=classification,
            confidence=confidence,
            reasoning=data["reasoning"],
            affected_files=tuple(data.get("affected_files", [])),
            recommended_action=data["recommended_action"],
        )
