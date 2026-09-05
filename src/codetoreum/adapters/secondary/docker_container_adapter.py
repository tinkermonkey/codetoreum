"""Docker adapter for IContainer interface."""

import asyncio
import gc
import io
import logging
import os
import re
import tarfile
import time
import uuid
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import docker
import docker.errors
from dateutil import parser as dateparser

from codetoreum.domain.types import ContainerId
from codetoreum.infrastructure.error_ids import ErrorRegistry
from codetoreum.infrastructure.observability.instrumentation import (
    add_span_attributes,
    instrument_async_function,
)
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
    ContainerHealthStatus,
    ContainerResult,
    ContainerStatus,
    IContainer,
)
from codetoreum.ports.output.failed_event_store import IFailedEventStore

logger = logging.getLogger(__name__)


@dataclass
class DockerConfig:
    """Configuration for Docker adapter."""

    # Docker connection
    docker_host: str | None = None  # Defaults to local socket
    tls_verify: bool = False
    cert_path: str | None = None

    # Container defaults
    default_timeout: int = 300  # 5 minutes
    remove_on_completion: bool = True
    default_user: str | None = None
    agent_network: str = field(default_factory=lambda: os.environ.get("AGENT_NETWORK", "bridge"))
    agent_otel_endpoint: str = field(
        default_factory=lambda: os.environ.get("AGENT_OTEL_ENDPOINT", "http://otel-collector:4317")
    )

    # Resource limits
    memory_limit: str | None = None  # e.g., "512m"
    cpu_limit: float | None = None  # e.g., 1.0 for 1 CPU

    # Logging
    log_driver: str = "json-file"

    # Write verification
    verify_workspace_writable: bool = True


class DockerContainerAdapter(IContainer):
    """
    Docker adapter for container operations.

    This adapter uses the Docker SDK for Python to manage containers.
    It implements all IContainer interface methods for Docker operations.
    """

    def __init__(
        self,
        config: DockerConfig | None = None,
        event_emitter: "Any | None" = None,
        event_bus: "Any | None" = None,
        failed_event_store: IFailedEventStore | None = None,
    ):
        """
        Initialize Docker adapter.

        Args:
            config: Docker configuration (optional, defaults to environment-based config)
            event_emitter: Optional IEventEmitter for emitting domain events
            event_bus: Optional EventBus for infrastructure events
            failed_event_store: Failed event store for routing failures to DLQ (INV-20)
        """
        self.config = config or DockerConfig()
        self._docker_client = None
        self.failed_event_store = failed_event_store
        self._event_emitter = event_emitter
        self._event_bus = event_bus
        self._host_workspace_path = self._detect_host_workspace_path()
        self._host_home_path = self._detect_host_home_path()
        self._validate_workspace_base()

    def _validate_workspace_base(self) -> None:
        """Validate that AGENT_WORKSPACE_BASE is under /workspace/, not /tmp/."""
        workspace_base = os.environ.get("AGENT_WORKSPACE_BASE")
        if workspace_base and workspace_base.startswith("/tmp/"):
            msg = (
                f"AGENT_WORKSPACE_BASE={workspace_base} is under /tmp/, which is not host-path-translated. "
                "Agent containers will receive empty volume mounts. "
                "Set AGENT_WORKSPACE_BASE=/workspace/codetoreum/agent-workspaces or similar path under /workspace/."
            )
            raise ContainerError(msg)

    @staticmethod
    def _detect_host_workspace_path() -> str:
        """Parse /proc/self/mountinfo to find the host path mapped to /workspace."""
        try:
            with open("/proc/self/mountinfo") as f:
                for line in f:
                    parts = line.split()
                    if len(parts) > 4 and parts[4] == "/workspace":
                        return parts[3]
        except Exception as e:
            logger.error("Failed to auto-detect host workspace: %s", e, exc_info=True)
        fallback = os.environ.get("HOST_WORKSPACE_PATH", "/workspace")
        logger.warning(
            "Could not auto-detect host workspace path; using HOST_WORKSPACE_PATH=%s. "
            "Agent containers may receive empty workspaces if this is wrong.",
            fallback,
        )
        return fallback

    # Placeholder values that ship in .env.example and should be treated as
    # "unset" rather than honoured. Otherwise a fresh bootstrap mounts an
    # empty placeholder dir into the agent container.
    _HOST_HOME_PLACEHOLDERS = frozenset({"/home/youruser", "/home/your-user", "<changeme>", ""})

    @staticmethod
    def _detect_host_home_path() -> str:
        """Read HOST_HOME env var. Warns if unset — Snap Docker breaks $HOME.

        Rejects known placeholder values so the auto-appended template from
        ``.env.example`` doesn't silently mount the wrong host directory.
        """
        host_home = os.environ.get("HOST_HOME", "").strip()
        if host_home and host_home not in DockerContainerAdapter._HOST_HOME_PLACEHOLDERS:
            return host_home

        if host_home:
            logger.warning(
                "HOST_HOME=%s looks like a placeholder; ignoring and falling back to $HOME. "
                "Set HOST_HOME=/home/<username> in .env to silence this.",
                host_home,
            )
        else:
            logger.warning(
                "HOST_HOME is not set. SSH/git mounts may fail if Docker is installed via Snap. "
                "Set HOST_HOME=/home/<username> in .env."
            )
        return os.environ.get("HOME", "/root")

    @staticmethod
    def _sanitize_container_name(name: str) -> str:
        """Sanitize container name to Docker naming constraints."""
        # Docker allows: [a-zA-Z0-9][a-zA-Z0-9_.-]*
        sanitized = re.sub(r"[^a-zA-Z0-9_.-]", "-", name)
        sanitized = re.sub(r"^[^a-zA-Z0-9]+", "", sanitized)
        sanitized = re.sub(r"-+", "-", sanitized)
        return sanitized

    def _build_agent_otel_env(
        self,
        execution_id: str,
        agent_name: str,
        project_id: str,
        work_item_id: str,
    ) -> dict[str, str]:
        """Build OTEL environment variables for agent container."""
        return {
            "CLAUDE_CODE_ENABLE_TELEMETRY": "1",
            "OTEL_METRICS_EXPORTER": "otlp",
            "OTEL_LOGS_EXPORTER": "otlp",
            "OTEL_EXPORTER_OTLP_ENDPOINT": self.config.agent_otel_endpoint,
            "OTEL_METRIC_EXPORT_INTERVAL": "10000",
            "OTEL_LOGS_EXPORT_INTERVAL": "5000",
            "OTEL_RESOURCE_ATTRIBUTES": (
                f"agent={agent_name},project={project_id}," f"execution_id={execution_id},work_item_id={work_item_id}"
            ),
        }

    async def _verify_workspace_writable(self, volume_spec: dict, working_dir: str) -> None:
        """
        Run a throwaway alpine container to verify workspace write access.
        Uses the Docker SDK directly (not self.run()) to avoid recursion.
        Makes a single attempt; raises ContainerError on failure.
        Retry logic (if needed) should be applied via infrastructure decorators.
        """
        test_filename = f".codetoreum_write_test_{uuid.uuid4().hex}"
        test_cmd = ["sh", "-c", f"touch {working_dir}/{test_filename} && rm {working_dir}/{test_filename}"]
        client = self._get_client()
        try:
            await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: client.containers.run(
                    "alpine:latest",
                    test_cmd,
                    volumes=volume_spec,
                    working_dir=working_dir,
                    remove=True,
                    user=self.config.default_user,
                ),
            )
        except Exception as e:
            msg = f"Workspace not writable — check volume mount permissions. " f"Volume: {volume_spec}. Error: {e}"
            raise ContainerError(msg) from e

    def _get_client(self):
        """Get or create Docker client."""
        if self._docker_client is None:
            try:
                if self.config.docker_host:
                    self._docker_client = docker.DockerClient(
                        base_url=self.config.docker_host,
                        tls=self.config.tls_verify,
                    )
                else:
                    self._docker_client = docker.from_env()

            except Exception as e:
                msg = f"Failed to connect to Docker: {e!s}"
                raise ContainerError(msg) from e

        return self._docker_client

    def _parse_volume_spec(self, volumes: dict[str, str]) -> dict[str, dict[str, str]]:
        """
        Parse volume specification with path traversal protection and host path translation.

        When running in a nested container (Level 2+), /workspace and $HOME are mounted
        from the host. This method translates container-local paths to host paths for
        mounting into child containers (Level 3+).

        Args:
            volumes: Volume mounts (host_path: container_path:mode)

        Returns:
            Docker SDK volume specification with translated host paths

        Raises:
            ValidationError: If volume specification is invalid or contains unsafe paths
        """
        docker_volumes = {}

        for host_path, spec in volumes.items():
            # Validate host path - resolve to absolute path and check for traversal
            try:
                resolved_host_path = Path(host_path).resolve()

                # Ensure host path is absolute
                if not resolved_host_path.is_absolute():
                    msg = f"Host path must be absolute: {host_path}"
                    raise ValidationError(msg)

            except (OSError, RuntimeError) as e:
                msg = f"Invalid host path '{host_path}': {e}"
                raise ValidationError(msg) from e

            # Translate paths that are under /workspace or $HOME to their host equivalents
            # This is necessary when running in nested containers
            translated_path = resolved_host_path
            try:
                if str(resolved_host_path).startswith("/workspace"):
                    # Translate /workspace paths to detected host path
                    relative = resolved_host_path.relative_to("/workspace")
                    translated_path = Path(self._host_workspace_path) / relative
                else:
                    # Check if path is under $HOME (only if HOME is set)
                    home_path = os.environ.get("HOME")
                    if home_path and str(resolved_host_path).startswith(home_path):
                        relative = resolved_host_path.relative_to(home_path)
                        translated_path = Path(self._host_home_path) / relative
            except ValueError:
                # Path is not under /workspace or $HOME, use as-is
                translated_path = resolved_host_path

            # Parse container_path:mode
            parts = spec.split(":")
            if len(parts) == 1:
                container_path = parts[0]
                mode = "rw"
            elif len(parts) == 2:
                container_path, mode = parts
            else:
                msg = f"Invalid volume spec: {spec}"
                raise ValidationError(msg)

            # Validate container path (should be absolute)
            if not container_path.startswith("/"):
                msg = f"Container path must be absolute (start with /): {container_path}"
                raise ValidationError(msg)

            # Validate mode
            if mode not in ["rw", "ro"]:
                msg = f"Invalid mount mode '{mode}'. Must be 'rw' (read-write) or 'ro' (read-only)"
                raise ValidationError(msg)

            docker_volumes[str(translated_path)] = {
                "bind": container_path,
                "mode": mode,
            }

        return docker_volumes

    def _try_reload_for_exit_code(self, container: Any, prior_wait_error: Exception | None = None) -> int:
        """Try to get exit code via reload() after wait() failed.

        Args:
            container: The container object
            prior_wait_error: The prior error from wait() if applicable, for context in error logging

        Returns:
            Exit code from container

        Raises:
            ContainerExecutionError: If exit code cannot be determined (container not found or reload fails).
                                    Container may have been OOM-killed, force-removed, or crashed, and
                                    the exit status cannot be recovered.
        """
        try:
            container.reload()
            return container.attrs["State"]["ExitCode"]
        except docker.errors.NotFound:
            # Container was removed - cannot determine exit code (may have been OOM-killed, force-removed, or crashed)
            container_id_str = container.short_id if container else "unknown"
            msg = (
                f"Container {container_id_str} was auto-removed before exit code could be retrieved. "
                "Cannot determine if container succeeded or failed. Container may have been OOM-killed, "
                "force-removed, or crashed, causing data loss or incomplete artifacts."
            )
            logger.error(
                msg,
                exc_info=True,
                extra={
                    "error_id": ErrorRegistry.ERR_CONTAINER_AUTO_REMOVED_AFTER_STREAMING,
                    "container_id": container_id_str,
                },
            )
            raise ContainerExecutionError(msg) from None
        except Exception as reload_error:
            container_id_str = container.short_id if container else "unknown"

            if prior_wait_error:
                # Dual failure: both wait() and reload() failed
                logger.error(
                    f"Failed to retrieve exit code via both wait() and reload(): "
                    f"{prior_wait_error} (wait), {reload_error} (reload). Container ID: {container_id_str}",
                    exc_info=True,
                    extra={
                        "error_id": ErrorRegistry.ERR_CONTAINER_DUAL_RETRIEVAL_FAILED,
                        "container_id": container_id_str,
                    },
                )
                raise ContainerExecutionError(
                    f"Failed to retrieve container exit code: {prior_wait_error}"
                ) from prior_wait_error
            # Single failure: wait() threw NotFound (expected), reload() failed
            logger.error(
                f"Failed to reload container {container_id_str} to retrieve exit code: {reload_error}",
                exc_info=True,
                extra={
                    "error_id": ErrorRegistry.ERR_CONTAINER_RELOAD_FAILED,
                    "container_id": container_id_str,
                },
            )
            raise ContainerExecutionError(
                f"Failed to retrieve container exit code: {reload_error}"
            ) from reload_error

    @instrument_async_function(
        name="container.run",
        attributes={
            "service": "docker_container_adapter",
            "operation": "run",
        },
        capture_args=False,
        capture_result=False,
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
        """Run a command in a container.

        Creates a span named "container.run" with service and operation attributes.

        Args:
            image: Docker image name to run
            command: Command and arguments to execute
            volumes: Volume mount mappings
            environment: Environment variables for the container
            timeout: Execution timeout in seconds
            stream_callback: Optional callback for stream output lines

        Returns:
            ContainerResult with exit code, stdout, and stderr

        Raises:
            ValidationError: If image name is missing
            ImageNotFoundError: If image not found
            ContainerTimeoutError: If execution exceeds timeout
            ContainerExecutionError: On execution failure
        """
        if not image:
            msg = "Image name is required"
            raise ValidationError(msg)

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
            "network": self.config.agent_network,
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
            container_id = None
            start_time = time.time()
            try:
                # Check if image exists locally
                try:
                    client.images.get(image)
                except docker.errors.ImageNotFound as e:
                    msg = f"Image not found: {image}"
                    raise ImageNotFoundError(msg) from e
                except docker.errors.APIError as e:
                    # Re-raise other Docker errors as ContainerExecutionError
                    msg = f"Failed to check image: {e!s}"
                    raise ContainerExecutionError(msg) from e

                # Create and start container with auto-removal enabled
                container = client.containers.run(**container_config)
                container_id = container.id

                # Buffer for collecting logs
                log_buffer = []

                # Always stream logs to capture output before container is auto-removed
                # Docker auto-removes the container after the stream ends
                exit_code = None
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
                                        "error_id": ErrorRegistry.ERR_CONTAINER_KILL_FAILED,
                                        "container_id": container.short_id,
                                    },
                                )
                            msg = f"Container execution timed out after {timeout}s"
                            raise ContainerTimeoutError(msg)

                        decoded_line = line.decode("utf-8", errors="replace")
                        log_buffer.append(decoded_line)

                        # Call user callback if provided
                        if stream_callback:
                            stream_callback(decoded_line)

                    # When streaming completes, container has finished
                    # Get exit code using wait() which is more reliable than reload()
                    # when auto-remove is enabled
                    try:
                        result = container.wait(timeout=5)
                        exit_code = result.get("StatusCode", 1)
                    except docker.errors.NotFound:
                        # Container was already removed - expected with remove_on_completion=True
                        # Try reload as fallback
                        exit_code = self._try_reload_for_exit_code(container)
                    except Exception as wait_error:
                        # Docker API error during wait (not NotFound) - log and try reload as fallback
                        logger.warning(
                            f"Failed to wait for container exit code: {wait_error}",
                            exc_info=True,
                            extra={
                                "error_id": ErrorRegistry.ERR_CONTAINER_WAIT_FAILED,
                                "container_id": container.short_id if container else "unknown",
                            },
                        )
                        exit_code = self._try_reload_for_exit_code(container, prior_wait_error=wait_error)

                    container_id = ContainerId(container_id)

                except Exception as e:
                    # If we get here due to timeout, re-raise it
                    if isinstance(e, ContainerTimeoutError):
                        raise
                    # If container was removed during streaming, we cannot determine its exit status
                    # The container may have been OOM-killed, force-removed, or crashed.
                    # Reporting success (exit_code=0) would cause workflows to proceed with
                    # potentially missing or incomplete artifacts - this is unacceptable.
                    if "404" in str(e) or "not found" in str(e).lower():
                        container_id_str = container.short_id if container else "unknown"
                        msg = (
                            f"Container disappeared during log streaming (possibly OOM-killed, "
                            f"force-removed, or crashed). Cannot determine exit status. "
                            f"Logs captured: {len(log_buffer)} lines. Container ID: {container_id_str}"
                        )
                        logger.error(
                            msg,
                            exc_info=True,
                            extra={
                                "error_id": ErrorRegistry.ERR_CONTAINER_DISAPPEARED_DURING_STREAMING,
                                "container_id": container_id_str,
                                "logs_captured": len(log_buffer),
                            },
                        )
                        raise ContainerExecutionError(msg) from e
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

            except ContainerError:
                # Re-raise port exceptions (ImageNotFoundError, ContainerExecutionError, ContainerTimeoutError)
                # without reprocessing to preserve exception chain
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
                                "error_id": ErrorRegistry.ERR_CONTAINER_CLEANUP_FAILED,
                                "container_id": container.short_id if container else "unknown",
                            },
                        )

                msg = f"Container execution failed: {e!s}"
                raise ContainerExecutionError(msg) from e

        try:
            # Create executor task for cancellation support
            executor_task = loop.run_in_executor(None, _run_container)

            # Await with cancellation support
            result = await executor_task

            # Add execution metrics to span after returning from executor
            add_span_attributes(
                **{
                    "container.id": str(result.container_id),
                    "container.exit_code": result.exit_code,
                    "container.duration_seconds": result.duration_ms / 1000.0,
                    "container.failed": result.exit_code != 0,
                }
            )

            return result

        except asyncio.CancelledError:
            # Handle cancellation - the container might still be running
            if executor_task and not executor_task.done():
                executor_task.cancel()
            raise
        except (ContainerError, ValidationError, ImageNotFoundError):
            raise
        except Exception as e:
            msg = f"Unexpected error: {e!s}"
            raise ContainerExecutionError(msg) from e

    @instrument_async_function(
        name="container.create",
        attributes={
            "service": "docker_container_adapter",
            "operation": "create",
        },
        capture_args=False,
        capture_result=False,
    )
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
        """Create a container without starting it.

        Creates a span named "container.create" with service and operation attributes.

        Args:
            image: Docker image name to use
            name: Optional container name
            command: Optional command to run
            volumes: Optional volume mount mappings
            environment: Optional environment variables
            working_dir: Optional working directory
            user: Optional user to run as
            network: Optional network to connect to
            labels: Optional labels for the container

        Returns:
            Container ID as string

        Raises:
            ImageNotFoundError: If image not found
            ContainerError: On creation failure
        """
        client = self._get_client()

        # Sanitize container name
        sanitized_name = None
        if name:
            sanitized_name = self._sanitize_container_name(name)
            # Convert empty string to None so Docker auto-generates a name
            sanitized_name = sanitized_name or None

        # Parse and translate volumes
        translated_volumes = {}
        if volumes:
            translated_volumes = self._parse_volume_spec(volumes)

        # Merge environment with OTEL vars
        merged_env = dict(environment or {})
        if labels:
            otel_env = self._build_agent_otel_env(
                execution_id=labels.get("org.codetoreum.execution_id", "unknown"),
                agent_name=labels.get("org.codetoreum.agent", "unknown"),
                project_id=labels.get("org.codetoreum.project", "unknown"),
                work_item_id=labels.get("org.codetoreum.work_item_id", "unknown"),
            )
            merged_env.update(otel_env)

        # Verify workspace write access before creating container (async, outside executor)
        if self.config.verify_workspace_writable and translated_volumes:
            workspace_volume = {k: v for k, v in translated_volumes.items() if v.get("bind") == "/workspace"}
            if workspace_volume:
                await self._verify_workspace_writable(workspace_volume, working_dir or "/workspace")

        container_config = {
            "image": image,
            "name": sanitized_name,
            "command": command,
            "environment": merged_env,
            "detach": True,
            "working_dir": working_dir,
            "user": user or self.config.default_user,
            "network": network or self.config.agent_network,
            "labels": labels or {},
        }

        if translated_volumes:
            container_config["volumes"] = translated_volumes

        loop = asyncio.get_event_loop()

        def _create():
            try:
                # Check image exists
                try:
                    client.images.get(image)
                except docker.errors.ImageNotFound as e:
                    msg = f"Image not found: {image}"
                    raise ImageNotFoundError(msg) from e
                except docker.errors.APIError as e:
                    # Re-raise other Docker errors as ContainerError
                    msg = f"Failed to check image: {e!s}"
                    raise ContainerError(msg) from e

                container = client.containers.create(**container_config)
                return container.id

            except (ImageNotFoundError, ContainerError):
                raise
            except Exception as e:
                msg = f"Failed to create container: {e!s}"
                raise ContainerError(msg) from e

        container_id = await loop.run_in_executor(None, _create)

        # Add container-specific span attributes after returning from executor
        add_span_attributes(
            **{
                "container.id": container_id,
                "container.image": image,
                # Extract context from labels if available
                **(
                    {
                        "work_item.id": labels.get("org.codetoreum.work_item_id"),
                        "agent.type": labels.get("org.codetoreum.agent"),
                    }
                    if labels
                    else {}
                ),
            }
        )

        return container_id

    @instrument_async_function(
        name="container.start",
        attributes={
            "service": "docker_container_adapter",
            "operation": "start",
        },
        capture_args=False,
    )
    async def start(self, container_id: str) -> None:
        """Start a container.

        Creates a span named "container.start" with service and operation attributes.

        Args:
            container_id: ID of container to start

        Raises:
            ResourceNotFoundError: If container not found
            ContainerError: On start failure
        """
        client = self._get_client()
        loop = asyncio.get_event_loop()

        def _start():
            try:
                container = client.containers.get(container_id)
                container.start()
            except Exception as e:
                if "not found" in str(e).lower():
                    msg = "Container"
                    raise ResourceNotFoundError(msg, container_id) from e
                msg = f"Failed to start container: {e!s}"
                raise ContainerError(msg) from e

        await loop.run_in_executor(None, _start)

        # Add start attributes to span
        add_span_attributes(
            **{
                "container.id": container_id,
                "container.started": True,
            }
        )

    @instrument_async_function(
        name="container.stop",
        attributes={
            "service": "docker_container_adapter",
            "operation": "stop",
        },
        capture_args=False,
    )
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
                    msg = "Container"
                    raise ResourceNotFoundError(msg, container_id) from e
                msg = f"Failed to stop container: {e!s}"
                raise ContainerError(msg) from e

        await loop.run_in_executor(None, _stop)

        # Add stop attributes to span
        add_span_attributes(
            **{
                "container.id": container_id,
                "container.stopped": True,
            }
        )

    @instrument_async_function(
        name="container.remove",
        attributes={
            "service": "docker_container_adapter",
            "operation": "remove",
        },
        capture_args=False,
    )
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
                    # Container already removed - still success
                    msg = "Container"
                    raise ResourceNotFoundError(msg, container_id) from e
                msg = f"Failed to remove container: {e!s}"
                raise ContainerError(msg) from e

        try:
            await loop.run_in_executor(None, _remove)
        except ResourceNotFoundError:
            # Container was already removed, add attributes and re-raise
            add_span_attributes(
                **{
                    "container.id": container_id,
                    "container.removed": True,
                    "container.already_removed": True,
                }
            )
            raise

        # Add cleanup attributes to span on success
        add_span_attributes(
            **{
                "container.id": container_id,
                "container.removed": True,
            }
        )

    @instrument_async_function(
        name="container.kill",
        attributes={
            "service": "docker_container_adapter",
            "operation": "kill",
        },
        capture_args=True,
    )
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
                    msg = "Container"
                    raise ResourceNotFoundError(msg, container_id) from e
                msg = f"Failed to kill container: {e!s}"
                raise ContainerError(msg) from e

        await loop.run_in_executor(None, _kill)

    @instrument_async_function(
        name="container.logs",
        attributes={
            "service": "docker_container_adapter",
            "operation": "logs",
        },
        capture_args=True,
        capture_result=False,
    )
    async def logs(
        self,
        container_id: str,
        stream: bool = False,
        follow: bool = False,
        tail: int | None = None,
        since: datetime | None = None,
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
                return logs.decode("utf-8", errors="replace")

            except Exception as e:
                if "not found" in str(e).lower():
                    msg = "Container"
                    raise ResourceNotFoundError(msg, container_id) from e
                msg = f"Failed to get logs: {e!s}"
                raise ContainerError(msg) from e

        return await loop.run_in_executor(None, _get_logs)

    @instrument_async_function(
        name="container.status",
        attributes={
            "service": "docker_container_adapter",
            "operation": "status",
        },
        capture_args=True,
        capture_result=False,
    )
    async def status(self, container_id: str) -> ContainerStatus:
        """Get container status.

        NOTE: If date parsing fails for created_at, started_at, or finished_at, the method
        falls back to datetime.now(UTC) for created_at and None for started_at/finished_at.
        Callers should be aware that created_at may be a fabricated value if the original
        date was unparseable (logged at WARN level with context).
        """
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
                                "date_value": state.get("StartedAt"),
                            },
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
                                "date_value": state.get("FinishedAt"),
                            },
                        )

                try:
                    created_at = dateparser.isoparse(attrs["Created"])
                except Exception as parse_error:
                    logger.warning(
                        f"Failed to parse Created date, using current time: {parse_error}",
                        exc_info=True,
                        extra={
                            "error_id": "ERR_DATE_PARSE_FAILED",
                            "date_value": attrs.get("Created"),
                        },
                    )
                    created_at = datetime.now(UTC)  # Fallback

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
                    msg = "Container"
                    raise ResourceNotFoundError(msg, container_id) from e
                msg = f"Failed to get status: {e!s}"
                raise ContainerError(msg) from e

        return await loop.run_in_executor(None, _get_status)

    @instrument_async_function(
        name="container.exec",
        attributes={
            "service": "docker_container_adapter",
            "operation": "exec",
        },
        capture_args=True,
        capture_result=False,
    )
    async def exec(
        self,
        container_id: str,
        command: list[str] | tuple[str, ...],
        user: str | None = None,
        working_dir: str | None = None,
        environment: dict[str, str] | Mapping[str, str] | None = None,
    ) -> ContainerResult:
        """Execute a command in a running container."""
        client = self._get_client()
        loop = asyncio.get_event_loop()

        def _exec():
            try:
                container = client.containers.get(container_id)

                # Check if container is running
                if container.status != "running":
                    msg = f"Container {container_id} is not running"
                    raise ContainerNotRunningError(msg)

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
                    msg = "Container"
                    raise ResourceNotFoundError(msg, container_id) from e
                msg = f"Failed to execute command: {e!s}"
                raise ContainerError(msg) from e

        return await loop.run_in_executor(None, _exec)

    @instrument_async_function(
        name="container.list_containers",
        attributes={
            "service": "docker_container_adapter",
            "operation": "list_containers",
        },
        capture_args=True,
        capture_result=False,
    )
    async def list_containers(
        self,
        all: bool = False,
        filters: dict[str, Any] | None = None,
    ) -> list[ContainerStatus]:
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
                                    "date_value": state.get("StartedAt"),
                                },
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
                                    "date_value": state.get("FinishedAt"),
                                },
                            )

                    try:
                        created_at = dateparser.isoparse(attrs["Created"])
                    except Exception as parse_error:
                        logger.warning(
                            f"Failed to parse Created date, using current time: {parse_error}",
                            exc_info=True,
                            extra={
                                "error_id": "ERR_CONTAINER_DATE_PARSE_CREATED",
                                "date_value": attrs.get("Created"),
                            },
                        )
                        created_at = datetime.now(UTC)  # Fallback

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
                msg = f"Failed to list containers: {e!s}"
                raise ContainerError(msg) from e

        return await loop.run_in_executor(None, _list)

    @instrument_async_function(
        name="container.pull_image",
        attributes={
            "service": "docker_container_adapter",
            "operation": "pull_image",
        },
        capture_args=True,
    )
    async def pull_image(
        self,
        image: str,
        tag: str = "latest",
        stream_callback: Callable | None = None,
    ) -> None:
        """Pull a container image."""
        client = self._get_client()
        loop = asyncio.get_event_loop()

        def _pull():
            try:
                if stream_callback:
                    for line in client.api.pull(image, tag=tag, stream=True, decode=True):
                        stream_callback(str(line))
                else:
                    client.images.pull(image, tag=tag)

            except Exception as e:
                if "not found" in str(e).lower():
                    msg = f"Image not found: {image}:{tag}"
                    raise ImageNotFoundError(msg) from e
                if "unauthorized" in str(e).lower() or "authentication" in str(e).lower():
                    msg = f"Authentication failed for image: {image}:{tag}"
                    raise AuthenticationError(msg) from e
                msg = f"Failed to pull image: {e!s}"
                raise ContainerError(msg) from e

        await loop.run_in_executor(None, _pull)

    @instrument_async_function(
        name="container.image_exists",
        attributes={
            "service": "docker_container_adapter",
            "operation": "image_exists",
        },
        capture_args=True,
        capture_result=False,
    )
    async def image_exists(self, image: str, tag: str = "latest") -> bool:
        """Check if an image exists locally."""
        client = self._get_client()
        loop = asyncio.get_event_loop()

        def _check():
            try:
                full_image = f"{image}:{tag}"
                client.images.get(full_image)
                return True
            except docker.errors.ImageNotFound:
                return False
            except docker.errors.APIError as e:
                # For other errors (network, auth, etc), log and raise
                logger.warning(
                    f"Failed to check if image exists: {e}",
                    exc_info=True,
                    extra={
                        "error_id": "ERR_IMAGE_CHECK_FAILED",
                        "image": image,
                        "tag": tag,
                    },
                )
                msg = f"Failed to check if image exists: {e!s}"
                raise ContainerError(msg) from e

        return await loop.run_in_executor(None, _check)

    @instrument_async_function(
        name="container.inspect",
        attributes={
            "service": "docker_container_adapter",
            "operation": "inspect",
        },
        capture_args=True,
        capture_result=False,
    )
    async def inspect(self, container_id: str) -> dict[str, Any]:
        """Get detailed container information."""
        client = self._get_client()
        loop = asyncio.get_event_loop()

        def _inspect():
            try:
                container = client.containers.get(container_id)
                return container.attrs
            except Exception as e:
                if "not found" in str(e).lower():
                    msg = "Container"
                    raise ResourceNotFoundError(msg, container_id) from e
                msg = f"Failed to inspect container: {e!s}"
                raise ContainerError(msg) from e

        return await loop.run_in_executor(None, _inspect)

    @instrument_async_function(
        name="container.wait",
        attributes={
            "service": "docker_container_adapter",
            "operation": "wait",
        },
        capture_args=False,
        capture_result=False,
    )
    async def wait(
        self,
        container_id: str,
        timeout: int | None = None,
    ) -> int:
        """Wait for a container to stop."""
        client = self._get_client()
        loop = asyncio.get_event_loop()
        start_time = time.time()

        def _wait():
            try:
                container = client.containers.get(container_id)
                result = container.wait(timeout=timeout)
                exit_code = result.get("StatusCode", 1)
                return exit_code
            except Exception as e:
                if "not found" in str(e).lower():
                    msg = "Container"
                    raise ResourceNotFoundError(msg, container_id) from e
                if "timeout" in str(e).lower():
                    msg = f"Wait timed out after {timeout}s"
                    raise ContainerTimeoutError(msg) from e
                msg = f"Failed to wait for container: {e!s}"
                raise ContainerError(msg) from e

        exit_code = await loop.run_in_executor(None, _wait)
        duration_seconds = time.time() - start_time

        # Add wait attributes to span
        add_span_attributes(
            **{
                "container.id": container_id,
                "container.exit_code": exit_code,
                "container.wait_duration_seconds": duration_seconds,
            }
        )

        return exit_code

    @instrument_async_function(
        name="container.copy_to_container",
        attributes={
            "service": "docker_container_adapter",
            "operation": "copy_to_container",
        },
        capture_args=True,
    )
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
                container = client.containers.get(container_id)

                # Create tar archive of source
                tar_stream = io.BytesIO()
                with tarfile.open(fileobj=tar_stream, mode="w") as tar:
                    tar.add(source, arcname=Path(source).name)

                tar_stream.seek(0)
                container.put_archive(destination, tar_stream)

            except Exception as e:
                if "not found" in str(e).lower() and "container" in str(e).lower():
                    msg = "Container"
                    raise ResourceNotFoundError(msg, container_id) from e
                msg = f"Failed to copy to container: {e!s}"
                raise ContainerError(msg) from e

        await loop.run_in_executor(None, _copy)

    @instrument_async_function(
        name="container.get_file_content",
        attributes={
            "service": "docker_container_adapter",
            "operation": "get_file_content",
        },
        capture_args=True,
    )
    async def get_file_content(
        self,
        container_id: str,
        file_path: str,
    ) -> bytes:
        """
        Get file content from a container's output directory.

        Args:
            container_id: Container identifier
            file_path: Path to file within container (relative to /output/)

        Returns:
            File content as bytes

        Raises:
            ResourceNotFoundError: If container or file doesn't exist
            ContainerError: If read operation failed
        """
        # Validate file_path to prevent traversal attacks
        if ".." in file_path or file_path.startswith("/"):
            msg = f"Invalid file path: {file_path}. Path must be relative to /output/ and cannot contain '..' or start with '/'"
            raise ValidationError(msg)

        client = self._get_client()
        loop = asyncio.get_event_loop()

        def _get_file():
            try:
                container = client.containers.get(container_id)

                # Construct full path to file in /output/ directory
                full_path = f"/output/{file_path}"

                # Get file from container via tar archive
                bits, _stat = container.get_archive(full_path)

                # Extract tar archive to get file content
                tar_stream = io.BytesIO()
                for chunk in bits:
                    tar_stream.write(chunk)

                tar_stream.seek(0)
                with tarfile.open(fileobj=tar_stream, mode="r") as tar:
                    # Docker's get_archive returns a tar where the member name
                    # is the basename, not the full path. Iterate through members
                    # and select the first file-type member.
                    for member in tar.getmembers():
                        if member.isfile():
                            extracted_file = tar.extractfile(member)
                            if extracted_file is None:
                                msg = f"Failed to extract file content: {file_path}"
                                raise ContainerError(msg)
                            return extracted_file.read()

                    # No file found in archive
                    msg = f"File not found in container output: {file_path}"
                    raise ResourceNotFoundError(msg, file_path)

            except (ContainerError, ResourceNotFoundError):
                # Re-raise port exceptions without reprocessing to preserve exception chain
                raise
            except Exception as e:
                if "not found" in str(e).lower():
                    if "container" in str(e).lower():
                        msg = "Container"
                        raise ResourceNotFoundError(msg, container_id) from e
                    msg = f"File not found in container output: {file_path}"
                    raise ResourceNotFoundError(msg, file_path) from e
                msg = f"Failed to get file content from container: {e!s}"
                raise ContainerError(msg) from e

        return await loop.run_in_executor(None, _get_file)

    def close(self) -> None:
        """Close Docker client and clean up all resources."""
        if self._docker_client is not None:
            try:
                # Close the API client's session and adapter connection pools
                if hasattr(self._docker_client, "api"):
                    api = self._docker_client.api
                    # Close HTTP session
                    if hasattr(api, "_session") and api._session:
                        try:
                            api._session.close()
                        except Exception as e:
                            logger.warning(
                                f"Error closing Docker API session: {e}",
                                exc_info=True,
                                extra={"error_id": ErrorRegistry.ERR_INFRASTRUCTURE_ERROR},
                            )
                    # Close adapters (which hold socket connections)
                    if hasattr(api, "_adapters") and api._adapters:
                        try:
                            for adapter in api._adapters.values():
                                if hasattr(adapter, "close"):
                                    adapter.close()
                        except Exception as e:
                            logger.warning(
                                f"Error closing Docker API adapters: {e}",
                                exc_info=True,
                                extra={"error_id": ErrorRegistry.ERR_INFRASTRUCTURE_ERROR},
                            )
                    if hasattr(api, "close"):
                        try:
                            api.close()
                        except Exception as e:
                            logger.warning(
                                f"Error closing Docker API: {e}",
                                exc_info=True,
                                extra={"error_id": ErrorRegistry.ERR_INFRASTRUCTURE_ERROR},
                            )
            except Exception as e:
                logger.warning(
                    f"Error cleaning up Docker API client: {e}",
                    exc_info=True,
                    extra={"error_id": ErrorRegistry.ERR_INFRASTRUCTURE_ERROR},
                )

            try:
                self._docker_client.close()
            except Exception as e:
                logger.warning(
                    f"Error closing Docker client: {e}",
                    exc_info=True,
                    extra={"error_id": ErrorRegistry.ERR_INFRASTRUCTURE_ERROR},
                )
            finally:
                self._docker_client = None

            # Force garbage collection to ensure all socket connections are released
            # The docker-py library uses connection pools that may keep sockets open
            # even after closing. Multiple gc.collect() calls may be needed as some
            # pools release resources asynchronously.
            gc.collect()
            gc.collect()

    @instrument_async_function(
        name="container.network_create",
        attributes={
            "service": "docker_container_adapter",
            "operation": "network_create",
        },
        capture_args=True,
    )
    async def network_create(self, name: str, driver: str = "bridge") -> str:
        """Create a Docker network."""
        if not isinstance(name, str) or not name:
            raise ValidationError("name must be a non-empty string")
        if not isinstance(driver, str) or not driver:
            raise ValidationError("driver must be a non-empty string")

        client = self._get_client()
        loop = asyncio.get_event_loop()

        def _create() -> str:
            try:
                network = client.networks.create(name=name, driver=driver)
                return str(network.id)
            except Exception as e:
                logger.error(
                    f"Failed to create network {name}: {e}",
                    exc_info=True,
                    extra={"error_id": ErrorRegistry.ERR_INFRASTRUCTURE_ERROR},
                )
                raise ContainerError(f"Failed to create network {name}: {e!s}") from e

        return await loop.run_in_executor(None, _create)

    @instrument_async_function(
        name="container.health_check",
        attributes={
            "service": "docker_container_adapter",
            "operation": "health_check",
        },
        capture_args=True,
    )
    async def health_check(self, container_id: str) -> ContainerHealthStatus:
        """Report Docker container health.

        Reads `State.Health.Status` from `container.attrs`. Returns `UNKNOWN`
        when the image has no HEALTHCHECK configured (no `Health` field).
        """
        client = self._get_client()
        loop = asyncio.get_event_loop()

        def _check() -> ContainerHealthStatus:
            try:
                container = client.containers.get(container_id)
                container.reload()
                state = container.attrs.get("State", {}) or {}
                health = state.get("Health")
                if not health:
                    return ContainerHealthStatus.UNKNOWN
                status = health.get("Status", "").lower()
                if status == "healthy":
                    return ContainerHealthStatus.HEALTHY
                if status == "unhealthy":
                    return ContainerHealthStatus.UNHEALTHY
                if status == "starting":
                    return ContainerHealthStatus.STARTING
                return ContainerHealthStatus.UNKNOWN
            except docker.errors.NotFound as e:
                raise ResourceNotFoundError("Container", container_id) from e
            except Exception as e:
                logger.error(
                    f"Failed to read health for {container_id}: {e}",
                    exc_info=True,
                    extra={"error_id": ErrorRegistry.ERR_INFRASTRUCTURE_ERROR},
                )
                raise ContainerError(f"Failed to read health: {e!s}") from e

        return await loop.run_in_executor(None, _check)

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
                f"Cleanup error in docker container context manager ({type(e).__name__}: {e}), suppressed to avoid masking original exception",
                exc_info=True,
            )
        return False  # Don't suppress exceptions
