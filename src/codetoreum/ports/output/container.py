"""IContainer output port interface."""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional

from codetoreum.domain.types import ContainerId, ImageId

# ============================================================================
# Data Models
# ============================================================================


@dataclass
class ContainerResult:
    """Result from container execution."""

    exit_code: int
    stdout: str
    stderr: str
    duration_ms: int
    container_id: ContainerId


@dataclass
class ContainerStatus:
    """Container status information."""

    id: ContainerId
    status: str  # running, stopped, exited, paused, restarting, dead
    created_at: datetime
    started_at: Optional[datetime]
    finished_at: Optional[datetime]
    exit_code: Optional[int] = None


# ============================================================================
# Port Interface
# ============================================================================


class IContainer(ABC):
    """Interface for container orchestration."""

    @abstractmethod
    async def run(
        self,
        image: str,
        command: List[str],
        volumes: Dict[str, str],
        environment: Dict[str, str],
        timeout: int = 300,
        stream_callback: Optional[Callable] = None,
    ) -> ContainerResult:
        """
        Run a command in a container.

        Args:
            image: Container image name
            command: Command to execute
            volumes: Volume mounts (host_path: container_path:mode)
                    e.g., {"/host/path": "/container/path:ro"}
            environment: Environment variables
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
        pass

    @abstractmethod
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
        """
        Create a container without starting it.

        Args:
            image: Container image name
            name: Optional container name
            command: Optional command to execute
            volumes: Optional volume mounts
            environment: Optional environment variables
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
        pass

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
        pass

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
        pass

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
        pass

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
        pass

    @abstractmethod
    async def logs(
        self,
        container_id: str,
        stream: bool = False,
        follow: bool = False,
        tail: Optional[int] = None,
        since: Optional[datetime] = None,
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
        pass

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
        pass

    @abstractmethod
    async def exec(
        self,
        container_id: str,
        command: List[str],
        user: Optional[str] = None,
        working_dir: Optional[str] = None,
        environment: Optional[Dict[str, str]] = None,
    ) -> ContainerResult:
        """
        Execute a command in a running container.

        Args:
            container_id: Container identifier
            command: Command to execute
            user: Optional user to run as
            working_dir: Optional working directory
            environment: Optional environment variables

        Returns:
            ContainerResult: Execution result

        Raises:
            ResourceNotFoundError: Container doesn't exist
            ContainerNotRunningError: Container is not running
            ContainerError: Exec operation failed
        """
        pass

    @abstractmethod
    async def list_containers(
        self,
        all: bool = False,
        filters: Optional[Dict[str, Any]] = None,
    ) -> List[ContainerStatus]:
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
        pass

    @abstractmethod
    async def pull_image(
        self,
        image: str,
        tag: str = "latest",
        stream_callback: Optional[Callable] = None,
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
        pass

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
        pass

    @abstractmethod
    async def inspect(self, container_id: str) -> Dict[str, Any]:
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
        pass

    @abstractmethod
    async def wait(
        self,
        container_id: str,
        timeout: Optional[int] = None,
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
        pass

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
        pass

    @abstractmethod
    async def copy_from_container(
        self,
        container_id: str,
        source: str,
        destination: str,
    ) -> None:
        """
        Copy files from a container.

        Args:
            container_id: Container identifier
            source: Source path in container
            destination: Destination path on host

        Raises:
            ResourceNotFoundError: Container or file doesn't exist
            ContainerError: Copy operation failed
        """
        pass
