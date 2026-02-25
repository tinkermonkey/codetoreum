"""Simulation infrastructure for testing."""
from typing import Any

from .mock_tracer import (
    MockTracer,
    SpanCapture,
    SpanKind,
    SpanStatus,
    TraceContextValidator,
)
from .scenario_models import (
    ScenarioAgentModel,
    ScenarioBoardItemPlacementModel,
    ScenarioBoardModel,
    ScenarioModel,
    ScenarioProjectModel,
    ScenarioStageModel,
    ScenarioWorkflowModel,
    ScenarioWorkItemModel,
)
from .simulation_clock import (
    RealTimeClock,
    SimulationClock,
    get_clock,
    reset_clock,
    set_clock,
)
from .simulation_config import (
    AgentBehaviorConfig,
    ContainerBehaviorConfig,
    MetricsConfig,
    NotificationConfig,
    SimulationConfig,
    TimeConfig,
)
from .simulation_engine import SimulationEngine
from .simulation_runner import (
    AssertionResult,
    SimulationResult,
    SimulationRunner,
)

__all__ = [
    # Clock
    "SimulationClock",
    "RealTimeClock",
    "get_clock",
    "set_clock",
    "reset_clock",
    # Engine
    "SimulationEngine",
    # Config
    "SimulationConfig",
    "AgentBehaviorConfig",
    "ContainerBehaviorConfig",
    "NotificationConfig",
    "MetricsConfig",
    "TimeConfig",
    # Runner
    "SimulationRunner",
    "SimulationResult",
    "AssertionResult",
    # Mock Tracer
    "MockTracer",
    "SpanCapture",
    "SpanKind",
    "SpanStatus",
    "TraceContextValidator",
    # Bootstrap (lazy imported to avoid circular import)
    "SimulationApplicationBootstrap",
    "SimulationAdapters",
    "SimulationServices",
    "SimulationPorts",
    "SimulationInfrastructure",
    # Seeding
    "SimulationDataSeeder",
    "CreatedItems",
    # Scenario Models
    "ScenarioModel",
    "ScenarioProjectModel",
    "ScenarioWorkflowModel",
    "ScenarioStageModel",
    "ScenarioAgentModel",
    "ScenarioWorkItemModel",
    "ScenarioBoardModel",
    "ScenarioBoardItemPlacementModel",
]


def __getattr__(name: str) -> Any:
    """Lazy import bootstrap and seeding components to avoid circular imports."""
    if name == "SimulationApplicationBootstrap":
        from .bootstrap import SimulationApplicationBootstrap
        return SimulationApplicationBootstrap
    elif name == "SimulationAdapters":
        from .bootstrap import SimulationAdapters
        return SimulationAdapters
    elif name == "SimulationServices":
        from .bootstrap import SimulationServices
        return SimulationServices
    elif name == "SimulationPorts":
        from .bootstrap import SimulationPorts
        return SimulationPorts
    elif name == "SimulationInfrastructure":
        from .bootstrap import SimulationInfrastructure
        return SimulationInfrastructure
    elif name == "SimulationDataSeeder":
        from .seeding import SimulationDataSeeder
        return SimulationDataSeeder
    elif name == "CreatedItems":
        from .seeding import CreatedItems
        return CreatedItems
    message = f"module {__name__!r} has no attribute {name!r}"
    raise AttributeError(message)
