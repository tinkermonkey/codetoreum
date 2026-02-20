# ILogger Output Port Design

## Overview

The `ILogger` port provides an abstraction for structured logging. This port enables consistent logging across the system with support for different log levels, structured fields, and context propagation.

## Port Interface

```python
from abc import ABC, abstractmethod
from typing import Dict, Any, Optional
from enum import Enum
from datetime import datetime

class LogLevel(Enum):
    """Log severity levels."""
    DEBUG = 10
    INFO = 20
    WARNING = 30
    ERROR = 40
    CRITICAL = 50

class ILogger(ABC):
    """Interface for structured logging."""

    @abstractmethod
    async def debug(self,
                   message: str,
                   **fields: Any) -> None:
        """Log debug message."""
        pass

    @abstractmethod
    async def info(self,
                  message: str,
                  **fields: Any) -> None:
        """Log info message."""
        pass

    @abstractmethod
    async def warning(self,
                     message: str,
                     **fields: Any) -> None:
        """Log warning message."""
        pass

    @abstractmethod
    async def error(self,
                   message: str,
                   exception: Optional[Exception] = None,
                   **fields: Any) -> None:
        """Log error message."""
        pass

    @abstractmethod
    async def critical(self,
                      message: str,
                      exception: Optional[Exception] = None,
                      **fields: Any) -> None:
        """Log critical message."""
        pass

    @abstractmethod
    def with_context(self, **fields: Any) -> 'ILogger':
        """Create logger with additional context fields."""
        pass

    @abstractmethod
    async def set_level(self, level: LogLevel) -> None:
        """Set minimum log level."""
        pass

    @abstractmethod
    async def query_logs(self,
                        start_time: datetime,
                        end_time: datetime,
                        level: Optional[LogLevel] = None,
                        filters: Optional[Dict[str, Any]] = None,
                        limit: int = 100) -> List[LogEntry]:
        """Query log entries."""
        pass
```

## Data Models

```python
@dataclass
class LogEntry:
    """Log entry data."""
    timestamp: datetime
    level: LogLevel
    message: str
    fields: Dict[str, Any]
    exception: Optional[str]
    stack_trace: Optional[str]
```

## Adapter Implementations

### Elasticsearch Logger

```python
class ElasticsearchLogger(ILogger):
    """Elasticsearch-based structured logging."""

    def __init__(self,
                 es_client,
                 index_prefix: str = "logs",
                 min_level: LogLevel = LogLevel.INFO):
        self.es = es_client
        self.index_prefix = index_prefix
        self.min_level = min_level
        self.context_fields: Dict[str, Any] = {}

    async def info(self, message: str, **fields: Any) -> None:
        """Log to Elasticsearch."""
        if self.min_level.value > LogLevel.INFO.value:
            return

        await self._log(LogLevel.INFO, message, fields)

    async def _log(self,
                   level: LogLevel,
                   message: str,
                   fields: Dict[str, Any]) -> None:
        """Internal log method."""
        log_entry = {
            'timestamp': datetime.utcnow(),
            'level': level.name,
            'message': message,
            **self.context_fields,
            **fields
        }

        await self.es.index(
            index=f"{self.index_prefix}-{datetime.utcnow():%Y.%m.%d}",
            document=log_entry
        )

    def with_context(self, **fields: Any) -> 'ILogger':
        """Create logger with context."""
        new_logger = ElasticsearchLogger(
            self.es,
            self.index_prefix,
            self.min_level
        )
        new_logger.context_fields = {**self.context_fields, **fields}
        return new_logger
```

### Stdout Logger

```python
class StdoutLogger(ILogger):
    """Simple stdout logging."""

    def __init__(self, min_level: LogLevel = LogLevel.INFO):
        self.min_level = min_level
        self.context_fields: Dict[str, Any] = {}

    async def info(self, message: str, **fields: Any) -> None:
        """Log to stdout."""
        if self.min_level.value > LogLevel.INFO.value:
            return

        import json
        log_data = {
            'timestamp': datetime.utcnow().isoformat(),
            'level': 'INFO',
            'message': message,
            **self.context_fields,
            **fields
        }
        print(json.dumps(log_data))
```

### In-Memory Logger (Testing)

```python
class InMemoryLogger(ILogger):
    """In-memory logger for testing."""

    def __init__(self):
        self.logs: List[LogEntry] = []
        self.context_fields: Dict[str, Any] = {}

    async def info(self, message: str, **fields: Any) -> None:
        """Store log in memory."""
        self.logs.append(LogEntry(
            timestamp=datetime.utcnow(),
            level=LogLevel.INFO,
            message=message,
            fields={**self.context_fields, **fields},
            exception=None,
            stack_trace=None
        ))

    def clear(self) -> None:
        """Clear all logs (useful for testing)."""
        self.logs.clear()
```

## Common Log Fields

### Standard Fields
- `timestamp`: Log timestamp
- `level`: Log level
- `message`: Log message
- `service`: Service name
- `component`: Component name
- `operation`: Operation being performed

### Context Fields
- `project_id`: Project identifier
- `agent_name`: Agent name
- `task_id`: Task identifier
- `workflow_run_id`: Pipeline run ID
- `user_id`: User identifier

## Integration Points

### Used By
- All components (ubiquitous)
- Error handling middleware
- Request/response logging

### Dependencies
- None (standalone port)

## Implementation Notes

1. **Structured Logging**: Always use structured fields, not string interpolation
2. **Context Propagation**: Use `with_context()` for consistent context
3. **Performance**: Async logging to avoid blocking
4. **Correlation**: Include correlation IDs for request tracing
5. **Sensitive Data**: Sanitize logs to remove secrets/PII
