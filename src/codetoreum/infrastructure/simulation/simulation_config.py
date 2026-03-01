"""Simulation configuration for test scenarios."""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any

import yaml


class FidelityLevel(Enum):
    """Fidelity levels for simulation testing.

    LOW: Preconfigured outcomes, zero/minimal delays, no causal linking
         Speed: 100x+ faster
         Use case: Unit tests, fast regression

    MEDIUM: Causal linking via events, proportional delays, realistic state propagation
            Speed: 10-50x faster
            Use case: Integration tests, workflow validation

    HIGH: Full simulation fidelity, realistic timing with jitter, probabilistic failures
          Speed: 1-5x faster
          Use case: Performance testing, chaos engineering
    """

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


@dataclass
class AgentBehaviorConfig:
    """Configuration for agent behavior in simulation."""

    agent_id: str
    # Execution delay in seconds
    execution_delay: float = 0.1
    # Success rate (0.0 to 1.0)
    success_rate: float = 1.0
    # Response templates based on context patterns
    response_patterns: dict[str, str] = field(default_factory=dict)
    # Simulated token usage
    token_usage: dict[str, int] = field(
        default_factory=lambda: {
            "input": 100,
            "output": 50,
        }
    )

    def __post_init__(self) -> None:
        """Validate configuration constraints."""
        if not self.agent_id:
            raise ValueError("agent_id cannot be empty")
        if self.execution_delay < 0:
            raise ValueError(f"execution_delay must be non-negative, got {self.execution_delay}")
        if not (0.0 <= self.success_rate <= 1.0):
            raise ValueError(f"success_rate must be between 0.0 and 1.0, got {self.success_rate}")


@dataclass
class ContainerBehaviorConfig:
    """Configuration for container behavior in simulation."""

    # Default exit code
    default_exit_code: int = 0
    # Execution delay in seconds
    execution_delay: float = 0.1
    # Command-specific exit codes
    command_exit_codes: dict[str, int] = field(default_factory=dict)
    # Command-specific outputs
    command_outputs: dict[str, dict[str, str]] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """Validate configuration constraints."""
        if self.execution_delay < 0:
            raise ValueError(f"execution_delay must be non-negative, got {self.execution_delay}")


@dataclass
class NotificationConfig:
    """Configuration for notification behavior in simulation."""

    # Send delay in seconds
    send_delay: float = 0.01
    # Whether to simulate failures
    simulate_failures: bool = False
    # Failure rate (0.0 to 1.0)
    failure_rate: float = 0.0

    def __post_init__(self) -> None:
        """Validate configuration constraints."""
        if self.send_delay < 0:
            raise ValueError(f"send_delay must be non-negative, got {self.send_delay}")
        if not (0.0 <= self.failure_rate <= 1.0):
            raise ValueError(f"failure_rate must be between 0.0 and 1.0, got {self.failure_rate}")


@dataclass
class MetricsConfig:
    """Configuration for metrics behavior in simulation."""

    # Whether to collect metrics
    enabled: bool = True
    # Metrics to track
    tracked_metrics: list[str] = field(
        default_factory=lambda: [
            "workflow.stage.duration",
            "agent.execution.count",
            "agent.execution.duration",
            "review.cycle.count",
        ]
    )


@dataclass
class TimeConfig:
    """Configuration for time behavior in simulation."""

    # Speed multiplier (how much faster than real time)
    speed_multiplier: float = 10.0
    # Starting time for simulation
    start_time: datetime | None = None
    # Auto-advance clock
    auto_advance: bool = False

    def __post_init__(self) -> None:
        """Validate configuration constraints."""
        if self.speed_multiplier <= 0:
            raise ValueError(f"speed_multiplier must be positive, got {self.speed_multiplier}")


@dataclass
class SimulationConfig:
    """
    Complete configuration for a simulation scenario.

    This defines how all mock adapters should behave during a simulation test.
    """

    # Scenario identification
    scenario_name: str
    scenario_description: str = ""

    # Time configuration
    time: TimeConfig = field(default_factory=TimeConfig)

    # Agent configurations by agent ID
    agents: dict[str, AgentBehaviorConfig] = field(default_factory=dict)

    # Container configuration
    container: ContainerBehaviorConfig = field(default_factory=ContainerBehaviorConfig)

    # Notification configuration
    notifications: NotificationConfig = field(default_factory=NotificationConfig)

    # Metrics configuration
    metrics: MetricsConfig = field(default_factory=MetricsConfig)

    # Fidelity level (determines timing accuracy and realism)
    fidelity_level: FidelityLevel = FidelityLevel.LOW

    # Proportional timing parameters (used when fidelity >= MEDIUM)
    ms_per_token: float = 50.0  # LLM latency
    ms_per_file_operation: float = 10.0  # Container/repo file operations
    ms_per_event: float = 1.0  # Event processing latency per (event * handler)
    event_handler_count: int = (
        1  # Number of handlers processing each event (for latency: event_count * handler_count * ms_per_event)
    )

    # Additional metadata
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """Validate configuration constraints."""
        if not self.scenario_name:
            raise ValueError("scenario_name cannot be empty")
        if self.ms_per_token < 0:
            raise ValueError(f"ms_per_token must be non-negative, got {self.ms_per_token}")
        if self.ms_per_file_operation < 0:
            raise ValueError(f"ms_per_file_operation must be non-negative, got {self.ms_per_file_operation}")
        if self.ms_per_event < 0:
            raise ValueError(f"ms_per_event must be non-negative, got {self.ms_per_event}")
        if self.event_handler_count < 1:
            raise ValueError(f"event_handler_count must be at least 1, got {self.event_handler_count}")

    def get_agent_config(self, agent_id: str) -> AgentBehaviorConfig:
        """
        Get configuration for a specific agent.

        This method does not mutate state. If no configuration exists for the agent,
        it returns a default configuration without modifying self.agents.

        Args:
            agent_id: Agent identifier

        Returns:
            Agent behavior configuration (default if not found)
        """
        return self.agents.get(agent_id) or AgentBehaviorConfig(agent_id=agent_id)

    def set_agent_config(self, agent_id: str, config: AgentBehaviorConfig) -> None:
        """
        Set configuration for a specific agent.

        Args:
            agent_id: Agent identifier
            config: Agent behavior configuration
        """
        if config.agent_id != agent_id:
            raise ValueError(f"config.agent_id ({config.agent_id}) does not match agent_id ({agent_id})")
        self.agents[agent_id] = config

    def add_agent_response_pattern(
        self,
        agent_id: str,
        pattern: str,
        response: str,
    ) -> None:
        """
        Add a response pattern for an agent.

        Args:
            agent_id: Agent identifier
            pattern: Regex pattern to match
            response: Response to return (can use metadata variables via {key})
        """
        # Get or create agent config
        if agent_id not in self.agents:
            self.agents[agent_id] = AgentBehaviorConfig(agent_id=agent_id)
        config = self.agents[agent_id]
        # Support template variables from metadata
        formatted_response = response.format(**self.metadata) if self.metadata else response
        config.response_patterns[pattern] = formatted_response

    def set_container_command_result(
        self,
        command: str,
        exit_code: int,
        stdout: str = "",
        stderr: str = "",
    ) -> None:
        """
        Set expected result for a container command.

        Args:
            command: Command string
            exit_code: Exit code to return
            stdout: Standard output
            stderr: Standard error
        """
        self.container.command_exit_codes[command] = exit_code
        self.container.command_outputs[command] = {
            "stdout": stdout,
            "stderr": stderr,
        }

    @classmethod
    def create_fast_config(
        cls,
        scenario_name: str,
        speed_multiplier: float = 100.0,
        fidelity_level: FidelityLevel = FidelityLevel.LOW,
        ms_per_token: float = 50.0,
        ms_per_file_operation: float = 10.0,
        ms_per_event: float = 1.0,
        event_handler_count: int = 1,
    ) -> "SimulationConfig":
        """
        Create a configuration optimized for fast test execution.

        Args:
            scenario_name: Name of the scenario
            speed_multiplier: How much faster than real time
            fidelity_level: Fidelity level (LOW, MEDIUM, HIGH)
            ms_per_token: Milliseconds per LLM token for proportional timing
            ms_per_file_operation: Milliseconds per file operation for proportional timing
            ms_per_event: Milliseconds per event processing for proportional timing
            event_handler_count: Number of handlers processing each event

        Returns:
            SimulationConfig optimized for speed
        """
        return cls(
            scenario_name=scenario_name,
            time=TimeConfig(
                speed_multiplier=speed_multiplier,
                auto_advance=False,
            ),
            agents={},
            container=ContainerBehaviorConfig(
                execution_delay=0.0,
            ),
            notifications=NotificationConfig(
                send_delay=0.0,
            ),
            fidelity_level=fidelity_level,
            ms_per_token=ms_per_token,
            ms_per_file_operation=ms_per_file_operation,
            ms_per_event=ms_per_event,
            event_handler_count=event_handler_count,
        )

    @classmethod
    def create_realistic_config(
        cls,
        scenario_name: str,
        speed_multiplier: float = 10.0,
        fidelity_level: FidelityLevel = FidelityLevel.MEDIUM,
        ms_per_token: float = 50.0,
        ms_per_file_operation: float = 10.0,
        ms_per_event: float = 1.0,
        event_handler_count: int = 1,
    ) -> "SimulationConfig":
        """
        Create a configuration that mimics realistic behavior.

        Args:
            scenario_name: Name of the scenario
            speed_multiplier: How much faster than real time
            fidelity_level: Fidelity level (LOW, MEDIUM, HIGH)
            ms_per_token: Milliseconds per LLM token for proportional timing
            ms_per_file_operation: Milliseconds per file operation for proportional timing
            ms_per_event: Milliseconds per event processing for proportional timing
            event_handler_count: Number of handlers processing each event

        Returns:
            SimulationConfig with realistic timing
        """
        return cls(
            scenario_name=scenario_name,
            time=TimeConfig(
                speed_multiplier=speed_multiplier,
                auto_advance=False,
            ),
            agents={},
            container=ContainerBehaviorConfig(
                execution_delay=0.5,  # 5 seconds at 10x speed
            ),
            notifications=NotificationConfig(
                send_delay=0.01,
            ),
            fidelity_level=fidelity_level,
            ms_per_token=ms_per_token,
            ms_per_file_operation=ms_per_file_operation,
            ms_per_event=ms_per_event,
            event_handler_count=event_handler_count,
        )

    @classmethod
    def create_high_fidelity_config(
        cls,
        scenario_name: str,
        speed_multiplier: float = 5.0,
        ms_per_token: float = 50.0,
        ms_per_file_operation: float = 10.0,
        ms_per_event: float = 1.0,
        event_handler_count: int = 1,
    ) -> "SimulationConfig":
        """
        Create a configuration with high fidelity simulation.

        HIGH fidelity includes:
        - Realistic timing with jitter (±20% randomness)
        - Probabilistic failures (agent timeouts, container failures)
        - Slower execution than MEDIUM (5x faster than real-time)

        Use case: Performance testing, chaos engineering, failure scenarios

        Args:
            scenario_name: Name of the scenario
            speed_multiplier: How much faster than real time (default 5x)
            ms_per_token: Milliseconds per LLM token for proportional timing
            ms_per_file_operation: Milliseconds per file operation for proportional timing
            ms_per_event: Milliseconds per event processing for proportional timing
            event_handler_count: Number of handlers processing each event

        Returns:
            SimulationConfig with HIGH fidelity
        """
        return cls(
            scenario_name=scenario_name,
            time=TimeConfig(
                speed_multiplier=speed_multiplier,
                auto_advance=False,
            ),
            agents={},
            container=ContainerBehaviorConfig(
                execution_delay=1.0,  # 5 seconds at 5x speed
            ),
            notifications=NotificationConfig(
                send_delay=0.01,
                simulate_failures=True,
                failure_rate=0.05,  # 5% failure rate
            ),
            fidelity_level=FidelityLevel.HIGH,
            ms_per_token=ms_per_token,
            ms_per_file_operation=ms_per_file_operation,
            ms_per_event=ms_per_event,
            event_handler_count=event_handler_count,
        )

    def to_dict(self) -> dict[str, Any]:
        """
        Convert configuration to dictionary.

        Returns:
            Dictionary representation
        """
        return {
            "scenario_name": self.scenario_name,
            "scenario_description": self.scenario_description,
            "time": {
                "speed_multiplier": self.time.speed_multiplier,
                "start_time": self.time.start_time.isoformat() if self.time.start_time else None,
                "auto_advance": self.time.auto_advance,
            },
            "agents": {
                agent_id: {
                    "execution_delay": config.execution_delay,
                    "success_rate": config.success_rate,
                    "response_patterns": config.response_patterns,
                    "token_usage": config.token_usage,
                }
                for agent_id, config in self.agents.items()
            },
            "container": {
                "default_exit_code": self.container.default_exit_code,
                "execution_delay": self.container.execution_delay,
                "command_exit_codes": self.container.command_exit_codes,
                "command_outputs": self.container.command_outputs,
            },
            "notifications": {
                "send_delay": self.notifications.send_delay,
                "simulate_failures": self.notifications.simulate_failures,
                "failure_rate": self.notifications.failure_rate,
            },
            "metrics": {
                "enabled": self.metrics.enabled,
                "tracked_metrics": self.metrics.tracked_metrics,
            },
            "fidelity_level": self.fidelity_level.value,
            "ms_per_token": self.ms_per_token,
            "ms_per_file_operation": self.ms_per_file_operation,
            "ms_per_event": self.ms_per_event,
            "event_handler_count": self.event_handler_count,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "SimulationConfig":
        """
        Create configuration from dictionary.

        Args:
            data: Dictionary data

        Returns:
            SimulationConfig instance
        """
        time_data = data.get("time", {})
        start_time = None
        if time_data.get("start_time"):
            start_time = datetime.fromisoformat(time_data["start_time"])

        time_config = TimeConfig(
            speed_multiplier=time_data.get("speed_multiplier", 10.0),
            start_time=start_time,
            auto_advance=time_data.get("auto_advance", False),
        )

        agents = {}
        for agent_id, agent_data in data.get("agents", {}).items():
            agents[agent_id] = AgentBehaviorConfig(
                agent_id=agent_id,
                execution_delay=agent_data.get("execution_delay", 0.1),
                success_rate=agent_data.get("success_rate", 1.0),
                response_patterns=agent_data.get("response_patterns", {}),
                token_usage=agent_data.get("token_usage", {"input": 100, "output": 50}),
            )

        container_data = data.get("container", {})
        container = ContainerBehaviorConfig(
            default_exit_code=container_data.get("default_exit_code", 0),
            execution_delay=container_data.get("execution_delay", 0.1),
            command_exit_codes=container_data.get("command_exit_codes", {}),
            command_outputs=container_data.get("command_outputs", {}),
        )

        notif_data = data.get("notifications", {})
        notifications = NotificationConfig(
            send_delay=notif_data.get("send_delay", 0.01),
            simulate_failures=notif_data.get("simulate_failures", False),
            failure_rate=notif_data.get("failure_rate", 0.0),
        )

        metrics_data = data.get("metrics", {})
        metrics = MetricsConfig(
            enabled=metrics_data.get("enabled", True),
            tracked_metrics=metrics_data.get("tracked_metrics", []),
        )

        fidelity_str = data.get("fidelity_level", "low")
        fidelity_level = FidelityLevel(fidelity_str) if isinstance(fidelity_str, str) else fidelity_str

        return cls(
            scenario_name=data["scenario_name"],
            scenario_description=data.get("scenario_description", ""),
            time=time_config,
            agents=agents,
            container=container,
            notifications=notifications,
            metrics=metrics,
            fidelity_level=fidelity_level,
            ms_per_token=data.get("ms_per_token", 50.0),
            ms_per_file_operation=data.get("ms_per_file_operation", 10.0),
            ms_per_event=data.get("ms_per_event", 1.0),
            event_handler_count=data.get("event_handler_count", 1),
            metadata=data.get("metadata", {}),
        )

    @classmethod
    def from_yaml(cls, file_path: str | Path) -> "SimulationConfig":
        """
        Load simulation configuration from YAML file.

        This method loads a scenario configuration file and creates a SimulationConfig
        object. The YAML file should contain simulation behavior settings (time, agents,
        container, etc.) but NOT the data seeding definitions (projects, workflows, etc.)
        which are handled by scenario_models.ScenarioModel.

        Args:
            file_path: Path to YAML scenario file

        Returns:
            SimulationConfig instance

        Raises:
            FileNotFoundError: If file doesn't exist
            yaml.YAMLError: If YAML is malformed
            ValueError: If required fields are missing
        """
        file_path = Path(file_path)

        if not file_path.exists():
            message = f"Scenario file not found: {file_path}"
            raise FileNotFoundError(message)

        with open(file_path) as f:
            data = yaml.safe_load(f)

        if not data:
            message = f"Empty YAML file: {file_path}"
            raise ValueError(message)

        # Extract scenario name (required)
        scenario_name = data.get("name")
        if not scenario_name:
            message = "Scenario file must contain 'name' field"
            raise ValueError(message)

        # Build config using from_dict for consistency
        config_dict = {
            "scenario_name": scenario_name,
            "scenario_description": data.get("description", ""),
            "time": {
                "speed_multiplier": data.get("speed_multiplier", 10.0),
                "auto_advance": data.get("auto_advance", False),
            },
            "agents": {},
            "container": data.get("container", {}),
            "notifications": data.get("notifications", {}),
            "metrics": data.get("metrics", {}),
            "fidelity_level": data.get("fidelity_level", "low"),
            "ms_per_token": data.get("ms_per_token", 50.0),
            "ms_per_file_operation": data.get("ms_per_file_operation", 10.0),
            "ms_per_event": data.get("ms_per_event", 1.0),
            "event_handler_count": data.get("event_handler_count", 1),
            "metadata": data.get("metadata", {}),
        }

        # Add YAML file path to metadata for reference
        config_dict["metadata"]["yaml_file"] = str(file_path)

        return cls.from_dict(config_dict)
