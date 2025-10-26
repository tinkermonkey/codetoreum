# Value Objects Design

## Overview

Value objects are immutable objects defined by their attributes rather than identity. They represent descriptive aspects of the domain with no conceptual identity.

## Core Value Objects

### WorkItemId

```python
from dataclasses import dataclass
from uuid import UUID, uuid4

@dataclass(frozen=True)
class WorkItemId:
    """Type-safe identifier for work items."""
    value: str

    def __post_init__(self):
        if not self.value:
            raise ValueError("WorkItemId cannot be empty")

    @classmethod
    def generate(cls) -> 'WorkItemId':
        """Generate new unique work item ID."""
        return cls(value=str(uuid4()))

    @classmethod
    def from_string(cls, value: str) -> 'WorkItemId':
        """Create from string value."""
        return cls(value=value)

    def __str__(self) -> str:
        return self.value
```

### WorkflowId, AgentId, ExecutionId

Similar structure to WorkItemId - type-safe wrappers around string IDs.

### AgentCapability

```python
@dataclass(frozen=True)
class AgentCapability:
    """Represents a skill/capability of an agent."""
    skill: str
    proficiency: float  # 0.0 to 1.0
    description: Optional[str] = None

    def __post_init__(self):
        if not 0.0 <= self.proficiency <= 1.0:
            raise ValueError("Proficiency must be between 0.0 and 1.0")

    def meets_requirement(self, min_proficiency: float) -> bool:
        """Check if capability meets minimum proficiency."""
        return self.proficiency >= min_proficiency
```

### Requirement

```python
@dataclass(frozen=True)
class Requirement:
    """Represents a skill requirement for work."""
    skill: str
    min_proficiency: float
    is_required: bool = True

    def __post_init__(self):
        if not 0.0 <= self.min_proficiency <= 1.0:
            raise ValueError("Min proficiency must be between 0.0 and 1.0")

    def is_satisfied_by(self, capability: AgentCapability) -> bool:
        """Check if capability satisfies this requirement."""
        return (
            capability.skill == self.skill and
            capability.proficiency >= self.min_proficiency
        )
```

### ReviewFeedback

```python
from enum import Enum

class ReviewDecision(Enum):
    APPROVE = "approve"
    REQUEST_CHANGES = "request_changes"
    ESCALATE = "escalate"

@dataclass(frozen=True)
class ReviewFeedback:
    """Structured review feedback."""
    decision: ReviewDecision
    comment: str
    issues: List[str]
    suggestions: List[str]
    timestamp: datetime

    def has_issues(self) -> bool:
        """Check if feedback contains issues."""
        return len(self.issues) > 0

    def is_approved(self) -> bool:
        """Check if review approved."""
        return self.decision == ReviewDecision.APPROVE
```

### ExecutionContext

```python
@dataclass(frozen=True)
class ExecutionContext:
    """Complete context for agent execution."""

    # Work context
    work_item_id: str
    workflow_id: str
    stage_name: str

    # Agent context
    agent_id: str
    model: str
    timeout_seconds: int

    # Workspace context
    workspace_type: str
    branch_name: Optional[str]
    discussion_id: Optional[str]

    # Project context
    project_id: str
    repository_url: str
    tech_stack: List[str]

    # Permissions
    filesystem_write_allowed: bool
    can_make_commits: bool
    requires_docker: bool

    # MCP servers
    mcp_servers: List[str]

    # Session continuity
    previous_session_id: Optional[str]

    # Metadata
    metadata: Dict[str, Any]

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "work_item_id": self.work_item_id,
            "workflow_id": self.workflow_id,
            "stage_name": self.stage_name,
            "agent_id": self.agent_id,
            "model": self.model,
            "timeout_seconds": self.timeout_seconds,
            "workspace_type": self.workspace_type,
            "branch_name": self.branch_name,
            "discussion_id": self.discussion_id,
            "project_id": self.project_id,
            "repository_url": self.repository_url,
            "tech_stack": self.tech_stack,
            "filesystem_write_allowed": self.filesystem_write_allowed,
            "can_make_commits": self.can_make_commits,
            "requires_docker": self.requires_docker,
            "mcp_servers": self.mcp_servers,
            "previous_session_id": self.previous_session_id,
            "metadata": self.metadata
        }
```

### TimeRange

```python
@dataclass(frozen=True)
class TimeRange:
    """Value object for time ranges."""
    start: datetime
    end: datetime

    def __post_init__(self):
        if self.end < self.start:
            raise ValueError("End time must be after start time")

    def duration_seconds(self) -> float:
        """Get duration in seconds."""
        return (self.end - self.start).total_seconds()

    def contains(self, timestamp: datetime) -> bool:
        """Check if timestamp is within range."""
        return self.start <= timestamp <= self.end

    def overlaps(self, other: 'TimeRange') -> bool:
        """Check if ranges overlap."""
        return (
            self.start <= other.end and
            other.start <= self.end
        )
```

### TokenUsage

```python
@dataclass(frozen=True)
class TokenUsage:
    """Token usage metrics."""
    input_tokens: int
    output_tokens: int

    def __post_init__(self):
        if self.input_tokens < 0 or self.output_tokens < 0:
            raise ValueError("Token counts cannot be negative")

    @property
    def total_tokens(self) -> int:
        """Get total tokens."""
        return self.input_tokens + self.output_tokens

    def add(self, other: 'TokenUsage') -> 'TokenUsage':
        """Add two token usages."""
        return TokenUsage(
            input_tokens=self.input_tokens + other.input_tokens,
            output_tokens=self.output_tokens + other.output_tokens
        )

    def to_dict(self) -> Dict[str, int]:
        """Serialize to dictionary."""
        return {
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "total_tokens": self.total_tokens
        }
```

## Value Object Principles

### 1. Immutability
All value objects are frozen dataclasses:

```python
@dataclass(frozen=True)
class MyValueObject:
    field: str

# Cannot modify
obj = MyValueObject("value")
obj.field = "new"  # Raises AttributeError
```

### 2. Equality by Value
Value objects with same attributes are equal:

```python
capability1 = AgentCapability("python", 0.9)
capability2 = AgentCapability("python", 0.9)
assert capability1 == capability2  # True
```

### 3. Self-Validation
Value objects validate themselves in `__post_init__`:

```python
@dataclass(frozen=True)
class Age:
    value: int

    def __post_init__(self):
        if self.value < 0:
            raise ValueError("Age cannot be negative")
```

### 4. No Identity
Value objects have no unique identity - they are compared by value.

### 5. Side-Effect Free Operations
Methods on value objects return new instances:

```python
tokens1 = TokenUsage(100, 50)
tokens2 = TokenUsage(200, 100)
total = tokens1.add(tokens2)  # Returns new TokenUsage
```

## Testing Value Objects

```python
def test_agent_capability():
    capability = AgentCapability("python", 0.9, "Expert Python")

    assert capability.skill == "python"
    assert capability.proficiency == 0.9
    assert capability.meets_requirement(0.8)
    assert not capability.meets_requirement(0.95)

def test_capability_immutability():
    capability = AgentCapability("python", 0.9)

    with pytest.raises(AttributeError):
        capability.proficiency = 1.0

def test_requirement_satisfaction():
    capability = AgentCapability("python", 0.9)
    requirement = Requirement("python", 0.8)

    assert requirement.is_satisfied_by(capability)

def test_token_usage_addition():
    tokens1 = TokenUsage(100, 50)
    tokens2 = TokenUsage(200, 100)

    total = tokens1.add(tokens2)

    assert total.input_tokens == 300
    assert total.output_tokens == 150
    assert total.total_tokens == 450

def test_time_range_validation():
    now = datetime.utcnow()
    later = now + timedelta(hours=1)

    time_range = TimeRange(now, later)
    assert time_range.duration_seconds() == 3600

    # Invalid range
    with pytest.raises(ValueError):
        TimeRange(later, now)
```

## Usage in Domain Models

```python
class Agent:
    capabilities: Dict[str, AgentCapability]

    def has_capability(self, requirement: Requirement) -> bool:
        """Check if agent satisfies requirement."""
        if requirement.skill not in self.capabilities:
            return False

        capability = self.capabilities[requirement.skill]
        return requirement.is_satisfied_by(capability)

class AgentExecution:
    def complete(self, result: ExecutionResult, tokens: TokenUsage) -> None:
        """Complete execution with value objects."""
        self.input_tokens = tokens.input_tokens
        self.output_tokens = tokens.output_tokens
        self.result = result
```

## References

- **Agent**: `agent_design.md`
- **Execution Result**: `execution_result_design.md`
- **Review Cycle**: `review_cycle_design.md`
