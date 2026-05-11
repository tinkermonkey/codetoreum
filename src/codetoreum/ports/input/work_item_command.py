"""Work Item Command Input Port

This module defines the input port interface for work item command operations,
including creating, updating, and deleting work items.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass

from codetoreum.domain.work_item import WorkItem, WorkItemPriority


@dataclass
class CreateWorkItemCommand:
    """Command to create a new work item"""

    project_id: str
    title: str
    description: str
    labels: list[str] | None = None
    priority: WorkItemPriority = WorkItemPriority.MEDIUM
    external_id: str | None = None
    external_url: str | None = None


@dataclass
class UpdateWorkItemCommand:
    """Command to update an existing work item"""

    work_item_id: str
    title: str | None = None
    description: str | None = None
    labels: list[str] | None = None
    priority: WorkItemPriority | None = None


@dataclass
class AssignAgentCommand:
    """Command to assign an agent to a work item"""

    work_item_id: str
    agent_id: str
    reason: str


@dataclass
class UpdateLabelsCommand:
    """Command to update work item labels"""

    work_item_id: str
    labels: list[str]


@dataclass
class UpdatePriorityCommand:
    """Command to update work item priority"""

    work_item_id: str
    priority: WorkItemPriority


@dataclass
class AttachWorkflowCommand:
    """Command to attach a workflow to a work item"""

    work_item_id: str
    workflow_id: str


@dataclass
class UpdateStageCommand:
    """Command to update work item stage"""

    work_item_id: str
    stage: str


@dataclass
class WorkItemCommandResult:
    """Result of executing a work item command"""

    success: bool
    work_item_id: str
    message: str
    errors: list[str] | None = None


class IWorkItemCommandPort(ABC):
    """
    Input port for work item commands.

    This port accepts commands to create, update, and manage work items.
    Implementations of this port should:
    - Validate command parameters
    - Delegate to application services for execution
    - Emit appropriate domain events
    - Handle errors and return results
    """

    @abstractmethod
    async def create_work_item(self, command: CreateWorkItemCommand) -> WorkItem:
        """
        Creates a new work item.

        Args: command: Command with work item creation parameters

        Returns: Created work item

        Raises: ValidationError: If command parameters invalid
            ProjectNotFoundError: If project doesn't exist
        """

    @abstractmethod
    async def update_work_item(self, command: UpdateWorkItemCommand) -> WorkItem:
        """
        Updates an existing work item.

        Args: command: Command with update parameters

        Returns: Updated work item

        Raises: WorkItemNotFoundError: If work item doesn't exist
            ValidationError: If command parameters invalid
        """

    @abstractmethod
    async def delete_work_item(self, work_item_id: str) -> WorkItemCommandResult:
        """
        Soft deletes a work item.

        Args: work_item_id: Work item ID

        Returns: Result containing success status and message

        Raises: WorkItemNotFoundError: If work item doesn't exist
        """

    @abstractmethod
    async def assign_agent(self, command: AssignAgentCommand) -> WorkItem:
        """
        Assigns an agent to a work item.

        Args: command: Command with assignment parameters

        Returns: Updated work item

        Raises: WorkItemNotFoundError: If work item doesn't exist
            AgentNotFoundError: If agent doesn't exist
        """

    @abstractmethod
    async def update_labels(self, command: UpdateLabelsCommand) -> WorkItem:
        """
        Updates work item labels.

        Args: command: Command with label updates

        Returns: Updated work item

        Raises: WorkItemNotFoundError: If work item doesn't exist
        """

    @abstractmethod
    async def update_priority(self, command: UpdatePriorityCommand) -> WorkItem:
        """
        Updates work item priority.

        Args: command: Command with priority update

        Returns: Updated work item

        Raises: WorkItemNotFoundError: If work item doesn't exist
        """

    @abstractmethod
    async def attach_workflow(self, command: AttachWorkflowCommand) -> WorkItem:
        """
        Attaches a workflow to a work item.

        Args: command: Command with workflow attachment parameters

        Returns: Updated work item

        Raises: WorkItemNotFoundError: If work item doesn't exist
            WorkflowNotFoundError: If workflow doesn't exist
        """

    @abstractmethod
    async def update_stage(self, command: UpdateStageCommand) -> WorkItem:
        """
        Updates work item stage.

        Args: command: Command with stage update

        Returns: Updated work item

        Raises: WorkItemNotFoundError: If work item doesn't exist
        """
