"""Unit tests for IPromptBuilder port + StructuredPrompt + ExecutionOutput (D1).

Covers:

- ``ExecutionOutput`` immutability (frozen value object).
- ``StructuredPrompt`` immutability and tuple-typed instructions /
  constraints / prior_outputs.
- ``IPromptBuilder`` cannot be instantiated directly (abstract).
"""

from dataclasses import FrozenInstanceError

import pytest

from codetoreum.domain.work_item import WorkItem
from codetoreum.domain.workspace_context import WorkspaceContext
from codetoreum.ports.output.prompt_builder import (
    ExecutionOutput,
    IPromptBuilder,
    StructuredPrompt,
)


def _make_work_item() -> WorkItem:
    """Minimal in-memory WorkItem for prompt assembly tests.

    Uses the ``WorkItem.create`` factory to construct a valid aggregate
    without enumerating every required field on the dataclass.
    """
    return WorkItem.create(
        title="Test work item",
        description="A short description.",
        project_id="proj-1",
    )


def _make_workspace_context() -> WorkspaceContext:
    return WorkspaceContext.for_issue(
        project_id="proj-1",
        work_item_id="wi-1",
        branch_name="feat/test",
    )


class TestExecutionOutput:
    """ExecutionOutput is a frozen value object."""

    def test_create_valid(self) -> None:
        eo = ExecutionOutput(
            stage_name="planning",
            output="Plan: do the thing.",
            created_at="2026-05-29T00:00:00+00:00",
        )
        assert eo.stage_name == "planning"
        assert eo.output == "Plan: do the thing."
        assert eo.created_at == "2026-05-29T00:00:00+00:00"

    def test_is_frozen(self) -> None:
        eo = ExecutionOutput(
            stage_name="planning",
            output="x",
            created_at="2026-05-29T00:00:00+00:00",
        )
        with pytest.raises(FrozenInstanceError):
            eo.output = "tampered"


class TestStructuredPrompt:
    """StructuredPrompt is a frozen value object with immutable collections."""

    def _make(self, **overrides) -> StructuredPrompt:
        defaults = {
            "role_description": "senior software engineer",
            "task_description": "Implement issue #42",
            "work_item": _make_work_item(),
            "workspace_context": _make_workspace_context(),
            "instructions": ("Write tests first", "Run the linter"),
            "constraints": ("Do not modify CI config",),
            "prior_outputs": (
                ExecutionOutput(
                    stage_name="planning",
                    output="Plan summary.",
                    created_at="2026-05-29T00:00:00+00:00",
                ),
            ),
        }
        defaults.update(overrides)
        return StructuredPrompt(**defaults)

    def test_create_valid(self) -> None:
        sp = self._make()
        assert sp.role_description == "senior software engineer"
        assert sp.task_description == "Implement issue #42"
        assert sp.work_item.title == "Test work item"
        assert sp.workspace_context.work_item_id == "wi-1"
        assert sp.instructions == ("Write tests first", "Run the linter")
        assert sp.constraints == ("Do not modify CI config",)
        assert len(sp.prior_outputs) == 1
        assert sp.prior_outputs[0].stage_name == "planning"

    def test_instructions_are_tuple(self) -> None:
        sp = self._make()
        assert isinstance(sp.instructions, tuple)

    def test_constraints_are_tuple(self) -> None:
        sp = self._make()
        assert isinstance(sp.constraints, tuple)

    def test_prior_outputs_are_tuple(self) -> None:
        sp = self._make()
        assert isinstance(sp.prior_outputs, tuple)
        assert all(isinstance(o, ExecutionOutput) for o in sp.prior_outputs)

    def test_is_frozen(self) -> None:
        sp = self._make()
        with pytest.raises(FrozenInstanceError):
            sp.role_description = "tampered"

    def test_empty_instructions_and_constraints_supported(self) -> None:
        sp = self._make(instructions=(), constraints=(), prior_outputs=())
        assert sp.instructions == ()
        assert sp.constraints == ()
        assert sp.prior_outputs == ()


class TestIPromptBuilder:
    """IPromptBuilder is an abstract base class."""

    def test_cannot_instantiate_directly(self) -> None:
        with pytest.raises(TypeError):
            IPromptBuilder()

    def test_subclass_without_build_is_still_abstract(self) -> None:
        class Incomplete(IPromptBuilder):
            pass

        with pytest.raises(TypeError):
            Incomplete()
