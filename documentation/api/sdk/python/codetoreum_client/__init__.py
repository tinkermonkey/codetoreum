"""
Codetoreum Python SDK

Official Python client library for the Codetoreum AI Agent Orchestration Platform.

Installation:
    pip install codetoreum-client

Usage:
    from codetoreum_client import CodetoreumClient

    client = CodetoreumClient(
        base_url="http://localhost:8000",
        api_token="your_token_here"
    )

    # Create a work item
    work_item = client.work_items.create(
        title="Implement feature X",
        description="Add feature X to the system",
        project_id="my-project",
        labels=["feature"]
    )

    # Start a workflow
    workflow_run = client.orchestrator.start_workflow(work_item.id)

    # Monitor execution
    for event in client.events.stream():
        print(f"Event: {event.type} - {event.data}")
"""

from .client import CodetoreumClient
from .exceptions import (
    CodetoreumError,
    AuthenticationError,
    NotFoundError,
    ValidationError,
    RateLimitError,
)
from .models import (
    WorkItem,
    Agent,
    Execution,
    Workflow,
    WorkflowRun,
)

__version__ = "2.0.0"
__all__ = [
    "CodetoreumClient",
    "CodetoreumError",
    "AuthenticationError",
    "NotFoundError",
    "ValidationError",
    "RateLimitError",
    "WorkItem",
    "Agent",
    "Execution",
    "Workflow",
    "WorkflowRun",
]
