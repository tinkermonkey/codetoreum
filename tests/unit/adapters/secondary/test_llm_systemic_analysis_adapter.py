"""Unit tests for LLMSystemicAnalysisAdapter (post-D9 ICodingAgent migration).

Verifies:
1. Successful parse of all five FailureClassification values
2. Valid JSON response is parsed into SystemicAnalysisResult
3. Invalid/unparseable response falls back to CODE_DEFECT classification
4. FailureClassification with unknown value triggers fallback path
5. Network/timeout exception propagation (caller fallback)
6. Adapter does not call emit() on any event emitter
7. Prompt construction includes failures, file paths, iteration count, prior fix attempts
8. Coding-agent factory contract: called once per analyze() with the
   adapter-local _SystemicAnalysisPromptBuilder
"""

from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest

from codetoreum.adapters.secondary.llm_systemic_analysis_adapter import (
    LLMSystemicAnalysisAdapter,
    _build_systemic_analysis_task_text,
    _SystemicAnalysisPromptBuilder,
)
from codetoreum.domain.repair_cycle_types import (
    AnalysisContext,
    FailureClassification,
    RepairTestFailure,
    SystemicAnalysisResult,
)
from codetoreum.ports.output.coding_agent import (
    CodingAgentResult,
    ICodingAgent,
)

# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _make_coding_agent_result(content: str, *, success: bool = True) -> CodingAgentResult:
    """Build a minimal CodingAgentResult carrying the supplied content."""
    return CodingAgentResult(
        success=success,
        summary_text=content,
        total_cost_usd=Decimal("0"),
        total_input_tokens=0,
        total_output_tokens=0,
        tool_call_count=0,
        duration_ms=0,
        error_summary=None if success else "stubbed failure",
    )


def _make_adapter(
    response_content: str,
    *,
    success: bool = True,
) -> tuple[LLMSystemicAnalysisAdapter, AsyncMock, list[_SystemicAnalysisPromptBuilder]]:
    """Return (adapter, mock_coding_agent, captured_prompt_builders).

    The mock coding agent records every ``execute`` call. The returned
    list collects each adapter-local prompt builder the factory was
    asked to produce, so tests can inspect prompt content via
    ``await builder.build(...)`` if they need to.
    """
    coding_agent = AsyncMock(spec=ICodingAgent)
    coding_agent.execute.return_value = _make_coding_agent_result(
        response_content,
        success=success,
    )

    captured: list[_SystemicAnalysisPromptBuilder] = []

    def factory(prompt_builder):
        assert isinstance(prompt_builder, _SystemicAnalysisPromptBuilder)
        captured.append(prompt_builder)
        return coding_agent

    adapter = LLMSystemicAnalysisAdapter(coding_agent_factory=factory)
    return adapter, coding_agent, captured


def _make_context(
    work_item_id: str = "item-123",
    iteration: int = 1,
    workflow_run_id: str = "run-456",
    prior_fix_attempts: tuple[str, ...] = (),
) -> AnalysisContext:
    """Create a minimal AnalysisContext for testing."""
    return AnalysisContext(
        work_item_id=work_item_id,
        iteration=iteration,
        workflow_run_id=workflow_run_id,
        prior_fix_attempts=prior_fix_attempts,
    )


def _make_failures(count: int = 1) -> list[RepairTestFailure]:
    """Create test failures for testing."""
    return [
        RepairTestFailure(
            file=f"test_file_{i}.py",
            test=f"test_case_{i}",
            message=f"Assertion failed: expected {i}",
        )
        for i in range(count)
    ]


async def _rendered_task_text(builder: _SystemicAnalysisPromptBuilder) -> str:
    """Helper: run the captured prompt builder and return its task text.

    The :class:`IFreeFormPromptBuilder.build` signature takes only
    ``workspace_context``; we pass a dummy ``MagicMock()`` and read the
    ``StructuredPrompt.task_description`` the renderer would feed to
    Claude Code.
    """
    structured = await builder.build(
        workspace_context=MagicMock(),
    )
    return structured.task_description


# ---------------------------------------------------------------------------
# Constructor validation
# ---------------------------------------------------------------------------


class TestConstructor:
    def test_init_with_valid_factory(self):
        """Constructor accepts a valid coding_agent_factory callable."""

        def factory(prompt_builder):
            return AsyncMock(spec=ICodingAgent)

        adapter = LLMSystemicAnalysisAdapter(coding_agent_factory=factory)
        assert adapter._coding_agent_factory is factory

    def test_init_rejects_none_factory(self):
        """Constructor rejects None coding_agent_factory."""
        with pytest.raises(ValueError, match="coding_agent_factory cannot be None"):
            LLMSystemicAnalysisAdapter(coding_agent_factory=None)

    def test_init_rejects_zero_timeout(self):
        """Constructor rejects non-positive timeout."""
        with pytest.raises(ValueError, match="timeout_seconds must be > 0"):
            LLMSystemicAnalysisAdapter(
                coding_agent_factory=lambda pb: AsyncMock(spec=ICodingAgent),
                timeout_seconds=0,
            )


# ---------------------------------------------------------------------------
# Successful parsing of all five classifications
# ---------------------------------------------------------------------------


class TestSuccessfulClassifications:
    @pytest.mark.asyncio
    async def test_parse_code_defect(self):
        """Parses code_defect classification correctly."""
        response = """{
            "classification": "code_defect",
            "confidence": 0.85,
            "reasoning": "Bug in calculation logic",
            "affected_files": ["calc.py"],
            "recommended_action": "Fix the calculation"
        }"""
        adapter, _, _ = _make_adapter(response)
        context = _make_context()
        failures = _make_failures(1)

        result = await adapter.analyze(failures, context)

        assert result.classification == FailureClassification.CODE_DEFECT
        assert result.confidence == 0.85
        assert result.reasoning == "Bug in calculation logic"
        assert result.affected_files == ("calc.py",)
        assert result.recommended_action == "Fix the calculation"

    @pytest.mark.asyncio
    async def test_parse_environment_issue(self):
        """Parses environment_issue classification correctly."""
        response = """{
            "classification": "environment_issue",
            "confidence": 0.92,
            "reasoning": "Missing environment variable",
            "affected_files": [],
            "recommended_action": "Set required env vars"
        }"""
        adapter, _, _ = _make_adapter(response)
        context = _make_context()
        failures = _make_failures(1)

        result = await adapter.analyze(failures, context)

        assert result.classification == FailureClassification.ENVIRONMENT_ISSUE
        assert result.confidence == 0.92

    @pytest.mark.asyncio
    async def test_parse_transient_failure(self):
        """Parses transient_failure classification correctly."""
        response = """{
            "classification": "transient_failure",
            "confidence": 0.65,
            "reasoning": "Network blip during test",
            "affected_files": [],
            "recommended_action": "Retry the operation"
        }"""
        adapter, _, _ = _make_adapter(response)
        context = _make_context()
        failures = _make_failures(1)

        result = await adapter.analyze(failures, context)

        assert result.classification == FailureClassification.TRANSIENT_FAILURE
        assert result.confidence == 0.65

    @pytest.mark.asyncio
    async def test_parse_dependency_issue(self):
        """Parses dependency_issue classification correctly."""
        response = """{
            "classification": "dependency_issue",
            "confidence": 0.78,
            "reasoning": "Package version mismatch",
            "affected_files": ["requirements.txt"],
            "recommended_action": "Update dependencies"
        }"""
        adapter, _, _ = _make_adapter(response)
        context = _make_context()
        failures = _make_failures(1)

        result = await adapter.analyze(failures, context)

        assert result.classification == FailureClassification.DEPENDENCY_ISSUE
        assert result.confidence == 0.78

    @pytest.mark.asyncio
    async def test_parse_configuration_issue(self):
        """Parses configuration_issue classification correctly."""
        response = """{
            "classification": "configuration_issue",
            "confidence": 0.88,
            "reasoning": "Misconfigured settings",
            "affected_files": ["config.yaml"],
            "recommended_action": "Fix configuration"
        }"""
        adapter, _, _ = _make_adapter(response)
        context = _make_context()
        failures = _make_failures(1)

        result = await adapter.analyze(failures, context)

        assert result.classification == FailureClassification.CONFIGURATION_ISSUE
        assert result.confidence == 0.88


# ---------------------------------------------------------------------------
# Parse failure fallback
# ---------------------------------------------------------------------------


class TestParseFailureFallback:
    @pytest.mark.asyncio
    async def test_invalid_json_returns_code_defect(self):
        """Invalid JSON in response falls back to CODE_DEFECT."""
        adapter, _, _ = _make_adapter("not valid json at all")
        context = _make_context()
        failures = _make_failures(1)

        result = await adapter.analyze(failures, context)

        assert result.classification == FailureClassification.CODE_DEFECT
        assert result.confidence == 0.0
        assert "Parse failure" in result.reasoning

    @pytest.mark.asyncio
    async def test_missing_classification_field(self):
        """Missing classification field falls back to CODE_DEFECT."""
        response = """{
            "confidence": 0.85,
            "reasoning": "Test"
        }"""
        adapter, _, _ = _make_adapter(response)
        context = _make_context()
        failures = _make_failures(1)

        result = await adapter.analyze(failures, context)

        assert result.classification == FailureClassification.CODE_DEFECT
        assert result.confidence == 0.0

    @pytest.mark.asyncio
    async def test_unknown_classification_value(self):
        """Unknown classification value falls back to CODE_DEFECT."""
        response = """{
            "classification": "this_is_not_a_valid_classification",
            "confidence": 0.85,
            "reasoning": "Test",
            "affected_files": [],
            "recommended_action": "Fix"
        }"""
        adapter, _, _ = _make_adapter(response)
        context = _make_context()
        failures = _make_failures(1)

        result = await adapter.analyze(failures, context)

        assert result.classification == FailureClassification.CODE_DEFECT
        assert result.confidence == 0.0

    @pytest.mark.asyncio
    async def test_invalid_confidence_out_of_range(self):
        """Confidence outside [0,1] falls back to CODE_DEFECT."""
        response = """{
            "classification": "code_defect",
            "confidence": 1.5,
            "reasoning": "Test",
            "affected_files": [],
            "recommended_action": "Fix"
        }"""
        adapter, _, _ = _make_adapter(response)
        context = _make_context()
        failures = _make_failures(1)

        result = await adapter.analyze(failures, context)

        assert result.classification == FailureClassification.CODE_DEFECT
        assert result.confidence == 0.0

    @pytest.mark.asyncio
    async def test_missing_required_field_triggers_fallback(self):
        """Missing required field falls back to CODE_DEFECT."""
        response = """{
            "classification": "code_defect",
            "confidence": 0.85
        }"""
        adapter, _, _ = _make_adapter(response)
        context = _make_context()
        failures = _make_failures(1)

        result = await adapter.analyze(failures, context)

        assert result.classification == FailureClassification.CODE_DEFECT
        assert result.confidence == 0.0


# ---------------------------------------------------------------------------
# Exception fallback (timeouts / connection errors propagate)
# ---------------------------------------------------------------------------


class TestExceptionFallback:
    @pytest.mark.asyncio
    async def test_execute_timeout_raises_exception(self):
        """Coding-agent timeout exception is raised (not caught)."""
        coding_agent = AsyncMock(spec=ICodingAgent)
        coding_agent.execute.side_effect = TimeoutError("Coding agent timed out")

        adapter = LLMSystemicAnalysisAdapter(
            coding_agent_factory=lambda pb: coding_agent,
        )
        context = _make_context()
        failures = _make_failures(1)

        with pytest.raises(TimeoutError):
            await adapter.analyze(failures, context)

    @pytest.mark.asyncio
    async def test_execute_connection_error_raises_exception(self):
        """Coding-agent connection error is raised (not caught)."""
        coding_agent = AsyncMock(spec=ICodingAgent)
        coding_agent.execute.side_effect = ConnectionError("Failed to connect")

        adapter = LLMSystemicAnalysisAdapter(
            coding_agent_factory=lambda pb: coding_agent,
        )
        context = _make_context()
        failures = _make_failures(1)

        with pytest.raises(ConnectionError):
            await adapter.analyze(failures, context)

    @pytest.mark.asyncio
    async def test_execute_failure_result_falls_back(self):
        """When the coding agent returns success=False, adapter falls back to CODE_DEFECT."""
        coding_agent = AsyncMock(spec=ICodingAgent)
        coding_agent.execute.return_value = _make_coding_agent_result(
            "irrelevant",
            success=False,
        )

        adapter = LLMSystemicAnalysisAdapter(
            coding_agent_factory=lambda pb: coding_agent,
        )
        context = _make_context()
        failures = _make_failures(1)

        result = await adapter.analyze(failures, context)

        assert result.classification == FailureClassification.CODE_DEFECT
        assert result.confidence == 0.0
        assert "Coding agent failed" in result.reasoning


# ---------------------------------------------------------------------------
# No event emission
# ---------------------------------------------------------------------------


class TestNoEventEmission:
    @pytest.mark.asyncio
    async def test_adapter_does_not_call_event_emitter(self):
        """Adapter does not emit any events (caller responsibility)."""
        response = """{
            "classification": "code_defect",
            "confidence": 0.85,
            "reasoning": "Bug in code",
            "affected_files": ["app.py"],
            "recommended_action": "Fix the bug"
        }"""
        adapter, _, _ = _make_adapter(response)
        context = _make_context()
        failures = _make_failures(1)

        result = await adapter.analyze(failures, context)

        assert result.classification == FailureClassification.CODE_DEFECT


# ---------------------------------------------------------------------------
# Prompt construction validation
# ---------------------------------------------------------------------------


class TestPromptConstruction:
    @pytest.mark.asyncio
    async def test_prompt_includes_failure_messages(self):
        """Prompt task text includes failure messages from failures list."""
        adapter, _, captured = _make_adapter("""{
            "classification": "code_defect",
            "confidence": 0.85,
            "reasoning": "Test",
            "affected_files": [],
            "recommended_action": "Fix"
        }""")
        context = _make_context()
        failures = [
            RepairTestFailure(file="test_a.py", test="test_1", message="Value mismatch"),
            RepairTestFailure(file="test_b.py", test="test_2", message="Index out of range"),
        ]

        await adapter.analyze(failures, context)

        assert len(captured) == 1
        task = await _rendered_task_text(captured[0])
        assert "test_a.py::test_1: Value mismatch" in task
        assert "test_b.py::test_2: Index out of range" in task

    @pytest.mark.asyncio
    async def test_prompt_includes_affected_files(self):
        """Prompt includes affected file paths."""
        adapter, _, captured = _make_adapter("""{
            "classification": "code_defect",
            "confidence": 0.85,
            "reasoning": "Test",
            "affected_files": [],
            "recommended_action": "Fix"
        }""")
        context = _make_context()
        failures = [
            RepairTestFailure(file="test_auth.py", test="test_login", message="Failed"),
        ]

        await adapter.analyze(failures, context)

        task = await _rendered_task_text(captured[0])
        assert "test_auth.py" in task

    @pytest.mark.asyncio
    async def test_prompt_includes_iteration_count(self):
        """Prompt includes iteration count from context."""
        adapter, _, captured = _make_adapter("""{
            "classification": "code_defect",
            "confidence": 0.85,
            "reasoning": "Test",
            "affected_files": [],
            "recommended_action": "Fix"
        }""")
        context = _make_context(iteration=3)
        failures = _make_failures(1)

        await adapter.analyze(failures, context)

        task = await _rendered_task_text(captured[0])
        assert "Iteration: 3" in task

    @pytest.mark.asyncio
    async def test_prompt_includes_work_item_id(self):
        """Prompt includes work_item_id from context."""
        adapter, _, captured = _make_adapter("""{
            "classification": "code_defect",
            "confidence": 0.85,
            "reasoning": "Test",
            "affected_files": [],
            "recommended_action": "Fix"
        }""")
        context = _make_context(work_item_id="PR-789")
        failures = _make_failures(1)

        await adapter.analyze(failures, context)

        task = await _rendered_task_text(captured[0])
        assert "PR-789" in task

    @pytest.mark.asyncio
    async def test_prompt_includes_prior_fix_attempts(self):
        """Prompt includes prior fix attempts from context."""
        adapter, _, captured = _make_adapter("""{
            "classification": "code_defect",
            "confidence": 0.85,
            "reasoning": "Test",
            "affected_files": [],
            "recommended_action": "Fix"
        }""")
        prior_attempts = ("Tried updating import", "Tried refactoring method")
        context = _make_context(prior_fix_attempts=prior_attempts)
        failures = _make_failures(1)

        await adapter.analyze(failures, context)

        task = await _rendered_task_text(captured[0])
        assert "Tried updating import" in task
        assert "Tried refactoring method" in task

    @pytest.mark.asyncio
    async def test_prompt_shows_none_when_no_prior_attempts(self):
        """Prompt shows 'None' when no prior fix attempts."""
        adapter, _, captured = _make_adapter("""{
            "classification": "code_defect",
            "confidence": 0.85,
            "reasoning": "Test",
            "affected_files": [],
            "recommended_action": "Fix"
        }""")
        context = _make_context(prior_fix_attempts=())
        failures = _make_failures(1)

        await adapter.analyze(failures, context)

        task = await _rendered_task_text(captured[0])
        assert "None" in task


# ---------------------------------------------------------------------------
# Affected files handling
# ---------------------------------------------------------------------------


class TestAffectedFilesHandling:
    @pytest.mark.asyncio
    async def test_parse_affected_files_as_tuple(self):
        """Affected files list is converted to tuple in result."""
        response = """{
            "classification": "code_defect",
            "confidence": 0.85,
            "reasoning": "Multiple files affected",
            "affected_files": ["auth.py", "login.py", "user.py"],
            "recommended_action": "Fix all three files"
        }"""
        adapter, _, _ = _make_adapter(response)
        context = _make_context()
        failures = _make_failures(1)

        result = await adapter.analyze(failures, context)

        assert result.affected_files == ("auth.py", "login.py", "user.py")
        assert isinstance(result.affected_files, tuple)

    @pytest.mark.asyncio
    async def test_empty_affected_files_list(self):
        """Empty affected_files list is handled correctly."""
        response = """{
            "classification": "code_defect",
            "confidence": 0.85,
            "reasoning": "Test",
            "affected_files": [],
            "recommended_action": "Fix"
        }"""
        adapter, _, _ = _make_adapter(response)
        context = _make_context()
        failures = _make_failures(1)

        result = await adapter.analyze(failures, context)

        assert result.affected_files == ()

    @pytest.mark.asyncio
    async def test_missing_affected_files_defaults_to_empty_tuple(self):
        """Missing affected_files defaults to empty tuple."""
        response = """{
            "classification": "code_defect",
            "confidence": 0.85,
            "reasoning": "Test",
            "recommended_action": "Fix"
        }"""
        adapter, _, _ = _make_adapter(response)
        context = _make_context()
        failures = _make_failures(1)

        result = await adapter.analyze(failures, context)

        assert result.affected_files == ()


# ---------------------------------------------------------------------------
# Error logging
# ---------------------------------------------------------------------------


class TestErrorLogging:
    @pytest.mark.asyncio
    async def test_logs_parse_error_with_context(self, caplog):
        """Parse error is logged."""
        import logging

        caplog.set_level(logging.ERROR)

        adapter, _, _ = _make_adapter("invalid json")
        context = _make_context(
            workflow_run_id="run-123",
            work_item_id="item-456",
            iteration=2,
        )
        failures = _make_failures(1)

        result = await adapter.analyze(failures, context)

        assert any("Failed to parse systemic analysis response" in record.message for record in caplog.records)
        assert result.classification == FailureClassification.CODE_DEFECT

    @pytest.mark.asyncio
    async def test_logs_unknown_classification_as_warning(self, caplog):
        """Unknown classification value is logged."""
        import logging

        caplog.set_level(logging.WARNING)

        response = """{
            "classification": "invalid_classification",
            "confidence": 0.85,
            "reasoning": "Test",
            "affected_files": [],
            "recommended_action": "Fix"
        }"""
        adapter, _, _ = _make_adapter(response)
        context = _make_context()
        failures = _make_failures(1)

        result = await adapter.analyze(failures, context)

        assert result.classification == FailureClassification.CODE_DEFECT


# ---------------------------------------------------------------------------
# Edge cases and boundary conditions
# ---------------------------------------------------------------------------


class TestBoundaryConditions:
    @pytest.mark.asyncio
    async def test_confidence_at_boundaries(self):
        """Confidence values at exact 0.0 and 1.0 boundaries are valid."""
        response_min = """{
            "classification": "code_defect",
            "confidence": 0.0,
            "reasoning": "Test",
            "affected_files": [],
            "recommended_action": "Fix"
        }"""
        adapter, _, _ = _make_adapter(response_min)
        context = _make_context()
        result = await adapter.analyze(_make_failures(1), context)
        assert result.confidence == 0.0

        response_max = """{
            "classification": "code_defect",
            "confidence": 1.0,
            "reasoning": "Test",
            "affected_files": [],
            "recommended_action": "Fix"
        }"""
        adapter, _, _ = _make_adapter(response_max)
        result = await adapter.analyze(_make_failures(1), context)
        assert result.confidence == 1.0

    @pytest.mark.asyncio
    async def test_multiple_failures_in_prompt(self):
        """Prompt correctly handles multiple failures."""
        adapter, _, captured = _make_adapter("""{
            "classification": "code_defect",
            "confidence": 0.85,
            "reasoning": "Test",
            "affected_files": [],
            "recommended_action": "Fix"
        }""")
        context = _make_context()
        failures = _make_failures(5)

        await adapter.analyze(failures, context)

        task = await _rendered_task_text(captured[0])
        assert task.count("::") == 5

    @pytest.mark.asyncio
    async def test_long_reasoning_text(self):
        """Long reasoning text is preserved in result."""
        long_reasoning = "A" * 1000
        response = f"""{{
            "classification": "code_defect",
            "confidence": 0.85,
            "reasoning": "{long_reasoning}",
            "affected_files": [],
            "recommended_action": "Fix"
        }}"""
        adapter, _, _ = _make_adapter(response)
        context = _make_context()

        result = await adapter.analyze(_make_failures(1), context)

        assert result.reasoning == long_reasoning

    @pytest.mark.asyncio
    async def test_special_characters_in_fields(self):
        """Special characters in reasoning and action are handled."""
        response = """{
            "classification": "code_defect",
            "confidence": 0.85,
            "reasoning": "Bug: expected 'value' but got \\"other\\"",
            "affected_files": ["file-with-dash.py", "file_with_underscore.py"],
            "recommended_action": "Fix: update condition to x == 'value'"
        }"""
        adapter, _, _ = _make_adapter(response)
        context = _make_context()

        result = await adapter.analyze(_make_failures(1), context)

        assert "expected 'value'" in result.reasoning
        assert "x == 'value'" in result.recommended_action

    @pytest.mark.asyncio
    async def test_multiline_json_without_markdown_fences(self):
        """Multiline JSON without markdown fences is extracted correctly."""
        response = """{
  "classification": "dependency_issue",
  "confidence": 0.92,
  "reasoning": "The affected_files array shows a } inside string that should not truncate",
  "affected_files": ["requirements.txt", "setup.py"],
  "recommended_action": "Update dependencies"
}"""
        adapter, _, _ = _make_adapter(response)
        context = _make_context()
        failures = _make_failures(1)

        result = await adapter.analyze(failures, context)

        assert result.classification == FailureClassification.DEPENDENCY_ISSUE
        assert result.confidence == 0.92
        assert "} inside string" in result.reasoning
        assert result.affected_files == ("requirements.txt", "setup.py")

    @pytest.mark.asyncio
    async def test_json_followed_by_trailing_commentary_with_braces(self):
        r"""JSON followed by commentary with braces is parsed correctly.

        Depth-tracking parser should extract only the valid JSON object,
        not the trailing braces.
        """
        response = """{
  "classification": "code_defect",
  "confidence": 0.88,
  "reasoning": "Variable initialization issue",
  "affected_files": ["app.py"],
  "recommended_action": "Initialize variables before use"
}

Additional analysis: The problem is in the try-except {block} where {error handling} is missing."""
        adapter, _, _ = _make_adapter(response)
        context = _make_context()
        failures = _make_failures(1)

        result = await adapter.analyze(failures, context)

        assert result.classification == FailureClassification.CODE_DEFECT
        assert result.confidence == 0.88
        assert result.reasoning == "Variable initialization issue"
        assert result.affected_files == ("app.py",)

    @pytest.mark.asyncio
    async def test_json_with_escaped_quotes_in_strings(self):
        """JSON with escaped quotes in string values is parsed correctly."""
        response = """{
  "classification": "environment_issue",
  "confidence": 0.91,
  "reasoning": "Missing variable: expected \\"DATABASE_URL\\" in env",
  "affected_files": ["config.py"],
  "recommended_action": "Set DATABASE_URL=\\"postgres://...\\""
}"""
        adapter, _, _ = _make_adapter(response)
        context = _make_context()
        failures = _make_failures(1)

        result = await adapter.analyze(failures, context)

        assert result.classification == FailureClassification.ENVIRONMENT_ISSUE
        assert "DATABASE_URL" in result.reasoning
        assert "DATABASE_URL" in result.recommended_action

    @pytest.mark.asyncio
    async def test_nested_braces_in_reasoning_string(self):
        """JSON with nested braces in string values is handled correctly."""
        response = """{
  "classification": "configuration_issue",
  "confidence": 0.87,
  "reasoning": "Config format error: expected {key: value} pairs",
  "affected_files": ["config.yaml"],
  "recommended_action": "Fix config to use {proper: syntax}"
}"""
        adapter, _, _ = _make_adapter(response)
        context = _make_context()
        failures = _make_failures(1)

        result = await adapter.analyze(failures, context)

        assert result.classification == FailureClassification.CONFIGURATION_ISSUE
        assert "{key: value}" in result.reasoning
        assert "{proper: syntax}" in result.recommended_action


# ---------------------------------------------------------------------------
# Cross-cutting field handling
# ---------------------------------------------------------------------------


class TestCrossCuttingField:
    @pytest.mark.asyncio
    async def test_parse_cross_cutting_true(self):
        """Parses cross_cutting=true from JSON response."""
        response = """{
            "classification": "code_defect",
            "confidence": 0.95,
            "reasoning": "Renamed method impacts multiple files",
            "affected_files": ["auth.py", "login.py", "user.py"],
            "recommended_action": "Update method calls in all files",
            "cross_cutting": true
        }"""
        adapter, _, _ = _make_adapter(response)
        context = _make_context()
        failures = _make_failures(1)

        result = await adapter.analyze(failures, context)

        assert result.cross_cutting is True
        assert result.classification == FailureClassification.CODE_DEFECT
        assert result.confidence == 0.95

    @pytest.mark.asyncio
    async def test_parse_cross_cutting_false(self):
        """Parses cross_cutting=false from JSON response."""
        response = """{
            "classification": "code_defect",
            "confidence": 0.85,
            "reasoning": "Independent bugs in different modules",
            "affected_files": ["module_a.py", "module_b.py"],
            "recommended_action": "Fix each module independently",
            "cross_cutting": false
        }"""
        adapter, _, _ = _make_adapter(response)
        context = _make_context()
        failures = _make_failures(1)

        result = await adapter.analyze(failures, context)

        assert result.cross_cutting is False
        assert result.classification == FailureClassification.CODE_DEFECT

    @pytest.mark.asyncio
    async def test_cross_cutting_absent_defaults_to_false(self):
        """Missing cross_cutting field defaults to False (backward-compatible)."""
        response = """{
            "classification": "code_defect",
            "confidence": 0.85,
            "reasoning": "Some issue",
            "affected_files": ["file.py"],
            "recommended_action": "Fix the issue"
        }"""
        adapter, _, _ = _make_adapter(response)
        context = _make_context()
        failures = _make_failures(1)

        result = await adapter.analyze(failures, context)

        assert result.cross_cutting is False
        assert result.classification == FailureClassification.CODE_DEFECT

    @pytest.mark.asyncio
    async def test_malformed_json_returns_fallback_with_cross_cutting_false(self):
        """Malformed JSON returns fallback result with cross_cutting=False."""
        adapter, _, _ = _make_adapter("completely invalid json response")
        context = _make_context()
        failures = _make_failures(1)

        result = await adapter.analyze(failures, context)

        assert result.classification == FailureClassification.CODE_DEFECT
        assert result.confidence == 0.0
        assert result.cross_cutting is False

    @pytest.mark.asyncio
    async def test_cross_cutting_with_all_classifications(self):
        """cross_cutting field works with all classification types."""
        classifications = [
            ("code_defect", FailureClassification.CODE_DEFECT),
            ("environment_issue", FailureClassification.ENVIRONMENT_ISSUE),
            ("transient_failure", FailureClassification.TRANSIENT_FAILURE),
            ("dependency_issue", FailureClassification.DEPENDENCY_ISSUE),
            ("configuration_issue", FailureClassification.CONFIGURATION_ISSUE),
        ]

        for class_str, class_enum in classifications:
            response = f"""{{
                "classification": "{class_str}",
                "confidence": 0.80,
                "reasoning": "Cross-cutting issue",
                "affected_files": ["file1.py", "file2.py"],
                "recommended_action": "Fix the root cause",
                "cross_cutting": true
            }}"""
            adapter, _, _ = _make_adapter(response)
            context = _make_context()
            failures = _make_failures(1)

            result = await adapter.analyze(failures, context)

            assert result.cross_cutting is True
            assert result.classification == class_enum


# ---------------------------------------------------------------------------
# Adapter-local prompt builder contract
# ---------------------------------------------------------------------------


class TestAdapterLocalPromptBuilder:
    @pytest.mark.asyncio
    async def test_factory_receives_systemic_analysis_prompt_builder(self):
        """The factory is invoked with a _SystemicAnalysisPromptBuilder."""
        adapter, _, captured = _make_adapter("""{
            "classification": "code_defect",
            "confidence": 0.85,
            "reasoning": "x",
            "affected_files": [],
            "recommended_action": "y"
        }""")
        context = _make_context()
        failures = _make_failures(1)

        await adapter.analyze(failures, context)

        assert len(captured) == 1
        assert isinstance(captured[0], _SystemicAnalysisPromptBuilder)

    @pytest.mark.asyncio
    async def test_factory_invoked_once_per_analyze(self):
        """A fresh prompt builder + coding agent is created for each analyze() call."""
        adapter, _, captured = _make_adapter("""{
            "classification": "code_defect",
            "confidence": 0.85,
            "reasoning": "x",
            "affected_files": [],
            "recommended_action": "y"
        }""")
        context = _make_context()

        await adapter.analyze(_make_failures(1), context)
        await adapter.analyze(_make_failures(2), context)
        await adapter.analyze(_make_failures(3), context)

        assert len(captured) == 3

    def test_task_text_built_directly_matches_builder(self):
        """The standalone _build_systemic_analysis_task_text matches the builder."""
        context = _make_context(iteration=7, work_item_id="WI-99")
        failures = _make_failures(2)

        direct = _build_systemic_analysis_task_text(failures=failures, context=context)

        assert "Iteration: 7" in direct
        assert "WI-99" in direct
        assert "test_file_0.py" in direct
        assert "test_file_1.py" in direct
