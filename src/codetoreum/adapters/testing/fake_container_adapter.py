"""Fake container adapter for testing."""

import asyncio
import logging
import re
import threading
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any
from uuid import uuid4

from codetoreum.domain.events import (
    ContainerExecutionCompletedEvent,
    now_iso,
)
from codetoreum.infrastructure.event_bus import EventBus
from codetoreum.ports.exceptions import (
    ContainerError,
    ContainerNotRunningError,
    ResourceNotFoundError,
    ValidationError,
)
from codetoreum.ports.output.container import (
    ContainerHealthStatus,
    ContainerResult,
    ContainerStatus,
    IContainer,
)
from codetoreum.ports.output.event_emitter import IEventEmitter

if TYPE_CHECKING:
    from codetoreum.infrastructure.simulation.proportional_delay_calculator import (
        ProportionalDelayCalculator,
    )
    from codetoreum.infrastructure.simulation.simulation_clock import SimulationClock
    from codetoreum.infrastructure.simulation.simulation_config import SimulationConfig

logger = logging.getLogger(__name__)


@dataclass
class CommandExecution:
    """Record of a single command execution in a container."""

    timestamp: datetime
    command: str
    exit_code: int
    stdout: str
    stderr: str
    duration_ms: float


class FakeContainerAdapter(IContainer):
    """
    Fake container implementation for testing.

    Simulates container execution without Docker. Returns predefined
    results based on image/command patterns.

    This adapter is thread-safe for concurrent test execution. All shared
    state modifications are protected by a lock.

    Attributes:
        _default_exit_code: Default exit code for executions
        _default_stdout: Default stdout content
        _default_stderr: Default stderr content
        _execution_delay: Simulated execution delay
        _max_containers: Maximum number of containers allowed
    """

    # Default images that are always available without explicit pull
    DEFAULT_SEEDED_IMAGES = {
        "ubuntu:latest",
        "ubuntu:22.04",
        "python:3.11",
        "python:3.10",
        "alpine:latest",
    }

    def __init__(
        self,
        default_exit_code: int = 0,
        default_stdout: str = "Fake container output",
        default_stderr: str = "",
        execution_delay: float = 0.0,
        max_containers: int = 100,
        event_emitter: IEventEmitter | None = None,
        event_bus: EventBus | None = None,
        config: "SimulationConfig | None" = None,
        clock: "SimulationClock | None" = None,
        llm_provider: "object | None" = None,
    ):
        """
        Initialize the fake container adapter.

        Args:
            default_exit_code: Default exit code for executions
            default_stdout: Default stdout content
            default_stderr: Default stderr content
            execution_delay: Simulated execution delay in seconds
            max_containers: Maximum number of containers allowed (default: 100)
            event_emitter: Optional event emitter for domain events
            event_bus: Optional event bus for event subscriptions
            config: Optional SimulationConfig for fidelity-based timing
            clock: Optional SimulationClock for time manipulation
            llm_provider: Optional LLM provider for command execution delegation

        Raises:
            ValidationError: If parameters are invalid
        """
        if execution_delay < 0:
            msg = "Execution delay cannot be negative"
            raise ValidationError(msg)
        if max_containers <= 0:
            msg = "Max containers must be positive"
            raise ValidationError(msg)

        self._default_exit_code = default_exit_code
        self._default_stdout = default_stdout
        self._default_stderr = default_stderr
        self._execution_delay = execution_delay
        self._max_containers = max_containers
        self._event_emitter = event_emitter
        self._event_bus = event_bus
        self._config = config
        self._clock = clock
        self._llm_provider = llm_provider

        # Lazy-load delay calculator to avoid circular import
        self._delay_calculator: ProportionalDelayCalculator | None = None

        # Container storage
        self._containers: dict[str, dict[str, Any]] = {}

        # Predefined results for specific commands
        self._command_results: dict[str, ContainerResult] = {}

        # Execution history (old format for backwards compatibility)
        self._execution_history: list[dict[str, Any]] = []

        # Command execution history by container ID
        self._command_history: dict[str, list[CommandExecution]] = {}

        # Virtual filesystem tracking (container_id -> {file_path -> content})
        self._virtual_filesystems: dict[str, dict[str, str]] = {}

        # Host-side files for copy operations (destination_path -> content)
        self._host_files: dict[str, str] = {}

        # Pulled images tracking (set of "image:tag" strings)
        self._pulled_images: set[str] = self.DEFAULT_SEEDED_IMAGES.copy()

        # Thread safety
        self._lock = threading.Lock()

        # Counter for probabilistic failures (deterministic for reproducibility)
        self._execution_counter = 0

    def set_command_result(
        self,
        command_pattern: str,
        exit_code: int,
        stdout: str = "",
        stderr: str = "",
    ) -> None:
        """
        Set predefined result for a command pattern.

        Args:
            command_pattern: Pattern to match (exact match on first command word)
            exit_code: Exit code to return
            stdout: Stdout content
            stderr: Stderr content

        Raises:
            ValidationError: If command_pattern is empty
        """
        if not command_pattern:
            msg = "Command pattern cannot be empty"
            raise ValidationError(msg)

        container_id = f"fake-{uuid4()}"
        with self._lock:
            self._command_results[command_pattern] = ContainerResult(
                exit_code=exit_code,
                stdout=stdout,
                stderr=stderr,
                duration_ms=int(self._execution_delay * 1000),
                container_id=container_id,
            )

    def _calculate_delay_seconds(self, command: str) -> float:
        """
        Calculate delay based on fidelity level and command complexity.

        Uses ProportionalDelayCalculator for centralized fidelity-aware timing.
        Falls back to fixed execution_delay if no config provided.

        Args:
            command: Command string to analyze

        Returns:
            Delay in seconds
        """
        if not self._config:
            return self._execution_delay

        if self._delay_calculator is None:
            from codetoreum.infrastructure.simulation.proportional_delay_calculator import (
                ProportionalDelayCalculator,
            )

            self._delay_calculator = ProportionalDelayCalculator(self._config)
        return self._delay_calculator.calculate_container_delay(command)

    def _should_fail_for_high_fidelity(self) -> bool:
        """
        Determine if execution should fail based on HIGH fidelity probabilistic failures.

        Uses counter-based approach for reproducibility in tests (not random).
        Only applies to HIGH fidelity level.
        NOTE: Caller must hold self._lock before calling this method.

        Returns:
            True if execution should fail, False otherwise
        """
        if not self._config:
            return False

        from codetoreum.infrastructure.simulation.simulation_config import FidelityLevel

        if self._config.fidelity_level != FidelityLevel.HIGH:
            return False

        # Counter-based: fail approximately every 20 executions (5% failure rate)
        # This is deterministic for reproducibility
        # NOTE: Assumes caller holds self._lock to avoid deadlock with reentrant lock
        self._execution_counter += 1
        should_fail = self._execution_counter % 20 == 0

        return should_fail

    async def _get_result_for_command_from_llm(
        self,
        command: list[str],
        container_id: str,
    ) -> ContainerResult:
        """
        Get result for a command by delegating to LLM provider.

        Constructs a prompt from the command and uses the LLM to generate
        realistic command output (stdout) and exit code.

        Args:
            command: Command list
            container_id: Container ID

        Returns:
            Container result with LLM-generated output
        """
        try:
            # Create a prompt asking the LLM to simulate command execution
            command_str = " ".join(command)
            prompt = (
                f"Simulate executing the following shell command and provide the output.\n"
                f"Command: {command_str}\n"
                f"Provide just the stdout output, no explanation."
            )

            # Execute via LLM provider
            result = await self._llm_provider.execute(prompt)

            # Use the LLM response as stdout
            stdout = result.content if result.content else ""

            return ContainerResult(
                exit_code=self._default_exit_code,
                stdout=stdout,
                stderr="",
                duration_ms=result.duration_ms,
                container_id=container_id,
            )
        except Exception:
            # If LLM delegation fails, fall back to predefined results
            logger.warning(
                "LLM delegation failed for command execution, falling back to predefined results",
                exc_info=True,
                extra={"command": " ".join(command), "container_id": container_id},
            )
            return self._get_result_for_command_predefined(command, container_id)

    def _get_result_for_command_predefined(
        self,
        command: list[str],
        container_id: str,
    ) -> ContainerResult:
        """
        Get result for a command from predefined patterns.

        For HIGH fidelity, may return a failure (exit code 1) based on
        probabilistic logic (~5% failure rate).

        Args:
            command: Command list
            container_id: Container ID

        Returns:
            Container result (either pattern-matched or default)
        """
        with self._lock:
            if command:
                # Check for exact command match
                cmd_key = " ".join(command)
                if cmd_key in self._command_results:
                    result = self._command_results[cmd_key]
                    return ContainerResult(
                        exit_code=result.exit_code,
                        stdout=result.stdout,
                        stderr=result.stderr,
                        duration_ms=result.duration_ms,
                        container_id=container_id,
                    )

                # Check for first word match
                first_word = command[0]
                if first_word in self._command_results:
                    result = self._command_results[first_word]
                    return ContainerResult(
                        exit_code=result.exit_code,
                        stdout=result.stdout,
                        stderr=result.stderr,
                        duration_ms=result.duration_ms,
                        container_id=container_id,
                    )

            # Apply probabilistic failures for HIGH fidelity
            if self._should_fail_for_high_fidelity():
                return ContainerResult(
                    exit_code=1,
                    stdout="",
                    stderr="Container execution failed (HIGH fidelity probabilistic failure)",
                    duration_ms=int(self._execution_delay * 1000),
                    container_id=container_id,
                )

            # Return default
            return ContainerResult(
                exit_code=self._default_exit_code,
                stdout=self._default_stdout,
                stderr=self._default_stderr,
                duration_ms=int(self._execution_delay * 1000),
                container_id=container_id,
            )

    async def run(
        self,
        image: str,
        command: list[str] | tuple[str, ...],
        volumes: dict[str, str] | Mapping[str, str],
        environment: dict[str, str] | Mapping[str, str],
        timeout: int = 300,
        stream_callback: Callable | None = None,
    ) -> ContainerResult:
        """
        Run a command in a container.

        Args:
            image: Container image name (required)
            command: Command to execute (required, non-empty list)
            volumes: Volume mounts
            environment: Environment variables
            timeout: Execution timeout in seconds
            stream_callback: Optional callback for streaming output

        Returns:
            Container execution result

        Raises:
            ValidationError: If image or command is invalid
        """
        if not image or not image.strip():
            msg = "Image name is required"
            raise ValidationError(msg)

        if not command or len(command) == 0:
            msg = "Command is required"
            raise ValidationError(msg)

        # Create container
        container_id = f"fake-{uuid4().hex[:12]}"

        # Initialize virtual filesystem for this container
        with self._lock:
            self._virtual_filesystems[container_id] = {}
            self._command_history[container_id] = []

        # Track start time for duration calculation
        start_time = datetime.now(UTC)

        # Calculate and apply delay based on fidelity level
        command_str = " ".join(command)
        delay_seconds = self._calculate_delay_seconds(command_str)

        # Apply delay using clock if available, otherwise use asyncio.sleep
        if delay_seconds > 0:
            if self._clock:
                # Use simulated clock for time manipulation support
                await self._clock.sleep(delay_seconds)
            else:
                # Fall back to asyncio.sleep for real-time execution
                await asyncio.sleep(delay_seconds)

        # Get result (delegate to LLM if provider available, otherwise use predefined results)
        if self._llm_provider:
            result = await self._get_result_for_command_from_llm(command, container_id)
        else:
            result = self._get_result_for_command_predefined(command, container_id)

        # Calculate actual duration
        end_time = datetime.now(UTC)
        duration_ms = int((end_time - start_time).total_seconds() * 1000)

        # Create CommandExecution record
        execution = CommandExecution(
            timestamp=start_time,
            command=command_str,
            exit_code=result.exit_code,
            stdout=result.stdout,
            stderr=result.stderr,
            duration_ms=duration_ms,
        )

        # Record execution in command history and legacy history format
        with self._lock:
            self._command_history[container_id].append(execution)
            self._execution_history.append(
                {
                    "container_id": container_id,
                    "image": image,
                    "command": command,
                    "volumes": volumes,
                    "environment": environment,
                    "timeout": timeout,
                    "result": result,
                    "executed_at": start_time,
                }
            )

        # Simulate streaming if callback provided
        if stream_callback:
            if result.stdout:
                for line in result.stdout.split("\n"):
                    await stream_callback(line + "\n")

        # Emit ContainerExecutionCompletedEvent with output files
        output_files = self._get_output_files(container_id)
        if self._event_emitter:
            event = ContainerExecutionCompletedEvent(
                type="container.execution_completed",
                timestamp=now_iso(),
                source="fake_container",
                container_id=container_id,
                command=" ".join(command),
                exit_code=result.exit_code,
                output_files=tuple(output_files),
                project_id=environment.get("PROJECT_ID"),
            )
            self._event_emitter.emit(event)

        return result

    async def create(
        self,
        image: str,
        name: str | None = None,
        command: list[str] | tuple[str, ...] | None = None,
        volumes: dict[str, str] | Mapping[str, str] | None = None,
        environment: dict[str, str] | Mapping[str, str] | None = None,
        working_dir: str | None = None,
        user: str | None = None,
        network: str | None = None,
        labels: dict[str, str] | None = None,
    ) -> str:
        """
        Create a container without starting it.

        Args:
            image: Container image name (required)
            name: Optional container name
            command: Optional command
            volumes: Optional volume mounts
            environment: Optional environment variables
            working_dir: Optional working directory
            user: Optional user
            network: Optional network name
            labels: Optional labels

        Returns:
            Container ID

        Raises:
            ValidationError: If image is invalid or max containers exceeded
        """
        if not image or not image.strip():
            msg = "Image name is required"
            raise ValidationError(msg)

        with self._lock:
            if len(self._containers) >= self._max_containers:
                msg = f"Maximum container limit ({self._max_containers}) reached"
                raise ValidationError(msg)

            # Validate container name format if provided
            if name:
                if not re.match(r"^[a-zA-Z0-9][a-zA-Z0-9_.-]*$", name):
                    msg = f"Invalid container name format: '{name}'"
                    raise ValidationError(msg)

            container_id = name or f"fake-{uuid4().hex[:12]}"

            self._containers[container_id] = {
                "id": container_id,
                "image": image,
                "command": command,
                "volumes": volumes or {},
                "environment": environment or {},
                "working_dir": working_dir,
                "user": user,
                "network": network,
                "labels": labels or {},
                "status": "exited",
                "created_at": datetime.now(UTC),
                "started_at": None,
                "finished_at": None,
                "exit_code": None,
            }

            # Initialize virtual filesystem for this container
            self._virtual_filesystems[container_id] = {}
            self._command_history[container_id] = []

            return container_id

    async def start(self, container_id: str) -> None:
        """
        Start a container.

        Args:
            container_id: Container ID

        Raises:
            ResourceNotFoundError: If container does not exist
        """
        if not container_id:
            msg = "Container ID cannot be empty"
            raise ValidationError(msg)

        with self._lock:
            if container_id not in self._containers:
                msg = "Container"
                raise ResourceNotFoundError(msg, container_id)

            container = self._containers[container_id]
            container["status"] = "running"
            container["started_at"] = datetime.now(UTC)

    async def stop(self, container_id: str, timeout: int = 10) -> None:
        """
        Stop a container.

        Args:
            container_id: Container ID
            timeout: Stop timeout in seconds

        Raises:
            ResourceNotFoundError: If container does not exist
        """
        if not container_id:
            msg = "Container ID cannot be empty"
            raise ValidationError(msg)

        with self._lock:
            if container_id not in self._containers:
                msg = "Container"
                raise ResourceNotFoundError(msg, container_id)

            container = self._containers[container_id]
            container["status"] = "exited"
            container["finished_at"] = datetime.now(UTC)
            container["exit_code"] = 0

    async def remove(self, container_id: str, force: bool = False) -> None:
        """
        Remove a container.

        Args:
            container_id: Container ID
            force: Force removal even if running

        Raises:
            ResourceNotFoundError: If container does not exist
            ContainerError: If container is running and force=False
        """
        if not container_id:
            msg = "Container ID cannot be empty"
            raise ValidationError(msg)

        with self._lock:
            if container_id not in self._containers:
                msg = "Container"
                raise ResourceNotFoundError(msg, container_id)

            container = self._containers[container_id]

            # If force=False, don't allow removal of running containers
            if not force and container["status"] == "running":
                msg = f"Cannot remove running container '{container_id}' without force=True"
                raise ContainerError(msg)

            del self._containers[container_id]
            # Clean up associated virtual filesystem and command history
            if container_id in self._virtual_filesystems:
                del self._virtual_filesystems[container_id]
            if container_id in self._command_history:
                del self._command_history[container_id]

    async def kill(self, container_id: str, signal: str = "SIGKILL") -> None:
        """
        Kill a container.

        Args:
            container_id: Container ID
            signal: Signal to send (default: SIGKILL)

        Raises:
            ResourceNotFoundError: If container does not exist
        """
        if not container_id:
            msg = "Container ID cannot be empty"
            raise ValidationError(msg)

        with self._lock:
            if container_id not in self._containers:
                msg = "Container"
                raise ResourceNotFoundError(msg, container_id)

            container = self._containers[container_id]
            container["status"] = "dead"
            container["finished_at"] = datetime.now(UTC)
            container["exit_code"] = 137 if signal == "SIGKILL" else 143

    async def logs(
        self,
        container_id: str,
        stream: bool = False,
        follow: bool = False,
        tail: int | None = None,
        since: datetime | None = None,
    ) -> Any:
        """
        Get container logs.

        Generates realistic logs from command execution history, including
        timestamps, commands, output, and exit codes.

        Args:
            container_id: Container ID
            stream: Return async generator for streaming
            follow: Follow log output
            tail: Number of lines from end
            since: Show logs since timestamp

        Returns:
            String or async generator of log lines

        Raises:
            ResourceNotFoundError: If container does not exist
        """
        if not container_id:
            msg = "Container ID cannot be empty"
            raise ValidationError(msg)

        # Check if container exists in either _containers (created) or _command_history (run)
        with self._lock:
            container_exists = container_id in self._containers or container_id in self._command_history

        if not container_exists:
            msg = "Container"
            raise ResourceNotFoundError(msg, container_id)

        # Generate logs from execution history
        log_lines = []

        with self._lock:
            history = self._command_history.get(container_id, [])

        if not history:
            # No executions, return default message with "Fake logs" for backward compatibility
            logs = f"Fake logs for container {container_id}\nLine 1\nLine 2\nLine 3"
        else:
            # Generate realistic logs from execution history
            for exec_record in history:
                # Add timestamp and command line
                log_lines.append(f"[{exec_record.timestamp.isoformat()}] $ {exec_record.command}")

                # Add stdout if present
                if exec_record.stdout:
                    log_lines.append(exec_record.stdout)

                # Add stderr if present
                if exec_record.stderr:
                    log_lines.append(f"[stderr] {exec_record.stderr}")

                # Add exit code and duration
                log_lines.append(f"[exit {exec_record.exit_code}] duration: {exec_record.duration_ms:.2f}ms")
                log_lines.append("")

            logs = "\n".join(log_lines)

        # Apply tail filter if specified
        if tail:
            lines = logs.split("\n")
            logs = "\n".join(lines[-tail:])

        # Apply since filter if specified
        if since:
            lines = logs.split("\n")
            filtered_lines = []
            for line in lines:
                # Try to parse timestamp from log line
                if line.startswith("["):
                    end_bracket = line.find("]")
                    # Only attempt parsing if bracket found at position > 0
                    if end_bracket > 0:
                        content_in_brackets = line[1:end_bracket]
                        # Skip lines with known non-timestamp bracket patterns (e.g., [stderr], [exit N])
                        is_known_pattern = content_in_brackets == "stderr" or content_in_brackets.startswith("exit ")
                        try:
                            timestamp_str = content_in_brackets
                            timestamp = datetime.fromisoformat(timestamp_str)
                            if timestamp >= since:
                                filtered_lines.append(line)
                        except ValueError:
                            # Only warn if this is not a known non-timestamp pattern
                            if not is_known_pattern:
                                logger.warning(
                                    "Failed to parse timestamp in log line",
                                    exc_info=True,
                                    extra={"line": line, "container_id": container_id},
                                )
                            # Always include the line if we've seen timestamps already
                            if filtered_lines:
                                filtered_lines.append(line)
                    # Bracket at position 0 or not found - this is not a timestamp line
                    # Include it only if we've already included timestamped lines
                    elif filtered_lines:
                        filtered_lines.append(line)
                # Non-timestamped lines are included if we have recent content
                elif filtered_lines:
                    filtered_lines.append(line)
            logs = "\n".join(filtered_lines)

        if stream:

            async def log_generator():
                for line in logs.split("\n"):
                    await asyncio.sleep(0.01)
                    yield line + "\n"

            return log_generator()

        return logs

    async def status(self, container_id: str) -> ContainerStatus:
        """
        Get container status.

        Args:
            container_id: Container ID

        Returns:
            Container status object

        Raises:
            ResourceNotFoundError: If container does not exist
        """
        if not container_id:
            msg = "Container ID cannot be empty"
            raise ValidationError(msg)

        with self._lock:
            if container_id not in self._containers:
                msg = "Container"
                raise ResourceNotFoundError(msg, container_id)

            container = self._containers[container_id]

            return ContainerStatus(
                id=container_id,
                status=container["status"],
                created_at=container["created_at"],
                started_at=container.get("started_at"),
                finished_at=container.get("finished_at"),
                exit_code=container.get("exit_code"),
            )

    async def exec(
        self,
        container_id: str,
        command: list[str] | tuple[str, ...],
        user: str | None = None,
        working_dir: str | None = None,
        environment: dict[str, str] | Mapping[str, str] | None = None,
    ) -> ContainerResult:
        """
        Execute a command in a running container.

        Args:
            container_id: Container ID
            command: Command to execute (required)
            user: Optional user
            working_dir: Optional working directory
            environment: Optional environment variables

        Returns:
            Container execution result

        Raises:
            ResourceNotFoundError: If container does not exist
            ContainerNotRunningError: If container is not running
            ValidationError: If command is empty
        """
        if not container_id:
            msg = "Container ID cannot be empty"
            raise ValidationError(msg)

        if not command:
            msg = "Command cannot be empty"
            raise ValidationError(msg)

        with self._lock:
            if container_id not in self._containers:
                msg = "Container"
                raise ResourceNotFoundError(msg, container_id)

            container = self._containers[container_id]
            if container["status"] != "running":
                msg = f"Container '{container_id}' is not running"
                raise ContainerNotRunningError(msg)

        # Track start time for duration calculation
        start_time = datetime.now(UTC)

        # Calculate and apply delay based on fidelity level
        command_str = " ".join(command)
        delay_seconds = self._calculate_delay_seconds(command_str)

        # Apply delay using clock if available, otherwise use asyncio.sleep
        if delay_seconds > 0:
            if self._clock:
                # Use simulated clock for time manipulation support
                await self._clock.sleep(delay_seconds)
            else:
                # Fall back to asyncio.sleep for real-time execution
                await asyncio.sleep(delay_seconds)

        # Get result (delegate to LLM if provider available, otherwise use predefined results)
        if self._llm_provider:
            result = await self._get_result_for_command_from_llm(command, container_id)
        else:
            result = self._get_result_for_command_predefined(command, container_id)

        # Calculate actual duration
        end_time = datetime.now(UTC)
        duration_ms = int((end_time - start_time).total_seconds() * 1000)

        # Create CommandExecution record
        execution = CommandExecution(
            timestamp=start_time,
            command=command_str,
            exit_code=result.exit_code,
            stdout=result.stdout,
            stderr=result.stderr,
            duration_ms=duration_ms,
        )

        # Record execution in command history
        # Note: The defensive check for container_id is needed because exec() can be called
        # on containers created outside the normal run() flow (e.g., in test scenarios where
        # containers are created by direct state manipulation). The run() method initializes
        # the history during creation, but we guard here for completeness.
        with self._lock:
            if container_id not in self._command_history:
                self._command_history[container_id] = []
            self._command_history[container_id].append(execution)

        return result

    async def list_containers(
        self,
        all: bool = False,
        filters: dict[str, Any] | None = None,
    ) -> list[ContainerStatus]:
        """
        List containers.

        Args:
            all: Include stopped containers
            filters: Optional filters (status, name, etc.)

        Returns:
            List of container status objects
        """
        with self._lock:
            containers = list(self._containers.values())

        if not all:
            containers = [c for c in containers if c["status"] == "running"]

        if filters:
            if "status" in filters:
                containers = [c for c in containers if c["status"] == filters["status"]]
            if "name" in filters:
                containers = [c for c in containers if c["id"] == filters["name"]]

        return [
            ContainerStatus(
                id=c["id"],
                status=c["status"],
                created_at=c["created_at"],
                started_at=c.get("started_at"),
                finished_at=c.get("finished_at"),
                exit_code=c.get("exit_code"),
            )
            for c in containers
        ]

    async def pull_image(
        self,
        image: str,
        tag: str = "latest",
        stream_callback: Callable | None = None,
    ) -> None:
        """
        Pull a container image.

        Records the pulled image reference in _pulled_images so that
        subsequent image_exists() calls return True.

        Args:
            image: Image name (required)
            tag: Image tag
            stream_callback: Optional callback for progress

        Raises:
            ValidationError: If image is invalid
        """
        if not image or not image.strip():
            msg = "Image name is required"
            raise ValidationError(msg)

        # Record the pulled image
        image_ref = f"{image}:{tag}"
        with self._lock:
            self._pulled_images.add(image_ref)

        # Simulate pull delay
        if self._execution_delay > 0:
            await asyncio.sleep(self._execution_delay)

        if stream_callback:
            await stream_callback(f"Pulling {image}:{tag}...")
            await stream_callback("Pull complete")

    async def image_exists(self, image: str, tag: str = "latest") -> bool:
        """
        Check if an image exists locally.

        Returns True only for images that have been pulled (via pull_image())
        or are pre-seeded in __init__.

        Args:
            image: Image name
            tag: Image tag

        Returns:
            True if image has been pulled or is pre-seeded, False otherwise
        """
        image_ref = f"{image}:{tag}"
        with self._lock:
            return image_ref in self._pulled_images

    async def inspect(self, container_id: str) -> dict[str, Any]:
        """
        Get detailed container information.

        Args:
            container_id: Container ID

        Returns:
            Container details dictionary

        Raises:
            ResourceNotFoundError: If container does not exist
        """
        if not container_id:
            msg = "Container ID cannot be empty"
            raise ValidationError(msg)

        with self._lock:
            if container_id not in self._containers:
                msg = "Container"
                raise ResourceNotFoundError(msg, container_id)

            return self._containers[container_id].copy()

    async def wait(
        self,
        container_id: str,
        timeout: int | None = None,
    ) -> int:
        """
        Wait for a container to stop.

        Args:
            container_id: Container ID
            timeout: Wait timeout in seconds

        Returns:
            Container exit code

        Raises:
            ResourceNotFoundError: If container does not exist
        """
        if not container_id:
            msg = "Container ID cannot be empty"
            raise ValidationError(msg)

        with self._lock:
            if container_id not in self._containers:
                msg = "Container"
                raise ResourceNotFoundError(msg, container_id)

        # Simulate wait
        if self._execution_delay > 0:
            await asyncio.sleep(self._execution_delay)

        with self._lock:
            container = self._containers[container_id]
            return container.get("exit_code", 0)

    async def copy_to_container(
        self,
        container_id: str,
        source: str,
        destination: str,
    ) -> None:
        """
        Copy files to a container.

        Reads content from _host_files[source] and writes to
        _virtual_filesystems[container_id][destination].

        Args:
            container_id: Container ID
            source: Source path (key in _host_files)
            destination: Destination path (in container's virtual filesystem)

        Raises:
            ResourceNotFoundError: If container does not exist or source file not found
            ValidationError: If paths are empty
        """
        if not container_id:
            msg = "Container ID cannot be empty"
            raise ValidationError(msg)
        if not source:
            msg = "Source path cannot be empty"
            raise ValidationError(msg)
        if not destination:
            msg = "Destination path cannot be empty"
            raise ValidationError(msg)

        with self._lock:
            if container_id not in self._containers:
                msg = "Container"
                raise ResourceNotFoundError(msg, container_id)

            # Check if source file exists in host_files
            if source not in self._host_files:
                msg = f"Source file '{source}' not found"
                raise ResourceNotFoundError(msg, source)

            # Copy content from host_files to container's virtual filesystem
            content = self._host_files[source]
            if container_id not in self._virtual_filesystems:
                self._virtual_filesystems[container_id] = {}
            self._virtual_filesystems[container_id][destination] = content

        # Simulate copy operation
        if self._execution_delay > 0:
            await asyncio.sleep(self._execution_delay * 0.1)

    # Helper methods for event emission and virtual filesystem tracking

    def write_output_file(self, container_id: str, file_path: str, content: str) -> None:
        """
        Write a file to the virtual output directory.

        Args:
            container_id: Container ID
            file_path: Relative path within /output/ directory
            content: File content

        Raises:
            ResourceNotFoundError: If container does not exist
        """
        with self._lock:
            if container_id not in self._virtual_filesystems:
                msg = "Container"
                raise ResourceNotFoundError(msg, container_id)
            self._virtual_filesystems[container_id][file_path] = content

    def _get_output_files(self, container_id: str) -> list[str]:
        """
        Get list of files written to output directory.

        Args:
            container_id: Container ID

        Returns:
            List of file paths
        """
        with self._lock:
            if container_id not in self._virtual_filesystems:
                return []
            return list(self._virtual_filesystems[container_id].keys())

    async def get_file_content(
        self,
        container_id: str,
        file_path: str,
    ) -> bytes:
        """
        Get file content from the virtual output directory.

        Args:
            container_id: Container ID
            file_path: Path to file within /output/

        Returns:
            File content as bytes

        Raises:
            ResourceNotFoundError: If container or file does not exist
        """
        if not container_id:
            msg = "Container ID cannot be empty"
            raise ValidationError(msg)
        if not file_path:
            msg = "File path cannot be empty"
            raise ValidationError(msg)

        with self._lock:
            if container_id not in self._virtual_filesystems:
                msg = "Container"
                raise ResourceNotFoundError(msg, container_id)

            virtual_fs = self._virtual_filesystems[container_id]
            if file_path not in virtual_fs:
                msg = f"File '{file_path}' not found in container output"
                raise ResourceNotFoundError(msg, file_path)

            # Return content as bytes
            content = virtual_fs[file_path]
            if isinstance(content, bytes):
                return content
            if isinstance(content, str):
                return content.encode("utf-8")
            # All content from write_output_file is str, so this shouldn't occur
            msg = f"Invalid content type for file '{file_path}': {type(content)}"
            raise ContainerError(msg)

    async def network_create(self, name: str, driver: str = "bridge") -> str:
        """Record a fake network creation and return a synthetic network id.

        The fake adapter has no real network surface; this method exists to
        satisfy the IContainer contract so application code that calls
        `network_create` (or test harnesses that wrap a real one) does not
        have to special-case the fake.
        """
        network_id = f"fake-network-{uuid4().hex[:12]}"
        logger.debug(f"FakeContainerAdapter.network_create({name!r}, driver={driver!r}) -> {network_id}")
        return network_id

    async def health_check(self, container_id: str) -> ContainerHealthStatus:
        """Report HEALTHY for any container the fake knows about, else raise.

        The fake adapter does not simulate healthcheck lifecycle; tests that
        need to assert STARTING/UNHEALTHY transitions should drive that
        through a mock instead.
        """
        if container_id not in self._containers:
            raise ResourceNotFoundError("Container", container_id)
        return ContainerHealthStatus.HEALTHY

    # Helper methods for testing

    def seed_host_file(self, path: str, content: str) -> None:
        """
        Seed a file into the host-side filesystem for use with copy_to_container.

        Args:
            path: File path (key in _host_files)
            content: File content (can be empty for legitimately empty files)

        Raises:
            ValidationError: If path is empty
        """
        if not path:
            msg = "File path cannot be empty"
            raise ValidationError(msg)

        with self._lock:
            self._host_files[path] = content

    def get_host_file(self, path: str) -> str:
        """
        Get content of a host-side file (populated by seed_host_file()).

        Args:
            path: File path (key in _host_files)

        Returns:
            File content

        Raises:
            ResourceNotFoundError: If file does not exist
        """
        with self._lock:
            if path not in self._host_files:
                msg = f"Host file '{path}' not found"
                raise ResourceNotFoundError(msg, path)
            return self._host_files[path]

    def clear(self) -> None:
        """Clear all containers and history."""
        with self._lock:
            self._containers.clear()
            self._execution_history.clear()
            self._command_results.clear()
            self._command_history.clear()
            self._host_files.clear()
            self._virtual_filesystems.clear()
            # Reset pulled images to pre-seeded set for test isolation
            self._pulled_images = self.DEFAULT_SEEDED_IMAGES.copy()

    def get_execution_history(self) -> list[dict[str, Any]]:
        """
        Get execution history.

        Returns:
            Copy of execution history list
        """
        with self._lock:
            return self._execution_history.copy()

    def get_execution_count(self) -> int:
        """
        Get number of executions.

        Returns:
            Total execution count
        """
        with self._lock:
            return len(self._execution_history)

    def get_container_count(self) -> int:
        """
        Get number of containers.

        Returns:
            Total container count
        """
        with self._lock:
            return len(self._containers)
