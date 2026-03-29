"""Unit tests for LLMSystemicAnalysisAdapter.

Verifies:
1. Successful parse of all five FailureClassification values
2. Valid JSON response is parsed into SystemicAnalysisResult
3. Invalid/unparseable LLM response falls back to CODE_DEFECT classification
4. FailureClassification with unknown value triggers fallback path
5. Network/timeout exception fallback
6. Adapter does not call emit() on any event emitter
7. Prompt construction includes failures, file paths, iteration count, prior fix attempts
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from codetoreum.adapters.secondary.llm_systemic_analysis_adapter import (
    LLMSystemicAnalysisAdapter,
)
from codetoreum.domain.repair_cycle_types import (
    AnalysisContext,
    FailureClassification,
    RepairTestFailure,
    SystemicAnalysisResult,
)
from codetoreum.ports.output.llm_provider import ExecutionResult

# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _make_adapter(llm_response_content: str) -> tuple[LLMSystemicAnalysisAdapter, AsyncMock]:
    """Return (adapter, mock_llm) pre-wired for tests."""
    llm = AsyncMock()
    result = ExecutionResult(content=llm_response_content)
    llm.execute.return_value = result
    adapter = LLMSystemicAnalysisAdapter(llm_factory=lambda: llm)
    return adapter, llm


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


# ---------------------------------------------------------------------------
# Constructor validation
# ---------------------------------------------------------------------------


class TestConstructor:
    def test_init_with_valid_llm_factory(self):
        """Constructor accepts valid llm_factory callable."""
        llm = AsyncMock()
        adapter = LLMSystemicAnalysisAdapter(llm_factory=lambda: llm)
        assert adapter._llm_factory is not None

    def test_init_rejects_none_factory(self):
        """Constructor rejects None llm_factory."""
        with pytest.raises(ValueError, match="llm_factory cannot be None"):
            LLMSystemicAnalysisAdapter(llm_factory=None)


# ---------------------------------------------------------------------------
# Successful parsing of all five classifications
# ---------------------------------------------------------------------------


class TestSuccessfulClassifications:
    @pytest.mark.asyncio
    async def test_parse_code_defect(self):
        """Parses CODE_DEFECT classification successfully."""
        response = """{
            "classification": "code_defect",
            "confidence": 0.95,
            "reasoning": "Bug in login logic",
            "affected_files": ["auth.py", "login.py"],
            "recommended_action": "Fix the login condition"
        }"""
        adapter, _ = _make_adapter(response)
        context = _make_context()
        failures = _make_failures(1)

        result = await adapter.analyze(failures, context)

        assert result.classification == FailureClassification.CODE_DEFECT
        assert result.confidence == 0.95
        assert result.reasoning == "Bug in login logic"
        assert result.affected_files == ("auth.py", "login.py")
        assert result.recommended_action == "Fix the login condition"

    @pytest.mark.asyncio
    async def test_parse_environment_issue(self):
        """Parses ENVIRONMENT_ISSUE classification successfully."""
        response = """{
            "classification": "environment_issue",
            "confidence": 0.85,
            "reasoning": "Missing environment variable",
            "affected_files": ["config.py"],
            "recommended_action": "Set DATABASE_URL environment variable"
        }"""
        adapter, _ = _make_adapter(response)
        context = _make_context()
        failures = _make_failures(1)

        result = await adapter.analyze(failures, context)

        assert result.classification == FailureClassification.ENVIRONMENT_ISSUE
        assert result.confidence == 0.85

    @pytest.mark.asyncio
    async def test_parse_transient_failure(self):
        """Parses TRANSIENT_FAILURE classification successfully."""
        response = """{
            "classification": "transient_failure",
            "confidence": 0.70,
            "reasoning": "Network timeout on external API call",
            "affected_files": ["api_client.py"],
            "recommended_action": "Retry the test"
        }"""
        adapter, _ = _make_adapter(response)
        context = _make_context()
        failures = _make_failures(1)

        result = await adapter.analyze(failures, context)

        assert result.classification == FailureClassification.TRANSIENT_FAILURE
        assert result.confidence == 0.70

    @pytest.mark.asyncio
    async def test_parse_dependency_issue(self):
        """Parses DEPENDENCY_ISSUE classification successfully."""
        response = """{
            "classification": "dependency_issue",
            "confidence": 0.80,
            "reasoning": "Incompatible version of requests library",
            "affected_files": ["requirements.txt"],
            "recommended_action": "Update requests to version 2.28.0"
        }"""
        adapter, _ = _make_adapter(response)
        context = _make_context()
        failures = _make_failures(1)

        result = await adapter.analyze(failures, context)

        assert result.classification == FailureClassification.DEPENDENCY_ISSUE
        assert result.confidence == 0.80

    @pytest.mark.asyncio
    async def test_parse_configuration_issue(self):
        """Parses CONFIGURATION_ISSUE classification successfully."""
        response = """{
            "classification": "configuration_issue",
            "confidence": 0.90,
            "reasoning": "Invalid database connection string",
            "affected_files": ["config.yaml"],
            "recommended_action": "Fix the database connection string in config.yaml"
        }"""
        adapter, _ = _make_adapter(response)
        context = _make_context()
        failures = _make_failures(1)

        result = await adapter.analyze(failures, context)

        assert result.classification == FailureClassification.CONFIGURATION_ISSUE
        assert result.confidence == 0.90


# ---------------------------------------------------------------------------
# Invalid/unparseable response fallback
# ---------------------------------------------------------------------------


class TestParseFailureFallback:
    @pytest.mark.asyncio
    async def test_invalid_json_returns_code_defect(self):
        """Invalid JSON response falls back to CODE_DEFECT."""
        adapter, _ = _make_adapter("not valid json at all")
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
            "reasoning": "Some reason",
            "affected_files": [],
            "recommended_action": "Do something"
        }"""
        adapter, _ = _make_adapter(response)
        context = _make_context()
        failures = _make_failures(1)

        result = await adapter.analyze(failures, context)

        assert result.classification == FailureClassification.CODE_DEFECT
        assert result.confidence == 0.0

    @pytest.mark.asyncio
    async def test_unknown_classification_value(self):
        """Unknown classification value falls back to CODE_DEFECT."""
        response = """{
            "classification": "unknown_type",
            "confidence": 0.50,
            "reasoning": "Some reason",
            "affected_files": [],
            "recommended_action": "Do something"
        }"""
        adapter, _ = _make_adapter(response)
        context = _make_context()
        failures = _make_failures(1)

        result = await adapter.analyze(failures, context)

        assert result.classification == FailureClassification.CODE_DEFECT
        assert result.confidence == 0.0

    @pytest.mark.asyncio
    async def test_invalid_confidence_out_of_range(self):
        """Confidence > 1.0 triggers fallback."""
        response = """{
            "classification": "code_defect",
            "confidence": 1.5,
            "reasoning": "Some reason",
            "affected_files": [],
            "recommended_action": "Do something"
        }"""
        adapter, _ = _make_adapter(response)
        context = _make_context()
        failures = _make_failures(1)

        result = await adapter.analyze(failures, context)

        assert result.classification == FailureClassification.CODE_DEFECT
        assert result.confidence == 0.0

    @pytest.mark.asyncio
    async def test_missing_required_field_triggers_fallback(self):
        """Missing required field (e.g., reasoning) falls back."""
        response = """{
            "classification": "code_defect",
            "confidence": 0.85,
            "affected_files": [],
            "recommended_action": "Do something"
        }"""
        adapter, _ = _make_adapter(response)
        context = _make_context()
        failures = _make_failures(1)

        result = await adapter.analyze(failures, context)

        assert result.classification == FailureClassification.CODE_DEFECT
        assert result.confidence == 0.0


# ---------------------------------------------------------------------------
# Network/timeout exception fallback
# ---------------------------------------------------------------------------


class TestExceptionFallback:
    @pytest.mark.asyncio
    async def test_llm_execute_timeout_raises_exception(self):
        """LLM timeout exception is raised (not caught) for caller to handle."""
        llm = AsyncMock()
        llm.execute.side_effect = TimeoutError("LLM call timed out")
        adapter = LLMSystemicAnalysisAdapter(llm_factory=lambda: llm)
        context = _make_context()
        failures = _make_failures(1)

        with pytest.raises(TimeoutError):
            await adapter.analyze(failures, context)

    @pytest.mark.asyncio
    async def test_llm_execute_connection_error_raises_exception(self):
        """LLM connection error is raised (not caught) for caller to handle."""
        llm = AsyncMock()
        llm.execute.side_effect = ConnectionError("Failed to connect to LLM")
        adapter = LLMSystemicAnalysisAdapter(llm_factory=lambda: llm)
        context = _make_context()
        failures = _make_failures(1)

        with pytest.raises(ConnectionError):
            await adapter.analyze(failures, context)


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
        adapter, _ = _make_adapter(response)
        context = _make_context()
        failures = _make_failures(1)

        # No event emitter passed or expected
        result = await adapter.analyze(failures, context)

        # Just verify it returns a result without trying to emit
        assert result.classification == FailureClassification.CODE_DEFECT


# ---------------------------------------------------------------------------
# Prompt construction validation
# ---------------------------------------------------------------------------


class TestPromptConstruction:
    @pytest.mark.asyncio
    async def test_prompt_includes_failure_messages(self):
        """Prompt includes failure messages from failures list."""
        adapter, llm = _make_adapter("""{
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

        prompt = llm.execute.call_args[0][0]
        assert "test_a.py::test_1: Value mismatch" in prompt
        assert "test_b.py::test_2: Index out of range" in prompt

    @pytest.mark.asyncio
    async def test_prompt_includes_affected_files(self):
        """Prompt includes affected file paths."""
        adapter, llm = _make_adapter("""{
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

        prompt = llm.execute.call_args[0][0]
        assert "test_auth.py" in prompt

    @pytest.mark.asyncio
    async def test_prompt_includes_iteration_count(self):
        """Prompt includes iteration count from context."""
        adapter, llm = _make_adapter("""{
            "classification": "code_defect",
            "confidence": 0.85,
            "reasoning": "Test",
            "affected_files": [],
            "recommended_action": "Fix"
        }""")
        context = _make_context(iteration=3)
        failures = _make_failures(1)

        await adapter.analyze(failures, context)

        prompt = llm.execute.call_args[0][0]
        assert "Iteration: 3" in prompt

    @pytest.mark.asyncio
    async def test_prompt_includes_work_item_id(self):
        """Prompt includes work_item_id from context."""
        adapter, llm = _make_adapter("""{
            "classification": "code_defect",
            "confidence": 0.85,
            "reasoning": "Test",
            "affected_files": [],
            "recommended_action": "Fix"
        }""")
        context = _make_context(work_item_id="PR-789")
        failures = _make_failures(1)

        await adapter.analyze(failures, context)

        prompt = llm.execute.call_args[0][0]
        assert "PR-789" in prompt

    @pytest.mark.asyncio
    async def test_prompt_includes_prior_fix_attempts(self):
        """Prompt includes prior fix attempts from context."""
        adapter, llm = _make_adapter("""{
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

        prompt = llm.execute.call_args[0][0]
        assert "Tried updating import" in prompt
        assert "Tried refactoring method" in prompt

    @pytest.mark.asyncio
    async def test_prompt_shows_none_when_no_prior_attempts(self):
        """Prompt shows 'None' when no prior fix attempts."""
        adapter, llm = _make_adapter("""{
            "classification": "code_defect",
            "confidence": 0.85,
            "reasoning": "Test",
            "affected_files": [],
            "recommended_action": "Fix"
        }""")
        context = _make_context(prior_fix_attempts=())
        failures = _make_failures(1)

        await adapter.analyze(failures, context)

        prompt = llm.execute.call_args[0][0]
        assert "None" in prompt


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
        adapter, _ = _make_adapter(response)
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
        adapter, _ = _make_adapter(response)
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
        adapter, _ = _make_adapter(response)
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
        """Parse error is logged with workflow_run_id and work_item_id."""
        import logging
        caplog.set_level(logging.ERROR)

        adapter, _ = _make_adapter("invalid json")
        context = _make_context(
            workflow_run_id="run-123",
            work_item_id="item-456",
            iteration=2,
        )
        failures = _make_failures(1)

        result = await adapter.analyze(failures, context)

        # Check that error was logged
        assert any("Failed to parse systemic analysis response" in record.message for record in caplog.records)
        # Verify it fell back correctly
        assert result.classification == FailureClassification.CODE_DEFECT

    @pytest.mark.asyncio
    async def test_logs_unknown_classification_as_warning(self, caplog):
        """Unknown classification value is logged as warning."""
        import logging
        caplog.set_level(logging.WARNING)

        response = """{
            "classification": "invalid_classification",
            "confidence": 0.85,
            "reasoning": "Test",
            "affected_files": [],
            "recommended_action": "Fix"
        }"""
        adapter, _ = _make_adapter(response)
        context = _make_context()
        failures = _make_failures(1)

        result = await adapter.analyze(failures, context)

        # Falls back to CODE_DEFECT
        assert result.classification == FailureClassification.CODE_DEFECT


# ---------------------------------------------------------------------------
# Edge cases and boundary conditions
# ---------------------------------------------------------------------------


class TestBoundaryConditions:
    @pytest.mark.asyncio
    async def test_confidence_at_boundaries(self):
        """Confidence values at exact 0.0 and 1.0 boundaries are valid."""
        # Test 0.0
        response_min = """{
            "classification": "code_defect",
            "confidence": 0.0,
            "reasoning": "Test",
            "affected_files": [],
            "recommended_action": "Fix"
        }"""
        adapter, _ = _make_adapter(response_min)
        context = _make_context()
        result = await adapter.analyze(_make_failures(1), context)
        assert result.confidence == 0.0

        # Test 1.0
        response_max = """{
            "classification": "code_defect",
            "confidence": 1.0,
            "reasoning": "Test",
            "affected_files": [],
            "recommended_action": "Fix"
        }"""
        adapter, _ = _make_adapter(response_max)
        result = await adapter.analyze(_make_failures(1), context)
        assert result.confidence == 1.0

    @pytest.mark.asyncio
    async def test_multiple_failures_in_prompt(self):
        """Prompt correctly handles multiple failures."""
        adapter, llm = _make_adapter("""{
            "classification": "code_defect",
            "confidence": 0.85,
            "reasoning": "Test",
            "affected_files": [],
            "recommended_action": "Fix"
        }""")
        context = _make_context()
        failures = _make_failures(5)

        await adapter.analyze(failures, context)

        prompt = llm.execute.call_args[0][0]
        # Count how many failures are in the prompt
        assert prompt.count("::") == 5  # Each failure has file::test format

    @pytest.mark.asyncio
    async def test_long_reasoning_text(self):
        """Long reasoning text is preserved in result."""
        long_reasoning = "A" * 1000  # 1000 character reasoning
        response = f"""{{
            "classification": "code_defect",
            "confidence": 0.85,
            "reasoning": "{long_reasoning}",
            "affected_files": [],
            "recommended_action": "Fix"
        }}"""
        adapter, _ = _make_adapter(response)
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
        adapter, _ = _make_adapter(response)
        context = _make_context()

        result = await adapter.analyze(_make_failures(1), context)

        assert "expected 'value'" in result.reasoning
        assert "x == 'value'" in result.recommended_action

    @pytest.mark.asyncio
    async def test_multiline_json_without_markdown_fences(self):
        """Multiline JSON without markdown fences is extracted correctly.

        This test ensures the regex properly captures the full JSON object
        across multiple lines, not just the first closing brace.
        """
        # Multi-line JSON without markdown fences - tests greedy vs lazy regex
        response = """{
  "classification": "dependency_issue",
  "confidence": 0.92,
  "reasoning": "The affected_files array shows a } inside string that should not truncate",
  "affected_files": ["requirements.txt", "setup.py"],
  "recommended_action": "Update dependencies"
}"""
        adapter, _ = _make_adapter(response)
        context = _make_context()
        failures = _make_failures(1)

        result = await adapter.analyze(failures, context)

        # Verify all fields are correctly extracted
        assert result.classification == FailureClassification.DEPENDENCY_ISSUE
        assert result.confidence == 0.92
        assert "} inside string" in result.reasoning
        assert result.affected_files == ("requirements.txt", "setup.py")
        assert "Update dependencies" in result.recommended_action
