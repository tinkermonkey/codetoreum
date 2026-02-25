"""
Input Port Exceptions

This module defines all exceptions that can be raised by input port implementations.
These exceptions represent error conditions during command and query execution.
"""


class PortException(Exception):
    """Base exception for all input port errors"""


# Project-related exceptions
class ProjectNotFoundError(PortException):
    """Raised when a project does not exist"""


# Workflow-related exceptions
class WorkflowNotFoundError(PortException):
    """Raised when a workflow does not exist"""


class WorkflowNotActiveError(PortException):
    """Raised when attempting to pause a workflow that is not in active state"""


class WorkflowNotPausedError(PortException):
    """Raised when attempting to resume a workflow that is not in paused state"""


# Pipeline-related exceptions
class PipelineNotFoundError(PortException):
    """Raised when a pipeline does not exist"""


# Work Item-related exceptions
class WorkItemNotFoundError(PortException):
    """Raised when a work item does not exist"""


# Stage-related exceptions
class StageNotFoundError(PortException):
    """Raised when a workflow stage does not exist"""


# Agent-related exceptions
class AgentNotFoundError(PortException):
    """Raised when an agent does not exist"""


class AgentExecutionNotFoundError(PortException):
    """Raised when an agent execution does not exist"""


# Configuration-related exceptions
class ValidationError(PortException):
    """Raised when command parameters or configuration updates are invalid"""


class VariableNotFoundError(PortException):
    """Raised when an environment variable does not exist"""


class CommandFileNotFoundError(PortException):
    """Raised when a command file does not exist"""


class CommandNotFoundError(PortException):
    """Raised when a mounted command does not exist"""


class SubAgentNotFoundError(PortException):
    """Raised when a mounted sub-agent does not exist"""


# Permission-related exceptions
class PermissionError(PortException):
    """Raised when user lacks permission to perform operation"""


# Artifact-related exceptions
class ArtifactNotFoundError(PortException):
    """Raised when an artifact does not exist"""
