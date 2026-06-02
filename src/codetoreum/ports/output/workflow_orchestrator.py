"""Workflow orchestrator port interface.

This interface defines contracts for orchestrating workflows within
a single project, handling card movements, stage transitions, and
agent execution.
"""

from abc import ABC


class IWorkflowOrchestrator(ABC):
    """Output port for orchestrating workflows within a project.

    Coordinates workflow execution for a single project, handling:
    - Card movements on project boards
    - Workflow stage transitions
    - Agent task queuing and execution
    - Review cycles and feedback loops

    Workflow orchestration is triggered by WorkItemColumnChangedEvent and other
    domain events emitted by adapters. The application is fully event-driven;
    polling is handled internally by adapters as a private concern.
    """

    pass
