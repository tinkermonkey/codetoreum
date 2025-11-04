"""
Workflow Definition Command Input Port

This module defines the input port interface for workflow definition management,
including creating, updating, and deleting workflow definitions.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class StageDefinition:
    """Stage definition for workflow"""
    name: str
    agent_name: str
    timeout_seconds: Optional[int] = None
    retry_count: int = 0
    entry_conditions: List[Dict[str, Any]] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class StageTransitionDefinition:
    """Stage transition definition"""
    from_stage: str
    to_stage: str
    condition: Optional[str] = None


@dataclass
class CreateWorkflowDefinitionCommand:
    """Command to create a new workflow definition"""
    name: str
    description: str
    project_id: str
    stages: List[StageDefinition]
    transitions: List[StageTransitionDefinition] = field(default_factory=list)
    work_item_types: List[str] = field(default_factory=list)
    is_template: bool = False
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class UpdateWorkflowDefinitionCommand:
    """Command to update an existing workflow definition"""
    workflow_id: str
    name: Optional[str] = None
    description: Optional[str] = None
    stages: Optional[List[StageDefinition]] = None
    transitions: Optional[List[StageTransitionDefinition]] = None
    work_item_types: Optional[List[str]] = None
    metadata: Optional[Dict[str, Any]] = None


@dataclass
class DeleteWorkflowDefinitionCommand:
    """Command to delete a workflow definition"""
    workflow_id: str
    force: bool = False  # If True, delete even if active executions exist


@dataclass
class WorkflowDefinitionCommandResult:
    """Result of executing a workflow definition command"""
    success: bool
    workflow_id: str
    version: Optional[int] = None  # New version number for updates
    message: str
    errors: Optional[List[str]] = field(default=None)


class IWorkflowDefinitionCommandPort(ABC):
    """
    Input port for workflow definition commands.

    This port accepts commands to manage workflow definitions, including
    creation, updates, and deletion. Updates create new versions while
    preserving history.

    Implementations of this port should:
    - Validate command parameters
    - Check for circular dependencies in stage transitions
    - Validate agent references
    - Create new versions on updates (preserve history)
    - Prevent deletion of workflows with active executions
    - Emit appropriate domain events
    - Handle errors and return results
    """

    @abstractmethod
    async def create_workflow_definition(
        self,
        command: CreateWorkflowDefinitionCommand
    ) -> WorkflowDefinitionCommandResult:
        """
        Creates a new workflow definition.

        This operation:
        1. Validates workflow structure (no circular dependencies)
        2. Validates agent references exist
        3. Creates workflow definition with version 1
        4. Emits WorkflowDefinitionCreated event

        Args:
            command: Command with workflow definition

        Returns:
            Result containing workflow ID and version

        Raises:
            ProjectNotFoundError: If project doesn't exist
            AgentNotFoundError: If referenced agent doesn't exist
            CircularDependencyError: If stage transitions create a cycle
            ValidationError: If command parameters invalid
        """
        pass

    @abstractmethod
    async def update_workflow_definition(
        self,
        command: UpdateWorkflowDefinitionCommand
    ) -> WorkflowDefinitionCommandResult:
        """
        Updates an existing workflow definition.

        This operation:
        1. Validates workflow exists
        2. Validates updated structure (no circular dependencies)
        3. Validates agent references
        4. Creates new version (increments version number)
        5. Preserves previous version in history
        6. Emits WorkflowDefinitionUpdated event

        Args:
            command: Command with workflow updates

        Returns:
            Result containing workflow ID and new version number

        Raises:
            WorkflowNotFoundError: If workflow doesn't exist
            AgentNotFoundError: If referenced agent doesn't exist
            CircularDependencyError: If stage transitions create a cycle
            ValidationError: If command parameters invalid
        """
        pass

    @abstractmethod
    async def delete_workflow_definition(
        self,
        command: DeleteWorkflowDefinitionCommand
    ) -> WorkflowDefinitionCommandResult:
        """
        Deletes a workflow definition.

        By default (force=False), deletion fails if there are active executions.
        If force=True, workflow is deleted regardless (active executions continue
        with the last known version).

        This operation:
        1. Checks for active executions (if force=False)
        2. Marks workflow as deleted (soft delete)
        3. Emits WorkflowDefinitionDeleted event

        Args:
            command: Command with deletion parameters

        Returns:
            Result indicating success or failure

        Raises:
            WorkflowNotFoundError: If workflow doesn't exist
            ActiveExecutionsExistError: If active executions exist and force=False
        """
        pass

    @abstractmethod
    async def activate_workflow_definition(
        self,
        workflow_id: str
    ) -> WorkflowDefinitionCommandResult:
        """
        Activates a workflow definition.

        Inactive workflows cannot be used for new executions.

        Args:
            workflow_id: Workflow to activate

        Returns:
            Result indicating success

        Raises:
            WorkflowNotFoundError: If workflow doesn't exist
        """
        pass

    @abstractmethod
    async def deactivate_workflow_definition(
        self,
        workflow_id: str
    ) -> WorkflowDefinitionCommandResult:
        """
        Deactivates a workflow definition.

        Prevents new executions from using this workflow, but existing
        executions continue.

        Args:
            workflow_id: Workflow to deactivate

        Returns:
            Result indicating success

        Raises:
            WorkflowNotFoundError: If workflow doesn't exist
        """
        pass
