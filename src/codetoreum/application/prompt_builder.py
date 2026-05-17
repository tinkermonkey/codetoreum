"""Prompt Builder application service for constructing comprehensive agent prompts.

This service assembles context from multiple sources (agent, work item, stage,
previous output) into a well-structured prompt that provides agents with all
necessary information to execute their task.
"""

import logging
from pathlib import Path

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
        """
        Build the agent context section with system prompt and role.

        Args:
            agent: Agent to describe

        Returns:
            Formatted agent context section
        """
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
        """
        Build the work item context section.

        Args:
            work_item: Work item to describe

        Returns:
            Formatted work item section
        """
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

        # Add acceptance criteria if present (from metadata or description)
        if hasattr(work_item, "acceptance_criteria") and work_item.acceptance_criteria:
            lines.append("## Acceptance Criteria")
            lines.append("")
            for i, criterion in enumerate(work_item.acceptance_criteria, 1):
                lines.append(f"{i}. {criterion}")
            lines.append("")

        return "\n".join(lines)

    @staticmethod
    def _build_stage_instructions(
        stage_name: str,
        workflow_template: BoardWorkflowTemplate | None = None,
    ) -> str:
        """
        Build stage-specific instructions section.

        Extracts stage-specific guidance from the workflow template if available.

        Args:
            stage_name: Current stage name
            workflow_template: Optional workflow configuration

        Returns:
            Formatted stage instructions section (may be empty)
        """
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
        """
        Extract task-specific instructions from column configuration.

        Args:
            column_config: Column template with configuration

        Returns:
            Formatted instructions (may be empty)
        """
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
        """
        Build the previous stage output section.

        Args:
            previous_output: Output from previous stage

        Returns:
            Formatted previous output section
        """
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
        """
        Build the constraints and guidelines section.

        Documents what the agent can and cannot do, based on agent configuration
        and work item context.

        Args:
            agent: Agent with constraints
            work_item: Work item being processed

        Returns:
            Formatted constraints section
        """
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

    @staticmethod
    def build_prompt_from_context_file(
        repository_path: str,
        stage_name: str,
        agent: Agent,
        work_item: WorkItem,
        workflow_template: BoardWorkflowTemplate | None = None,
    ) -> str:
        """
        Build prompt by reading previous output from context file on disk.

        Attempts to read /context/previous_stage.txt from the mounted context
        directory. If the file doesn't exist, builds prompt without previous output.

        Args:
            repository_path: Local path to repository where context files are mounted
            stage_name: Current stage name
            agent: Agent configuration
            work_item: Work item being processed
            workflow_template: Optional workflow configuration

        Returns:
            Comprehensive prompt string

        Raises:
            Logs warnings if context file reading fails, but does not raise exception
        """
        previous_output = None

        try:
            context_file = Path(repository_path) / "context" / "previous_stage.txt"
            if context_file.exists():
                previous_output = context_file.read_text(encoding="utf-8")
                logger.debug(f"Loaded previous stage output from {context_file}")
        except OSError as e:
            logger.warning(
                f"Failed to read previous stage context from {repository_path}: {e}",
                exc_info=True,
            )

        return PromptBuilder.build_prompt(
            work_item=work_item,
            agent=agent,
            stage_name=stage_name,
            workflow_template=workflow_template,
            previous_output=previous_output,
        )
