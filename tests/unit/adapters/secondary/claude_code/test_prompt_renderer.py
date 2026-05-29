"""Unit tests for :func:`render_structured_prompt_to_text`.

Golden-output tests for representative :class:`StructuredPrompt` shapes.
"""

from __future__ import annotations

import pytest

from codetoreum.adapters.secondary.claude_code.prompt_renderer import (
    render_structured_prompt_to_text,
)
from codetoreum.domain.work_item import WorkItem, WorkItemPriority
from codetoreum.domain.workspace_context import WorkspaceContext
from codetoreum.ports.output.prompt_builder import (
    ExecutionOutput,
    StructuredPrompt,
)


@pytest.fixture
def work_item() -> WorkItem:
    wi = WorkItem.create(
        title="Implement widget",
        description="Add the widget endpoint per #42.",
        project_id="proj-1",
        external_id="42",
        external_url="https://example.com/issues/42",
        priority=WorkItemPriority.MEDIUM,
    )
    # Pin the id so golden output is deterministic.
    object.__setattr__(wi, "id", "wi-1")
    return wi


@pytest.fixture
def workspace_context() -> WorkspaceContext:
    return WorkspaceContext.for_issue(
        project_id="proj-1",
        work_item_id="wi-1",
        branch_name="feature/widget",
        create_pr=True,
    )


def _make_prompt(
    work_item: WorkItem,
    workspace_context: WorkspaceContext,
    *,
    role_description: str = "senior software engineer — Implements features",
    task_description: str = "Implement widget\n\nAdd the widget endpoint per #42.",
    instructions: tuple[str, ...] = (
        "Make the changes described above.",
        "You may edit files in the repository.",
    ),
    constraints: tuple[str, ...] = ("Do not modify .env files or any file containing credentials.",),
    prior_outputs: tuple[ExecutionOutput, ...] = (),
) -> StructuredPrompt:
    return StructuredPrompt(
        role_description=role_description,
        task_description=task_description,
        work_item=work_item,
        workspace_context=workspace_context,
        instructions=instructions,
        constraints=constraints,
        prior_outputs=prior_outputs,
    )


class TestRenderStructuredPromptToText:
    def test_full_prompt_golden(self, work_item, workspace_context):
        prompt = _make_prompt(work_item, workspace_context)
        rendered = render_structured_prompt_to_text(prompt)
        expected = (
            "# Your Role\n"
            "senior software engineer — Implements features\n\n"
            "# Work Item\n"
            "ID: wi-1\n"
            "Title: Implement widget\n"
            "Reference: https://example.com/issues/42\n"
            "\n"
            "## Description\n"
            "Implement widget\n\nAdd the widget endpoint per #42.\n\n"
            "# Instructions\n"
            "- Make the changes described above.\n"
            "- You may edit files in the repository.\n\n"
            "# Constraints\n"
            "- Do not modify .env files or any file containing credentials."
        )
        assert rendered == expected

    def test_empty_role_omitted(self, work_item, workspace_context):
        prompt = _make_prompt(
            work_item,
            workspace_context,
            role_description="",
        )
        rendered = render_structured_prompt_to_text(prompt)
        assert not rendered.startswith("# Your Role")
        assert rendered.startswith("# Work Item")

    def test_empty_instructions_section_omitted(self, work_item, workspace_context):
        prompt = _make_prompt(
            work_item,
            workspace_context,
            instructions=(),
        )
        rendered = render_structured_prompt_to_text(prompt)
        assert "# Instructions" not in rendered

    def test_blank_instructions_dropped(self, work_item, workspace_context):
        prompt = _make_prompt(
            work_item,
            workspace_context,
            instructions=("", "   ", "Do the thing."),
        )
        rendered = render_structured_prompt_to_text(prompt)
        # Only the substantive instruction appears.
        assert "- Do the thing." in rendered
        assert "- \n" not in rendered

    def test_prior_outputs_included(self, work_item, workspace_context):
        prompt = _make_prompt(
            work_item,
            workspace_context,
            prior_outputs=(
                ExecutionOutput(
                    stage_name="planning",
                    output="Build the widget.",
                    created_at="2026-01-01T00:00:00Z",
                ),
                ExecutionOutput(
                    stage_name="design",
                    output="Use REST.",
                    created_at="2026-01-02T00:00:00Z",
                ),
            ),
        )
        rendered = render_structured_prompt_to_text(prompt)
        assert "# Prior Outputs" in rendered
        assert "## planning (at 2026-01-01T00:00:00Z)" in rendered
        assert "Build the widget." in rendered
        assert "## design (at 2026-01-02T00:00:00Z)" in rendered
        assert "Use REST." in rendered

    def test_prior_outputs_without_timestamp(self, work_item, workspace_context):
        prompt = _make_prompt(
            work_item,
            workspace_context,
            prior_outputs=(ExecutionOutput(stage_name="planning", output="x", created_at=""),),
        )
        rendered = render_structured_prompt_to_text(prompt)
        assert "## planning" in rendered
        assert "(at " not in rendered.split("## planning")[1].splitlines()[0]

    def test_no_trailing_newline(self, work_item, workspace_context):
        prompt = _make_prompt(work_item, workspace_context)
        rendered = render_structured_prompt_to_text(prompt)
        assert not rendered.endswith("\n")

    def test_deterministic(self, work_item, workspace_context):
        prompt = _make_prompt(work_item, workspace_context)
        assert render_structured_prompt_to_text(prompt) == render_structured_prompt_to_text(prompt)
