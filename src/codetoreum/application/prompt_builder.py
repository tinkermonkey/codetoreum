"""Prompt Builder application service for constructing comprehensive agent prompts.

This service assembles context from multiple sources (agent, work item, stage,
previous output) into a well-structured prompt that provides agents with all
necessary information to execute their task.
"""

# Retired by DefaultPromptBuilder (Phase D2); D5 deletes this module.
#
# The legacy ``PromptBuilder`` returns a pre-rendered ``str`` and is consumed
# only by ``ExecutionServiceAgentExecutor`` (the pre-redesign execution path).
# The new ``DefaultPromptBuilder`` in
# ``codetoreum.application.prompt_building`` returns a vendor-agnostic
# ``StructuredPrompt`` per the D-series rewrite. The two cannot coexist in
# the long run — D3 rewires the executor to the new port, and D5 deletes
# this module. See ``~/.claude/plans/coding-agent-port-redesign.md`` §6.

import logging

from codetoreum.domain.agent import Agent
from codetoreum.domain.board_workflow_template import BoardWorkflowTemplate, ColumnTemplate
from codetoreum.domain.work_item import WorkItem

logger = logging.getLogger(__name__)


class PromptBuilder:
    """
    Application service for constructing comprehensive agent prompts.

    Assembles:
    - Agent system prompt and role description
    - Full work item context (title, description, acceptance criteria, labels)
    - Previous stage output (if available)
    - Stage-specific instructions from workflow configuration
    - Metadata about priority, status, and other contextual information

    The resulting prompt provides agents with complete context needed to
    execute their assigned task effectively.
    """

    @staticmethod
    def build_prompt(
        work_item: WorkItem,
        agent: Agent,
        stage_name: str,
        workflow_template: BoardWorkflowTemplate | None = None,
        previous_output: str | None = None,
    ) -> str:
        """
        Build a comprehensive prompt for agent execution.

        Combines all available context into a well-structured prompt that guides
        the agent through the task.

        Args:
            work_item: Work item being processed
            agent: Agent that will execute
            stage_name: Current pipeline stage name
            workflow_template: Optional workflow configuration for stage-specific instructions
            previous_output: Optional output from previous pipeline stage

        Returns:
            Comprehensive prompt string for the agent
        """
        sections = []

        # 1. Agent system prompt and role
        sections.append(PromptBuilder._build_agent_context_section(agent))

        # 2. Work item context
        sections.append(PromptBuilder._build_work_item_section(work_item))

        # 3. Stage context and instructions
        stage_instructions = PromptBuilder._build_stage_instructions(stage_name, workflow_template)
        if stage_instructions:
            sections.append(stage_instructions)

        # 4. Previous stage output (if available)
        if previous_output:
            sections.append(PromptBuilder._build_previous_output_section(previous_output))

        # 5. Execution constraints and guidelines
        sections.append(PromptBuilder._build_constraints_section(agent, work_item))

        # Join all sections with clear separators
        return "\n\n---\n\n".join(filter(None, sections))

    @staticmethod
    def _build_agent_context_section(agent: Agent) -> str:
        """Build agent context section with system prompt and role."""
        lines = []

        # Add agent system prompt if available
        if agent.system_prompt and agent.system_prompt.strip():
            lines.append("# System Prompt")
            lines.append("")
            lines.append(agent.system_prompt)
            lines.append("")

        # Add role information
        lines.append("# Your Role")
        lines.append("")
        lines.append(f"**Agent**: {agent.display_name} ({agent.agent_type.value})")
        lines.append("")
        lines.append("## Role Description")
        lines.append("")
        lines.append(agent.role_description)
        lines.append("")

        # Add capabilities
        if agent.capabilities:
            lines.append("## Capabilities")
            lines.append("")
            for skill, capability in agent.capabilities.items():
                proficiency_pct = int(capability.proficiency * 100)
                description = f" — {capability.description}" if capability.description else ""
                lines.append(f"- **{skill}** ({proficiency_pct}% proficiency){description}")
            lines.append("")

        return "\n".join(lines)

    @staticmethod
    def _build_work_item_section(work_item: WorkItem) -> str:
        """Build work item context section."""
        lines = [
            "# Work Item",
            "",
            f"**ID**: {work_item.id}",
            f"**Title**: {work_item.title}",
            f"**Status**: {work_item.status.value}",
            f"**Priority**: {work_item.priority.value}",
            "",
        ]

        # Add labels if present
        if work_item.labels:
            lines.append(f"**Labels**: {', '.join(work_item.labels)}")
            lines.append("")

        # Add external reference if present
        if work_item.external_url:
            lines.append(f"**Reference**: {work_item.external_url}")
            lines.append("")

        # Add description (required)
        if work_item.description:
            lines.append("## Description")
            lines.append("")
            lines.append(work_item.description)
            lines.append("")

        return "\n".join(lines)

    @staticmethod
    def _build_stage_instructions(
        stage_name: str,
        workflow_template: BoardWorkflowTemplate | None = None,
    ) -> str:
        """Build stage-specific instructions from workflow template."""
        lines = []

        lines.append("# Stage Instructions")
        lines.append("")
        lines.append(f"**Current Stage**: {stage_name}")
        lines.append("")

        # Extract stage-specific details from workflow template
        if workflow_template:
            column_config = workflow_template.get_column_config(stage_name)
            if column_config:
                instructions = PromptBuilder._extract_column_instructions(column_config)
                if instructions:
                    lines.append(instructions)
                    lines.append("")

        # Generic guidance for all stages
        lines.append("## Your Task")
        lines.append("")
        lines.append("Process the work item described above through this pipeline stage.")
        lines.append("Follow all acceptance criteria and success guidelines.")
        lines.append("")

        return "\n".join(lines)

    @staticmethod
    def _extract_column_instructions(column_config: ColumnTemplate) -> str:
        """Extract task-specific instructions from column configuration."""
        lines = []

        # Document the execution type
        execution_type = column_config.execution_type or "task_queue"
        if execution_type == "conversational":
            lines.append("**Execution Mode**: Conversational (multi-turn dialogue)")
            lines.append("")
            lines.append("You will engage in a multi-turn conversation about this work item.")
        elif execution_type == "task_queue":
            lines.append("**Execution Mode**: Task-oriented (single execution)")
            lines.append("")
            lines.append("Complete the work item as a single task.")

        # Document success criteria
        if column_config.auto_progress_on_completion:
            lines.append("")
            lines.append("**Success Criteria**: Completion will trigger automatic advancement to the next stage.")
        else:
            lines.append("")
            lines.append("**Success Criteria**: Completion will be recorded but not automatically advanced.")

        # Document failure handling
        if column_config.on_failure_column:
            lines.append("")
            lines.append(
                f"**Failure Handling**: If execution fails, the work item will be moved to "
                f"'{column_config.on_failure_column}' for remediation."
            )

        return "\n".join(lines)

    @staticmethod
    def _build_previous_output_section(previous_output: str) -> str:
        """Build previous stage output section."""
        lines = [
            "# Previous Stage Output",
            "",
            "The following is the output from the previous pipeline stage.",
            "Use this context to understand what has been completed and to build upon it.",
            "",
            "---",
            "",
            previous_output,
            "",
            "---",
        ]

        return "\n".join(lines)

    @staticmethod
    def _build_constraints_section(agent: Agent, work_item: WorkItem) -> str:
        """Build constraints and guidelines section."""
        lines = [
            "# Execution Constraints & Guidelines",
            "",
        ]

        # Document code change permissions
        if agent.makes_code_changes and agent.filesystem_write_allowed:
            lines.append("✅ **You may make code changes** and modify files in the repository.")
        elif agent.makes_code_changes:
            lines.append("⚠️ **You may NOT directly modify files** (filesystem writes are disabled).")
        else:
            lines.append("❌ **You may NOT make code changes.** This is an analysis/review role.")

        lines.append("")

        # Document container execution
        if agent.requires_docker:
            lines.append("✅ **Container execution available** — you can run commands, tests, builds.")
        else:
            lines.append("⚠️ **Container execution NOT available** — analysis-only mode.")

        lines.append("")

        # Document available tools/MCP servers
        if agent.mcp_servers:
            lines.append("**Available MCP Servers**:")
            for server in agent.mcp_servers:
                lines.append(f"- {server}")
            lines.append("")

        # Document timeout
        lines.append(f"⏱️ **Execution timeout**: {agent.timeout_seconds} seconds")
        lines.append("")

        # Document work item status for context
        lines.append(f"**Work Item Status**: {work_item.status.value}")
        if work_item.assigned_agent_id:
            lines.append(f"**Assigned Agent**: {work_item.assigned_agent_id}")

        lines.append("")

        return "\n".join(lines)
