"""Workflow orchestrator port interface.

This interface defines contracts for orchestrating workflows within
a single project, handling card movements, stage transitions, and
agent execution.
"""

from abc import ABC, abstractmethod

from codetoreum.domain.value_objects import ProjectConfig


class IWorkflowOrchestrator(ABC):
    """Output port for orchestrating workflows within a project.

    Coordinates workflow execution for a single project, handling:
    - Card movements on project boards
    - Workflow stage transitions
    - Agent task queuing and execution
    - Review cycles and feedback loops

    This interface is implemented by the WorkflowOrchestrator application
    service and called by MultiProjectOrchestrator for each project.
    """

    @abstractmethod
    async def orchestrate_project(self, project_name: str, workspace_path: str, config: ProjectConfig) -> int:
        """Execute orchestration for a single project.

        Coordinates workflow activities for the project:
        1. Checks if project is enabled via config.enabled flag
        2. Scans automated columns for work items requiring agent execution
        3. Queues agent tasks for items in automated columns
        4. Emits routing decisions and updates workflow state

        Args:
            project_name: Name of the project
            workspace_path: Local workspace path for the project
            config: Project configuration (repo, branch, enabled status)

        Returns:
            int: Number of actions taken (tasks queued, etc.)

        Raises:
            ExternalServiceError: External service communication failure
        """
