"""Workspace Router application service."""

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from codetoreum.domain.agent import Agent
from codetoreum.domain.project_context import ProjectContext
from codetoreum.domain.types import BranchName
from codetoreum.domain.work_item import WorkItem
from codetoreum.domain.workspace_context import WorkspaceContext
from codetoreum.ports.output import IContainer, IEventStore, IRepository

logger = logging.getLogger(__name__)


# ============================================================================
# Configuration
# ============================================================================


@dataclass
class WorkspaceRouterConfig:
    """Configuration for WorkspaceRouter service."""

    # Branch naming
    branch_prefix_default: str = "feature/"
    branch_name_format: str = "{prefix}issue-{number}-{title}"
    branch_title_max_length: int = 40

    # Commit message format
    commit_message_format: str = (
        "Complete work for issue #{work_item_id}\n\n"
        "Automated changes by agent: {agent_id}\n"
        "{summary}"
        "\n🤖 Generated with Codetoreum\n"
        "Co-Authored-By: Codetoreum <noreply@codetoreum.ai>\n"
    )

    # Workspace labels
    discussion_labels: set[str] = field(default_factory=lambda: {"discussion", "research", "question", "analysis"})

    # Author info defaults
    default_author_name: str = "Codetoreum"
    default_author_email: str = "noreply@codetoreum.ai"


# ============================================================================
# Data Models
# ============================================================================


@dataclass
class WorkspacePreparationResult:
    """Result of workspace preparation operation."""

    success: bool
    workspace_context: WorkspaceContext
    workspace_dir: Path
    reason: str
    metadata: dict[str, Any]


@dataclass
class WorkspaceFinalizationResult:
    """Result of workspace finalization operation."""

    success: bool
    commit_sha: str | None
    pr_url: str | None
    reason: str
    metadata: dict[str, Any]


# ============================================================================
# Service
# ============================================================================


class WorkspaceRouter:
    """
    Workspace Router application service.

    Manages container workspaces, handles file mounting, coordinates repository
    operations, and manages environment variables for agent executions.

    This service is responsible for:
    - Routing work items to appropriate workspace types (issue/discussion/hybrid)
    - Preparing workspace environments before agent execution
    - Managing file mounting for containerized execution
    - Coordinating repository operations (branch creation, commits, etc.)
    - Managing environment variables for agent containers
    - Finalizing workspace state after execution
    """

    def __init__(
        self,
        repository: IRepository,
        container: IContainer,
        event_store: IEventStore,
        config: WorkspaceRouterConfig | None = None,
    ):
        """
        Initialize WorkspaceRouter.

        Args:
            repository: Repository operations port
            container: Container orchestration port
            event_store: Event store port for emitting events
            config: Optional configuration (uses defaults if not provided)
        """
        self.repository = repository
        self.container = container
        self.event_store = event_store
        self.config = config or WorkspaceRouterConfig()
        self._logger = logging.getLogger(f"{__name__}.WorkspaceRouter")

    async def _emit_event_safely(self, event: Any) -> None:
        """
        Emit event to event store with error handling.

        Logs failures but doesn't break main flow.

        Args:
            event: Event to emit
        """
        try:
            await self.event_store.append(event.aggregate_id, [event])
        except Exception as e:
            self._logger.error(
                f"Failed to emit event {type(event).__name__}: {e}",
                exc_info=True,
                extra={"error_id": "ERR_WORKSPACE_EVENT_EMIT_FAILURE"},
            )

    # ========================================================================
    # Public API
    # ========================================================================

    async def route_workspace(
        self,
        work_item: WorkItem,
        agent: Agent,
        project: ProjectContext,
    ) -> WorkspaceContext:
        """
        Determine workspace type for work item and agent.

        Business rules:
        - Issues with 'discussion', 'research', or 'question' labels → Discussion workspace
        - Agents that don't make code changes → Discussion workspace
        - Default → Issue workspace with feature branch
        - Validates agent capabilities match work item requirements

        Args:
            work_item: Work item being processed
            agent: Agent that will execute
            project: Project context

        Returns:
            WorkspaceContext: Configured workspace context

        Raises:
            ValueError: If work item or agent configuration is invalid
        """
        self._logger.info(f"Routing workspace for work_item={work_item.id}, agent={agent.id}, project={project.id}")

        # Check for discussion labels
        has_discussion_label = any(label.lower() in self.config.discussion_labels for label in work_item.labels)

        # Check if agent makes code changes
        agent_makes_code_changes = agent.makes_code_changes

        # Validate agent capabilities match work item
        self._validate_agent_capabilities(work_item, agent, has_discussion_label)

        # Determine workspace type
        if has_discussion_label or not agent_makes_code_changes:
            # Discussion workspace
            self._logger.info(
                f"Routing to DISCUSSION workspace: "
                f"discussion_label={has_discussion_label}, "
                f"agent_makes_code_changes={agent_makes_code_changes}"
            )
            return WorkspaceContext.for_discussion(
                project_id=project.id,
                work_item_id=work_item.id,
                discussion_id=work_item.external_id or "",
            )
        # Issue workspace with feature branch
        branch_name = self._generate_branch_name(work_item, project)
        self._logger.info(f"Routing to ISSUE workspace with branch={branch_name}")
        return WorkspaceContext.for_issue(
            project_id=project.id,
            work_item_id=work_item.id,
            branch_name=branch_name,
            create_pr=True,
        )

    def _validate_agent_capabilities(
        self,
        work_item: WorkItem,
        agent: Agent,
        has_discussion_label: bool,
    ) -> None:
        """
        Validate agent capabilities match work item requirements.

        Args:
            work_item: Work item being processed
            agent: Agent to validate
            has_discussion_label: Whether work item has discussion label

        Raises:
            ValueError: If agent capabilities don't match work item
        """
        # If work item is discussion-only, agent shouldn't make code changes
        if has_discussion_label and agent.makes_code_changes:
            self._logger.warning(
                f"Code-changing agent {agent.id} assigned to discussion work item {work_item.id}. "
                f"This may not be optimal.",
                extra={"error_id": "ERR_WORKSPACE_SUBOPTIMAL_AGENT_ASSIGNMENT"},
            )

        # If work item needs code changes, agent must have that capability
        if not has_discussion_label and not agent.makes_code_changes:
            message = f"Agent {agent.id} cannot make code changes but is assigned to code work item {work_item.id}"
            raise ValueError(message)

    async def prepare_workspace(
        self,
        context: WorkspaceContext,
        project: ProjectContext,
        work_item: WorkItem,
        repository_path: str,
    ) -> WorkspacePreparationResult:
        """
        Prepare workspace for agent execution.

        For ISSUE workspaces:
        - Create or checkout feature branch
        - Ensure branch is up-to-date with base branch
        - Set up file mounts for container execution

        For DISCUSSION workspaces:
        - No branch operations needed
        - Minimal setup

        Args:
            context: Workspace context
            project: Project context
            work_item: Work item being processed
            repository_path: Local path to cloned repository

        Returns:
            WorkspacePreparationResult: Result of preparation operation

        Raises:
            RepositoryError: If repository operations fail
            ContainerError: If container operations fail
        """
        self._logger.info(
            f"Preparing workspace type={context.workspace_type.value}, project={project.id}, work_item={work_item.id}"
        )

        metadata: dict[str, Any] = {}

        try:
            if context.should_create_branch():
                # Issue workspace - prepare git branch
                repo_path = Path(repository_path)

                # Check if branch exists
                branches = await self.repository.list_branches(repo_path, remote=True)
                branch_exists = context.branch_name in branches

                if branch_exists:
                    # Checkout existing branch
                    self._logger.info(f"Checking out existing branch: {context.branch_name}")
                    await self.repository.checkout(repo_path, BranchName(context.branch_name or ""), create=False)
                    metadata["branch_action"] = "checkout_existing"
                else:
                    # Create new branch from base
                    self._logger.info(f"Creating new branch: {context.branch_name}")
                    await self.repository.create_branch(
                        repo_path,
                        BranchName(context.branch_name or ""),
                        from_branch=BranchName(project.default_branch),
                    )
                    await self.repository.checkout(repo_path, BranchName(context.branch_name or ""), create=False)
                    metadata["branch_action"] = "create_new"

                # Update branch with latest from base
                self._logger.info(f"Pulling latest changes from {project.default_branch}")
                await self.repository.pull(repo_path, remote="origin", branch=project.default_branch)
                metadata["updated_from_base"] = True

                return WorkspacePreparationResult(
                    success=True,
                    workspace_context=context,
                    workspace_dir=repo_path,
                    reason="Issue workspace prepared successfully",
                    metadata=metadata,
                )
            # Discussion workspace - minimal setup
            self._logger.info("Discussion workspace - minimal setup")
            return WorkspacePreparationResult(
                success=True,
                workspace_context=context,
                workspace_dir=Path(repository_path),
                reason="Discussion workspace prepared successfully",
                metadata=metadata,
            )

        except Exception as e:
            self._logger.error(
                f"Failed to prepare workspace: {e}",
                exc_info=True,
                extra={"error_id": "ERR_WORKSPACE_PREPARE_FAILURE"},
            )
            return WorkspacePreparationResult(
                success=False,
                workspace_context=context,
                workspace_dir=Path(repository_path),
                reason=f"Workspace preparation failed: {e!s}",
                metadata={"error": str(e)},
            )

    async def finalize_workspace(
        self,
        context: WorkspaceContext,
        project: ProjectContext,
        execution_result: dict[str, Any],
        repository_path: str,
    ) -> WorkspaceFinalizationResult:
        """
        Finalize workspace after agent execution.

        For ISSUE workspaces:
        - Commit changes if any
        - Push branch to remote
        - Optionally create pull request

        For DISCUSSION workspaces:
        - No-op (output already posted via ticket system)

        Args:
            context: Workspace context
            project: Project context
            execution_result: Result from agent execution
            repository_path: Local path to cloned repository

        Returns:
            WorkspaceFinalizationResult: Result of finalization operation

        Raises:
            RepositoryError: If repository operations fail
        """
        self._logger.info(f"Finalizing workspace type={context.workspace_type.value}, project={project.id}")

        metadata: dict[str, Any] = {}
        commit_sha = None
        pr_url = None

        try:
            if context.is_issue_workspace() and context.create_commits:
                repo_path = Path(repository_path)

                # Check if there are changes to commit
                status = await self.repository.status(repo_path)
                has_changes = status.is_dirty or status.staged_files or status.unstaged_files

                if has_changes:
                    # Commit changes
                    commit_message = self._generate_commit_message(context, execution_result)
                    self._logger.info(f"Committing changes: {commit_message}")

                    # Get author info, use config defaults if not in project
                    author_name = getattr(project, "author_name", self.config.default_author_name)
                    author_email = getattr(project, "author_email", self.config.default_author_email)

                    commit_sha = await self.repository.commit(
                        repo_path,
                        message=commit_message,
                        author_name=author_name,
                        author_email=author_email,
                        files=None,  # Commit all changes
                    )
                    metadata["commit_sha"] = commit_sha
                    metadata["commit_message"] = commit_message

                    # Push branch
                    self._logger.info(f"Pushing branch: {context.branch_name}")
                    await self.repository.push(repo_path, remote="origin", branch=context.branch_name)
                    metadata["pushed"] = True

                    # TODO: Create PR if needed (requires ticket system integration)
                    if context.create_pr:
                        self._logger.info("PR creation would happen here")
                        metadata["pr_requested"] = True

                    return WorkspaceFinalizationResult(
                        success=True,
                        commit_sha=commit_sha,
                        pr_url=pr_url,
                        reason="Issue workspace finalized successfully with commit",
                        metadata=metadata,
                    )
                self._logger.info("No changes to commit")
                return WorkspaceFinalizationResult(
                    success=True,
                    commit_sha=None,
                    pr_url=None,
                    reason="Issue workspace finalized successfully (no changes)",
                    metadata=metadata,
                )
            # Discussion workspace or no commits needed
            self._logger.info("Discussion workspace - no finalization needed")
            return WorkspaceFinalizationResult(
                success=True,
                commit_sha=None,
                pr_url=None,
                reason="Discussion workspace finalized successfully",
                metadata=metadata,
            )

        except Exception as e:
            self._logger.error(
                f"Failed to finalize workspace: {e}",
                exc_info=True,
                extra={"error_id": "ERR_WORKSPACE_FINALIZE_FAILURE"},
            )
            return WorkspaceFinalizationResult(
                success=False,
                commit_sha=None,
                pr_url=None,
                reason=f"Workspace finalization failed: {e!s}",
                metadata={"error": str(e)},
            )

    def prepare_container_environment(
        self,
        context: WorkspaceContext,
        project: ProjectContext,
        agent: Agent,
    ) -> dict[str, str]:
        """
        Prepare environment variables for container execution.

        Args:
            context: Workspace context
            project: Project context
            agent: Agent configuration

        Returns:
            Dict[str, str]: Environment variables for container
        """
        # Git author/committer info via env vars instead of .gitconfig bind mount.
        # .gitconfig file mounts break in Docker-in-Docker (DinD) environments
        # because the file appears as a directory inside the target container.
        author_name = getattr(project, "author_name", self.config.default_author_name)
        author_email = getattr(project, "author_email", self.config.default_author_email)

        env_vars = {
            # Project identification
            "CODETOREUM_PROJECT_ID": project.id,
            "CODETOREUM_WORK_ITEM_ID": context.work_item_id,
            # Workspace configuration
            "CODETOREUM_WORKSPACE_TYPE": context.workspace_type.value,
            "CODETOREUM_ALLOW_CODE_CHANGES": str(context.allow_code_changes),
            # Agent identification
            "CODETOREUM_AGENT_ID": agent.id,
            "CODETOREUM_AGENT_TYPE": agent.agent_type.value,
            # Git author/committer identity (replaces .gitconfig bind mount)
            "GIT_AUTHOR_NAME": author_name,
            "GIT_AUTHOR_EMAIL": author_email,
            "GIT_COMMITTER_NAME": author_name,
            "GIT_COMMITTER_EMAIL": author_email,
        }

        # Add branch info for issue workspaces
        if context.is_issue_workspace():
            env_vars["CODETOREUM_BRANCH_NAME"] = context.branch_name or ""

        # Add discussion info for discussion workspaces
        if context.is_discussion_workspace():
            env_vars["CODETOREUM_DISCUSSION_ID"] = context.discussion_id or ""

        # Merge with project-level environment variables
        if hasattr(project, "environment_variables"):
            env_vars.update(project.environment_variables)

        self._logger.debug(f"Prepared environment variables: {list(env_vars.keys())}")
        return env_vars

    def prepare_container_volumes(
        self,
        context: WorkspaceContext,
        project: ProjectContext,
        repository_path: str,
    ) -> dict[str, str]:
        """
        Prepare volume mounts for container execution.

        Args:
            context: Workspace context
            project: Project context
            repository_path: Local path to cloned repository

        Returns:
            Dict[str, str]: Volume mounts (host_path: container_path:mode)
        """
        repo_path = Path(repository_path)

        volumes = {}

        if context.can_make_code_changes():
            # Read-write mount for code changes
            volumes[str(repo_path.absolute())] = "/workspace:rw"
        else:
            # Read-only mount for analysis
            volumes[str(repo_path.absolute())] = "/workspace:ro"

        # Add context directory if exists
        context_dir = repo_path / ".codetoreum" / "context"
        if context_dir.exists():
            volumes[str(context_dir.absolute())] = "/context:ro"

        self._logger.debug(f"Prepared volume mounts: {volumes}")
        return volumes

    # ========================================================================
    # Private Methods
    # ========================================================================

    def _generate_branch_name(self, work_item: WorkItem, project: ProjectContext) -> str:
        """
        Generate branch name following project conventions.

        Uses configured format from WorkspaceRouterConfig.

        Args:
            work_item: Work item
            project: Project context

        Returns:
            str: Branch name
        """
        issue_number = work_item.external_id

        # Create title slug
        title_slug = (
            work_item.title.lower()
            .replace(" ", "-")
            .replace("/", "-")
            .replace("_", "-")[: self.config.branch_title_max_length]
        )
        # Remove any non-alphanumeric characters except hyphens
        title_slug = "".join(c for c in title_slug if c.isalnum() or c == "-")
        # Remove consecutive hyphens
        while "--" in title_slug:
            title_slug = title_slug.replace("--", "-")
        title_slug = title_slug.strip("-")

        # Get branch prefix from project or use default
        branch_prefix = getattr(project, "branch_prefix", self.config.branch_prefix_default)

        # Format using config template
        return self.config.branch_name_format.format(
            prefix=branch_prefix,
            number=issue_number,
            title=title_slug,
        )

    def _generate_commit_message(self, context: WorkspaceContext, execution_result: dict[str, Any]) -> str:
        """
        Generate commit message for workspace changes.

        Uses configured format from WorkspaceRouterConfig.

        Args:
            context: Workspace context
            execution_result: Execution result with agent output

        Returns:
            str: Commit message
        """
        agent_id = execution_result.get("agent_id", "unknown")
        work_item_id = context.work_item_id

        # Build summary section
        summary = ""
        if "summary" in execution_result:
            summary = f"\n{execution_result['summary']}\n"

        # Format using config template
        return self.config.commit_message_format.format(
            work_item_id=work_item_id,
            agent_id=agent_id,
            summary=summary,
        )
