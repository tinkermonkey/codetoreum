# Infrastructure Adapters - Detailed Design

## Overview

This document covers the detailed design for infrastructure-related secondary adapters:
- Repository Adapters (Git operations)
- Container Runtime Adapters (Docker execution)
- Event Store Adapters (Event persistence and streaming)
- Metrics & Observability Adapters (Metrics collection)
- Storage Adapters (Configuration and state storage)
- Notification Adapters (User notifications)

---

# Repository Adapters

## Port Interface

```python
from abc import ABC, abstractmethod
from typing import List, Optional, Dict, Any
from dataclasses import dataclass
from enum import Enum

class BranchStatus(Enum):
    """Branch status relative to main."""
    UP_TO_DATE = "up_to_date"
    AHEAD = "ahead"
    BEHIND = "behind"
    DIVERGED = "diverged"

@dataclass
class BranchInfo:
    """Information about a branch."""
    name: str
    exists: bool
    commits_ahead: int = 0
    commits_behind: int = 0
    has_conflicts: bool = False
    conflicting_files: List[str] = None
    last_commit_sha: Optional[str] = None
    last_commit_message: Optional[str] = None

class IRepository(ABC):
    """Output port for repository operations."""

    @abstractmethod
    async def clone(self, url: str, destination: str) -> None:
        """Clone a repository."""
        pass

    @abstractmethod
    async def checkout(self, branch: str, create: bool = False) -> None:
        """Checkout a branch, optionally creating it."""
        pass

    @abstractmethod
    async def commit(
        self,
        message: str,
        author_name: str,
        author_email: str,
        files: Optional[List[str]] = None
    ) -> str:
        """Commit changes. Returns commit SHA."""
        pass

    @abstractmethod
    async def push(
        self,
        branch: str,
        remote: str = "origin",
        force: bool = False
    ) -> None:
        """Push branch to remote."""
        pass

    @abstractmethod
    async def pull(
        self,
        branch: str,
        remote: str = "origin",
        rebase: bool = True
    ) -> None:
        """Pull changes from remote."""
        pass

    @abstractmethod
    async def get_branch_info(self, branch: str) -> BranchInfo:
        """Get information about a branch."""
        pass

    @abstractmethod
    async def has_uncommitted_changes(self) -> bool:
        """Check if there are uncommitted changes."""
        pass
```

## Git Repository Adapter (Production)

```python
import subprocess
from pathlib import Path
from typing import List, Optional

class GitRepositoryAdapter(IRepository):
    """Production adapter using Git CLI."""

    def __init__(self, work_dir: str):
        self.work_dir = Path(work_dir)

    async def clone(self, url: str, destination: str) -> None:
        """Clone using git CLI."""
        cmd = ['git', 'clone', url, destination]
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            raise RepositoryError(f"Clone failed: {result.stderr}")

    async def checkout(self, branch: str, create: bool = False) -> None:
        """Checkout branch."""
        cmd = ['git', 'checkout']
        if create:
            cmd.append('-b')
        cmd.append(branch)

        result = subprocess.run(
            cmd,
            cwd=self.work_dir,
            capture_output=True,
            text=True
        )
        if result.returncode != 0:
            raise RepositoryError(f"Checkout failed: {result.stderr}")

    async def commit(
        self,
        message: str,
        author_name: str,
        author_email: str,
        files: Optional[List[str]] = None
    ) -> str:
        """Commit changes."""
        # Stage files
        if files:
            for file in files:
                subprocess.run(
                    ['git', 'add', file],
                    cwd=self.work_dir,
                    check=True
                )
        else:
            subprocess.run(
                ['git', 'add', '.'],
                cwd=self.work_dir,
                check=True
            )

        # Commit with author info
        env = {
            'GIT_AUTHOR_NAME': author_name,
            'GIT_AUTHOR_EMAIL': author_email,
            'GIT_COMMITTER_NAME': author_name,
            'GIT_COMMITTER_EMAIL': author_email
        }

        result = subprocess.run(
            ['git', 'commit', '-m', message],
            cwd=self.work_dir,
            capture_output=True,
            text=True,
            env=env
        )

        if result.returncode != 0:
            raise RepositoryError(f"Commit failed: {result.stderr}")

        # Get commit SHA
        result = subprocess.run(
            ['git', 'rev-parse', 'HEAD'],
            cwd=self.work_dir,
            capture_output=True,
            text=True,
            check=True
        )
        return result.stdout.strip()

    async def get_branch_info(self, branch: str) -> BranchInfo:
        """Get branch information."""
        # Check if branch exists
        result = subprocess.run(
            ['git', 'show-ref', '--verify', f'refs/heads/{branch}'],
            cwd=self.work_dir,
            capture_output=True
        )
        exists = result.returncode == 0

        if not exists:
            return BranchInfo(name=branch, exists=False)

        # Get commits ahead/behind
        result = subprocess.run(
            ['git', 'rev-list', '--left-right', '--count', f'origin/main...{branch}'],
            cwd=self.work_dir,
            capture_output=True,
            text=True
        )
        behind, ahead = map(int, result.stdout.strip().split('\t'))

        # Check for conflicts
        has_conflicts = await self._check_for_conflicts(branch)
        conflicting_files = await self._get_conflicting_files() if has_conflicts else []

        return BranchInfo(
            name=branch,
            exists=True,
            commits_ahead=ahead,
            commits_behind=behind,
            has_conflicts=has_conflicts,
            conflicting_files=conflicting_files
        )

    async def _check_for_conflicts(self, branch: str) -> bool:
        """Check if merging branch would cause conflicts."""
        # Dry-run merge
        result = subprocess.run(
            ['git', 'merge-tree',
             subprocess.run(['git', 'merge-base', 'origin/main', branch],
                          cwd=self.work_dir, capture_output=True,
                          text=True, check=True).stdout.strip(),
             'origin/main',
             branch],
            cwd=self.work_dir,
            capture_output=True,
            text=True
        )
        return '<<<<<' in result.stdout
```

## In-Memory Repository Adapter (Testing/Mock)

```python
class InMemoryRepositoryAdapter(IRepository):
    """Mock adapter for testing without actual Git operations."""

    def __init__(self):
        self._branches: Dict[str, List[Dict]] = {'main': []}
        self._current_branch = 'main'
        self._uncommitted_changes: List[str] = []

    async def checkout(self, branch: str, create: bool = False) -> None:
        """Mock checkout."""
        if create:
            if branch in self._branches:
                raise RepositoryError(f"Branch {branch} already exists")
            self._branches[branch] = list(self._branches[self._current_branch])

        if branch not in self._branches:
            raise RepositoryError(f"Branch {branch} does not exist")

        self._current_branch = branch

    async def commit(
        self,
        message: str,
        author_name: str,
        author_email: str,
        files: Optional[List[str]] = None
    ) -> str:
        """Mock commit."""
        import uuid
        commit_sha = str(uuid.uuid4())[:8]

        commit = {
            'sha': commit_sha,
            'message': message,
            'author': f"{author_name} <{author_email}>",
            'files': files or list(self._uncommitted_changes)
        }

        self._branches[self._current_branch].append(commit)
        self._uncommitted_changes.clear()

        return commit_sha

    async def has_uncommitted_changes(self) -> bool:
        """Mock uncommitted changes check."""
        return len(self._uncommitted_changes) > 0

    # Test helpers
    def add_uncommitted_file(self, filename: str) -> None:
        """Add file to uncommitted changes."""
        self._uncommitted_changes.append(filename)

    def get_commits(self, branch: str) -> List[Dict]:
        """Get commits for testing."""
        return self._branches.get(branch, [])
```

---

# Container Runtime Adapters

## Port Interface

```python
from abc import ABC, abstractmethod
from typing import Dict, List, Optional, Callable

@dataclass
class ContainerConfig:
    """Configuration for container execution."""
    image: str
    command: List[str]
    working_dir: str
    volumes: Dict[str, Dict[str, str]]  # {host_path: {bind: container_path, mode: rw}}
    environment: Dict[str, str]
    network: Optional[str] = None
    user: Optional[str] = None

@dataclass
class ContainerResult:
    """Result from container execution."""
    exit_code: int
    stdout: str
    stderr: str
    duration_ms: float
    container_id: Optional[str] = None

class IContainer(ABC):
    """Output port for container runtime operations."""

    @abstractmethod
    async def run(
        self,
        config: ContainerConfig,
        stream_callback: Optional[Callable[[str], None]] = None
    ) -> ContainerResult:
        """Run a container and wait for completion."""
        pass

    @abstractmethod
    async def build_image(
        self,
        dockerfile_path: str,
        build_context: str,
        tag: str
    ) -> None:
        """Build a Docker image."""
        pass

    @abstractmethod
    async def image_exists(self, tag: str) -> bool:
        """Check if an image exists."""
        pass

    @abstractmethod
    async def stop_container(self, container_id: str) -> None:
        """Stop a running container."""
        pass
```

## Docker Container Adapter (Production)

```python
import subprocess
import asyncio

class DockerContainerAdapter(IContainer):
    """Production adapter using Docker."""

    async def run(
        self,
        config: ContainerConfig,
        stream_callback: Optional[Callable] = None
    ) -> ContainerResult:
        """Run Docker container."""

        cmd = self._build_docker_command(config)

        start_time = asyncio.get_event_loop().time()

        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )

        # Stream output
        stdout_lines = []
        async for line in process.stdout:
            line_str = line.decode('utf-8')
            stdout_lines.append(line_str)
            if stream_callback:
                stream_callback(line_str)

        stderr = (await process.stderr.read()).decode('utf-8')
        await process.wait()

        duration_ms = (asyncio.get_event_loop().time() - start_time) * 1000

        return ContainerResult(
            exit_code=process.returncode,
            stdout=''.join(stdout_lines),
            stderr=stderr,
            duration_ms=duration_ms
        )

    def _build_docker_command(self, config: ContainerConfig) -> List[str]:
        """Build docker run command."""
        cmd = ['docker', 'run', '--rm']

        if config.user:
            cmd.extend(['--user', config.user])

        if config.working_dir:
            cmd.extend(['--workdir', config.working_dir])

        if config.network:
            cmd.extend(['--network', config.network])

        for host_path, mount_config in config.volumes.items():
            mount_str = f"{host_path}:{mount_config['bind']}:{mount_config['mode']}"
            cmd.extend(['-v', mount_str])

        for key, value in config.environment.items():
            cmd.extend(['-e', f"{key}={value}"])

        cmd.append(config.image)
        cmd.extend(config.command)

        return cmd

    async def build_image(
        self,
        dockerfile_path: str,
        build_context: str,
        tag: str
    ) -> None:
        """Build Docker image."""
        cmd = [
            'docker', 'build',
            '-f', dockerfile_path,
            '-t', tag,
            build_context
        ]

        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )

        await process.wait()

        if process.returncode != 0:
            stderr = (await process.stderr.read()).decode('utf-8')
            raise ContainerError(f"Build failed: {stderr}")

    async def image_exists(self, tag: str) -> bool:
        """Check if image exists."""
        result = subprocess.run(
            ['docker', 'images', '-q', tag],
            capture_output=True,
            text=True
        )
        return bool(result.stdout.strip())
```

## Fake Container Adapter (Testing/Mock)

```python
class FakeContainerAdapter(IContainer):
    """Mock adapter that simulates container execution."""

    def __init__(self):
        self.execution_history: List[ContainerConfig] = []
        self.mock_results: Dict[str, ContainerResult] = {}

    async def run(
        self,
        config: ContainerConfig,
        stream_callback: Optional[Callable] = None
    ) -> ContainerResult:
        """Simulate container execution."""
        self.execution_history.append(config)

        # Find mock result by image name
        result = self.mock_results.get(
            config.image,
            ContainerResult(
                exit_code=0,
                stdout="Mock container output",
                stderr="",
                duration_ms=100.0
            )
        )

        # Simulate streaming
        if stream_callback:
            for line in result.stdout.split('\n'):
                stream_callback(line + '\n')
                await asyncio.sleep(0.01)

        return result

    async def build_image(self, dockerfile_path: str, build_context: str, tag: str) -> None:
        """Simulate image build."""
        # No-op for testing
        pass

    async def image_exists(self, tag: str) -> bool:
        """Simulate image existence check."""
        return True

    # Test helpers
    def set_mock_result(self, image: str, result: ContainerResult) -> None:
        """Set mock result for an image."""
        self.mock_results[image] = result
```

---

# Event Store Adapters

## Port Interface

```python
from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional
from datetime import datetime

@dataclass
class DomainEvent:
    """Domain event structure."""
    event_id: str
    event_type: str
    aggregate_id: str
    aggregate_type: str
    timestamp: datetime
    data: Dict[str, Any]
    metadata: Dict[str, Any]

class IEventStore(ABC):
    """Output port for event storage."""

    @abstractmethod
    async def append(self, event: DomainEvent) -> None:
        """Append an event to the store."""
        pass

    @abstractmethod
    async def get_events(
        self,
        aggregate_id: Optional[str] = None,
        event_type: Optional[str] = None,
        from_time: Optional[datetime] = None,
        to_time: Optional[datetime] = None,
        limit: int = 1000
    ) -> List[DomainEvent]:
        """Query events from the store."""
        pass

    @abstractmethod
    async def replay_events(
        self,
        aggregate_id: str,
        from_event_id: Optional[str] = None
    ) -> List[DomainEvent]:
        """Replay events for an aggregate."""
        pass
```

## Redis Event Store (Production)

```python
import redis.asyncio as aioredis
import json
from typing import List, Optional
from datetime import datetime

class RedisEventStore(IEventStore):
    """Event store using Redis Streams."""

    def __init__(self, redis_url: str):
        self.redis = aioredis.from_url(redis_url)
        self.stream_key = "orchestrator:events"

    async def append(self, event: DomainEvent) -> None:
        """Append event to Redis Stream."""
        event_data = {
            'event_id': event.event_id,
            'event_type': event.event_type,
            'aggregate_id': event.aggregate_id,
            'aggregate_type': event.aggregate_type,
            'timestamp': event.timestamp.isoformat(),
            'data': json.dumps(event.data),
            'metadata': json.dumps(event.metadata)
        }

        await self.redis.xadd(self.stream_key, event_data)

    async def get_events(
        self,
        aggregate_id: Optional[str] = None,
        event_type: Optional[str] = None,
        from_time: Optional[datetime] = None,
        to_time: Optional[datetime] = None,
        limit: int = 1000
    ) -> List[DomainEvent]:
        """Query events from Redis Stream."""
        # Read from stream
        events = await self.redis.xrange(
            self.stream_key,
            min='-',
            max='+',
            count=limit
        )

        # Parse and filter
        domain_events = []
        for event_id, event_data in events:
            event = self._parse_event(event_id, event_data)

            # Apply filters
            if aggregate_id and event.aggregate_id != aggregate_id:
                continue
            if event_type and event.event_type != event_type:
                continue
            if from_time and event.timestamp < from_time:
                continue
            if to_time and event.timestamp > to_time:
                continue

            domain_events.append(event)

        return domain_events

    def _parse_event(self, event_id: str, event_data: Dict) -> DomainEvent:
        """Parse Redis event to DomainEvent."""
        return DomainEvent(
            event_id=event_data['event_id'].decode('utf-8'),
            event_type=event_data['event_type'].decode('utf-8'),
            aggregate_id=event_data['aggregate_id'].decode('utf-8'),
            aggregate_type=event_data['aggregate_type'].decode('utf-8'),
            timestamp=datetime.fromisoformat(event_data['timestamp'].decode('utf-8')),
            data=json.loads(event_data['data'].decode('utf-8')),
            metadata=json.loads(event_data['metadata'].decode('utf-8'))
        )
```

## In-Memory Event Store (Testing/Mock)

```python
class InMemoryEventStore(IEventStore):
    """In-memory event store for testing."""

    def __init__(self):
        self._events: List[DomainEvent] = []

    async def append(self, event: DomainEvent) -> None:
        """Append event to memory."""
        self._events.append(event)

    async def get_events(
        self,
        aggregate_id: Optional[str] = None,
        event_type: Optional[str] = None,
        from_time: Optional[datetime] = None,
        to_time: Optional[datetime] = None,
        limit: int = 1000
    ) -> List[DomainEvent]:
        """Query events from memory."""
        filtered = self._events

        if aggregate_id:
            filtered = [e for e in filtered if e.aggregate_id == aggregate_id]
        if event_type:
            filtered = [e for e in filtered if e.event_type == event_type]
        if from_time:
            filtered = [e for e in filtered if e.timestamp >= from_time]
        if to_time:
            filtered = [e for e in filtered if e.timestamp <= to_time]

        return filtered[:limit]

    def reset(self) -> None:
        """Clear all events for testing."""
        self._events.clear()

    def get_all_events(self) -> List[DomainEvent]:
        """Get all events for testing."""
        return list(self._events)
```

---

# Storage, Metrics, and Notification Adapters

## Storage Adapters

```python
class IStorage(ABC):
    """Output port for configuration/state storage."""

    @abstractmethod
    async def save(self, key: str, value: Any) -> None:
        """Save data."""
        pass

    @abstractmethod
    async def load(self, key: str) -> Any:
        """Load data."""
        pass

    @abstractmethod
    async def delete(self, key: str) -> None:
        """Delete data."""
        pass

# File system implementation
class FileSystemStorage(IStorage):
    def __init__(self, base_path: str):
        self.base_path = Path(base_path)

    async def save(self, key: str, value: Any) -> None:
        import yaml
        file_path = self.base_path / f"{key}.yaml"
        file_path.parent.mkdir(parents=True, exist_ok=True)
        with open(file_path, 'w') as f:
            yaml.dump(value, f)

# In-memory implementation
class InMemoryStorage(IStorage):
    def __init__(self):
        self._data: Dict[str, Any] = {}

    async def save(self, key: str, value: Any) -> None:
        self._data[key] = value

    async def load(self, key: str) -> Any:
        if key not in self._data:
            raise KeyError(f"Key {key} not found")
        return self._data[key]
```

## Metrics Adapters

```python
class IMetrics(ABC):
    """Output port for metrics collection."""

    @abstractmethod
    async def record_task_metric(
        self,
        agent: str,
        duration_ms: float,
        success: bool,
        metadata: Dict[str, Any]
    ) -> None:
        """Record task execution metric."""
        pass

# Elasticsearch implementation
class ElasticsearchMetrics(IMetrics):
    def __init__(self, es_client):
        self.es = es_client

    async def record_task_metric(self, agent: str, duration_ms: float, success: bool, metadata: Dict) -> None:
        await self.es.index(
            index=f"metrics-{datetime.now().strftime('%Y.%m.%d')}",
            document={
                'agent': agent,
                'duration_ms': duration_ms,
                'success': success,
                'metadata': metadata,
                'timestamp': datetime.utcnow().isoformat()
            }
        )

# In-memory implementation
class InMemoryMetrics(IMetrics):
    def __init__(self):
        self.metrics: List[Dict] = []

    async def record_task_metric(self, agent: str, duration_ms: float, success: bool, metadata: Dict) -> None:
        self.metrics.append({
            'agent': agent,
            'duration_ms': duration_ms,
            'success': success,
            'metadata': metadata
        })
```

## Notification Adapters

```python
class INotifier(ABC):
    """Output port for notifications."""

    @abstractmethod
    async def notify(
        self,
        title: str,
        message: str,
        level: str,
        metadata: Dict[str, Any]
    ) -> None:
        """Send notification."""
        pass

# Console implementation
class ConsoleNotifier(INotifier):
    async def notify(self, title: str, message: str, level: str, metadata: Dict) -> None:
        print(f"[{level.upper()}] {title}")
        print(f"  {message}")

# In-memory implementation
class InMemoryNotifier(INotifier):
    def __init__(self):
        self.notifications: List[Dict] = []

    async def notify(self, title: str, message: str, level: str, metadata: Dict) -> None:
        self.notifications.append({
            'title': title,
            'message': message,
            'level': level,
            'metadata': metadata
        })
```

---

## Testing Strategy

All adapters follow the same testing pattern:

1. **Unit Tests**: Test adapter logic with mocked external dependencies
2. **Integration Tests**: Test with real external systems (optional, marked)
3. **Contract Tests**: Verify adapters implement interface correctly
4. **Mock Adapters**: Provide deterministic behavior for downstream testing

---

## Migration Strategy

1. Extract interfaces from existing implementations
2. Create production adapters implementing interfaces
3. Create mock adapters for testing
4. Update application services to depend on interfaces
5. Inject adapters via dependency injection
6. Migrate tests to use mock adapters
7. Add adapter registries for configuration-based selection
