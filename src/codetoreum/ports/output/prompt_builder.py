"""``IPromptBuilder`` output port — vendor-agnostic prompt assembly.

This port is the **business-logic** boundary for prompt assembly:
*what context the agent needs, what instructions, what constraints*.
Each :class:`~codetoreum.ports.output.coding_agent.ICodingAgent`
adapter renders the resulting :class:`StructuredPrompt` to its
vendor's expected shape — text for Claude Code's ``claude --print``,
a ``[{role, content}, ...]`` message array for GitHub Copilot's Chat
API, Codex CLI's prompt format, etc.

Separating prompt **business logic** (what to include) from prompt
**presentation** (how to format for a specific vendor) is what lets
a single prompt-building strategy drive all three planned target
adapters. This separation is enforced by INV-18 (see
``bootstrap/ARCHITECTURE.md`` §6):

    Prompt-building business logic lives in IPromptBuilder
    implementations, not inside coding agent adapters. Adapters
    render the structured prompt to their vendor's expected format
    but do not own *what context to include*.

The default implementation, ``DefaultPromptBuilder``, will live in the
application layer (``application/prompt_building/default_prompt_builder.py``)
and is delivered in Phase D2. Projects can override it for custom
prompt strategies; that remains a forward concern.

See DEF-015 in ``bootstrap/ARCHITECTURE.md`` §9 and the design
proposal at ``~/.claude/plans/coding-agent-port-redesign.md`` (§3b)
for the broader context.

This module also defines :class:`ExecutionOutput`, a small immutable
value object that summarises a prior pipeline stage's output for
inclusion in subsequent prompts. It is tightly coupled to
``StructuredPrompt`` and lives here as a sibling; if it grows wider
usage, move it to ``codetoreum.domain``.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass

from codetoreum.domain.agent import Agent
from codetoreum.domain.work_item import WorkItem
from codetoreum.domain.workspace_context import WorkspaceContext


@dataclass(frozen=True)
class ExecutionOutput:
    """Summary of a prior pipeline stage's output.

    A small immutable value object passed to :meth:`IPromptBuilder.build`
    via the ``prior_outputs`` tuple. Lets a downstream agent see the
    upstream stage's artefact / summary without depending on the
    upstream agent's vendor or invocation details.

    Attributes:
        stage_name: Identifier of the upstream pipeline stage
            (e.g. ``"planning"``, ``"design"``).
        output: The stage's textual output. For binary artefacts, the
            string carries a reference rather than the raw bytes
            (artefact storage is out of scope here).
        created_at: ISO 8601 timestamp string when the upstream stage
            produced the output.
    """

    stage_name: str
    output: str
    created_at: str


@dataclass(frozen=True)
class StructuredPrompt:
    """Vendor-agnostic structured prompt produced by an IPromptBuilder.

    Each coding agent adapter renders this to its vendor's expected
    format. The same structured prompt can drive Claude Code, GitHub
    Copilot, Codex, and any future vendor that conforms to
    :class:`~codetoreum.ports.output.coding_agent.ICodingAgent`.

    Immutable value object (frozen dataclass).

    Attributes:
        role_description: Short description of the agent's role
            (e.g. ``"senior software engineer"``).
        task_description: Short description of the task to perform.
        work_item: The :class:`~codetoreum.domain.work_item.WorkItem`
            being processed. ``None`` for free-form prompts produced by
            :class:`IFreeFormPromptBuilder` (systemic-analysis,
            environment-repair, file-fix), where there is no backing
            work item. Renderers must skip the work-item section when
            this is ``None``.
        workspace_context: Logical workspace description (path, branch,
            git identity, project env vars).
        instructions: Ordered tuple of free-form instructions for the
            agent. Tuples are used for immutability.
        constraints: Ordered tuple of free-form constraints / negative
            instructions for the agent.
        prior_outputs: Ordered tuple of upstream-stage summaries the
            agent should incorporate as context.
    """

    role_description: str
    task_description: str
    work_item: WorkItem | None
    workspace_context: WorkspaceContext
    instructions: tuple[str, ...]
    constraints: tuple[str, ...]
    prior_outputs: tuple[ExecutionOutput, ...]


class IPromptBuilder(ABC):
    """Assembles a :class:`StructuredPrompt` for a coding agent execution.

    This is the **business-logic** port for prompt assembly. It is
    separate from any specific coding agent adapter so the same
    prompt-building strategy applies across Claude Code, GitHub
    Copilot, Codex, and future vendors.

    Adapters render the resulting :class:`StructuredPrompt` to their
    vendor's expected format (the **presentation** concern). The split
    is enforced by INV-18 — adapters do not own *what* context to
    include.
    """

    @abstractmethod
    async def build(
        self,
        agent: Agent,
        work_item: WorkItem,
        workspace_context: WorkspaceContext,
        prior_outputs: tuple[ExecutionOutput, ...] = (),
    ) -> StructuredPrompt:
        """Assemble a structured prompt for a coding agent execution.

        Args:
            agent: The :class:`~codetoreum.domain.agent.Agent` being
                invoked. Provides the role, capabilities, system
                prompt seed material, etc.
            work_item: The :class:`~codetoreum.domain.work_item.WorkItem`
                being processed.
            workspace_context: Logical workspace description.
            prior_outputs: Optional ordered tuple of outputs from prior
                pipeline stages that should be incorporated as context.

        Returns:
            A :class:`StructuredPrompt` ready for the coding agent
            adapter to render to its vendor's expected format.
        """


class IFreeFormPromptBuilder(ABC):
    """Assembles a :class:`StructuredPrompt` for a free-form coding-agent call.

    Sibling port to :class:`IPromptBuilder`. Used by callers that have
    *no* backing :class:`Agent` / :class:`WorkItem` to build a prompt
    around — systemic-failure analysis, environment-repair rebuild /
    verify, repair-cycle file-fix, etc. The builder closure-captures
    the call-specific data (failure list, rebuild context, file diff)
    at construction time; :meth:`build` only needs the runtime
    workspace context to fold in.

    The resulting :class:`StructuredPrompt` carries ``work_item=None``;
    renderers must handle this by skipping the work-item section.
    """

    @abstractmethod
    async def build(
        self,
        workspace_context: WorkspaceContext,
    ) -> StructuredPrompt:
        """Assemble a structured prompt for a free-form coding-agent call.

        Args:
            workspace_context: Logical workspace description (path,
                branch, git identity, project env vars). Free-form
                calls typically have a synthetic
                :class:`WorkspaceContext` whose ``workspace_path``
                points at a temp dir or the orchestrator's working
                directory.

        Returns:
            A :class:`StructuredPrompt` with ``work_item=None``, ready
            for the coding agent adapter to render to its vendor's
            expected format.
        """


__all__ = [
    "ExecutionOutput",
    "IFreeFormPromptBuilder",
    "IPromptBuilder",
    "StructuredPrompt",
]
