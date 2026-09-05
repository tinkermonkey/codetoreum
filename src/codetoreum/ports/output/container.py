"""IContainer output port interface."""

from abc import ABC, abstractmethod
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any

from codetoreum.domain.types import ContainerId

# ============================================================================
# Data Models
# ============================================================================


class ContainerHealthStatus(Enum):
    """Container health status.

    Mirrors the values produced by the Docker daemon's healthcheck subsystem
    (`State.Health.Status`), with `UNKNOWN` covering the no-healthcheck case
    and any orchestrators that cannot report health (e.g., the in-process
    fake adapter). Defined on the port rather than reused from
    `codetoreum.infrastructure.health` to keep the port boundary clean —
    ports must not depend on infrastructure.
    """

    HEALTHY = "healthy"
    UNHEALTHY = "unhealthy"
    STARTING = "starting"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class ContainerResult:
    """Result from container execution.

    All fields are validated at construction to ensure contract boundary integrity.
    Frozen to prevent accidental mutation after creation.
    """

    exit_code: int
    stdout: str
    stderr: str
    duration_ms: int
    container_id: ContainerId

    def __post_init__(self) -> None:
        """Validate all fields at construction time."""
        if isinstance(self.exit_code, bool) or not isinstance(self.exit_code, int):
            msg = "exit_code must be an integer"
            raise ValueError(msg)

        if not isinstance(self.stdout, str):
            msg = "stdout must be a string"
            raise ValueError(msg)

        if not isinstance(self.stderr, str):
            msg = "stderr must be a string"
            raise ValueError(msg)

        if isinstance(self.duration_ms, bool) or not isinstance(self.duration_ms, int) or self.duration_ms < 0:
            msg = "duration_ms must be a non-negative integer"
            raise ValueError(msg)

        if not isinstance(self.container_id, str) or not self.container_id:
            msg = "container_id must be a non-empty string"
            raise ValueError(msg)


@dataclass(frozen=True)
class ContainerStatus:
    """Container status information.

    All fields are validated at construction to ensure contract boundary integrity.
    Frozen to prevent accidental mutation after creation.
    """

    id: ContainerId
    status: str  # created, running, paused, restarting, removing, exited, dead
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None
    exit_code: int | None = None

    def __post_init__(self) -> None:
        """Validate all fields at construction time."""
        if not isinstance(self.id, str) or not self.id:
            msg = "id must be a non-empty string"
            raise ValueError(msg)

        if not isinstance(self.status, str) or self.status not in (
            "created",
            "running",
            "paused",
            "restarting",
            "removing",
            "exited",
            "dead",
        ):
            msg = "status must be one of: created, running, paused, restarting, removing, exited, dead"
            raise ValueError(msg)

        if not isinstance(self.created_at, datetime):
            msg = "created_at must be a datetime instance"
            raise ValueError(msg)

        if self.started_at is not None:
            if not isinstance(self.started_at, datetime):
                msg = "started_at must be a datetime instance or None"
                raise ValueError(msg)

        if self.finished_at is not None:
            if not isinstance(self.finished_at, datetime):
                msg = "finished_at must be a datetime instance or None"
                raise ValueError(msg)

        if self.exit_code is not None:
            if isinstance(self.exit_code, bool) or not isinstance(self.exit_code, int):
                msg = "exit_code must be an integer or None"
                raise ValueError(msg)


# ============================================================================
# Port Interface
# ============================================================================


class IContainer(ABC):
    """Interface for container orchestration."""

    @abstractmethod
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
            image: Container image name
            command: Command to execute (list or immutable tuple)
            volumes: Volume mounts (host_path: container_path:mode)
                    e.g., {"/host/path": "/container/path:ro"}
            environment: Environment variables (dict or Mapping)
            timeout: Execution timeout in seconds
            stream_callback: Optional callback for streaming logs

        Returns:
            ContainerResult: Execution result

        Raises:
            ContainerExecutionError: Container execution failed
            ContainerTimeoutError: Execution timed out
            ImageNotFoundError: Container image doesn't exist
            ValidationError: Invalid configuration
        """

    @abstractmethod
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
            image: Container image name
            name: Optional container name
            command: Optional command to execute (list or immutable tuple)
            volumes: Optional volume mounts (dict or Mapping)
            environment: Optional environment variables (dict or Mapping)
            working_dir: Optional working directory
            user: Optional user (UID:GID or username)
            network: Optional network name
            labels: Optional container labels

        Returns:
            str: Container ID

        Raises:
            ImageNotFoundError: Container image doesn't exist
            ValidationError: Invalid configuration
            ContainerError: Container creation failed
        """

    @abstractmethod
    async def start(self, container_id: str) -> None:
        """
        Start a container.

        Args:
            container_id: Container identifier

        Raises:
            ResourceNotFoundError: Container doesn't exist
            ContainerError: Start operation failed
        """

    @abstractmethod
    async def stop(self, container_id: str, timeout: int = 10) -> None:
        """
        Stop a container.

        Args:
            container_id: Container identifier
            timeout: Seconds to wait before killing

        Raises:
            ResourceNotFoundError: Container doesn't exist
            ContainerError: Stop operation failed
        """

    @abstractmethod
    async def remove(self, container_id: str, force: bool = False) -> None:
        """
        Remove a container.

        Args:
            container_id: Container identifier
            force: Force removal even if running

        Raises:
            ResourceNotFoundError: Container doesn't exist
            ContainerError: Remove operation failed
        """

    @abstractmethod
    async def kill(self, container_id: str, signal: str = "SIGKILL") -> None:
        """
        Kill a container.

        Args:
            container_id: Container identifier
            signal: Signal to send (SIGKILL, SIGTERM, etc.)

        Raises:
            ResourceNotFoundError: Container doesn't exist
            ContainerError: Kill operation failed
        """

    @abstractmethod
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
            container_id: Container identifier
            stream: Return generator instead of all logs
            follow: Follow log output (requires stream=True)
            tail: Only return this many lines from end
            since: Only return logs since this timestamp

        Returns:
            str or AsyncIterator: Logs as string or async iterator if streaming

        Raises:
            ResourceNotFoundError: Container doesn't exist
            ContainerError: Logs operation failed
        """

    @abstractmethod
    async def status(self, container_id: str) -> ContainerStatus:
        """
        Get container status.

        Args:
            container_id: Container identifier

        Returns:
            ContainerStatus: Current container status

        Raises:
            ResourceNotFoundError: Container doesn't exist
            ContainerError: Status check failed
        """

    @abstractmethod
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
            container_id: Container identifier
            command: Command to execute (list or immutable tuple)
            user: Optional user to run as
            working_dir: Optional working directory
            environment: Optional environment variables (dict or Mapping)

        Returns:
            ContainerResult: Execution result

        Raises:
            ResourceNotFoundError: Container doesn't exist
            ContainerNotRunningError: Container is not running
            ContainerError: Exec operation failed
        """

    @abstractmethod
    async def list_containers(
        self,
        all: bool = False,
        filters: dict[str, Any] | None = None,
    ) -> list[ContainerStatus]:
        """
        List containers.

        Args:
            all: Include stopped containers
            filters: Optional filters (name, status, label, etc.)

        Returns:
            List[ContainerStatus]: List of container statuses

        Raises:
            ContainerError: List operation failed
        """

    @abstractmethod
    async def pull_image(
        self,
        image: str,
        tag: str = "latest",
        stream_callback: Callable | None = None,
    ) -> None:
        """
        Pull a container image.

        Args:
            image: Image name
            tag: Image tag
            stream_callback: Optional callback for progress updates

        Raises:
            ImageNotFoundError: Image doesn't exist
            AuthenticationError: Registry authentication failed
            ContainerError: Pull operation failed
        """

    @abstractmethod
    async def image_exists(self, image: str, tag: str = "latest") -> bool:
        """
        Check if an image exists locally.

        Args:
            image: Image name
            tag: Image tag

        Returns:
            bool: True if image exists locally

        Raises:
            ContainerError: Check operation failed
        """

    @abstractmethod
    async def inspect(self, container_id: str) -> dict[str, Any]:
        """
        Get detailed container information.

        Args:
            container_id: Container identifier

        Returns:
            Dict[str, Any]: Container configuration and state

        Raises:
            ResourceNotFoundError: Container doesn't exist
            ContainerError: Inspect operation failed
        """

    @abstractmethod
    async def wait(
        self,
        container_id: str,
        timeout: int | None = None,
    ) -> int:
        """
        Wait for a container to stop.

        Args:
            container_id: Container identifier
            timeout: Optional timeout in seconds

        Returns:
            int: Container exit code

        Raises:
            ResourceNotFoundError: Container doesn't exist
            TimeoutError: Wait timed out
            ContainerError: Wait operation failed
        """

    @abstractmethod
    async def copy_to_container(
        self,
        container_id: str,
        source: str,
        destination: str,
    ) -> None:
        """
        Copy files to a container.

        Args:
            container_id: Container identifier
            source: Source path on host
            destination: Destination path in container

        Raises:
            ResourceNotFoundError: Container or file doesn't exist
            ContainerError: Copy operation failed
        """

    @abstractmethod
    async def get_file_content(
        self,
        container_id: str,
        file_path: str,
    ) -> bytes:
        """
        Get file content from a container's output directory.

        This method enables retrieval of files written by container execution,
        supporting the causal link between ContainerExecutionCompletedEvent and
        artifact persistence in InMemoryStorageAdapter.

        Args:
            container_id: Container identifier
            file_path: Path to file within container (relative to /output/)

        Returns:
            bytes: File content

        Raises:
            ResourceNotFoundError: Container or file doesn't exist
            ContainerError: Read operation failed
        """

    @abstractmethod
    async def network_create(self, name: str, driver: str = "bridge") -> str:
        """Create a container network.

        Required by orchestrators that compose multiple containers per work item
        (database + agent + service-mesh sidecar). The Docker adapter delegates
        to `docker.networks.create`; Kubernetes adapters would create a
        NetworkPolicy or namespace.

        Args:
            name: Network name. Must be unique within the host's network scope.
            driver: Network driver (default: "bridge"). Adapter-defined values
                accepted (e.g., "overlay" on Docker Swarm).

        Returns:
            str: Network identifier assigned by the runtime.

        Raises:
            ValidationError: Invalid name or driver.
            ContainerError: Network creation failed.
        """

    @abstractmethod
    async def health_check(self, container_id: str) -> ContainerHealthStatus:
        """Report container health.

        Reads the container's healthcheck status (if a HEALTHCHECK is configured
        on the image). Returns `UNKNOWN` when the container has no healthcheck.

        Args:
            container_id: Container identifier.

        Returns:
            ContainerHealthStatus: One of HEALTHY, UNHEALTHY, STARTING, UNKNOWN.

        Raises:
            ResourceNotFoundError: Container doesn't exist.
            ContainerError: Status query failed.
        """
