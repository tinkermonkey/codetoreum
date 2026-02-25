"""Simulation infrastructure for testing."""
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


def __getattr__(name: str) -> object:
    """Lazy import bootstrap and seeding components to avoid circular imports."""
    if name in (
        "SimulationApplicationBootstrap",
        "SimulationAdapters",
        "SimulationServices",
        "SimulationPorts",
        "SimulationInfrastructure",
    ):
        from .bootstrap import (
            SimulationAdapters,
            SimulationApplicationBootstrap,
            SimulationInfrastructure,
            SimulationPorts,
            SimulationServices,
        )

        return {
            "SimulationApplicationBootstrap": SimulationApplicationBootstrap,
            "SimulationAdapters": SimulationAdapters,
            "SimulationServices": SimulationServices,
            "SimulationPorts": SimulationPorts,
            "SimulationInfrastructure": SimulationInfrastructure,
        }[name]
    elif name in ("SimulationDataSeeder", "CreatedItems"):
        from .seeding import CreatedItems, SimulationDataSeeder

        return {
            "SimulationDataSeeder": SimulationDataSeeder,
            "CreatedItems": CreatedItems,
        }[name]
    message = f"module {__name__!r} has no attribute {name!r}"
    raise AttributeError(message)
