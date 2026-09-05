"""Domain type aliases for Codetoreum.

This module defines type aliases used throughout the domain layer to provide
better type safety and expressiveness.

Note: These NewType aliases provide static type checking only and do not perform
runtime validation. For critical identifiers that require runtime validation
(e.g., format validation, existence checks), consider implementing validated
value objects as a future enhancement.
"""

from typing import NewType

# Work Item identifiers
WorkItemId = NewType("WorkItemId", str)
ProjectId = NewType("ProjectId", str)
UserId = NewType("UserId", str)
ColumnId = NewType("ColumnId", str)
CommentId = NewType("CommentId", str)

# Agent and execution identifiers
AgentId = NewType("AgentId", str)
ExecutionId = NewType("ExecutionId", str)
WorkflowId = NewType("WorkflowId", str)
StageId = NewType("StageId", str)

# Repository identifiers
RepositoryId = NewType("RepositoryId", str)
CommitHash = NewType("CommitHash", str)
BranchName = NewType("BranchName", str)
RemoteName = NewType("RemoteName", str)

# Container identifiers
ContainerId = NewType("ContainerId", str)
ImageId = NewType("ImageId", str)

# Event store identifiers
StreamId = NewType("StreamId", str)
EventId = NewType("EventId", str)
CorrelationId = NewType("CorrelationId", str)

# Storage identifiers
StorageKey = NewType("StorageKey", str)
BucketName = NewType("BucketName", str)

# Metrics identifiers
MetricName = NewType("MetricName", str)

# Notification identifiers
NotificationId = NewType("NotificationId", str)
TemplateId = NewType("TemplateId", str)
ChannelId = NewType("ChannelId", str)

# Container label constants for Docker container labeling and recovery
# These labels enable the container recovery service to identify, track, and manage
# agent containers at orchestrator startup. All agent containers MUST include these labels.
CONTAINER_LABEL_TYPE = "org.codetoreum.type"
CONTAINER_LABEL_PROJECT = "org.codetoreum.project"
CONTAINER_LABEL_AGENT = "org.codetoreum.agent"
CONTAINER_LABEL_WORK_ITEM_ID = "org.codetoreum.work_item_id"
CONTAINER_LABEL_TASK_ID = "org.codetoreum.task_id"
CONTAINER_LABEL_WORKFLOW_RUN_ID = "org.codetoreum.workflow_run_id"
CONTAINER_LABEL_EXECUTION_ID = "org.codetoreum.execution_id"

# Valid container type values for org.codetoreum.type label
CONTAINER_TYPE_AGENT = "agent"
CONTAINER_TYPE_REPAIR_CYCLE = "repair-cycle"
