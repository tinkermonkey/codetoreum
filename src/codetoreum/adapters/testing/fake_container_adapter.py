"""Fake container adapter for testing."""

import asyncio
import re
import threading
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from codetoreum.ports.exceptions import (
    ContainerError,
    ResourceNotFoundError,
    ValidationError,
)
from codetoreum.ports.output.container import (
    ContainerResult,
    ContainerStatus,
    IContainer,
)


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

    def __init__(
        self,
        default_exit_code: int = 0,
        default_stdout: str = "Fake container output",
        default_stderr: str = "",
        execution_delay: float = 0.0,
        max_containers: int = 100,
    ):
        """
        Initialize the fake container adapter.

        Args:
            default_exit_code: Default exit code for executions
            default_stdout: Default stdout content
            default_stderr: Default stderr content
            execution_delay: Simulated execution delay in seconds
            max_containers: Maximum number of containers allowed (default: 100)

        Raises:
            ValidationError: If parameters are invalid
        """
        if execution_delay < 0:
            raise ValidationError("Execution delay cannot be negative")
        if max_containers <= 0:
            raise ValidationError("Max containers must be positive")

        self._default_exit_code = default_exit_code
        self._default_stdout = default_stdout
        self._default_stderr = default_stderr
        self._execution_delay = execution_delay
        self._max_containers = max_containers

        # Container storage
        self._containers: dict[str, dict[str, Any]] = {}

        # Predefined results for specific commands
        self._command_results: dict[str, ContainerResult] = {}

        # Execution history
        self._execution_history: list[dict[str, Any]] = []

        # Thread safety
        self._lock = threading.Lock()

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
            raise ValidationError("Command pattern cannot be empty")

        container_id = f"fake-{uuid4()}"
        with self._lock:
            self._command_results[command_pattern] = ContainerResult(
                exit_code=exit_code,
                stdout=stdout,
                stderr=stderr,
                duration_ms=int(self._execution_delay * 1000),
                container_id=container_id,
            )

    def _get_result_for_command(
        self,
        command: list[str],
        container_id: str,
    ) -> ContainerResult:
        """
        Get result for a command.

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
                    result.container_id = container_id
                    return result

                # Check for first word match
                first_word = command[0]
                if first_word in self._command_results:
                    result = self._command_results[first_word]
                    result.container_id = container_id
                    return result

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
        command: list[str],
        volumes: dict[str, str],
        environment: dict[str, str],
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
            raise ValidationError("Image name is required")

        if not command or len(command) == 0:
            raise ValidationError("Command is required")

        # Simulate execution delay
        if self._execution_delay > 0:
            await asyncio.sleep(self._execution_delay)

        # Create container
        container_id = f"fake-{uuid4().hex[:12]}"

        # Get result
        result = self._get_result_for_command(command, container_id)

        # Record execution
        with self._lock:
            self._execution_history.append({
                "container_id": container_id,
                "image": image,
                "command": command,
                "volumes": volumes,
                "environment": environment,
                "timeout": timeout,
                "result": result,
                "executed_at": datetime.now(UTC),
            })

        # Simulate streaming if callback provided
        if stream_callback:
            if result.stdout:
                for line in result.stdout.split("\n"):
                    await stream_callback(line + "\n")

        return result

    async def create(
        self,
        image: str,
        name: str | None = None,
        command: list[str] | None = None,
        volumes: dict[str, str] | None = None,
        environment: dict[str, str] | None = None,
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
            raise ValidationError("Image name is required")

        with self._lock:
            if len(self._containers) >= self._max_containers:
                raise ValidationError(f"Maximum container limit ({self._max_containers}) reached")

            # Validate container name format if provided
            if name:
                if not re.match(r"^[a-zA-Z0-9][a-zA-Z0-9_.-]*$", name):
                    raise ValidationError(f"Invalid container name format: '{name}'")

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
                "status": "created",
                "created_at": datetime.now(UTC),
                "started_at": None,
                "finished_at": None,
                "exit_code": None,
            }

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
            raise ValidationError("Container ID cannot be empty")

        with self._lock:
            if container_id not in self._containers:
                raise ResourceNotFoundError("Container", container_id)

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
            raise ValidationError("Container ID cannot be empty")

        with self._lock:
            if container_id not in self._containers:
                raise ResourceNotFoundError("Container", container_id)

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
        """
        if not container_id:
            raise ValidationError("Container ID cannot be empty")

        with self._lock:
            if container_id not in self._containers:
                raise ResourceNotFoundError("Container", container_id)

            del self._containers[container_id]

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
            raise ValidationError("Container ID cannot be empty")

        with self._lock:
            if container_id not in self._containers:
                raise ResourceNotFoundError("Container", container_id)

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
            raise ValidationError("Container ID cannot be empty")

        with self._lock:
            if container_id not in self._containers:
                raise ResourceNotFoundError("Container", container_id)

        # Return fake logs
        logs = f"Fake logs for container {container_id}\nLine 1\nLine 2\nLine 3"

        if tail:
            lines = logs.split("\n")
            logs = "\n".join(lines[-tail:])

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
            raise ValidationError("Container ID cannot be empty")

        with self._lock:
            if container_id not in self._containers:
                raise ResourceNotFoundError("Container", container_id)

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
        command: list[str],
        user: str | None = None,
        working_dir: str | None = None,
        environment: dict[str, str] | None = None,
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
            ContainerError: If container is not running
            ValidationError: If command is empty
        """
        if not container_id:
            raise ValidationError("Container ID cannot be empty")

        if not command:
            raise ValidationError("Command cannot be empty")

        with self._lock:
            if container_id not in self._containers:
                raise ResourceNotFoundError("Container", container_id)

            container = self._containers[container_id]
            if container["status"] != "running":
                raise ContainerError(f"Container '{container_id}' is not running")

        # Simulate execution
        if self._execution_delay > 0:
            await asyncio.sleep(self._execution_delay)

        return self._get_result_for_command(command, container_id)

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

        Args:
            image: Image name (required)
            tag: Image tag
            stream_callback: Optional callback for progress

        Raises:
            ValidationError: If image is invalid
        """
        if not image or not image.strip():
            raise ValidationError("Image name is required")

        # Simulate pull delay
        if self._execution_delay > 0:
            await asyncio.sleep(self._execution_delay)

        if stream_callback:
            await stream_callback(f"Pulling {image}:{tag}...")
            await stream_callback("Pull complete")

    async def image_exists(self, image: str, tag: str = "latest") -> bool:
        """
        Check if an image exists locally.

        Args:
            image: Image name
            tag: Image tag

        Returns:
            Always True for fake adapter
        """
        return True

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
            raise ValidationError("Container ID cannot be empty")

        with self._lock:
            if container_id not in self._containers:
                raise ResourceNotFoundError("Container", container_id)

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
            raise ValidationError("Container ID cannot be empty")

        with self._lock:
            if container_id not in self._containers:
                raise ResourceNotFoundError("Container", container_id)

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

        Args:
            container_id: Container ID
            source: Source path
            destination: Destination path

        Raises:
            ResourceNotFoundError: If container does not exist
            ValidationError: If paths are empty
        """
        if not container_id:
            raise ValidationError("Container ID cannot be empty")
        if not source:
            raise ValidationError("Source path cannot be empty")
        if not destination:
            raise ValidationError("Destination path cannot be empty")

        with self._lock:
            if container_id not in self._containers:
                raise ResourceNotFoundError("Container", container_id)

        # Simulate copy operation
        if self._execution_delay > 0:
            await asyncio.sleep(self._execution_delay * 0.1)

    async def copy_from_container(
        self,
        container_id: str,
        source: str,
        destination: str,
    ) -> None:
        """
        Copy files from a container.

        Args:
            container_id: Container ID
            source: Source path in container
            destination: Destination path on host

        Raises:
            ResourceNotFoundError: If container does not exist
            ValidationError: If paths are empty
        """
        if not container_id:
            raise ValidationError("Container ID cannot be empty")
        if not source:
            raise ValidationError("Source path cannot be empty")
        if not destination:
            raise ValidationError("Destination path cannot be empty")

        with self._lock:
            if container_id not in self._containers:
                raise ResourceNotFoundError("Container", container_id)

        # Simulate copy operation
        if self._execution_delay > 0:
            await asyncio.sleep(self._execution_delay * 0.1)

    # Helper methods for testing

    def clear(self) -> None:
        """Clear all containers and history."""
        with self._lock:
            self._containers.clear()
            self._execution_history.clear()
            self._command_results.clear()

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
