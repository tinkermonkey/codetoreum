"""Domain type aliases for Codetoreum.

This module defines type aliases used throughout the domain layer to provide
better type safety and expressiveness.
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
