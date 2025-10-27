"""
Input Ports Module

This module exports all input port interfaces and their related types.
Input ports define how external systems interact with the application.
"""

from .config_command import (
    AddEnvironmentVariableCommand,
    ConfigurationCommandResult,
    IConfigCommandPort,
    MountCommandCommand,
    MountSubAgentCommand,
    RemoveEnvironmentVariableCommand,
    UnmountCommandCommand,
    UnmountSubAgentCommand,
    UpdateAgentConfigCommand,
    UpdatePipelineConfigCommand,
    UpdateProjectConfigCommand,
)
from .task_query import (
    ArtifactInfo,
    ArtifactListResult,
    ExecutionHistory,
    ExecutionHistoryEntry,
    ExecutionListItem,
    ExecutionListResult,
    ExecutionStatus,
    ExecutionStatusInfo,
    ITaskQueryPort,
)
from .workflow_command import (
    CancelWorkflowCommand,
    IWorkflowCommandPort,
    PauseWorkflowCommand,
    ResumeWorkflowCommand,
    RetryStageCommand,
    StartWorkflowCommand,
    TriggerType,
    WorkflowCommandResult,
)

__all__ = [
    # Workflow Command Port
    "IWorkflowCommandPort",
    "StartWorkflowCommand",
    "PauseWorkflowCommand",
    "ResumeWorkflowCommand",
    "CancelWorkflowCommand",
    "RetryStageCommand",
    "WorkflowCommandResult",
    "TriggerType",
    # Task Query Port
    "ITaskQueryPort",
    "ExecutionStatusInfo",
    "ExecutionListItem",
    "ExecutionListResult",
    "ArtifactInfo",
    "ArtifactListResult",
    "ExecutionHistory",
    "ExecutionHistoryEntry",
    "ExecutionStatus",
    # Config Command Port
    "IConfigCommandPort",
    "UpdateProjectConfigCommand",
    "UpdateAgentConfigCommand",
    "UpdatePipelineConfigCommand",
    "AddEnvironmentVariableCommand",
    "RemoveEnvironmentVariableCommand",
    "MountCommandCommand",
    "UnmountCommandCommand",
    "MountSubAgentCommand",
    "UnmountSubAgentCommand",
    "ConfigurationCommandResult",
]
