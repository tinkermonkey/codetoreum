"""
Input Port Exceptions

This module defines all exceptions that can be raised by input port implementations.
These exceptions represent error conditions during command and query execution.
"""


class PortException(Exception):
    """Base exception for all input port errors"""
    pass


# Project-related exceptions
class ProjectNotFoundError(PortException):
    """Raised when a project does not exist"""
    pass


# Workflow-related exceptions
class WorkflowNotFoundError(PortException):
    """Raised when a workflow does not exist"""
    pass


class WorkflowNotActiveError(PortException):
    """Raised when attempting to pause a workflow that is not in active state"""
    pass


class WorkflowNotPausedError(PortException):
    """Raised when attempting to resume a workflow that is not in paused state"""
    pass


# Pipeline-related exceptions
class PipelineNotFoundError(PortException):
    """Raised when a pipeline does not exist"""
    pass


# Work Item-related exceptions
class WorkItemNotFoundError(PortException):
    """Raised when a work item does not exist"""
    pass


# Stage-related exceptions
class StageNotFoundError(PortException):
    """Raised when a workflow stage does not exist"""
    pass


# Agent-related exceptions
class AgentNotFoundError(PortException):
    """Raised when an agent does not exist"""
    pass


class AgentExecutionNotFoundError(PortException):
    """Raised when an agent execution does not exist"""
    pass


# Configuration-related exceptions
class ValidationError(PortException):
    """Raised when command parameters or configuration updates are invalid"""
    pass


class VariableNotFoundError(PortException):
    """Raised when an environment variable does not exist"""
    pass


class CommandFileNotFoundError(PortException):
    """Raised when a command file does not exist"""
    pass


class CommandNotFoundError(PortException):
    """Raised when a mounted command does not exist"""
    pass


class SubAgentNotFoundError(PortException):
    """Raised when a mounted sub-agent does not exist"""
    pass


# Permission-related exceptions
class PermissionError(PortException):
    """Raised when user lacks permission to perform operation"""
    pass


# Artifact-related exceptions
class ArtifactNotFoundError(PortException):
    """Raised when an artifact does not exist"""
    pass
