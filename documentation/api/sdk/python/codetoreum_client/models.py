"""
Data models for Codetoreum API resources
"""

from dataclasses import dataclass, field
from typing import Any, TypeVar, cast

T = TypeVar("T")


@dataclass
class WorkItem:
    """Represents a work item (issue, task, etc.)."""

    id: str
    title: str
    description: str
    status: str
    project_id: str
    created_at: str
    updated_at: str
    external_id: str | None = None
    assignee: str | None = None
    labels: list[str] = field(default_factory=list)
    priority: str = "medium"
    workflow_stage: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "WorkItem":
        """Create WorkItem from API response dict."""
        return cls(**{k: v for k, v in data.items() if k in cls.__annotations__})


@dataclass
class Agent:
    """Represents an AI agent."""

    id: str
    name: str
    description: str
    agent_type: str
    capabilities: list[str]
    configuration: dict[str, Any]
    active: bool
    created_at: str
    updated_at: str | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Agent":
        """Create Agent from API response dict."""
        return cls(**{k: v for k, v in data.items() if k in cls.__annotations__})


@dataclass
class Execution:
    """Represents an agent execution."""

    id: str
    agent_id: str
    work_item_id: str
    workflow_run_id: str
    stage_name: str
    status: str
    started_at: str
    completed_at: str | None = None
    duration_seconds: float | None = None
    container_id: str | None = None
    progress: dict[str, Any] | None = None
    error_message: str | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Execution":
        """Create Execution from API response dict."""
        return cls(**{k: v for k, v in data.items() if k in cls.__annotations__})


@dataclass
class WorkflowStage:
    """Represents a workflow stage definition."""

    name: str
    agent_id: str
    entry_conditions: list[str] = field(default_factory=list)
    timeout_minutes: int = 60
    retry_policy: dict[str, Any] | None = None


@dataclass
class Workflow:
    """Represents a workflow definition."""

    id: str
    name: str
    description: str
    version: str
    active: bool
    stages: list[dict[str, Any]]
    created_at: str
    updated_at: str | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Workflow":
        """Create Workflow from API response dict."""
        return cls(**{k: v for k, v in data.items() if k in cls.__annotations__})


@dataclass
class WorkflowRun:
    """Represents a workflow execution run."""

    workflow_run_id: str
    work_item_id: str
    workflow_id: str | None = None
    workflow_name: str | None = None
    current_stage: str | None = None
    status: str = "pending"
    started_at: str | None = None
    completed_at: str | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "WorkflowRun":
        """Create WorkflowRun from API response dict."""
        return cls(**{k: v for k, v in data.items() if k in cls.__annotations__})


@dataclass
class PaginatedResponse:
    """Represents a paginated API response."""

    items: list[Any]
    total: int
    offset: int
    limit: int

    @classmethod
    def from_dict(cls, data: dict[str, Any], item_class: type[T]) -> "PaginatedResponse":
        """Create PaginatedResponse from API response dict."""
        return cls(
            items=[cast("Any", item_class).from_dict(item) for item in data.get("items", [])],
            total=data.get("total", 0),
            offset=data.get("offset", 0),
            limit=data.get("limit", 50),
        )
