"""Fake container adapter for testing."""

import asyncio
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional
from uuid import uuid4

from codetoreum.ports.exceptions import (
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
    """

    def __init__(
        self,
        default_exit_code: int = 0,
        default_stdout: str = "Fake container output",
        default_stderr: str = "",
        execution_delay: float = 0.0,
    ):
        """
        Initialize the fake container adapter.

        Args:
            default_exit_code: Default exit code for executions
            default_stdout: Default stdout content
            default_stderr: Default stderr content
            execution_delay: Simulated execution delay in seconds
        """
        self._default_exit_code = default_exit_code
        self._default_stdout = default_stdout
        self._default_stderr = default_stderr
        self._execution_delay = execution_delay

        # Container storage
        self._containers: Dict[str, Dict[str, Any]] = {}

        # Predefined results for specific commands
        self._command_results: Dict[str, ContainerResult] = {}

        # Execution history
        self._execution_history: List[Dict[str, Any]] = []

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
        """
        container_id = f"fake-{uuid4()}"
        self._command_results[command_pattern] = ContainerResult(
            exit_code=exit_code,
            stdout=stdout,
            stderr=stderr,
            duration_ms=int(self._execution_delay * 1000),
            container_id=container_id,
        )

    def _get_result_for_command(
        self,
        command: List[str],
        container_id: str,
    ) -> ContainerResult:
        """Get result for a command."""
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
        command: List[str],
        volumes: Dict[str, str],
        environment: Dict[str, str],
        timeout: int = 300,
        stream_callback: Optional[Callable] = None,
    ) -> ContainerResult:
        """Run a command in a container."""
        if not image:
            raise ValidationError("Image name is required")

        if not command:
            raise ValidationError("Command is required")

        # Simulate execution delay
        if self._execution_delay > 0:
            await asyncio.sleep(self._execution_delay)

        # Create container
        container_id = f"fake-{uuid4().hex[:12]}"

        # Get result
        result = self._get_result_for_command(command, container_id)

        # Record execution
        self._execution_history.append({
            "container_id": container_id,
            "image": image,
            "command": command,
            "volumes": volumes,
            "environment": environment,
            "timeout": timeout,
            "result": result,
            "executed_at": datetime.now(timezone.utc),
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
        name: Optional[str] = None,
        command: Optional[List[str]] = None,
        volumes: Optional[Dict[str, str]] = None,
        environment: Optional[Dict[str, str]] = None,
        working_dir: Optional[str] = None,
        user: Optional[str] = None,
        network: Optional[str] = None,
        labels: Optional[Dict[str, str]] = None,
    ) -> str:
        """Create a container without starting it."""
        if not image:
            raise ValidationError("Image name is required")

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
            "created_at": datetime.now(timezone.utc),
            "started_at": None,
            "finished_at": None,
            "exit_code": None,
        }

        return container_id

    async def start(self, container_id: str) -> None:
        """Start a container."""
        if container_id not in self._containers:
            raise ResourceNotFoundError("Container", container_id)

        container = self._containers[container_id]
        container["status"] = "running"
        container["started_at"] = datetime.now(timezone.utc)

    async def stop(self, container_id: str, timeout: int = 10) -> None:
        """Stop a container."""
        if container_id not in self._containers:
            raise ResourceNotFoundError("Container", container_id)

        container = self._containers[container_id]
        container["status"] = "exited"
        container["finished_at"] = datetime.now(timezone.utc)
        container["exit_code"] = 0

    async def remove(self, container_id: str, force: bool = False) -> None:
        """Remove a container."""
        if container_id not in self._containers:
            raise ResourceNotFoundError("Container", container_id)

        del self._containers[container_id]

    async def kill(self, container_id: str, signal: str = "SIGKILL") -> None:
        """Kill a container."""
        if container_id not in self._containers:
            raise ResourceNotFoundError("Container", container_id)

        container = self._containers[container_id]
        container["status"] = "dead"
        container["finished_at"] = datetime.now(timezone.utc)
        container["exit_code"] = 137 if signal == "SIGKILL" else 143

    async def logs(
        self,
        container_id: str,
        stream: bool = False,
        follow: bool = False,
        tail: Optional[int] = None,
        since: Optional[datetime] = None,
    ) -> Any:
        """Get container logs."""
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
        """Get container status."""
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
        command: List[str],
        user: Optional[str] = None,
        working_dir: Optional[str] = None,
        environment: Optional[Dict[str, str]] = None,
    ) -> ContainerResult:
        """Execute a command in a running container."""
        if container_id not in self._containers:
            raise ResourceNotFoundError("Container", container_id)

        container = self._containers[container_id]
        if container["status"] != "running":
            from codetoreum.ports.exceptions import ContainerError
            raise ContainerError(f"Container {container_id} is not running")

        # Simulate execution
        if self._execution_delay > 0:
            await asyncio.sleep(self._execution_delay)

        return self._get_result_for_command(command, container_id)

    async def list_containers(
        self,
        all: bool = False,
        filters: Optional[Dict[str, Any]] = None,
    ) -> List[ContainerStatus]:
        """List containers."""
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
        stream_callback: Optional[Callable] = None,
    ) -> None:
        """Pull a container image."""
        if not image:
            raise ValidationError("Image name is required")

        # Simulate pull delay
        if self._execution_delay > 0:
            await asyncio.sleep(self._execution_delay)

        if stream_callback:
            await stream_callback(f"Pulling {image}:{tag}...")
            await stream_callback("Pull complete")

    async def image_exists(self, image: str, tag: str = "latest") -> bool:
        """Check if an image exists locally."""
        # For fake adapter, always return True
        return True

    async def inspect(self, container_id: str) -> Dict[str, Any]:
        """Get detailed container information."""
        if container_id not in self._containers:
            raise ResourceNotFoundError("Container", container_id)

        return self._containers[container_id].copy()

    async def wait(
        self,
        container_id: str,
        timeout: Optional[int] = None,
    ) -> int:
        """Wait for a container to stop."""
        if container_id not in self._containers:
            raise ResourceNotFoundError("Container", container_id)

        # Simulate wait
        if self._execution_delay > 0:
            await asyncio.sleep(self._execution_delay)

        container = self._containers[container_id]
        return container.get("exit_code", 0)

    async def copy_to_container(
        self,
        container_id: str,
        source: str,
        destination: str,
    ) -> None:
        """Copy files to a container."""
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
        """Copy files from a container."""
        if container_id not in self._containers:
            raise ResourceNotFoundError("Container", container_id)

        # Simulate copy operation
        if self._execution_delay > 0:
            await asyncio.sleep(self._execution_delay * 0.1)

    # Helper methods for testing

    def clear(self) -> None:
        """Clear all containers and history."""
        self._containers.clear()
        self._execution_history.clear()
        self._command_results.clear()

    def get_execution_history(self) -> List[Dict[str, Any]]:
        """Get execution history."""
        return self._execution_history.copy()

    def get_execution_count(self) -> int:
        """Get number of executions."""
        return len(self._execution_history)

    def get_container_count(self) -> int:
        """Get number of containers."""
        return len(self._containers)
