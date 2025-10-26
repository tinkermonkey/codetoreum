# Docker External System - Detailed Design

## Overview

Docker provides container isolation and execution environments for agent operations in the Codetoreum platform. This external system is critical for workspace isolation, dependency management, and secure agent execution. This document details the abstraction layer, container lifecycle management, and mock implementations.

## System Purpose

**Primary Functions**:
1. Isolated agent execution environments
2. Project-specific dependency management
3. Development environment setup and verification
4. Long-running repair cycle containers
5. Workspace isolation and security
6. Resource management and cleanup

## Port Interface Design

### IContainer Interface

```python
from abc import ABC, abstractmethod
from typing import List, Dict, Optional, Any
from dataclasses import dataclass
from pathlib import Path
from enum import Enum

class ContainerStatus(Enum):
    """Container lifecycle states."""
    CREATED = "created"
    RUNNING = "running"
    PAUSED = "paused"
    EXITED = "exited"
    DEAD = "dead"

@dataclass
class ContainerConfig:
    """Configuration for container creation."""
    image: str                           # Image name:tag
    name: Optional[str] = None           # Container name
    command: Optional[List[str]] = None  # Command to run
    entrypoint: Optional[List[str]] = None
    working_dir: str = "/workspace"
    user: str = "1000:1000"              # UID:GID
    environment: Dict[str, str] = None
    volumes: Dict[str, Dict[str, str]] = None  # {host_path: {bind: container_path, mode: rw/ro}}
    network: Optional[str] = None
    auto_remove: bool = False            # --rm flag
    detached: bool = False               # -d flag
    stdin_open: bool = False             # -i flag
    tty: bool = False                    # -t flag

@dataclass
class ContainerResult:
    """Result from container execution."""
    exit_code: int
    stdout: str
    stderr: str
    container_id: str
    duration_seconds: float

@dataclass
class ContainerInfo:
    """Information about a container."""
    id: str
    name: str
    image: str
    status: ContainerStatus
    created_at: str
    started_at: Optional[str]
    finished_at: Optional[str]
    exit_code: Optional[int]

@dataclass
class ImageInfo:
    """Information about an image."""
    id: str
    tags: List[str]
    created: str
    size_bytes: int

class IContainer(ABC):
    """
    Port interface for container operations.

    Abstracts Docker, Podman, and mock implementations.
    """

    # Container Lifecycle
    @abstractmethod
    async def create(self, config: ContainerConfig) -> str:
        """
        Create a container.

        Args:
            config: Container configuration

        Returns:
            Container ID
        """
        pass

    @abstractmethod
    async def start(self, container_id: str) -> None:
        """Start a container."""
        pass

    @abstractmethod
    async def stop(
        self,
        container_id: str,
        timeout: int = 10
    ) -> None:
        """Stop a container gracefully."""
        pass

    @abstractmethod
    async def kill(self, container_id: str) -> None:
        """Force kill a container."""
        pass

    @abstractmethod
    async def remove(
        self,
        container_id: str,
        force: bool = False
    ) -> None:
        """Remove a container."""
        pass

    # Container Execution
    @abstractmethod
    async def run(self, config: ContainerConfig) -> ContainerResult:
        """
        Create and run a container to completion.

        Equivalent to: docker run
        """
        pass

    @abstractmethod
    async def exec(
        self,
        container_id: str,
        command: List[str],
        working_dir: Optional[str] = None,
        environment: Optional[Dict[str, str]] = None,
        stream_callback: Optional[Callable[[str], None]] = None
    ) -> ContainerResult:
        """
        Execute command in running container.

        Equivalent to: docker exec
        """
        pass

    # Container Inspection
    @abstractmethod
    async def inspect(self, container_id: str) -> ContainerInfo:
        """Get detailed container information."""
        pass

    @abstractmethod
    async def list(
        self,
        all: bool = False,
        filters: Optional[Dict[str, str]] = None
    ) -> List[ContainerInfo]:
        """List containers."""
        pass

    @abstractmethod
    async def logs(
        self,
        container_id: str,
        follow: bool = False,
        tail: Optional[int] = None,
        stream_callback: Optional[Callable[[str], None]] = None
    ) -> str:
        """Retrieve container logs."""
        pass

    # Image Management
    @abstractmethod
    async def build_image(
        self,
        dockerfile_path: Path,
        context_path: Path,
        tag: str,
        build_args: Optional[Dict[str, str]] = None
    ) -> str:
        """
        Build image from Dockerfile.

        Returns:
            Image ID
        """
        pass

    @abstractmethod
    async def inspect_image(self, image_name: str) -> ImageInfo:
        """Get image information."""
        pass

    @abstractmethod
    async def image_exists(self, image_name: str) -> bool:
        """Check if image exists locally."""
        pass

    @abstractmethod
    async def pull_image(
        self,
        image_name: str,
        tag: str = "latest"
    ) -> None:
        """Pull image from registry."""
        pass
```

## Production Adapter: DockerAdapter

### Implementation Structure

```python
import asyncio
import json
from pathlib import Path

class DockerAdapter(IContainer):
    """
    Production adapter for Docker daemon.

    Uses Docker CLI for operations.
    """

    def __init__(
        self,
        docker_host: str = "unix:///var/run/docker.sock",
        default_network: str = "bridge"
    ):
        """
        Initialize Docker adapter.

        Args:
            docker_host: Docker daemon socket
            default_network: Default network for containers
        """
        self.docker_host = docker_host
        self.default_network = default_network

    async def run(self, config: ContainerConfig) -> ContainerResult:
        """Execute container to completion."""
        cmd = self._build_run_command(config)

        start_time = time.time()

        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )

        stdout, stderr = await process.communicate()
        duration = time.time() - start_time

        return ContainerResult(
            exit_code=process.returncode,
            stdout=stdout.decode(),
            stderr=stderr.decode(),
            container_id="",  # Not available with --rm
            duration_seconds=duration
        )

    async def create(self, config: ContainerConfig) -> str:
        """Create container without starting."""
        cmd = self._build_create_command(config)

        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )

        stdout, stderr = await process.communicate()

        if process.returncode != 0:
            raise ContainerError(f"Failed to create container: {stderr.decode()}")

        container_id = stdout.decode().strip()
        return container_id

    async def start(self, container_id: str) -> None:
        """Start an existing container."""
        cmd = ['docker', 'start', container_id]

        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )

        await process.communicate()

        if process.returncode != 0:
            raise ContainerError(f"Failed to start container {container_id}")

    async def exec(
        self,
        container_id: str,
        command: List[str],
        working_dir: Optional[str] = None,
        environment: Optional[Dict[str, str]] = None,
        stream_callback: Optional[Callable[[str], None]] = None
    ) -> ContainerResult:
        """Execute command in running container."""
        cmd = ['docker', 'exec']

        if working_dir:
            cmd.extend(['-w', working_dir])

        if environment:
            for key, value in environment.items():
                cmd.extend(['-e', f"{key}={value}"])

        cmd.append(container_id)
        cmd.extend(command)

        start_time = time.time()

        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )

        if stream_callback:
            # Stream output
            stdout_lines = []
            async for line in process.stdout:
                decoded = line.decode()
                stdout_lines.append(decoded)
                stream_callback(decoded)

            stderr = await process.stderr.read()
            stdout = ''.join(stdout_lines)
        else:
            stdout, stderr = await process.communicate()
            stdout = stdout.decode()
            stderr = stderr.decode()

        duration = time.time() - start_time

        return ContainerResult(
            exit_code=process.returncode,
            stdout=stdout,
            stderr=stderr,
            container_id=container_id,
            duration_seconds=duration
        )

    async def inspect(self, container_id: str) -> ContainerInfo:
        """Get container details."""
        cmd = ['docker', 'inspect', container_id]

        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )

        stdout, stderr = await process.communicate()

        if process.returncode != 0:
            raise ContainerError(f"Container {container_id} not found")

        data = json.loads(stdout.decode())[0]

        return ContainerInfo(
            id=data['Id'],
            name=data['Name'].lstrip('/'),
            image=data['Config']['Image'],
            status=ContainerStatus(data['State']['Status']),
            created_at=data['Created'],
            started_at=data['State'].get('StartedAt'),
            finished_at=data['State'].get('FinishedAt'),
            exit_code=data['State'].get('ExitCode')
        )

    async def build_image(
        self,
        dockerfile_path: Path,
        context_path: Path,
        tag: str,
        build_args: Optional[Dict[str, str]] = None
    ) -> str:
        """Build Docker image."""
        cmd = [
            'docker', 'build',
            '-f', str(dockerfile_path),
            '-t', tag
        ]

        if build_args:
            for key, value in build_args.items():
                cmd.extend(['--build-arg', f"{key}={value}"])

        cmd.append(str(context_path))

        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )

        stdout, stderr = await process.communicate()

        if process.returncode != 0:
            raise ContainerError(f"Image build failed: {stderr.decode()}")

        # Extract image ID from output
        # (parsing logic...)

        return tag  # Return tag as image ID

    async def image_exists(self, image_name: str) -> bool:
        """Check if image exists."""
        cmd = ['docker', 'image', 'inspect', image_name]

        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )

        await process.communicate()

        return process.returncode == 0

    def _build_run_command(self, config: ContainerConfig) -> List[str]:
        """Build docker run command."""
        cmd = ['docker', 'run']

        # Auto-remove
        if config.auto_remove:
            cmd.append('--rm')

        # Detached mode
        if config.detached:
            cmd.append('-d')

        # Name
        if config.name:
            cmd.extend(['--name', config.name])

        # User
        cmd.extend(['--user', config.user])

        # Working directory
        cmd.extend(['--workdir', config.working_dir])

        # Network
        network = config.network or self.default_network
        cmd.extend(['--network', network])

        # Volumes
        if config.volumes:
            for host_path, mount_config in config.volumes.items():
                bind_path = mount_config['bind']
                mode = mount_config.get('mode', 'rw')
                cmd.extend(['-v', f"{host_path}:{bind_path}:{mode}"])

        # Environment variables
        if config.environment:
            for key, value in config.environment.items():
                cmd.extend(['-e', f"{key}={value}"])

        # Image
        cmd.append(config.image)

        # Command
        if config.command:
            cmd.extend(config.command)

        return cmd

    def _build_create_command(self, config: ContainerConfig) -> List[str]:
        """Build docker create command (same as run but 'create')."""
        cmd = self._build_run_command(config)
        cmd[1] = 'create'  # Replace 'run' with 'create'
        return cmd
```

## Mock Adapter: FakeContainerAdapter

```python
class FakeContainerAdapter(IContainer):
    """
    Mock container adapter for testing.

    Simulates container operations without Docker.
    """

    def __init__(self):
        self.containers: Dict[str, Dict[str, Any]] = {}
        self.images: Dict[str, ImageInfo] = {}
        self.next_container_id = 1
        self.execution_logs: List[Dict] = []

    async def run(self, config: ContainerConfig) -> ContainerResult:
        """Simulate container run."""
        self.execution_logs.append({
            'operation': 'run',
            'config': config,
            'timestamp': datetime.utcnow()
        })

        # Simulate execution
        await asyncio.sleep(0.1)  # Minimal delay

        # Determine stdout based on command
        stdout = self._generate_fake_output(config)

        return ContainerResult(
            exit_code=0,
            stdout=stdout,
            stderr="",
            container_id="fake-container-123",
            duration_seconds=0.1
        )

    async def create(self, config: ContainerConfig) -> str:
        """Simulate container creation."""
        container_id = f"fake-{self.next_container_id}"
        self.next_container_id += 1

        self.containers[container_id] = {
            'config': config,
            'status': ContainerStatus.CREATED,
            'created_at': datetime.utcnow().isoformat(),
            'started_at': None,
            'exit_code': None
        }

        return container_id

    async def start(self, container_id: str) -> None:
        """Simulate container start."""
        if container_id not in self.containers:
            raise ContainerError(f"Container {container_id} not found")

        self.containers[container_id]['status'] = ContainerStatus.RUNNING
        self.containers[container_id]['started_at'] = datetime.utcnow().isoformat()

    async def exec(
        self,
        container_id: str,
        command: List[str],
        working_dir: Optional[str] = None,
        environment: Optional[Dict[str, str]] = None,
        stream_callback: Optional[Callable[[str], None]] = None
    ) -> ContainerResult:
        """Simulate command execution."""
        if container_id not in self.containers:
            raise ContainerError(f"Container {container_id} not found")

        # Generate fake output based on command
        stdout = self._generate_command_output(command)

        if stream_callback:
            # Simulate streaming
            for line in stdout.split('\n'):
                stream_callback(line + '\n')
                await asyncio.sleep(0.01)

        return ContainerResult(
            exit_code=0,
            stdout=stdout,
            stderr="",
            container_id=container_id,
            duration_seconds=0.1
        )

    async def build_image(
        self,
        dockerfile_path: Path,
        context_path: Path,
        tag: str,
        build_args: Optional[Dict[str, str]] = None
    ) -> str:
        """Simulate image build."""
        image_id = f"fake-image-{len(self.images) + 1}"

        self.images[tag] = ImageInfo(
            id=image_id,
            tags=[tag],
            created=datetime.utcnow().isoformat(),
            size_bytes=1000000  # 1MB fake size
        )

        return image_id

    async def image_exists(self, image_name: str) -> bool:
        """Check if fake image exists."""
        return image_name in self.images

    def _generate_fake_output(self, config: ContainerConfig) -> str:
        """Generate plausible output based on command."""
        if not config.command:
            return ""

        command_str = ' '.join(config.command)

        # Simulate Claude CLI output
        if 'claude' in command_str:
            return json.dumps({
                'type': 'assistant',
                'message': {
                    'content': [
                        {'type': 'text', 'text': 'Mock Claude response'}
                    ]
                },
                'usage': {'input_tokens': 100, 'output_tokens': 50}
            })

        # Simulate test output
        if 'pytest' in command_str or 'npm test' in command_str:
            return "===== test session starts =====\ntest_example.py::test_success PASSED\n===== 1 passed in 0.01s ====="

        return "Mock output"

    def _generate_command_output(self, command: List[str]) -> str:
        """Generate output for exec command."""
        command_str = ' '.join(command)

        if 'pytest' in command_str:
            return "===== test session starts =====\ntest_example.py::test_success PASSED\n===== 1 passed in 0.01s ====="

        return f"Mock exec output for: {command_str}"

    def add_fake_image(self, tag: str):
        """Helper to add pre-existing image."""
        self.images[tag] = ImageInfo(
            id=f"fake-{tag}",
            tags=[tag],
            created=datetime.utcnow().isoformat(),
            size_bytes=1000000
        )
```

## Container Lifecycle Management

### Agent Container Manager

```python
class AgentContainerManager:
    """
    Manages agent container lifecycle.

    Handles creation, execution, and cleanup.
    """

    def __init__(
        self,
        container_adapter: IContainer,
        redis_client: Any,  # For tracking
        project_name: str
    ):
        self.container = container_adapter
        self.redis = redis_client
        self.project_name = project_name

    async def run_agent(
        self,
        agent_name: str,
        task_id: str,
        prompt: str,
        context: Dict[str, Any],
        stream_callback: Optional[Callable] = None
    ) -> str:
        """
        Run agent in isolated container.

        Returns:
            Agent output
        """
        # Build config
        config = self._build_agent_config(
            agent_name=agent_name,
            task_id=task_id,
            prompt=prompt,
            context=context
        )

        # Track in Redis
        await self._track_container(config.name, agent_name, task_id)

        try:
            # Run container
            result = await self.container.run(config)

            if result.exit_code != 0:
                raise AgentExecutionError(
                    f"Agent failed: {result.stderr}"
                )

            return result.stdout

        finally:
            # Cleanup tracking
            await self._untrack_container(config.name)

    def _build_agent_config(
        self,
        agent_name: str,
        task_id: str,
        prompt: str,
        context: Dict[str, Any]
    ) -> ContainerConfig:
        """Build container configuration for agent."""
        project_dir = Path(context['work_dir'])
        container_name = f"claude-agent-{self.project_name}-{task_id}"

        return ContainerConfig(
            image=f"{self.project_name}-agent:latest",
            name=container_name,
            command=[
                'claude',
                '--print',
                '--verbose',
                '--output-format', 'stream-json',
                '--model', context.get('claude_model', 'claude-sonnet-4-5-20250929'),
                '--permission-mode', 'bypassPermissions',
                prompt
            ],
            working_dir="/workspace",
            user="1000:1000",
            environment={
                'CLAUDE_CODE_OAUTH_TOKEN': os.getenv('CLAUDE_CODE_OAUTH_TOKEN'),
                'HOME': '/home/orchestrator'
            },
            volumes={
                str(project_dir): {'bind': '/workspace', 'mode': 'rw'},
                str(Path.home() / '.ssh/id_ed25519'): {
                    'bind': '/home/orchestrator/.ssh/id_ed25519',
                    'mode': 'ro'
                },
                str(Path.home() / '.gitconfig'): {
                    'bind': '/home/orchestrator/.gitconfig',
                    'mode': 'ro'
                }
            },
            network='orchestrator_default',
            auto_remove=True
        )

    async def _track_container(
        self,
        container_name: str,
        agent_name: str,
        task_id: str
    ):
        """Track container in Redis."""
        key = f"agent_container:{container_name}"
        value = json.dumps({
            'agent': agent_name,
            'task_id': task_id,
            'project': self.project_name,
            'started_at': datetime.utcnow().isoformat()
        })

        await self.redis.set(key, value, ex=7200)  # 2 hour TTL

    async def _untrack_container(self, container_name: str):
        """Remove container tracking."""
        key = f"agent_container:{container_name}"
        await self.redis.delete(key)
```

## Error Handling

```python
class ContainerError(Exception):
    """Base exception for container operations."""
    pass

class ImageNotFoundError(ContainerError):
    """Raised when image doesn't exist."""
    pass

class ContainerNotFoundError(ContainerError):
    """Raised when container doesn't exist."""
    pass

class AgentExecutionError(ContainerError):
    """Raised when agent execution fails."""
    pass
```

## Configuration

```python
@dataclass
class DockerConfig:
    """Docker adapter configuration."""
    docker_host: str = "unix:///var/run/docker.sock"
    default_network: str = "orchestrator_default"
    default_user: str = "1000:1000"

    # Image settings
    image_build_timeout: int = 600
    image_pull_timeout: int = 300

    # Container settings
    container_stop_timeout: int = 10
    container_start_timeout: int = 30

    # Resource limits
    memory_limit: Optional[str] = None  # e.g., "2g"
    cpu_limit: Optional[float] = None   # e.g., 1.5 CPUs
```

## Testing Strategy

### Unit Tests

```python
import pytest

@pytest.fixture
def fake_container():
    return FakeContainerAdapter()

async def test_container_run(fake_container):
    """Test container execution."""
    config = ContainerConfig(
        image="test-image:latest",
        command=['echo', 'hello']
    )

    result = await fake_container.run(config)

    assert result.exit_code == 0
    assert len(fake_container.execution_logs) == 1

async def test_image_build(fake_container):
    """Test image building."""
    image_id = await fake_container.build_image(
        dockerfile_path=Path("/tmp/Dockerfile"),
        context_path=Path("/tmp"),
        tag="test-image:latest"
    )

    assert await fake_container.image_exists("test-image:latest")
```

## Summary

The Docker integration provides:
1. **Clean abstraction** through IContainer port
2. **Production adapter** for real Docker daemon
3. **Mock adapter** for testing without Docker
4. **Lifecycle management** for agent containers
5. **Resource tracking** via Redis
6. **Error handling** with specific exceptions
7. **Configuration** for various Docker settings
8. **Full testing** support with fake implementations

This design enables the platform to use Docker for isolation while maintaining flexibility to swap in alternative container runtimes (Podman, lightweight alternatives) or run without containers in test mode.
