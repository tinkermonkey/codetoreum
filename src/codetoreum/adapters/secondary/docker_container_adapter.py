"""Docker adapter for IContainer interface."""

import asyncio
import gc
import logging
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional

from dateutil import parser as dateparser

from codetoreum.domain.types import ContainerId

logger = logging.getLogger(__name__)
from codetoreum.ports.exceptions import (
    AuthenticationError,
    ContainerError,
    ContainerExecutionError,
    ContainerNotRunningError,
    ContainerTimeoutError,
    ImageNotFoundError,
    ResourceNotFoundError,
    ValidationError,
)
from codetoreum.ports.output.container import (
    ContainerResult,
    ContainerStatus,
    IContainer,
)


@dataclass
class DockerConfig:
    """Configuration for Docker adapter."""

    # Docker connection
    docker_host: Optional[str] = None  # Defaults to local socket
    tls_verify: bool = False
    cert_path: Optional[str] = None

    # Container defaults
    default_timeout: int = 300  # 5 minutes
    remove_on_completion: bool = True
    default_user: Optional[str] = None
    default_network: str = "bridge"

    # Resource limits
    memory_limit: Optional[str] = None  # e.g., "512m"
    cpu_limit: Optional[float] = None  # e.g., 1.0 for 1 CPU

    # Logging
    log_driver: str = "json-file"


class DockerContainerAdapter(IContainer):
    """
    Docker adapter for container operations.

    This adapter uses the Docker SDK for Python to manage containers.
    It implements all IContainer interface methods for Docker operations.
    """

    def __init__(self, config: DockerConfig):
        """
        Initialize Docker adapter.

        Args:
            config: Docker configuration
        """
        self.config = config
        self._docker_client = None

    def _get_client(self):
        """Get or create Docker client."""
        if self._docker_client is None:
            try:
                import docker

                if self.config.docker_host:
                    self._docker_client = docker.DockerClient(
                        base_url=self.config.docker_host,
                        tls=self.config.tls_verify,
                    )
                else:
                    self._docker_client = docker.from_env()

            except Exception as e:
                raise ContainerError(f"Failed to connect to Docker: {str(e)}")

        return self._docker_client

    def _parse_volume_spec(self, volumes: Dict[str, str]) -> Dict[str, Dict[str, str]]:
        """
        Parse volume specification with path traversal protection.

        Args:
            volumes: Volume mounts (host_path: container_path:mode)

        Returns:
            Docker SDK volume specification

        Raises:
            ValidationError: If volume specification is invalid or contains unsafe paths
        """
        from pathlib import Path

        docker_volumes = {}

        for host_path, spec in volumes.items():
            # Validate host path - resolve to absolute path and check for traversal
            try:
                resolved_host_path = Path(host_path).resolve()

                # Ensure host path is absolute
                if not resolved_host_path.is_absolute():
                    raise ValidationError(f"Host path must be absolute: {host_path}")

                # Check if path exists (optional - comment out if you want to allow non-existent paths)
                # if not resolved_host_path.exists():
                #     raise ValidationError(f"Host path does not exist: {host_path}")

            except (OSError, RuntimeError) as e:
                raise ValidationError(f"Invalid host path '{host_path}': {e}")

            # Parse container_path:mode
            parts = spec.split(":")
            if len(parts) == 1:
                container_path = parts[0]
                mode = "rw"
            elif len(parts) == 2:
                container_path, mode = parts
            else:
                raise ValidationError(f"Invalid volume spec: {spec}")

            # Validate container path (should be absolute)
            if not container_path.startswith("/"):
                raise ValidationError(
                    f"Container path must be absolute (start with /): {container_path}"
                )

            # Validate mode
            if mode not in ["rw", "ro"]:
                raise ValidationError(
                    f"Invalid mount mode '{mode}'. Must be 'rw' (read-write) or 'ro' (read-only)"
                )

            docker_volumes[str(resolved_host_path)] = {
                "bind": container_path,
                "mode": mode,
            }

        return docker_volumes

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

        client = self._get_client()

        # Parse volumes
        docker_volumes = self._parse_volume_spec(volumes)

        # Build container configuration
        container_config = {
            "image": image,
            "command": command if command else None,
            "volumes": docker_volumes,
            "environment": environment,
            "detach": True,
            "remove": self.config.remove_on_completion,
            "network": self.config.default_network,
            "user": self.config.default_user,
        }

        # Add resource limits
        if self.config.memory_limit:
            container_config["mem_limit"] = self.config.memory_limit
        if self.config.cpu_limit:
            container_config["nano_cpus"] = int(self.config.cpu_limit * 1e9)

        # Run in thread pool to avoid blocking
        loop = asyncio.get_event_loop()

        # Track task for cancellation handling
        executor_task = None

        def _run_container():
            container = None
            try:
                # Check if image exists locally
                try:
                    client.images.get(image)
                except Exception:
                    raise ImageNotFoundError(f"Image not found: {image}")

                # Create and start container with auto-removal enabled
                container = client.containers.run(**container_config)

                start_time = time.time()

                # Buffer for collecting logs
                log_buffer = []

                # Always stream logs to capture output before container is auto-removed
                # Docker auto-removes the container after the stream ends
                try:
                    for line in container.logs(stream=True, follow=True):
                        # Check if we've exceeded timeout
                        if time.time() - start_time > timeout:
                            # Kill container if it's still running
                            try:
                                container.kill()
                            except Exception as kill_error:
                                logger.warning(
                                    f"Failed to kill container on timeout: {kill_error}",
                                    exc_info=True,
                                    extra={
                                        "error_id": "ERR_CONTAINER_KILL_FAILED",
                                        "container_id": container.short_id
                                    }
                                )
                            raise ContainerTimeoutError(f"Container execution timed out after {timeout}s")

                        decoded_line = line.decode("utf-8", errors="replace")
                        log_buffer.append(decoded_line)

                        # Call user callback if provided
                        if stream_callback:
                            stream_callback(decoded_line)

                    # When streaming completes, container has finished
                    # Get final state before it's auto-removed
                    container.reload()
                    exit_code = container.attrs["State"]["ExitCode"]
                    container_id = ContainerId(container.id)

                except Exception as e:
                    # If we get here due to timeout, re-raise it
                    if isinstance(e, ContainerTimeoutError):
                        raise
                    # If container was removed during streaming, we might not get all logs
                    # but we can still return what we captured
                    if "404" in str(e) or "not found" in str(e).lower():
                        # Container was removed, use what we have
                        exit_code = 0  # Assume success if container completed and was removed
                        container_id = ContainerId(container.short_id if container else "unknown")
                    else:
                        raise

                duration_ms = int((time.time() - start_time) * 1000)

                # Reconstruct stdout/stderr from buffered logs
                # Note: Docker's logs API doesn't cleanly separate stdout/stderr when streaming
                # so we return combined output in stdout
                combined_logs = "".join(log_buffer)

                return ContainerResult(
                    exit_code=exit_code,
                    stdout=combined_logs,
                    stderr="",  # stderr is mixed with stdout in stream mode
                    duration_ms=duration_ms,
                    container_id=container_id,
                )

            except ContainerTimeoutError:
                raise
            except Exception as e:
                # Cleanup container on error if it still exists and wasn't auto-removed
                if container:
                    try:
                        container.remove(force=True)
                    except Exception as cleanup_error:
                        logger.warning(
                            f"Failed to remove container during cleanup: {cleanup_error}",
                            exc_info=True,
                            extra={
                                "error_id": "ERR_CONTAINER_CLEANUP_FAILED",
                                "container_id": container.short_id if container else "unknown"
                            }
                        )

                if "timeout" in str(e).lower():
                    raise ContainerTimeoutError(f"Container execution timed out after {timeout}s")
                elif "not found" in str(e).lower() and "image" in str(e).lower():
                    raise ImageNotFoundError(f"Image not found: {image}")
                else:
                    raise ContainerExecutionError(f"Container execution failed: {str(e)}")

        try:
            # Create executor task for cancellation support
            executor_task = loop.run_in_executor(None, _run_container)

            # Await with cancellation support
            result = await executor_task
            return result

        except asyncio.CancelledError:
            # Handle cancellation - the container might still be running
            if executor_task and not executor_task.done():
                executor_task.cancel()
            raise
        except (ContainerError, ValidationError, ImageNotFoundError):
            raise
        except Exception as e:
            raise ContainerExecutionError(f"Unexpected error: {str(e)}")

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
        client = self._get_client()

        container_config = {
            "image": image,
            "name": name,
            "command": command,
            "environment": environment or {},
            "detach": True,
            "working_dir": working_dir,
            "user": user or self.config.default_user,
            "network": network or self.config.default_network,
            "labels": labels or {},
        }

        if volumes:
            container_config["volumes"] = self._parse_volume_spec(volumes)

        loop = asyncio.get_event_loop()

        def _create():
            try:
                # Check image exists
                try:
                    client.images.get(image)
                except Exception:
                    raise ImageNotFoundError(f"Image not found: {image}")

                container = client.containers.create(**container_config)
                return container.id

            except Exception as e:
                if "not found" in str(e).lower() and "image" in str(e).lower():
                    raise ImageNotFoundError(f"Image not found: {image}")
                raise ContainerError(f"Failed to create container: {str(e)}")

        return await loop.run_in_executor(None, _create)

    async def start(self, container_id: str) -> None:
        """Start a container."""
        client = self._get_client()
        loop = asyncio.get_event_loop()

        def _start():
            try:
                container = client.containers.get(container_id)
                container.start()
            except Exception as e:
                if "not found" in str(e).lower():
                    raise ResourceNotFoundError("Container", container_id)
                raise ContainerError(f"Failed to start container: {str(e)}")

        await loop.run_in_executor(None, _start)

    async def stop(self, container_id: str, timeout: int = 10) -> None:
        """Stop a container."""
        client = self._get_client()
        loop = asyncio.get_event_loop()

        def _stop():
            try:
                container = client.containers.get(container_id)
                container.stop(timeout=timeout)
            except Exception as e:
                if "not found" in str(e).lower():
                    raise ResourceNotFoundError("Container", container_id)
                raise ContainerError(f"Failed to stop container: {str(e)}")

        await loop.run_in_executor(None, _stop)

    async def remove(self, container_id: str, force: bool = False) -> None:
        """Remove a container."""
        client = self._get_client()
        loop = asyncio.get_event_loop()

        def _remove():
            try:
                container = client.containers.get(container_id)
                container.remove(force=force)
            except Exception as e:
                if "not found" in str(e).lower():
                    raise ResourceNotFoundError("Container", container_id)
                raise ContainerError(f"Failed to remove container: {str(e)}")

        await loop.run_in_executor(None, _remove)

    async def kill(self, container_id: str, signal: str = "SIGKILL") -> None:
        """Kill a container."""
        client = self._get_client()
        loop = asyncio.get_event_loop()

        def _kill():
            try:
                container = client.containers.get(container_id)
                container.kill(signal=signal)
            except Exception as e:
                if "not found" in str(e).lower():
                    raise ResourceNotFoundError("Container", container_id)
                raise ContainerError(f"Failed to kill container: {str(e)}")

        await loop.run_in_executor(None, _kill)

    async def logs(
        self,
        container_id: str,
        stream: bool = False,
        follow: bool = False,
        tail: Optional[int] = None,
        since: Optional[datetime] = None,
    ) -> Any:
        """Get container logs."""
        client = self._get_client()
        loop = asyncio.get_event_loop()

        def _get_logs():
            try:
                container = client.containers.get(container_id)

                kwargs = {
                    "stream": stream,
                    "follow": follow,
                }

                if tail:
                    kwargs["tail"] = tail

                if since:
                    kwargs["since"] = since

                logs = container.logs(**kwargs)

                if stream:
                    # Return async generator
                    async def log_generator():
                        for line in logs:
                            yield line.decode("utf-8", errors="replace")

                    return log_generator()
                else:
                    return logs.decode("utf-8", errors="replace")

            except Exception as e:
                if "not found" in str(e).lower():
                    raise ResourceNotFoundError("Container", container_id)
                raise ContainerError(f"Failed to get logs: {str(e)}")

        return await loop.run_in_executor(None, _get_logs)

    async def status(self, container_id: str) -> ContainerStatus:
        """Get container status."""
        client = self._get_client()
        loop = asyncio.get_event_loop()

        def _get_status():
            try:
                container = client.containers.get(container_id)
                attrs = container.attrs

                state = attrs["State"]
                status = state["Status"]

                # Parse dates using proper date parser
                started_at = None
                if state.get("StartedAt"):
                    try:
                        started_at = dateparser.isoparse(state["StartedAt"])
                    except Exception as parse_error:
                        logger.warning(
                            f"Failed to parse StartedAt date: {parse_error}",
                            exc_info=True,
                            extra={
                                "error_id": "ERR_DATE_PARSE_FAILED",
                                "date_value": state.get("StartedAt")
                            }
                        )

                finished_at = None
                if state.get("FinishedAt") and state["FinishedAt"] != "0001-01-01T00:00:00Z":
                    try:
                        finished_at = dateparser.isoparse(state["FinishedAt"])
                    except Exception as parse_error:
                        logger.warning(
                            f"Failed to parse FinishedAt date: {parse_error}",
                            exc_info=True,
                            extra={
                                "error_id": "ERR_DATE_PARSE_FAILED",
                                "date_value": state.get("FinishedAt")
                            }
                        )

                try:
                    created_at = dateparser.isoparse(attrs["Created"])
                except Exception:
                    created_at = datetime.now(timezone.utc)  # Fallback

                return ContainerStatus(
                    id=ContainerId(container_id),
                    status=status,
                    created_at=created_at,
                    started_at=started_at,
                    finished_at=finished_at,
                    exit_code=state.get("ExitCode"),
                )

            except Exception as e:
                if "not found" in str(e).lower():
                    raise ResourceNotFoundError("Container", container_id)
                raise ContainerError(f"Failed to get status: {str(e)}")

        return await loop.run_in_executor(None, _get_status)

    async def exec(
        self,
        container_id: str,
        command: List[str],
        user: Optional[str] = None,
        working_dir: Optional[str] = None,
        environment: Optional[Dict[str, str]] = None,
    ) -> ContainerResult:
        """Execute a command in a running container."""
        client = self._get_client()
        loop = asyncio.get_event_loop()

        def _exec():
            try:
                container = client.containers.get(container_id)

                # Check if container is running
                if container.status != "running":
                    raise ContainerNotRunningError(f"Container {container_id} is not running")

                start_time = time.time()

                # Execute command
                exec_result = container.exec_run(
                    command,
                    user=user,
                    workdir=working_dir,
                    environment=environment,
                )

                duration_ms = int((time.time() - start_time) * 1000)

                # Parse output
                output = exec_result.output.decode("utf-8", errors="replace")

                return ContainerResult(
                    exit_code=exec_result.exit_code,
                    stdout=output,
                    stderr="",  # exec_run doesn't separate stderr
                    duration_ms=duration_ms,
                    container_id=ContainerId(container_id),
                )

            except ContainerNotRunningError:
                raise
            except Exception as e:
                if "not found" in str(e).lower():
                    raise ResourceNotFoundError("Container", container_id)
                raise ContainerError(f"Failed to execute command: {str(e)}")

        return await loop.run_in_executor(None, _exec)

    async def list_containers(
        self,
        all: bool = False,
        filters: Optional[Dict[str, Any]] = None,
    ) -> List[ContainerStatus]:
        """List containers."""
        client = self._get_client()
        loop = asyncio.get_event_loop()

        def _list():
            try:
                containers = client.containers.list(all=all, filters=filters)

                statuses = []
                for container in containers:
                    attrs = container.attrs
                    state = attrs["State"]

                    # Parse dates using proper date parser
                    started_at = None
                    if state.get("StartedAt"):
                        try:
                            started_at = dateparser.isoparse(state["StartedAt"])
                        except Exception as parse_error:
                            logger.warning(
                                f"Failed to parse StartedAt date: {parse_error}",
                                exc_info=True,
                                extra={
                                    "error_id": "ERR_CONTAINER_DATE_PARSE_STARTED_AT",
                                    "date_value": state.get("StartedAt")
                                }
                            )

                    finished_at = None
                    if state.get("FinishedAt") and state["FinishedAt"] != "0001-01-01T00:00:00Z":
                        try:
                            finished_at = dateparser.isoparse(state["FinishedAt"])
                        except Exception as parse_error:
                            logger.warning(
                                f"Failed to parse FinishedAt date: {parse_error}",
                                exc_info=True,
                                extra={
                                    "error_id": "ERR_CONTAINER_DATE_PARSE_FINISHED_AT",
                                    "date_value": state.get("FinishedAt")
                                }
                            )

                    try:
                        created_at = dateparser.isoparse(attrs["Created"])
                    except Exception as parse_error:
                        logger.warning(
                            f"Failed to parse Created date, using current time: {parse_error}",
                            exc_info=True,
                            extra={
                                "error_id": "ERR_CONTAINER_DATE_PARSE_CREATED",
                                "date_value": attrs.get("Created")
                            }
                        )
                        created_at = datetime.now(timezone.utc)  # Fallback

                    statuses.append(
                        ContainerStatus(
                            id=ContainerId(container.id),
                            status=state["Status"],
                            created_at=created_at,
                            started_at=started_at,
                            finished_at=finished_at,
                            exit_code=state.get("ExitCode"),
                        )
                    )

                return statuses

            except Exception as e:
                raise ContainerError(f"Failed to list containers: {str(e)}")

        return await loop.run_in_executor(None, _list)

    async def pull_image(
        self,
        image: str,
        tag: str = "latest",
        stream_callback: Optional[Callable] = None,
    ) -> None:
        """Pull a container image."""
        client = self._get_client()
        loop = asyncio.get_event_loop()

        def _pull():
            try:
                full_image = f"{image}:{tag}"

                if stream_callback:
                    for line in client.api.pull(image, tag=tag, stream=True, decode=True):
                        stream_callback(str(line))
                else:
                    client.images.pull(image, tag=tag)

            except Exception as e:
                if "not found" in str(e).lower():
                    raise ImageNotFoundError(f"Image not found: {image}:{tag}")
                elif "unauthorized" in str(e).lower() or "authentication" in str(e).lower():
                    raise AuthenticationError(f"Authentication failed for image: {image}:{tag}")
                raise ContainerError(f"Failed to pull image: {str(e)}")

        await loop.run_in_executor(None, _pull)

    async def image_exists(self, image: str, tag: str = "latest") -> bool:
        """Check if an image exists locally."""
        client = self._get_client()
        loop = asyncio.get_event_loop()

        def _check():
            try:
                full_image = f"{image}:{tag}"
                client.images.get(full_image)
                return True
            except Exception:
                return False

        return await loop.run_in_executor(None, _check)

    async def inspect(self, container_id: str) -> Dict[str, Any]:
        """Get detailed container information."""
        client = self._get_client()
        loop = asyncio.get_event_loop()

        def _inspect():
            try:
                container = client.containers.get(container_id)
                return container.attrs
            except Exception as e:
                if "not found" in str(e).lower():
                    raise ResourceNotFoundError("Container", container_id)
                raise ContainerError(f"Failed to inspect container: {str(e)}")

        return await loop.run_in_executor(None, _inspect)

    async def wait(
        self,
        container_id: str,
        timeout: Optional[int] = None,
    ) -> int:
        """Wait for a container to stop."""
        client = self._get_client()
        loop = asyncio.get_event_loop()

        def _wait():
            try:
                container = client.containers.get(container_id)
                result = container.wait(timeout=timeout)
                return result.get("StatusCode", 0)
            except Exception as e:
                if "not found" in str(e).lower():
                    raise ResourceNotFoundError("Container", container_id)
                elif "timeout" in str(e).lower():
                    raise ContainerTimeoutError(f"Wait timed out after {timeout}s")
                raise ContainerError(f"Failed to wait for container: {str(e)}")

        return await loop.run_in_executor(None, _wait)

    async def copy_to_container(
        self,
        container_id: str,
        source: str,
        destination: str,
    ) -> None:
        """Copy files to a container."""
        client = self._get_client()
        loop = asyncio.get_event_loop()

        def _copy():
            try:
                import tarfile
                import io
                from pathlib import Path

                container = client.containers.get(container_id)

                # Create tar archive of source
                tar_stream = io.BytesIO()
                with tarfile.open(fileobj=tar_stream, mode="w") as tar:
                    tar.add(source, arcname=Path(source).name)

                tar_stream.seek(0)
                container.put_archive(destination, tar_stream)

            except Exception as e:
                if "not found" in str(e).lower() and "container" in str(e).lower():
                    raise ResourceNotFoundError("Container", container_id)
                raise ContainerError(f"Failed to copy to container: {str(e)}")

        await loop.run_in_executor(None, _copy)

    async def copy_from_container(
        self,
        container_id: str,
        source: str,
        destination: str,
    ) -> None:
        """Copy files from a container."""
        client = self._get_client()
        loop = asyncio.get_event_loop()

        def _copy():
            try:
                import tarfile
                import io

                container = client.containers.get(container_id)

                # Get tar archive from container
                bits, stat = container.get_archive(source)

                # Extract tar archive
                tar_stream = io.BytesIO()
                for chunk in bits:
                    tar_stream.write(chunk)

                tar_stream.seek(0)
                with tarfile.open(fileobj=tar_stream, mode="r") as tar:
                    tar.extractall(destination)

            except Exception as e:
                if "not found" in str(e).lower() and "container" in str(e).lower():
                    raise ResourceNotFoundError("Container", container_id)
                raise ContainerError(f"Failed to copy from container: {str(e)}")

        await loop.run_in_executor(None, _copy)

    def close(self) -> None:
        """Close Docker client and clean up all resources."""
        if self._docker_client is not None:
            try:
                # Close the API client's session and adapter connection pools
                if hasattr(self._docker_client, 'api'):
                    api = self._docker_client.api
                    # Close HTTP session
                    if hasattr(api, '_session') and api._session:
                        try:
                            api._session.close()
                        except Exception:
                            pass
                    # Close adapters (which hold socket connections)
                    if hasattr(api, '_adapters') and api._adapters:
                        try:
                            for adapter in api._adapters.values():
                                if hasattr(adapter, 'close'):
                                    adapter.close()
                        except Exception:
                            pass
                    if hasattr(api, 'close'):
                        try:
                            api.close()
                        except Exception:
                            pass
            except Exception:
                logger.debug("Error cleaning up Docker API client", exc_info=True)

            try:
                self._docker_client.close()
            except Exception:
                logger.debug("Error closing Docker client", exc_info=True)
            finally:
                self._docker_client = None

            # Force garbage collection to ensure all socket connections are released
            # The docker-py library uses connection pools that may keep sockets open
            # even after closing. Multiple gc.collect() calls may be needed as some
            # pools release resources asynchronously.
            gc.collect()
            gc.collect()

    async def __aenter__(self):
        """Async context manager entry."""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """
        Async context manager exit with proper cleanup.

        Ensures cleanup happens even if exceptions occur.
        """
        try:
            self.close()
        except Exception as e:
            # Suppress cleanup errors to avoid masking original exception
            # but log for observability
            logger.debug(
                f"Cleanup error in docker container context manager, suppressed to avoid masking original exception",
                exc_info=True
            )
        return False  # Don't suppress exceptions
