"""Context Builder application service."""

import json
import logging
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

from codetoreum.domain.agent import Agent
from codetoreum.domain.exceptions import DomainError
from codetoreum.domain.project_context import ProjectContext
from codetoreum.domain.services.execution_context_builder import (
    ExecutionContextBuilder as DomainContextBuilder,
)
from codetoreum.domain.value_objects import ExecutionContext
from codetoreum.domain.workspace_context import WorkspaceContext, WorkspaceType
from codetoreum.domain.work_item import WorkItem
from codetoreum.ports.exceptions import ResourceNotFoundError, TicketSystemError
from codetoreum.ports.output import IStorage, ITicketSystem

logger = logging.getLogger(__name__)


@dataclass
class ContextFile:
    """Represents a context file to be mounted."""

    path: str  # Path in container
    content: str
    description: str


@dataclass
class WorkspaceContextResult:
    """Result of building workspace context."""

    success: bool
    context_files: List[ContextFile]
    workspace_path: Optional[Path] = None
    error: Optional[str] = None


class ContextBuilder:
    """
    Application service for building execution contexts.

    Responsibilities:
    - Gather all context for execution
    - Fetch work item details from ticket system
    - Fetch project context
    - Build workspace context
    - Write context files for container mounting
    """

    def __init__(
        self,
        ticket_system: ITicketSystem,
        storage: IStorage,
        workspace_base_path: Optional[Path] = None,
    ):
        """
        Initialize ContextBuilder.

        Args:
            ticket_system: Ticket system adapter for fetching work items
            storage: Storage adapter for persisting context files
            workspace_base_path: Base path for workspace files
        """
        self.ticket_system = ticket_system
        self.storage = storage
        self.workspace_base_path = workspace_base_path or Path("/tmp/codetoreum")

    async def build_execution_context(
        self,
        work_item: WorkItem,
        workflow_id: str,
        stage_name: str,
        agent: Agent,
        project: ProjectContext,
        workspace: WorkspaceContext,
        previous_session_id: Optional[str] = None,
        additional_metadata: Optional[Dict[str, Any]] = None,
    ) -> ExecutionContext:
        """
        Build complete execution context.

        This is a thin wrapper around the domain service that adds
        application-level concerns like logging and validation.

        Args:
            work_item: Work item being processed
            workflow_id: Workflow instance ID
            stage_name: Current pipeline stage
            agent: Agent that will execute
            project: Project context configuration
            workspace: Workspace routing context
            previous_session_id: Previous session ID for continuity
            additional_metadata: Additional metadata to include

        Returns:
            Complete execution context

        Raises:
            DomainError: If validation fails
        """
        try:
            logger.info(
                f"Building execution context for work item {work_item.id}, "
                f"agent {agent.name}, stage {stage_name}"
            )

            # Use domain service to build context
            context = DomainContextBuilder.build_context(
                work_item=work_item,
                workflow_id=workflow_id,
                stage_name=stage_name,
                agent=agent,
                project=project,
                workspace=workspace,
                previous_session_id=previous_session_id,
                additional_metadata=additional_metadata,
            )

            logger.info(f"Built execution context successfully: {context.to_dict()}")

            return context

        except DomainError as e:
            logger.error(f"Failed to build execution context: {e}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error building execution context: {e}")
            raise DomainError(f"Failed to build execution context: {e}")

    async def fetch_work_item_details(
        self, work_item_id: str
    ) -> Optional[WorkItem]:
        """
        Fetch detailed work item information from ticket system.

        Args:
            work_item_id: Work item identifier

        Returns:
            WorkItem with full details, or None if not found
        """
        try:
            logger.info(f"Fetching work item details for {work_item_id}")

            work_item = await self.ticket_system.get_work_item(work_item_id)

            if work_item:
                logger.info(
                    f"Fetched work item {work_item_id}: {work_item.title}"
                )
            else:
                logger.warning(f"Work item {work_item_id} not found")

            return work_item

        except TicketSystemError as e:
            logger.error(f"Ticket system error fetching work item {work_item_id}: {e}")
            return None
        except ResourceNotFoundError as e:
            logger.warning(f"Work item {work_item_id} not found: {e}")
            return None

    async def build_workspace_context(
        self,
        work_item: WorkItem,
        agent: Agent,
        project: ProjectContext,
        workspace: WorkspaceContext,
        previous_output: Optional[str] = None,
    ) -> WorkspaceContextResult:
        """
        Build workspace context files for execution.

        Creates context files that will be mounted into the container:
        - issue.txt: Work item details
        - code/: Code snippets referenced in work item
        - previous_stage.txt: Output from previous stage (if any)
        - project_info.json: Project metadata

        Args:
            work_item: Work item being processed
            agent: Agent that will execute
            project: Project context
            workspace: Workspace context
            previous_output: Optional output from previous stage

        Returns:
            WorkspaceContextResult with context files
        """
        try:
            logger.info(
                f"Building workspace context for work item {work_item.id}, "
                f"workspace type {workspace.workspace_type.value}"
            )

            context_files: List[ContextFile] = []

            # Create issue context file
            issue_content = self._format_work_item_context(work_item)
            context_files.append(
                ContextFile(
                    path="/context/issue.txt",
                    content=issue_content,
                    description="Work item details",
                )
            )

            # Create project info file
            project_info = self._format_project_context(project)
            context_files.append(
                ContextFile(
                    path="/context/project_info.json",
                    content=json.dumps(project_info, indent=2),
                    description="Project configuration and metadata",
                )
            )

            # Add previous stage output if available
            if previous_output:
                context_files.append(
                    ContextFile(
                        path="/context/previous_stage.txt",
                        content=previous_output,
                        description="Output from previous pipeline stage",
                    )
                )

            # Add agent context
            agent_context = self._format_agent_context(agent)
            context_files.append(
                ContextFile(
                    path="/context/agent_config.json",
                    content=json.dumps(agent_context, indent=2),
                    description="Agent configuration and capabilities",
                )
            )

            # Add workspace-specific context
            workspace_info = self._format_workspace_context(workspace)
            context_files.append(
                ContextFile(
                    path="/context/workspace_info.json",
                    content=json.dumps(workspace_info, indent=2),
                    description="Workspace configuration",
                )
            )

            # Create workspace directory
            workspace_path = (
                self.workspace_base_path / work_item.id / workspace.workspace_id
            )
            workspace_path.mkdir(parents=True, exist_ok=True)

            logger.info(
                f"Built workspace context with {len(context_files)} files "
                f"at {workspace_path}"
            )

            return WorkspaceContextResult(
                success=True,
                context_files=context_files,
                workspace_path=workspace_path,
            )

        except Exception as e:
            logger.error(f"Failed to build workspace context: {e}")
            return WorkspaceContextResult(
                success=False, context_files=[], error=str(e)
            )

    async def write_context_files(
        self,
        workspace_path: Path,
        context_files: List[ContextFile],
    ) -> bool:
        """
        Write context files to disk for mounting.

        Args:
            workspace_path: Base workspace directory
            context_files: Context files to write

        Returns:
            True if successful, False otherwise
        """
        try:
            logger.info(
                f"Writing {len(context_files)} context files to {workspace_path}"
            )

            for context_file in context_files:
                # Get relative path within workspace
                relative_path = context_file.path.lstrip("/")
                file_path = workspace_path / relative_path

                # Create parent directories
                file_path.parent.mkdir(parents=True, exist_ok=True)

                # Write file
                file_path.write_text(context_file.content, encoding="utf-8")

                logger.debug(f"Wrote context file: {file_path}")

            logger.info(f"Successfully wrote all context files to {workspace_path}")
            return True

        except OSError as e:
            logger.error(f"File system error writing context files: {e}")
            return False
        except Exception as e:
            logger.error(f"Unexpected error writing context files: {e}")
            return False

    async def cleanup_workspace(self, workspace_path: Path) -> bool:
        """
        Clean up workspace directory.

        Args:
            workspace_path: Workspace directory to clean up

        Returns:
            True if successful, False otherwise
        """
        try:
            if workspace_path.exists():
                shutil.rmtree(workspace_path)
                logger.info(f"Cleaned up workspace: {workspace_path}")
                return True
            else:
                logger.debug(f"Workspace {workspace_path} does not exist, skipping cleanup")
                return True

        except OSError as e:
            logger.error(f"File system error cleaning up workspace {workspace_path}: {e}")
            return False
        except Exception as e:
            logger.error(f"Unexpected error cleaning up workspace {workspace_path}: {e}")
            return False

    # Helper methods for formatting context

    def _format_work_item_context(self, work_item: WorkItem) -> str:
        """
        Format work item details as context.

        Args:
            work_item: Work item to format

        Returns:
            Formatted context string
        """
        lines = [
            f"# Work Item: {work_item.title}",
            "",
            f"**ID**: {work_item.id}",
            f"**Status**: {work_item.status.value}",
            f"**Priority**: {work_item.priority.value}",
            "",
        ]

        if work_item.labels:
            lines.append(f"**Labels**: {', '.join(work_item.labels)}")
            lines.append("")

        if work_item.description:
            lines.append("## Description")
            lines.append("")
            lines.append(work_item.description)
            lines.append("")

        if work_item.acceptance_criteria:
            lines.append("## Acceptance Criteria")
            lines.append("")
            for i, criterion in enumerate(work_item.acceptance_criteria, 1):
                lines.append(f"{i}. {criterion}")
            lines.append("")

        if work_item.comments:
            lines.append("## Comments")
            lines.append("")
            for comment in work_item.comments:
                author = comment.get("author", "Unknown")
                body = comment.get("body", "")
                timestamp = comment.get("created_at", "")
                lines.append(f"**{author}** ({timestamp}):")
                lines.append(body)
                lines.append("")

        return "\n".join(lines)

    def _format_project_context(self, project: ProjectContext) -> Dict[str, Any]:
        """
        Format project context as dictionary.

        Args:
            project: Project context to format

        Returns:
            Project context dictionary
        """
        return {
            "id": project.id,
            "name": project.name,
            "display_name": project.display_name,
            "repository_url": project.repository_url,
            "default_branch": project.default_branch,
            "primary_language": project.primary_language,
            "tech_stack": project.tech_stack,
            "has_ci_cd": project.has_ci_cd,
            "test_framework": project.test_framework,
            "test_command": project.test_command,
            "has_dockerfile": project.has_dockerfile,
            "requires_dev_container": project.requires_dev_container,
            "mcp_servers": project.mcp_servers,
        }

    def _format_agent_context(self, agent: Agent) -> Dict[str, Any]:
        """
        Format agent context as dictionary.

        Args:
            agent: Agent to format

        Returns:
            Agent context dictionary
        """
        return {
            "id": agent.id,
            "name": agent.name,
            "display_name": agent.display_name,
            "type": agent.agent_type.value,
            "model": agent.model,
            "capabilities": [
                {
                    "skill": cap.skill,
                    "proficiency": cap.proficiency,
                    "description": cap.description,
                }
                for cap in agent.capabilities
            ],
            "makes_code_changes": agent.makes_code_changes,
            "filesystem_write_allowed": agent.filesystem_write_allowed,
            "requires_docker": agent.requires_docker,
            "requires_dev_container": agent.requires_dev_container,
            "timeout_seconds": agent.timeout_seconds,
        }

    def _format_workspace_context(
        self, workspace: WorkspaceContext
    ) -> Dict[str, Any]:
        """
        Format workspace context as dictionary.

        Args:
            workspace: Workspace context to format

        Returns:
            Workspace context dictionary
        """
        return {
            "workspace_id": workspace.workspace_id,
            "workspace_type": workspace.workspace_type.value,
            "project_id": workspace.project_id,
            "work_item_id": workspace.work_item_id,
            "branch_name": workspace.branch_name,
            "discussion_id": workspace.discussion_id,
            "create_commits": workspace.create_commits,
            "mounted_files": workspace.mounted_files,
            "read_only_paths": workspace.read_only_paths,
            "environment_variables": workspace.environment_variables,
        }

    async def gather_previous_stage_context(
        self, workflow_id: str, current_stage: str
    ) -> Optional[str]:
        """
        Gather context from previous pipeline stages.

        Args:
            workflow_id: Workflow instance ID
            current_stage: Current stage name

        Returns:
            Previous stage output or None
        """
        try:
            # This would query the event store or storage for previous stage outputs
            # For now, return None (to be implemented when pipeline manager is ready)
            logger.debug(
                f"Gathering previous stage context for workflow {workflow_id}, "
                f"stage {current_stage}"
            )
            return None

        except Exception as e:
            logger.error(f"Failed to gather previous stage context: {e}")
            return None
