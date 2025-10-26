# Execution Result Domain Design

## Overview

Execution Result is a value object capturing the outcome of an agent execution, including output, status, and metadata.

## Domain Model

```python
from dataclasses import dataclass
from typing import Optional, List, Dict, Any
from datetime import datetime

@dataclass(frozen=True)
class ExecutionResult:
    """
    Execution Result value object.

    Immutable representation of agent execution outcome.
    """

    # Status
    success: bool
    exit_code: int

    # Output
    output: str
    error_message: Optional[str]

    # Files modified (for code changes)
    modified_files: List[str]
    added_files: List[str]
    deleted_files: List[str]

    # Metrics
    input_tokens: int
    output_tokens: int
    duration_seconds: float

    # Session continuity
    session_id: Optional[str]

    # Metadata
    metadata: Dict[str, Any]

    # Timestamp
    timestamp: datetime

    @classmethod
    def success_result(cls,
                      output: str,
                      input_tokens: int,
                      output_tokens: int,
                      duration_seconds: float,
                      modified_files: Optional[List[str]] = None,
                      added_files: Optional[List[str]] = None,
                      deleted_files: Optional[List[str]] = None,
                      session_id: Optional[str] = None,
                      metadata: Optional[Dict[str, Any]] = None) -> 'ExecutionResult':
        """Create successful execution result."""
        return cls(
            success=True,
            exit_code=0,
            output=output,
            error_message=None,
            modified_files=modified_files or [],
            added_files=added_files or [],
            deleted_files=deleted_files or [],
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            duration_seconds=duration_seconds,
            session_id=session_id,
            metadata=metadata or {},
            timestamp=datetime.utcnow()
        )

    @classmethod
    def failure_result(cls,
                      error_message: str,
                      exit_code: int,
                      output: str = "",
                      duration_seconds: float = 0.0,
                      metadata: Optional[Dict[str, Any]] = None) -> 'ExecutionResult':
        """Create failed execution result."""
        return cls(
            success=False,
            exit_code=exit_code,
            output=output,
            error_message=error_message,
            modified_files=[],
            added_files=[],
            deleted_files=[],
            input_tokens=0,
            output_tokens=0,
            duration_seconds=duration_seconds,
            session_id=None,
            metadata=metadata or {},
            timestamp=datetime.utcnow()
        )

    def get_total_tokens(self) -> int:
        """Get total tokens used."""
        return self.input_tokens + self.output_tokens

    def has_file_changes(self) -> bool:
        """Check if execution made file changes."""
        return bool(
            self.modified_files or
            self.added_files or
            self.deleted_files
        )

    def get_all_affected_files(self) -> List[str]:
        """Get all files affected by execution."""
        return list(set(
            self.modified_files +
            self.added_files +
            self.deleted_files
        ))

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "success": self.success,
            "exit_code": self.exit_code,
            "output": self.output,
            "error_message": self.error_message,
            "modified_files": self.modified_files,
            "added_files": self.added_files,
            "deleted_files": self.deleted_files,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "total_tokens": self.get_total_tokens(),
            "duration_seconds": self.duration_seconds,
            "session_id": self.session_id,
            "metadata": self.metadata,
            "timestamp": self.timestamp.isoformat()
        }
```

## Usage Patterns

### Creating Results

```python
# Success case
result = ExecutionResult.success_result(
    output="Implementation complete",
    input_tokens=1000,
    output_tokens=500,
    duration_seconds=45.2,
    modified_files=["src/main.py", "tests/test_main.py"],
    session_id="session-123"
)

# Failure case
result = ExecutionResult.failure_result(
    error_message="Compilation failed",
    exit_code=1,
    output="Error: syntax error on line 42",
    duration_seconds=12.5
)
```

### Query Methods

```python
# Check status
if result.success:
    print(f"Success! Modified {len(result.modified_files)} files")

# Token usage
total = result.get_total_tokens()
print(f"Used {total} tokens")

# File changes
if result.has_file_changes():
    print(f"Affected files: {result.get_all_affected_files()}")
```

## Integration with Agent Execution

```python
# In agent execution completion
execution.complete(
    output=result.output,
    input_tokens=result.input_tokens,
    output_tokens=result.output_tokens,
    session_id=result.session_id
)

# Store result for later use
await result_store.save_execution_result(
    execution_id=execution.id,
    result=result.to_dict()
)
```

## Business Rules

1. Result is immutable (frozen dataclass)
2. Success results have exit_code = 0
3. Failure results have non-zero exit_code
4. Timestamp set automatically on creation
5. Token counts must be non-negative

## Value Object Properties

1. **Immutability**: Frozen dataclass ensures no modification
2. **Equality**: Two results with same values are equal
3. **Self-validation**: Factory methods ensure consistency
4. **No identity**: Results are compared by value, not ID

## Testing

```python
def test_success_result():
    result = ExecutionResult.success_result(
        output="Done",
        input_tokens=100,
        output_tokens=50,
        duration_seconds=10.0
    )

    assert result.success
    assert result.exit_code == 0
    assert result.get_total_tokens() == 150

def test_failure_result():
    result = ExecutionResult.failure_result(
        error_message="Failed",
        exit_code=1
    )

    assert not result.success
    assert result.exit_code == 1
    assert result.error_message == "Failed"

def test_immutability():
    result = ExecutionResult.success_result(
        output="Test",
        input_tokens=100,
        output_tokens=50,
        duration_seconds=1.0
    )

    # This should raise error (frozen dataclass)
    with pytest.raises(AttributeError):
        result.output = "Modified"

def test_file_changes():
    result = ExecutionResult.success_result(
        output="Done",
        input_tokens=100,
        output_tokens=50,
        duration_seconds=10.0,
        modified_files=["a.py"],
        added_files=["b.py"]
    )

    assert result.has_file_changes()
    assert set(result.get_all_affected_files()) == {"a.py", "b.py"}
```

## Migration from Legacy

| Legacy | Domain |
|--------|--------|
| agent output dict | ExecutionResult value object |
| success flag | success field |
| error dict | error_message field |
| tokens_used | input_tokens + output_tokens |

## References

- **Agent Execution**: `agent_execution_design.md`
- **Value Objects**: `value_objects_design.md`
