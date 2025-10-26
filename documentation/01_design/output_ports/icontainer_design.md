# IContainer Output Port Design

## Overview

The `IContainer` port provides an abstraction for container orchestration and execution. This port is critical for running LLM providers (especially Claude Code) in isolated, controlled environments.

## Port Interface

```python
from abc import ABC, abstractmethod
from typing import Dict, List, Optional, Callable, Any
from dataclasses import dataclass
from pathlib import Path

class IContainer(ABC):
    """Interface for container orchestration."""

    @abstractmethod
    async def run(self,
                  image: str,
                  command: List[str],
                  volumes: Dict[str, str],
                  environment: Dict[str, str],
                  timeout: int = 300,
                  stream_callback: Optional[Callable] = None) -> ContainerResult:
        """
        Run a command in a container.

        Args:
            image: Container image name
            command: Command to execute
            volumes: Volume mounts (host_path: container_path:mode)
            environment: Environment variables
            timeout: Execution timeout in seconds
            stream_callback: Optional callback for streaming logs

        Returns:
            ContainerResult: Execution result

        Raises:
            ContainerExecutionError: Container execution failed
            ContainerTimeoutError: Execution timed out
        """
        pass

    @abstractmethod
    async def create(self,
                     image: str,
                     name: Optional[str] = None,
                     volumes: Optional[Dict[str, str]] = None,
                     environment: Optional[Dict[str, str]] = None) -> str:
        """Create a container. Returns container ID."""
        pass

    @abstractmethod
    async def start(self, container_id: str) -> None:
        """Start a container."""
        pass

    @abstractmethod
    async def stop(self, container_id: str, timeout: int = 10) -> None:
        """Stop a container."""
        pass

    @abstractmethod
    async def remove(self, container_id: str, force: bool = False) -> None:
        """Remove a container."""
        pass

    @abstractmethod
    async def logs(self,
                   container_id: str,
                   stream: bool = False,
                   follow: bool = False) -> Any:
        """Get container logs."""
        pass

    @abstractmethod
    async def status(self, container_id: str) -> ContainerStatus:
        """Get container status."""
        pass
```

## Data Models

```python
@dataclass
class ContainerResult:
    """Result from container execution."""
    exit_code: int
    stdout: str
    stderr: str
    duration_ms: int
    container_id: str

@dataclass
class ContainerStatus:
    """Container status information."""
    id: str
    status: str  # running, stopped, exited, etc.
    created_at: datetime
    started_at: Optional[datetime]
    finished_at: Optional[datetime]
```

## Adapter Implementations

### Docker Adapter

```python
class DockerContainerAdapter(IContainer):
    """Docker implementation."""

    def __init__(self):
        import docker
        self.client = docker.from_env()

    async def run(self,
                  image: str,
                  command: List[str],
                  volumes: Dict[str, str],
                  environment: Dict[str, str],
                  timeout: int = 300,
                  stream_callback: Optional[Callable] = None) -> ContainerResult:
        """Run command in Docker container."""
        container = self.client.containers.run(
            image,
            command=command,
            volumes=volumes,
            environment=environment,
            detach=True,
            remove=False
        )

        try:
            # Stream logs if callback provided
            if stream_callback:
                for line in container.logs(stream=True, follow=True):
                    await stream_callback(line.decode('utf-8'))

            # Wait for completion
            result = container.wait(timeout=timeout)

            return ContainerResult(
                exit_code=result['StatusCode'],
                stdout=container.logs(stdout=True, stderr=False).decode('utf-8'),
                stderr=container.logs(stdout=False, stderr=True).decode('utf-8'),
                duration_ms=0,  # Calculate from timestamps
                container_id=container.id
            )
        finally:
            container.remove(force=True)
```

### Fake Adapter (Testing)

```python
class FakeContainerAdapter(IContainer):
    """Mock container for testing (no actual execution)."""

    def __init__(self):
        self.execution_history: List[Dict[str, Any]] = []
        self.responses: Dict[str, ContainerResult] = {}

    async def run(self,
                  image: str,
                  command: List[str],
                  volumes: Dict[str, str],
                  environment: Dict[str, str],
                  timeout: int = 300,
                  stream_callback: Optional[Callable] = None) -> ContainerResult:
        """Simulate container execution."""
        self.execution_history.append({
            'image': image,
            'command': command,
            'volumes': volumes,
            'environment': environment
        })

        # Return predefined response or default success
        key = f"{image}:{' '.join(command)}"
        return self.responses.get(key, ContainerResult(
            exit_code=0,
            stdout="Mock output",
            stderr="",
            duration_ms=100,
            container_id="mock-container-id"
        ))
```

## Integration Points

### Used By
- ILLMProvider (ClaudeCodeAdapter)
- Agent Execution Services

### Dependencies
- None (standalone port)

## Implementation Notes

1. **Security**: Ensure containers run with minimal privileges
2. **Resource Limits**: Set CPU/memory limits for all containers
3. **Cleanup**: Always remove containers after execution
4. **Networking**: Isolate container networks when possible
5. **Volumes**: Mount volumes as read-only when possible
