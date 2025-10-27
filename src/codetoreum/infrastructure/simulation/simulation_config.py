"""Simulation configuration for test scenarios."""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional


@dataclass
class AgentBehaviorConfig:
    """Configuration for agent behavior in simulation."""

    agent_id: str
    # Execution delay in seconds
    execution_delay: float = 0.1
    # Success rate (0.0 to 1.0)
    success_rate: float = 1.0
    # Response templates based on context patterns
    response_patterns: Dict[str, str] = field(default_factory=dict)
    # Simulated token usage
    token_usage: Dict[str, int] = field(default_factory=lambda: {
        "input": 100,
        "output": 50,
    })


@dataclass
class ContainerBehaviorConfig:
    """Configuration for container behavior in simulation."""

    # Default exit code
    default_exit_code: int = 0
    # Execution delay in seconds
    execution_delay: float = 0.1
    # Command-specific exit codes
    command_exit_codes: Dict[str, int] = field(default_factory=dict)
    # Command-specific outputs
    command_outputs: Dict[str, Dict[str, str]] = field(default_factory=dict)


@dataclass
class NotificationConfig:
    """Configuration for notification behavior in simulation."""

    # Send delay in seconds
    send_delay: float = 0.01
    # Whether to simulate failures
    simulate_failures: bool = False
    # Failure rate (0.0 to 1.0)
    failure_rate: float = 0.0


@dataclass
class MetricsConfig:
    """Configuration for metrics behavior in simulation."""

    # Whether to collect metrics
    enabled: bool = True
    # Metrics to track
    tracked_metrics: List[str] = field(default_factory=lambda: [
        "workflow.stage.duration",
        "agent.execution.count",
        "agent.execution.duration",
        "review.cycle.count",
    ])


@dataclass
class TimeConfig:
    """Configuration for time behavior in simulation."""

    # Speed multiplier (how much faster than real time)
    speed_multiplier: float = 10.0
    # Starting time for simulation
    start_time: Optional[datetime] = None
    # Auto-advance clock
    auto_advance: bool = False


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
    agents: Dict[str, AgentBehaviorConfig] = field(default_factory=dict)

    # Container configuration
    container: ContainerBehaviorConfig = field(default_factory=ContainerBehaviorConfig)

    # Notification configuration
    notifications: NotificationConfig = field(default_factory=NotificationConfig)

    # Metrics configuration
    metrics: MetricsConfig = field(default_factory=MetricsConfig)

    # Additional metadata
    metadata: Dict[str, Any] = field(default_factory=dict)

    def get_agent_config(self, agent_id: str) -> AgentBehaviorConfig:
        """
        Get configuration for a specific agent.

        Args:
            agent_id: Agent identifier

        Returns:
            Agent behavior configuration (creates default if not found)
        """
        if agent_id not in self.agents:
            self.agents[agent_id] = AgentBehaviorConfig(agent_id=agent_id)
        return self.agents[agent_id]

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
            response: Response to return
        """
        config = self.get_agent_config(agent_id)
        config.response_patterns[pattern] = response

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
    ) -> "SimulationConfig":
        """
        Create a configuration optimized for fast test execution.

        Args:
            scenario_name: Name of the scenario
            speed_multiplier: How much faster than real time

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
        )

    @classmethod
    def create_realistic_config(
        cls,
        scenario_name: str,
        speed_multiplier: float = 10.0,
    ) -> "SimulationConfig":
        """
        Create a configuration that mimics realistic behavior.

        Args:
            scenario_name: Name of the scenario
            speed_multiplier: How much faster than real time

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
        )

    def to_dict(self) -> Dict[str, Any]:
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
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SimulationConfig":
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

        return cls(
            scenario_name=data["scenario_name"],
            scenario_description=data.get("scenario_description", ""),
            time=time_config,
            agents=agents,
            container=container,
            notifications=notifications,
            metrics=metrics,
            metadata=data.get("metadata", {}),
        )
