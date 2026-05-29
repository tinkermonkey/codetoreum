"""Render a :class:`StructuredPrompt` to text for ``claude --print TEXT``.

This module is the **presentation boundary** for Claude Code (per INV-18).
It owns *how* a vendor-agnostic :class:`StructuredPrompt` is formatted into
the single text-blob payload Claude Code expects on the CLI. It does
**not** own *what* to include — that's the
:class:`~codetoreum.ports.output.prompt_builder.IPromptBuilder` injected
into the adapter.

Render contract:

- Pure function, no I/O, no state. Deterministic — given the same input,
  identical output (asserted by golden-file tests in
  ``tests/unit/adapters/secondary/claude_code/test_prompt_renderer.py``).
- Output is plain text (Markdown-style headers). Claude Code parses
  Markdown well inside ``--print`` prompts and the format is familiar to
  reviewers reading event-store snapshots.
- Sections are emitted in a stable order. Empty optional sections are
  omitted entirely (no leftover ``"## (none)"`` placeholders) to keep
  shorter prompts shorter.
"""

from __future__ import annotations

from codetoreum.ports.output.prompt_builder import StructuredPrompt


def render_structured_prompt_to_text(prompt: StructuredPrompt) -> str:
    """Render a :class:`StructuredPrompt` to a single text prompt.

    The output layout, when every section is populated:

    .. code-block:: markdown

        # Your Role
        <role_description>

        # Work Item
        ID: <work_item.id>
        Title: <work_item.title>
        Reference: <work_item.external_url>

        ## Description
        <task_description>

        # Instructions
        - <instruction 1>
        - <instruction 2>

        # Constraints
        - <constraint 1>

        # Prior Outputs
        ## <stage_name> (at <created_at>)
        <output>

    Args:
        prompt: The structured prompt to render.

    Returns:
        Single text string, no trailing newline.
    """
    sections: list[str] = []

    # ---- Your Role ----
    role = (prompt.role_description or "").strip()
    if role:
        sections.append("# Your Role\n" + role)

    # ---- Work Item ----
    work_item_lines = _render_work_item(prompt)
    if work_item_lines:
        sections.append(work_item_lines)

    # ---- Instructions ----
    instructions = _render_bullet_section("# Instructions", prompt.instructions)
    if instructions:
        sections.append(instructions)

    # ---- Constraints ----
    constraints = _render_bullet_section("# Constraints", prompt.constraints)
    if constraints:
        sections.append(constraints)

    # ---- Prior Outputs ----
    prior = _render_prior_outputs(prompt)
    if prior:
        sections.append(prior)

    return "\n\n".join(sections)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _render_work_item(prompt: StructuredPrompt) -> str:
    work_item = prompt.work_item
    lines: list[str] = ["# Work Item"]
    if work_item.id:
        lines.append(f"ID: {work_item.id}")
    if work_item.title:
        lines.append(f"Title: {work_item.title}")
    if work_item.external_url:
        lines.append(f"Reference: {work_item.external_url}")

    task = (prompt.task_description or "").strip()
    if task:
        lines.append("")
        lines.append("## Description")
        lines.append(task)

    # If only the header survives (no fields at all + no description),
    # omit the section entirely.
    if len(lines) == 1:
        return ""
    return "\n".join(lines)


def _render_bullet_section(header: str, items: tuple[str, ...]) -> str:
    cleaned = [item.strip() for item in items if item and item.strip()]
    if not cleaned:
        return ""
    bullets = "\n".join(f"- {item}" for item in cleaned)
    return f"{header}\n{bullets}"


def _render_prior_outputs(prompt: StructuredPrompt) -> str:
    if not prompt.prior_outputs:
        return ""
    blocks: list[str] = ["# Prior Outputs"]
    for output in prompt.prior_outputs:
        stage = (output.stage_name or "(unknown stage)").strip()
        created_at = (output.created_at or "").strip()
        if created_at:
            blocks.append(f"## {stage} (at {created_at})")
        else:
            blocks.append(f"## {stage}")
        body = (output.output or "").strip()
        if body:
            blocks.append(body)
    return "\n".join(blocks)


__all__ = ["render_structured_prompt_to_text"]
