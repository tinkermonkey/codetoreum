"""Default :class:`IPromptBuilder` implementation (Phase D2).

Assembles a vendor-agnostic
:class:`~codetoreum.ports.output.prompt_builder.StructuredPrompt` from the
work item, agent role, workspace context, and any prior stage outputs.

Per INV-18 (see ``bootstrap/ARCHITECTURE.md`` §6), prompt-building business
logic lives in this application-layer class, not inside coding agent
adapters. The same structured output drives Claude Code, GitHub Copilot,
Codex, and future coding agents — each adapter renders it to its vendor's
expected format (text for ``claude --print``, message array for Copilot's
Chat API, Codex CLI's prompt format, etc.).

See ``~/.claude/plans/coding-agent-port-redesign.md`` §3b and §6 D2 for the
broader design context.
"""

from codetoreum.domain.agent import Agent
from codetoreum.domain.work_item import WorkItem
from codetoreum.domain.workspace_context import WorkspaceContext
from codetoreum.ports.output.prompt_builder import (
    ExecutionOutput,
    IPromptBuilder,
    StructuredPrompt,
)


class DefaultPromptBuilder(IPromptBuilder):
    """Application-layer concrete :class:`IPromptBuilder`.

    Assembles a vendor-agnostic
    :class:`~codetoreum.ports.output.prompt_builder.StructuredPrompt` from
    the work item, agent role, workspace context, and any prior stage
    outputs. The same structured output drives Claude Code, GitHub Copilot,
    Codex, and future coding agents — each adapter renders it to its
    vendor's expected format.

    Per INV-18, prompt-building business logic lives here, not inside
    coding agent adapters. Adapters are restricted to rendering: turning
    the :class:`StructuredPrompt` into their vendor's specific shape.

    This is the **default** strategy. Projects can register alternative
    strategies (e.g. compact prompts for shorter context windows, A/B
    test variants) as sibling classes; the wiring selects which one to
    inject.
    """

    async def build(
        self,
        agent: Agent,
        work_item: WorkItem,
        workspace_context: WorkspaceContext,
        prior_outputs: tuple[ExecutionOutput, ...] = (),
    ) -> StructuredPrompt:
        """Assemble a structured prompt for a coding agent execution.

        Field-by-field mapping:

        - ``role_description``: agent display name, type, and role
          description, plus a short capability summary. Drawn from
          :attr:`Agent.display_name`, :attr:`Agent.agent_type`,
          :attr:`Agent.role_description`, and
          :attr:`Agent.capabilities`.
        - ``task_description``: work item title + (trimmed) description.
          Adapters can re-render; this gives them the raw signal.
        - ``work_item``: the domain object is passed through unchanged so
          vendor renderers may select whichever fields suit their format.
        - ``workspace_context``: the value object is passed through
          unchanged for the same reason.
        - ``instructions``: imperative-mode strings. Always starts with
          "Make the changes described above"; additional items depend on
          workspace and agent capabilities.
        - ``constraints``: hard limits and "don't do this" items. Project
          policy hard-codes a small set today; richer policy resolution
          is a forward concern.
        - ``prior_outputs``: passed through as-is.

        Args:
            agent: The :class:`Agent` being invoked.
            work_item: The :class:`WorkItem` being processed.
            workspace_context: Logical workspace description.
            prior_outputs: Ordered tuple of outputs from prior pipeline
                stages.

        Returns:
            An immutable :class:`StructuredPrompt`.
        """
        return StructuredPrompt(
            role_description=self._build_role_description(agent),
            task_description=self._build_task_description(work_item),
            work_item=work_item,
            workspace_context=workspace_context,
            instructions=self._build_instructions(agent, workspace_context),
            constraints=self._build_constraints(agent, workspace_context),
            prior_outputs=prior_outputs,
        )

    @staticmethod
    def _build_role_description(agent: Agent) -> str:
        """Compose a short role description.

        Uses the agent's display name, type, and role description, plus
        a concise capability summary. The format is *intentionally*
        text — adapter renderers may split this back into structured
        fields if their vendor format prefers that shape.
        """
        agent_type_value = agent.agent_type.value if hasattr(agent.agent_type, "value") else str(agent.agent_type)
        parts = [
            f"{agent.display_name} ({agent_type_value})",
            agent.role_description.strip(),
        ]

        if agent.capabilities:
            capability_summary = ", ".join(sorted(agent.capabilities.keys()))
            parts.append(f"Capabilities: {capability_summary}")

        return " — ".join(filter(None, parts))

    @staticmethod
    def _build_task_description(work_item: WorkItem) -> str:
        """Compose a short task description from work item title + description.

        Title comes first as a single line; the description follows on a
        blank-line-separated paragraph. Both are passed through as-is —
        adapters can re-render or further trim.
        """
        title = (work_item.title or "").strip()
        description = (work_item.description or "").strip()

        if title and description:
            return f"{title}\n\n{description}"
        return title or description

    @staticmethod
    def _build_instructions(
        agent: Agent,
        workspace_context: WorkspaceContext,
    ) -> tuple[str, ...]:
        """Compose ordered imperative-mode instructions.

        The minimum baseline is ``"Make the changes described above."``.
        Additional items depend on workspace permissions (edit files,
        post comments) and agent capabilities (e.g. a ``testing``
        capability adds "Run tests after making changes").
        """
        instructions: list[str] = [
            "Make the changes described above.",
        ]

        if workspace_context.allow_code_changes:
            instructions.append("You may edit files in the repository.")

        if workspace_context.should_post_to_discussion():
            instructions.append("You may post comments to the associated discussion thread.")

        # Capability-derived instructions. Keys are matched in sorted
        # order for deterministic output across runs.
        capability_keys = set(agent.capabilities.keys())
        if "testing" in capability_keys:
            instructions.append("Run the project's tests after making changes.")
        if "documentation" in capability_keys:
            instructions.append("Update documentation when changing public APIs.")
        if "code_review" in capability_keys:
            instructions.append("Review the changes for correctness before signalling completion.")

        return tuple(instructions)

    @staticmethod
    def _build_constraints(
        agent: Agent,
        workspace_context: WorkspaceContext,
    ) -> tuple[str, ...]:
        """Compose ordered constraints / negative instructions.

        Project-policy items today are hard-coded; richer per-project
        constraint resolution is a forward concern (config-driven, see
        the D6/D7 cycle in the design proposal).
        """
        constraints: list[str] = [
            "Do not modify .env files or any file containing credentials.",
            "Do not commit binary artefacts (build outputs, compiled assets).",
            "Stay within the mounted workspace directory.",
        ]

        if not workspace_context.allow_code_changes:
            constraints.append("Do not modify any files in the repository — analysis only.")

        if not agent.filesystem_write_allowed:
            constraints.append("Filesystem writes are disabled for this agent role.")

        return tuple(constraints)


__all__ = ["DefaultPromptBuilder"]
