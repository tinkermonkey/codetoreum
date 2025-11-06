"""
Data models for Codetoreum API resources
"""
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any
from datetime import datetime


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
    external_id: Optional[str] = None
    assignee: Optional[str] = None
    labels: List[str] = field(default_factory=list)
    priority: str = "medium"
    workflow_stage: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict) -> "WorkItem":
        """Create WorkItem from API response dict."""
        return cls(**{k: v for k, v in data.items() if k in cls.__annotations__})


@dataclass
class Agent:
    """Represents an AI agent."""

    id: str
    name: str
    description: str
    agent_type: str
    capabilities: List[str]
    configuration: Dict[str, Any]
    active: bool
    created_at: str
    updated_at: Optional[str] = None

    @classmethod
    def from_dict(cls, data: dict) -> "Agent":
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
    completed_at: Optional[str] = None
    duration_seconds: Optional[float] = None
    container_id: Optional[str] = None
    progress: Optional[Dict[str, Any]] = None
    error_message: Optional[str] = None

    @classmethod
    def from_dict(cls, data: dict) -> "Execution":
        """Create Execution from API response dict."""
        return cls(**{k: v for k, v in data.items() if k in cls.__annotations__})


@dataclass
class WorkflowStage:
    """Represents a workflow stage definition."""

    name: str
    agent_id: str
    entry_conditions: List[str] = field(default_factory=list)
    timeout_minutes: int = 60
    retry_policy: Optional[Dict[str, Any]] = None


@dataclass
class Workflow:
    """Represents a workflow definition."""

    id: str
    name: str
    description: str
    version: str
    active: bool
    stages: List[Dict[str, Any]]
    created_at: str
    updated_at: Optional[str] = None

    @classmethod
    def from_dict(cls, data: dict) -> "Workflow":
        """Create Workflow from API response dict."""
        return cls(**{k: v for k, v in data.items() if k in cls.__annotations__})


@dataclass
class WorkflowRun:
    """Represents a workflow execution run."""

    workflow_run_id: str
    work_item_id: str
    workflow_id: Optional[str] = None
    workflow_name: Optional[str] = None
    current_stage: Optional[str] = None
    status: str = "pending"
    started_at: Optional[str] = None
    completed_at: Optional[str] = None

    @classmethod
    def from_dict(cls, data: dict) -> "WorkflowRun":
        """Create WorkflowRun from API response dict."""
        return cls(**{k: v for k, v in data.items() if k in cls.__annotations__})


@dataclass
class PaginatedResponse:
    """Represents a paginated API response."""

    items: List[Any]
    total: int
    offset: int
    limit: int

    @classmethod
    def from_dict(cls, data: dict, item_class: type) -> "PaginatedResponse":
        """Create PaginatedResponse from API response dict."""
        return cls(
            items=[item_class.from_dict(item) for item in data.get("items", [])],
            total=data.get("total", 0),
            offset=data.get("offset", 0),
            limit=data.get("limit", 50),
        )
