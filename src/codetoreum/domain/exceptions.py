"""Domain layer exceptions."""


class DomainError(Exception):
    """Base exception for domain layer errors."""

    def __init__(self, message: str):
        """
        Initialize domain error.

        Args:
            message: Error message describing the business rule violation
        """
        self.message = message
        super().__init__(self.message)


# Entity Not Found Exceptions
class AgentNotFoundError(DomainError):
    """Raised when an agent cannot be found."""

    def __init__(self, agent_id: str):
        super().__init__(f"Agent not found: {agent_id}")
        self.agent_id = agent_id


class ExecutionNotFoundError(DomainError):
    """Raised when an execution cannot be found."""

    def __init__(self, execution_id: str):
        super().__init__(f"Execution not found: {execution_id}")
        self.execution_id = execution_id


class WorkItemNotFoundError(DomainError):
    """Raised when a work item cannot be found."""

    def __init__(self, work_item_id: str):
        super().__init__(f"Work item not found: {work_item_id}")
        self.work_item_id = work_item_id


class WorkspaceNotFoundError(DomainError):
    """Raised when a workspace cannot be found."""

    def __init__(self, workspace_id: str):
        super().__init__(f"Workspace not found: {workspace_id}")
        self.workspace_id = workspace_id


class PipelineNotFoundError(DomainError):
    """Raised when a pipeline configuration cannot be found."""

    def __init__(self, pipeline_id: str):
        super().__init__(f"Pipeline not found: {pipeline_id}")
        self.pipeline_id = pipeline_id


class ConfigNotFoundError(DomainError):
    """Raised when a configuration cannot be found."""

    def __init__(self, config_id: str):
        super().__init__(f"Configuration not found: {config_id}")
        self.config_id = config_id


# State Transition Exceptions
class InvalidStateError(DomainError):
    """Raised when an invalid state transition is attempted."""

    def __init__(self, message: str):
        super().__init__(message)
