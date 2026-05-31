"""Execution context builder service for building execution contexts."""

from typing import Any

from codetoreum.domain.agent import Agent
from codetoreum.domain.coding_agent_types import InvocationMode
from codetoreum.domain.exceptions import DomainError
from codetoreum.domain.project_context import ProjectContext
from codetoreum.domain.value_objects import ExecutionContext
from codetoreum.domain.work_item import WorkItem
from codetoreum.domain.workspace_context import WorkspaceContext


class ExecutionContextBuilder:
    """
    Service for building execution contexts from project and workspace.

    Combines project configuration, workspace routing, agent settings,
    and work item details into complete execution context.
    """

    @staticmethod
    def build_context(
        work_item: WorkItem,
        workflow_id: str,
        stage_name: str,
        agent: Agent,
        project: ProjectContext,
        workspace: WorkspaceContext,
        previous_session_id: str | None = None,
        additional_metadata: dict[str, Any] | None = None,
        repository_path: str | None = None,
    ) -> ExecutionContext:
        """
        Build complete execution context from components.

        Args:
            work_item: Work item being processed
            workflow_id: Workflow instance ID
            stage_name: Current pipeline stage name
            agent: Agent that will execute
            project: Project context configuration
            workspace: Workspace routing context
            previous_session_id: Previous session ID for continuity (optional)
            additional_metadata: Additional metadata to include (optional)
            repository_path: Local path to the checked-out repository (optional).
                Set by the executor after workspace preparation so that
                ExecutionService can commit without re-querying the workspace router.

        Returns:
            Complete execution context

        Raises:
            DomainError: If validation fails
        """
        # Validate inputs
        ExecutionContextBuilder._validate_inputs(work_item, workflow_id, stage_name, agent, project, workspace)

        # Validate workspace and work item match
        if workspace.work_item_id != work_item.id:
            msg = f"Workspace work_item_id ({workspace.work_item_id}) does not match work item ID ({work_item.id})"
            raise DomainError(msg)

        # Validate project IDs match
        if workspace.project_id != project.id:
            msg = f"Workspace project_id ({workspace.project_id}) does not match project ID ({project.id})"
            raise DomainError(msg)

        # Determine permissions
        filesystem_write_allowed = agent.filesystem_write_allowed and workspace.can_make_code_changes()
        can_make_commits = agent.makes_code_changes and workspace.create_commits

        # Build metadata
        metadata = ExecutionContextBuilder._build_metadata(
            work_item, agent, project, workspace, additional_metadata or {}
        )

        # Create execution context
        return ExecutionContext(
            work_item_id=work_item.id,
            workflow_id=workflow_id,
            stage_name=stage_name,
            agent_id=agent.id,
            model=agent.invocation.model,
            timeout_seconds=agent.invocation.timeout_seconds,
            workspace_type=workspace.workspace_type.value,
            branch_name=workspace.branch_name,
            discussion_id=workspace.discussion_id,
            project_id=project.id,
            repository_url=project.repository_url,
            tech_stack=tuple(project.tech_stack),
            filesystem_write_allowed=filesystem_write_allowed,
            can_make_commits=can_make_commits,
            requires_docker=agent.invocation.mode == InvocationMode.CONTAINERIZED,
            mcp_servers=tuple(ExecutionContextBuilder._merge_mcp_servers(agent, project)),
            commit_policy=agent.commit_policy,
            repository_path=repository_path,
            previous_session_id=previous_session_id,
            environment_variables=project.environment_variables or {},
            auto_create_pull_requests=project.auto_create_pull_requests,
            metadata=metadata,
        )

    @staticmethod
    def _validate_inputs(
        work_item: WorkItem,
        workflow_id: str,
        stage_name: str,
        agent: Agent,
        project: ProjectContext,
        workspace: WorkspaceContext,
    ) -> None:
        """
        Validate all input parameters.

        Args:
            work_item: Work item to validate
            workflow_id: Workflow ID to validate
            stage_name: Stage name to validate
            agent: Agent to validate
            project: Project context to validate
            workspace: Workspace context to validate

        Raises:
            DomainError: If any validation fails
        """
        if not workflow_id or not workflow_id.strip():
            msg = "Workflow ID cannot be empty"
            raise DomainError(msg)

        if not stage_name or not stage_name.strip():
            msg = "Stage name cannot be empty"
            raise DomainError(msg)

        # Validate agent can execute in project environment
        if (
            agent.invocation.mode == InvocationMode.CONTAINERIZED
            and not project.has_dockerfile
            and not project.requires_dev_container
        ):
            # Agent requires Docker but project doesn't have Dockerfile or dev container
            # This is a warning condition but not a hard error - we can use a generic container
            pass

        if agent.requires_dev_container and not project.requires_dev_container:
            msg = f"Agent {agent.name} requires dev container but project {project.name} does not have one configured"
            raise DomainError(msg)

    @staticmethod
    def _build_metadata(
        work_item: WorkItem,
        agent: Agent,
        project: ProjectContext,
        workspace: WorkspaceContext,
        additional_metadata: dict[str, Any],
    ) -> dict[str, Any]:
        """
        Build metadata dictionary for execution context.

        Args:
            work_item: Work item
            agent: Agent
            project: Project context
            workspace: Workspace context
            additional_metadata: Additional metadata to merge

        Returns:
            Complete metadata dictionary
        """
        metadata = {
            "work_item_title": work_item.title,
            "work_item_status": work_item.status.value,
            "work_item_priority": work_item.priority.value,
            "work_item_labels": work_item.labels,
            "agent_name": agent.name,
            "agent_display_name": agent.display_name,
            "agent_type": agent.agent_type.value,
            "project_name": project.name,
            "project_display_name": project.display_name,
            "workspace_type": workspace.workspace_type.value,
            "default_branch": project.default_branch,
            "primary_language": project.primary_language,
            "has_ci_cd": project.has_ci_cd,
            "test_command": project.test_command,
            "test_framework": project.test_framework,
        }

        # Merge additional metadata (overrides defaults)
        metadata.update(additional_metadata)

        return metadata

    @staticmethod
    def _merge_mcp_servers(agent: Agent, project: ProjectContext) -> list[str]:
        """
        Merge MCP servers from agent and project.

        Combines agent-specific and project-level MCP servers,
        removing duplicates and maintaining order (agent servers first).

        Args:
            agent: Agent with MCP server configuration
            project: Project context with MCP server configuration

        Returns:
            Combined list of unique MCP server names
        """
        # Start with agent servers
        servers = list(agent.mcp_servers)

        # Add project servers that aren't already in the list
        for server in project.mcp_servers:
            if server not in servers:
                servers.append(server)

        return servers

    @staticmethod
    def build_context_for_stage(
        work_item: WorkItem,
        workflow_id: str,
        stage_name: str,
        agents: list[Agent],
        agent_id: str,
        project: ProjectContext,
        workspace: WorkspaceContext,
        previous_session_id: str | None = None,
    ) -> ExecutionContext:
        """
        Build execution context for a specific stage.

        Convenience method that looks up the agent from the list.

        Args:
            work_item: Work item being processed
            workflow_id: Workflow instance ID
            stage_name: Current pipeline stage name
            agents: List of all available agents
            agent_id: ID of agent to use
            project: Project context configuration
            workspace: Workspace routing context
            previous_session_id: Previous session ID for continuity (optional)

        Returns:
            Complete execution context

        Raises:
            DomainError: If agent not found or validation fails
        """
        # Find agent
        agent = next((a for a in agents if a.id == agent_id), None)
        if not agent:
            msg = f"Agent {agent_id} not found"
            raise DomainError(msg)

        return ExecutionContextBuilder.build_context(
            work_item=work_item,
            workflow_id=workflow_id,
            stage_name=stage_name,
            agent=agent,
            project=project,
            workspace=workspace,
            previous_session_id=previous_session_id,
        )
