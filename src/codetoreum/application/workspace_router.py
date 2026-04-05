"""Workspace Router application service."""

import asyncio
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from codetoreum.domain.agent import Agent
from codetoreum.domain.exceptions import DomainError
from codetoreum.domain.project_context import ProjectContext
from codetoreum.domain.value_objects import BranchResolution
from codetoreum.domain.work_item import WorkItem
from codetoreum.domain.workspace_context import WorkspaceContext
from codetoreum.infrastructure.error_ids import ErrorRegistry
from codetoreum.ports.exceptions import ExternalServiceError
from codetoreum.ports.output import IContainer, IEventStore
from codetoreum.ports.output.branch_resolution_service import IBranchResolutionService
from codetoreum.ports.output.version_control_service import IVersionControlService

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
        vcs: IVersionControlService | None = None,
        container: IContainer | None = None,
        event_store: IEventStore | None = None,
        config: WorkspaceRouterConfig | None = None,
        repository: IVersionControlService | None = None,  # Backward-compat: used as vcs if vcs is None
        branch_resolution_service: IBranchResolutionService | None = None,
    ):
        """
        Initialize WorkspaceRouter.

        Args:
            vcs: Version control service port (preferred)
            container: Container orchestration port
            event_store: Event store port for emitting events
            config: Optional configuration (uses defaults if not provided)
            repository: Deprecated; pass vcs instead. Used as vcs if vcs is None.
            branch_resolution_service: Optional branch resolution service for intelligent branch reuse.
                                      When None, falls back to generating branch names.
        """
        # Accept repository as vcs for backward compatibility
        self.vcs: IVersionControlService | None = vcs if vcs is not None else repository
        self.container = container
        self.event_store = event_store
        self.config = config or WorkspaceRouterConfig()
        self.branch_resolution_service = branch_resolution_service
        self._logger = logging.getLogger(f"{__name__}.WorkspaceRouter")

        # Cache for branch resolutions: work_item_id -> BranchResolution
        # Populated and consumed within prepare_workspace() by _resolve_branch_name()
        # Protected by lock for async-safety in concurrent prepare_workspace calls
        self._branch_resolutions: dict[str, BranchResolution] = {}
        # Track which work items fell back due to resolution failure
        self._branch_resolution_fallbacks: dict[str, str] = {}  # work_item_id -> error_message
        # Cache actual resolved branch names (work_item_id -> branch_name)
        # Used by finalize_workspace() and prepare_container_environment() to get the actual
        # branch name after resolution, since WorkspaceContext is frozen with placeholder name
        self._resolved_branch_names: dict[str, str] = {}
        self._branch_resolutions_lock = asyncio.Lock()

    async def _emit_event_safely(self, event: Any) -> None:
        """
        Emit event to event store with error handling.

        Logs failures but doesn't break main flow.

        Args:
            event: Event to emit
        """
        try:
            if self.event_store is None:
                return
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

        Note: Branch name resolution is deferred to prepare_workspace() where repository_path
        is available. Here we use a placeholder that will be overridden if resolution is configured.

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
        # Generate a temporary branch name (will be resolved in prepare_workspace if service is configured)
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

        **Expected Call Order**: Call this method BEFORE prepare_container_environment() and
        finalize_workspace(). The resolved branch name is cached internally and returned in
        the result metadata for explicit passing to callers. The cache is cleaned up in
        finalize_workspace's finally block.

        Args:
            context: Workspace context
            project: Project context
            work_item: Work item being processed
            repository_path: Local path to cloned repository

        Returns:
            WorkspacePreparationResult: Result of preparation operation. Metadata includes
                'resolved_branch_name' with the actual branch name after resolution.

        Raises:
            RepositoryError: If repository operations fail
            ContainerError: If container operations fail
        """
        self._logger.info(
            f"Preparing workspace type={context.workspace_type.value}, project={project.id}, work_item={work_item.id}"
        )

        # Clean up any stale resolved branch name from a previous call for this work_item.
        # This prevents permanent cache leaks if finalize_workspace is never called (e.g.,
        # in long-lived router instances where prepare_workspace may be called multiple times
        # for the same work_item without an intervening finalize_workspace call). (async-safe)
        async with self._branch_resolutions_lock:
            self._resolved_branch_names.pop(work_item.id, None)

        if self.vcs is None:
            return WorkspacePreparationResult(
                success=False,
                workspace_context=context,
                workspace_dir=Path(repository_path),
                reason="No VCS adapter configured",
                metadata={},
            )

        metadata: dict[str, Any] = {}

        try:
            if context.should_create_branch():
                # Issue workspace - prepare git branch
                repo_path = Path(repository_path)
                repo_path_str = str(repo_path)

                # First, attempt intelligent branch resolution if service is configured
                # This will cache the resolution decision in _branch_resolutions
                resolved_branch_name = await self._resolve_branch_name(work_item, project, repository_path)

                # Check if there's a cached branch resolution from _resolve_branch_name() (async-safe)
                async with self._branch_resolutions_lock:
                    resolution = self._branch_resolutions.get(work_item.id)
                    fallback_error = self._branch_resolution_fallbacks.get(work_item.id)

                try:
                    if resolution is not None:
                        # Use resolution service decision
                        self._logger.info(
                            f"Using branch resolution decision: action={resolution.action}, "
                            f"branch={resolution.branch_name}"
                        )

                        if resolution.action == "reuse":
                            # Resolution service says to reuse existing branch
                            self._logger.info(f"Reusing branch (resolved): {resolution.branch_name}")
                            await self.vcs.checkout(repo_path_str, resolution.branch_name or "")
                            metadata["branch_action"] = "reuse_resolved"
                            metadata["resolution_strategy"] = resolution.resolution_strategy
                        else:  # resolution.action == "create"
                            # Resolution service says to create new branch
                            self._logger.info(f"Creating new branch (resolved): {resolution.branch_name}")
                            await self.vcs.create_branch(
                                repo_path_str,
                                resolution.branch_name or "",
                                from_branch=project.default_branch,
                            )
                            await self.vcs.checkout(repo_path_str, resolution.branch_name or "")
                            metadata["branch_action"] = "create_resolved"
                            metadata["resolution_strategy"] = resolution.resolution_strategy
                    else:
                        # No resolution service or service wasn't used: use default logic
                        # Check if branch exists
                        branches = await self.vcs.list_branches(repo_path_str, remote=True)
                        branch_exists = resolved_branch_name in branches

                        if branch_exists:
                            # Checkout existing branch
                            self._logger.info(f"Checking out existing branch: {resolved_branch_name}")
                            await self.vcs.checkout(repo_path_str, resolved_branch_name or "")
                            metadata["branch_action"] = "checkout_existing"
                        else:
                            # Create new branch from base
                            self._logger.info(f"Creating new branch: {resolved_branch_name}")
                            await self.vcs.create_branch(
                                repo_path_str,
                                resolved_branch_name or "",
                                from_branch=project.default_branch,
                            )
                            await self.vcs.checkout(repo_path_str, resolved_branch_name or "")
                            metadata["branch_action"] = "create_new"

                        # Record fallback if resolution failed
                        if fallback_error is not None:
                            metadata["branch_resolution_fallback"] = True
                            metadata["branch_resolution_fallback_reason"] = fallback_error
                finally:
                    # Clean up the cached resolutions to prevent memory leaks in long-lived router (async-safe)
                    async with self._branch_resolutions_lock:
                        self._branch_resolutions.pop(work_item.id, None)
                        self._branch_resolution_fallbacks.pop(work_item.id, None)

                # Update branch with latest from base
                self._logger.info(f"Pulling latest changes from {project.default_branch}")
                await self.vcs.pull(repo_path_str, branch=project.default_branch)
                metadata["updated_from_base"] = True

                # Cache the actual resolved branch name for later use by finalize_workspace()
                # and prepare_container_environment() (async-safe)
                async with self._branch_resolutions_lock:
                    self._resolved_branch_names[work_item.id] = resolved_branch_name

                # Add resolved branch name to metadata for explicit passing to consumers
                metadata["resolved_branch_name"] = resolved_branch_name

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
        - Push branch to remote (using resolved branch name from cache)
        - Optionally create pull request

        For DISCUSSION workspaces:
        - No-op (output already posted via ticket system)

        **Expected Call Order**: This method should be called AFTER prepare_workspace()
        and prepare_container_environment(). It cleans up the resolved branch name cache
        in the finally block to prevent memory leaks. The cache is thread-safe via asyncio.Lock.

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

        if self.vcs is None:
            return WorkspaceFinalizationResult(
                success=False,
                commit_sha=None,
                pr_url=None,
                reason="No VCS adapter configured",
                metadata={},
            )

        metadata: dict[str, Any] = {}
        commit_sha = None
        pr_url = None

        try:
            if context.is_issue_workspace() and context.create_commits:
                repo_path = Path(repository_path)
                repo_path_str = str(repo_path)

                # Check if there are changes to commit
                vcs_status = await self.vcs.status(repo_path_str)
                has_changes = vcs_status.is_dirty or vcs_status.staged_files or vcs_status.unstaged_files

                if has_changes:
                    # Commit changes
                    commit_message = self._generate_commit_message(context, execution_result)
                    self._logger.info(f"Committing changes: {commit_message}")

                    # Get author info, use config defaults if not in project
                    author_name = getattr(project, "author_name", self.config.default_author_name)
                    author_email = getattr(project, "author_email", self.config.default_author_email)

                    commit_sha = await self.vcs.commit(
                        repo_path_str,
                        message=commit_message,
                        author_name=author_name,
                        author_email=author_email,
                        files=None,  # Commit all changes
                    )
                    metadata["commit_sha"] = commit_sha
                    metadata["commit_message"] = commit_message

                    # Push branch - use resolved name if available, fall back to context name
                    branch_to_push = await self._get_resolved_branch_name(context.work_item_id, context.branch_name or "")
                    self._logger.info(f"Pushing branch: {branch_to_push}")
                    await self.vcs.push(repo_path_str, branch_to_push)
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
        finally:
            # Clean up resolved branch name cache to prevent memory leaks (async-safe)
            async with self._branch_resolutions_lock:
                self._resolved_branch_names.pop(context.work_item_id, None)

    async def prepare_container_environment(
        self,
        context: WorkspaceContext,
        project: ProjectContext,
        agent: Agent,
    ) -> dict[str, str]:
        """
        Prepare environment variables for container execution.

        **Expected Call Order**: This method should be called AFTER prepare_workspace()
        and BEFORE finalize_workspace(). It retrieves the resolved branch name from the
        cache populated during prepare_workspace() and sets CODETOREUM_BRANCH_NAME env var.

        Args:
            context: Workspace context
            project: Project context
            agent: Agent configuration

        Returns:
            Dict[str, str]: Environment variables for container. For issue workspaces,
                includes CODETOREUM_BRANCH_NAME with the resolved branch name.
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
            # Use resolved branch name if available (actual name after resolution),
            # fall back to context branch name (placeholder from route_workspace)
            branch_name = await self._get_resolved_branch_name(context.work_item_id, context.branch_name or "")
            env_vars["CODETOREUM_BRANCH_NAME"] = branch_name

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

    async def _resolve_branch_name(
        self, work_item: WorkItem, project: ProjectContext, repository_path: str
    ) -> str:
        """
        Resolve branch name using intelligent branch resolution or fallback to generation.

        If branch_resolution_service is configured, attempts to resolve branch via that service.
        Otherwise, falls back to generating a new branch name.

        The resolution decision is cached for later use by prepare_workspace().

        Args:
            work_item: Work item
            project: Project context
            repository_path: Actual path to the repository (used by resolution service)

        Returns:
            str: Resolved or generated branch name
        """
        if self.branch_resolution_service is not None:
            try:
                # Build issue metadata for resolution service
                issue_metadata = {
                    "title": work_item.title,
                    "description": work_item.description or "",
                    "labels": work_item.labels or [],
                }

                # Call branch resolution service with actual repository path
                resolution = await self.branch_resolution_service.resolve_branch(
                    project_id=project.id,
                    issue_id=work_item.id,
                    issue_metadata=issue_metadata,
                    repo_path=repository_path,
                )

                # Cache the resolution for prepare_workspace() to use (async-safe)
                async with self._branch_resolutions_lock:
                    self._branch_resolutions[work_item.id] = resolution

                self._logger.info(
                    f"Branch resolved with action={resolution.action}, "
                    f"branch={resolution.branch_name}, "
                    f"strategy={resolution.resolution_strategy}, "
                    f"confidence={resolution.confidence}"
                )
                return resolution.branch_name

            except ExternalServiceError as e:
                # External service errors (e.g., GitHub API down) are operational errors
                error_msg = f"Branch resolution failed: {e}"
                self._logger.error(
                    f"Falling back to branch generation. {error_msg}",
                    exc_info=True,
                    extra={"error_id": ErrorRegistry.ERR_BRANCH_RESOLUTION_FALLBACK},
                )
                # Record fallback for metadata reporting in prepare_workspace() (async-safe)
                async with self._branch_resolutions_lock:
                    self._branch_resolution_fallbacks[work_item.id] = error_msg
                # Fall through to generate name
            except (TypeError, AttributeError, KeyError, ValueError, RuntimeError, DomainError):
                # Programming errors should propagate, not silently fall back
                raise
            except Exception as e:
                # Other transient errors: log at WARNING and fall back to generation
                error_msg = f"Branch resolution failed: {e}"
                self._logger.warning(
                    f"Falling back to branch generation. {error_msg}",
                    exc_info=True,
                    extra={"error_id": ErrorRegistry.ERR_BRANCH_RESOLUTION_ERROR},
                )
                # Record fallback for metadata reporting in prepare_workspace() (async-safe)
                async with self._branch_resolutions_lock:
                    self._branch_resolution_fallbacks[work_item.id] = error_msg
                # Fall through to generate name

        # No service or service failed: generate branch name
        return self._generate_branch_name(work_item, project)

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

    async def _get_resolved_branch_name(self, work_item_id: str, fallback_name: str) -> str:
        """
        Get the actual resolved branch name for a work item.

        Checks the cache of resolved branch names (set during prepare_workspace).
        If not found, returns the fallback name (placeholder from route_workspace).

        This handles the case where WorkspaceContext is frozen with a placeholder
        branch name, but the actual branch may have been resolved to a different
        name during prepare_workspace().

        Args:
            work_item_id: Work item identifier
            fallback_name: Placeholder/default name to use if no resolution cached

        Returns:
            str: The actual resolved branch name, or fallback if not resolved
        """
        async with self._branch_resolutions_lock:
            return self._resolved_branch_names.get(work_item_id, fallback_name)

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
