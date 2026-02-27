"""Simulation infrastructure for testing."""

from typing import TYPE_CHECKING, Any

from .causal_link_registry import CausalLinkRegistry
from .contract_test_generator import ContractTestGenerator
from .mock_tracer import (
    MockTracer,
    SpanCapture,
    SpanKind,
    SpanStatus,
    TraceContextValidator,
)
from .proportional_delay_calculator import ProportionalDelayCalculator
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

if TYPE_CHECKING:
    from .bootstrap import (
        SimulationAdapters,
        SimulationApplicationBootstrap,
        SimulationInfrastructure,
        SimulationPorts,
        SimulationServices,
    )
    from .seeding import CreatedItems, SimulationDataSeeder

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
    # Components (new in #346)
    "CausalLinkRegistry",
    "ProportionalDelayCalculator",
    "ContractTestGenerator",
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
    if name == "SimulationAdapters":
        from .bootstrap import SimulationAdapters

        return SimulationAdapters
    if name == "SimulationServices":
        from .bootstrap import SimulationServices

        return SimulationServices
    if name == "SimulationPorts":
        from .bootstrap import SimulationPorts

        return SimulationPorts
    if name == "SimulationInfrastructure":
        from .bootstrap import SimulationInfrastructure

        return SimulationInfrastructure
    if name == "SimulationDataSeeder":
        from .seeding import SimulationDataSeeder

        return SimulationDataSeeder
    if name == "CreatedItems":
        from .seeding import CreatedItems

        return CreatedItems
    message = f"module {__name__!r} has no attribute {name!r}"
    raise AttributeError(message)
