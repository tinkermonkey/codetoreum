"""Lightweight test event helpers for simulation scenario tests.

These classes provide the simplified aggregate_id/payload interface used
by scenario tests that exercise SimulationRunner assertion infrastructure.
They are NOT domain events — they exist solely to support manual event
capture in scenario tests without requiring full CodetoreumEvent constructors.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone


@dataclass
class _SimTestEvent:
    aggregate_id: str = ""
    payload: dict = field(default_factory=dict)
    correlation_id: str | None = None
    occurred_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    @property
    def event_type(self) -> str:
        return self.__class__.__name__


@dataclass
class WorkflowStarted(_SimTestEvent):
    pass


@dataclass
class WorkflowCompleted(_SimTestEvent):
    pass


@dataclass
class AgentExecutionStarted(_SimTestEvent):
    pass


@dataclass
class AgentExecutionCompleted(_SimTestEvent):
    pass


@dataclass
class AgentExecutionFailed(_SimTestEvent):
    pass


@dataclass
class ExecutionRetryScheduled(_SimTestEvent):
    pass


@dataclass
class ReviewRejected(_SimTestEvent):
    pass


@dataclass
class ReviewApproved(_SimTestEvent):
    pass


@dataclass
class WorkItemColumnChanged(_SimTestEvent):
    pass


@dataclass
class WorkflowBranchSelected(_SimTestEvent):
    pass
