"""Production LLM-based systemic analysis adapter.

Implements :class:`~codetoreum.ports.output.systemic_analysis_service.ISystemicAnalysisService`
by delegating failure classification to a coding agent via the
:class:`~codetoreum.ports.output.coding_agent.ICodingAgent` port.

This adapter analyzes test failures and classifies their root causes
using Claude Code (or any other ``ICodingAgent`` implementation), enabling
the repair cycle to dispatch to the correct handling strategy (code fix,
environment rebuild, dependency fix, or transient retry).

Architecture
------------

- A bootstrap-wired ``coding_agent_factory: Callable[[IPromptBuilder], ICodingAgent]``
  is injected at construction. For each call, the adapter builds a
  call-local :class:`_SystemicAnalysisPromptBuilder` that closure-captures
  the failures + analysis context, then asks the factory for a fresh
  ``ICodingAgent`` bound to that builder.
- The adapter then drives the coding agent with a minimal synthetic
  :class:`AgentExecution` / :class:`WorkspaceContext` and a
  :class:`CodingAgentInvocationOptions`. The adapter-local prompt
  builder ignores the synthetic ``agent`` / ``work_item`` arguments
  and assembles the :class:`StructuredPrompt` from its closure-captured
  state.
- JSON parsing falls back to ``CODE_DEFECT`` on parse errors so a
  malformed agent response does not blow up the repair cycle.
- No event emission (caller's responsibility).
- Comprehensive error logging with no silent failures.
"""

from __future__ import annotations

import json
import logging
import re
from typing import TYPE_CHECKING

from codetoreum.adapters.secondary.free_form_coding_agent import (
    synthetic_agent_execution,
    synthetic_workspace_context,
)
from codetoreum.domain.coding_agent_types import InvocationMode
from codetoreum.domain.repair_cycle_types import (
    AnalysisContext,
    FailureClassification,
    RepairTestFailure,
    SystemicAnalysisResult,
)
from codetoreum.infrastructure.error_ids import ErrorRegistry
from codetoreum.ports.output.coding_agent import CodingAgentInvocationOptions
from codetoreum.ports.output.prompt_builder import IPromptBuilder, StructuredPrompt
from codetoreum.ports.output.systemic_analysis_service import ISystemicAnalysisService

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

    from codetoreum.domain.agent import Agent
    from codetoreum.domain.work_item import WorkItem
    from codetoreum.domain.workspace_context import WorkspaceContext
    from codetoreum.ports.output.coding_agent import ICodingAgent
    from codetoreum.ports.output.prompt_builder import ExecutionOutput

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Adapter-local prompt builder
# ---------------------------------------------------------------------------


class _SystemicAnalysisPromptBuilder(IPromptBuilder):
    """Per-call :class:`IPromptBuilder` for systemic failure analysis.

    Closure-captures the test failures and analysis context. The
    :meth:`build` method ignores the standard ``agent`` / ``work_item``
    / ``prior_outputs`` arguments — only the synthetic ``workspace_context``
    is used.

    The resulting :class:`StructuredPrompt` carries the full failure-
    analysis prompt in its ``task_description`` field. The rendered text
    (via :func:`render_structured_prompt_to_text`) becomes the prompt
    Claude Code receives.
    """

    def __init__(
        self,
        *,
        failures: list[RepairTestFailure],
        context: AnalysisContext,
    ) -> None:
        self._failures = failures
        self._context = context

    async def build(
        self,
        agent: Agent,
        work_item: WorkItem,
        workspace_context: WorkspaceContext,
        prior_outputs: tuple[ExecutionOutput, ...] = (),
    ) -> StructuredPrompt:
        """Assemble the structured prompt for systemic failure analysis."""
        task_description = _build_systemic_analysis_task_text(
            failures=self._failures,
            context=self._context,
        )
        return StructuredPrompt(
            role_description="Systemic analysis specialist",
            task_description=task_description,
            work_item=work_item,
            workspace_context=workspace_context,
            instructions=(
                "Respond with JSON only — no markdown, no commentary.",
                "Use the schema described in the task description.",
            ),
            constraints=(
                "Do not modify any files in the repository.",
                "Do not invoke any tools beyond what is needed to read the failures.",
            ),
            prior_outputs=(),
        )


def _build_systemic_analysis_task_text(
    *,
    failures: list[RepairTestFailure],
    context: AnalysisContext,
) -> str:
    """Build the textual systemic-analysis task body.

    Includes the failure list, prior fix attempts, iteration count, and
    the JSON-output schema. Kept as a module-level function so tests can
    exercise it directly.
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


# ---------------------------------------------------------------------------
# Adapter
# ---------------------------------------------------------------------------


class LLMSystemicAnalysisAdapter(ISystemicAnalysisService):
    """Production systemic analysis adapter using a coding agent.

    Constructs a per-call adapter-local
    :class:`_SystemicAnalysisPromptBuilder`, asks the injected
    ``coding_agent_factory`` for an :class:`ICodingAgent` bound to that
    builder, and drives a single short-lived execution to classify the
    failures.

    Example:
        adapter = LLMSystemicAnalysisAdapter(
            coding_agent_factory=lambda pb: ResilientCodingAgentDecorator(
                wrapped=FreeFormCodingAgent(prompt_builder=pb, ...),
            ),
        )
        result = await adapter.analyze(failures, context)
    """

    def __init__(
        self,
        coding_agent_factory: Callable[[IPromptBuilder], ICodingAgent],
        *,
        timeout_seconds: int = 300,
        invocation_mode: InvocationMode = InvocationMode.CONTAINERIZED,
        model: str = "claude-sonnet-4-6",
        container_image: str = "codetoreum-agent:latest",
        workspace_path: Path | None = None,
    ) -> None:
        """Initialize the systemic-analysis adapter.

        Args:
            coding_agent_factory: Per-call factory returning a fresh
                :class:`ICodingAgent` bound to the supplied
                :class:`IPromptBuilder`. The bootstrap wires this to a
                resilience-decorated
                :class:`~codetoreum.adapters.secondary.free_form_coding_agent.FreeFormCodingAgent`.
            timeout_seconds: Hard timeout for each coding-agent
                invocation (default 300s).
            invocation_mode: Where the coding agent runs. Defaults to
                :class:`InvocationMode.CONTAINERIZED` for production
                isolation; tests may pass :class:`InvocationMode.HOST`.
            model: Model name to request from the coding agent.
            container_image: Docker image for containerised mode. Only
                consumed when ``invocation_mode == CONTAINERIZED``.
            workspace_path: Optional workspace path the coding agent
                runs in. Systemic analysis has no workspace of its own;
                callers typically pass the orchestrator's working
                directory (or a temp dir for tests).

        Raises:
            ValueError: If ``coding_agent_factory`` is None or
                ``timeout_seconds`` is non-positive.
        """
        if coding_agent_factory is None:
            msg = "coding_agent_factory cannot be None"
            raise ValueError(msg)
        if timeout_seconds <= 0:
            msg = "timeout_seconds must be > 0"
            raise ValueError(msg)
        self._coding_agent_factory = coding_agent_factory
        self._timeout_seconds = timeout_seconds
        self._invocation_mode = invocation_mode
        self._model = model
        self._container_image = container_image
        self._workspace_path = workspace_path
        self._logger = logging.getLogger(__name__)

    async def analyze(
        self,
        failures: list[RepairTestFailure],
        context: AnalysisContext,
    ) -> SystemicAnalysisResult:
        """Classify test failures via the injected coding agent.

        Constructs an adapter-local prompt builder for the call, asks
        the factory for a fresh coding agent bound to it, then drives
        a single short-lived execution. Parses the agent's
        ``summary_text`` as JSON; falls back to ``CODE_DEFECT`` on
        parse errors.

        Args:
            failures: List of test failures to classify.
            context: Context including work item id, iteration count,
                and prior fix attempt history.

        Returns:
            :class:`SystemicAnalysisResult` with classification,
            confidence, reasoning, affected files, and recommended
            action.

        Raises:
            TimeoutError: If the coding agent exceeds its timeout.
            Exception: Other coding-agent failures (propagated for
                caller fallback).

        Note:
            Response parsing errors (json.JSONDecodeError, ValueError,
            KeyError) are caught internally and result in a
            ``CODE_DEFECT`` fallback response rather than propagating
            to the caller.
        """
        prompt_builder = _SystemicAnalysisPromptBuilder(
            failures=failures,
            context=context,
        )
        coding_agent = self._coding_agent_factory(prompt_builder)

        execution = synthetic_agent_execution(
            purpose="systemic_analysis",
            model=self._model,
        )
        workspace_context = synthetic_workspace_context(
            purpose="systemic_analysis",
            workspace_path=self._workspace_path,
        )

        mode_config: dict[str, object] = {}
        if self._invocation_mode == InvocationMode.CONTAINERIZED:
            mode_config = {"image": self._container_image}

        options = CodingAgentInvocationOptions(
            invocation_mode=self._invocation_mode,
            model=self._model,
            timeout_seconds=self._timeout_seconds,
            cost_limit_usd=None,
            mode_config=mode_config,
        )

        try:
            result = await coding_agent.execute(execution, workspace_context, options)
        except TimeoutError:
            self._logger.error(
                "Systemic analysis coding agent timed out",
                extra={
                    "workflow_run_id": context.workflow_run_id,
                    "work_item_id": context.work_item_id,
                    "iteration": context.iteration,
                    "timeout_seconds": self._timeout_seconds,
                    "error_id": ErrorRegistry.ERR_REPAIR_CYCLE_ERROR,
                },
                exc_info=True,
            )
            raise

        if not result.success:
            self._logger.error(
                "Systemic analysis coding agent failed",
                extra={
                    "workflow_run_id": context.workflow_run_id,
                    "work_item_id": context.work_item_id,
                    "iteration": context.iteration,
                    "error_summary": result.error_summary,
                    "error_id": ErrorRegistry.ERR_REPAIR_CYCLE_ERROR,
                },
            )
            return SystemicAnalysisResult(
                classification=FailureClassification.CODE_DEFECT,
                confidence=0.0,
                reasoning=f"Coding agent failed: {result.error_summary or 'unknown error'}",
                affected_files=(),
                recommended_action="Fix code defects",
                cross_cutting=False,
            )

        try:
            return self._parse_response(result.summary_text, context)
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

    # ------------------------------------------------------------------
    # Response parsing (kept identical to pre-migration behaviour)
    # ------------------------------------------------------------------

    def _parse_response(
        self,
        response_text: str,
        context: AnalysisContext,
    ) -> SystemicAnalysisResult:
        """Parse coding-agent response into :class:`SystemicAnalysisResult`.

        Strips markdown code fences from the response and extracts JSON.
        Validates JSON structure and enum values. On parse error or
        invalid enum, raises an exception that :meth:`analyze` catches
        for fallback handling.
        """
        json_text = self._extract_json_from_response(response_text, context)

        data = json.loads(json_text)

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

        confidence = float(data["confidence"])
        if not 0.0 <= confidence <= 1.0:
            msg = f"Confidence must be between 0.0 and 1.0, got {confidence}"
            raise ValueError(msg)

        cross_cutting = bool(data.get("cross_cutting", False))

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

        Attempts to extract JSON from markdown code blocks
        (```json ... ```), falling back to depth-tracked brace matching
        if no fences are found.
        """
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

        msg = f"No JSON found in coding-agent response: {response_text[:200]}"
        raise ValueError(msg)

    def _find_json_by_depth(self, response_text: str) -> str | None:
        """Find JSON object by tracking brace depth.

        Locates the first opening brace and finds its matching closing
        brace by tracking depth. This prevents greedy matching from
        capturing trailing braces from commentary.
        """
        start_idx = response_text.find("{")
        if start_idx == -1:
            return None

        depth = 0
        in_string = False
        escape_next = False

        for idx in range(start_idx, len(response_text)):
            char = response_text[idx]

            if escape_next:
                escape_next = False
                continue
            if char == "\\":
                escape_next = True
                continue
            if char == '"':
                in_string = not in_string
                continue

            if not in_string:
                if char == "{":
                    depth += 1
                elif char == "}":
                    depth -= 1
                    if depth == 0:
                        return response_text[start_idx : idx + 1]

        return None
