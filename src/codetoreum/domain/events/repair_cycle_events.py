"""Repair cycle domain events.

Events emitted during the test-driven repair cycle execution:
- Cycle start/completion
- Test execution events
- File fix events
- Warning review events
- Fast-fail (circuit breaker) events

All events are immutable (frozen dataclasses) for event sourcing audit trail integrity.
"""

from dataclasses import dataclass
from typing import Optional
from uuid import uuid4

from .adapter_events import CodetoreumEvent


@dataclass(frozen=True)
class RepairCycleStartedEvent(CodetoreumEvent):
    """Emitted when a repair cycle begins.

    Attributes:
        type: Fixed to "repair_cycle.started"
        pipeline_run_id: Unique identifier for this pipeline run
        stage_name: Name of the workflow stage
        agent_name: Name of the agent to execute
    """

    pipeline_run_id: str = ""
    stage_name: str = ""
    agent_name: str = ""

    def __post_init__(self) -> None:
        """Validate event after initialization."""
        super().__post_init__()
        if not self.pipeline_run_id:
            raise ValueError("pipeline_run_id is required")
        if not self.stage_name:
            raise ValueError("stage_name is required")
        if not self.agent_name:
            raise ValueError("agent_name is required")

    def to_dict(self) -> dict:
        """Serialize to dictionary."""
        d = super().to_dict()
        d.update({
            "pipeline_run_id": self.pipeline_run_id,
            "stage_name": self.stage_name,
            "agent_name": self.agent_name,
        })
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "RepairCycleStartedEvent":
        """Deserialize from dictionary."""
        return cls(
            type=data.get("type", "repair_cycle.started"),
            timestamp=data.get("timestamp", ""),
            source=data.get("source", ""),
            correlation_id=data.get("correlation_id"),
            event_id=data.get("event_id") or str(uuid4()),
            pipeline_run_id=data.get("pipeline_run_id", ""),
            stage_name=data.get("stage_name", ""),
            agent_name=data.get("agent_name", ""),
        )


@dataclass(frozen=True)
class RepairCycleTestExecutionCompletedEvent(CodetoreumEvent):
    """Emitted when a test run completes (one iteration of one test type).

    Attributes:
        type: Fixed to "repair_cycle.test_execution_completed"
        pipeline_run_id: Unique identifier for this pipeline run
        test_type: Type of test (unit, integration, e2e)
        iteration: Iteration number
        passed_count: Number of passing tests
        failed_count: Number of failing tests
        warnings_count: Number of warnings
    """

    pipeline_run_id: str = ""
    test_type: str = ""
    iteration: int = 0
    passed_count: int = 0
    failed_count: int = 0
    warnings_count: int = 0

    def __post_init__(self) -> None:
        """Validate event after initialization."""
        super().__post_init__()
        if not self.pipeline_run_id:
            raise ValueError("pipeline_run_id is required")
        if not self.test_type:
            raise ValueError("test_type is required")
        if self.iteration < 1:
            raise ValueError("iteration must be >= 1")

    def to_dict(self) -> dict:
        """Serialize to dictionary."""
        d = super().to_dict()
        d.update({
            "pipeline_run_id": self.pipeline_run_id,
            "test_type": self.test_type,
            "iteration": self.iteration,
            "passed_count": self.passed_count,
            "failed_count": self.failed_count,
            "warnings_count": self.warnings_count,
        })
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "RepairCycleTestExecutionCompletedEvent":
        """Deserialize from dictionary."""
        return cls(
            type=data.get("type", "repair_cycle.test_execution_completed"),
            timestamp=data.get("timestamp", ""),
            source=data.get("source", ""),
            correlation_id=data.get("correlation_id"),
            event_id=data.get("event_id") or str(uuid4()),
            pipeline_run_id=data.get("pipeline_run_id", ""),
            test_type=data.get("test_type", ""),
            iteration=data.get("iteration", 0),
            passed_count=data.get("passed_count", 0),
            failed_count=data.get("failed_count", 0),
            warnings_count=data.get("warnings_count", 0),
        )


@dataclass(frozen=True)
class RepairCycleTestCycleCompletedEvent(CodetoreumEvent):
    """Emitted when a complete test type cycle completes (all iterations).

    Attributes:
        type: Fixed to "repair_cycle.test_cycle_completed"
        pipeline_run_id: Unique identifier for this pipeline run
        test_type: Type of test that completed
        passed: Whether tests passed
        iterations: Total iterations executed
        files_fixed: Number of files fixed
    """

    pipeline_run_id: str = ""
    test_type: str = ""
    passed: bool = False
    iterations: int = 0
    files_fixed: int = 0

    def __post_init__(self) -> None:
        """Validate event after initialization."""
        super().__post_init__()
        if not self.pipeline_run_id:
            raise ValueError("pipeline_run_id is required")
        if not self.test_type:
            raise ValueError("test_type is required")

    def to_dict(self) -> dict:
        """Serialize to dictionary."""
        d = super().to_dict()
        d.update({
            "pipeline_run_id": self.pipeline_run_id,
            "test_type": self.test_type,
            "passed": self.passed,
            "iterations": self.iterations,
            "files_fixed": self.files_fixed,
        })
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "RepairCycleTestCycleCompletedEvent":
        """Deserialize from dictionary."""
        return cls(
            type=data.get("type", "repair_cycle.test_cycle_completed"),
            timestamp=data.get("timestamp", ""),
            source=data.get("source", ""),
            correlation_id=data.get("correlation_id"),
            event_id=data.get("event_id") or str(uuid4()),
            pipeline_run_id=data.get("pipeline_run_id", ""),
            test_type=data.get("test_type", ""),
            passed=data.get("passed", False),
            iterations=data.get("iterations", 0),
            files_fixed=data.get("files_fixed", 0),
        )


@dataclass(frozen=True)
class RepairCycleFileFixStartedEvent(CodetoreumEvent):
    """Emitted when starting to fix failures in a file.

    Attributes:
        type: Fixed to "repair_cycle.file_fix_started"
        pipeline_run_id: Unique identifier for this pipeline run
        file_path: Path to the file being fixed
        failure_count: Number of failures in this file
    """

    pipeline_run_id: str = ""
    file_path: str = ""
    failure_count: int = 0

    def __post_init__(self) -> None:
        """Validate event after initialization."""
        super().__post_init__()
        if not self.pipeline_run_id:
            raise ValueError("pipeline_run_id is required")
        if not self.file_path:
            raise ValueError("file_path is required")

    def to_dict(self) -> dict:
        """Serialize to dictionary."""
        d = super().to_dict()
        d.update({
            "pipeline_run_id": self.pipeline_run_id,
            "file_path": self.file_path,
            "failure_count": self.failure_count,
        })
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "RepairCycleFileFixStartedEvent":
        """Deserialize from dictionary."""
        return cls(
            type=data.get("type", "repair_cycle.file_fix_started"),
            timestamp=data.get("timestamp", ""),
            source=data.get("source", ""),
            correlation_id=data.get("correlation_id"),
            event_id=data.get("event_id") or str(uuid4()),
            pipeline_run_id=data.get("pipeline_run_id", ""),
            file_path=data.get("file_path", ""),
            failure_count=data.get("failure_count", 0),
        )


@dataclass(frozen=True)
class RepairCycleFileFixCompletedEvent(CodetoreumEvent):
    """Emitted when file fix is completed.

    Attributes:
        type: Fixed to "repair_cycle.file_fix_completed"
        pipeline_run_id: Unique identifier for this pipeline run
        file_path: Path to the file that was fixed
        fixed: Whether the file was successfully fixed
        iterations_used: Number of iterations used to fix this file
    """

    pipeline_run_id: str = ""
    file_path: str = ""
    fixed: bool = False
    iterations_used: int = 0

    def __post_init__(self) -> None:
        """Validate event after initialization."""
        super().__post_init__()
        if not self.pipeline_run_id:
            raise ValueError("pipeline_run_id is required")
        if not self.file_path:
            raise ValueError("file_path is required")

    def to_dict(self) -> dict:
        """Serialize to dictionary."""
        d = super().to_dict()
        d.update({
            "pipeline_run_id": self.pipeline_run_id,
            "file_path": self.file_path,
            "fixed": self.fixed,
            "iterations_used": self.iterations_used,
        })
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "RepairCycleFileFixCompletedEvent":
        """Deserialize from dictionary."""
        return cls(
            type=data.get("type", "repair_cycle.file_fix_completed"),
            timestamp=data.get("timestamp", ""),
            source=data.get("source", ""),
            correlation_id=data.get("correlation_id"),
            event_id=data.get("event_id") or str(uuid4()),
            pipeline_run_id=data.get("pipeline_run_id", ""),
            file_path=data.get("file_path", ""),
            fixed=data.get("fixed", False),
            iterations_used=data.get("iterations_used", 0),
        )


@dataclass(frozen=True)
class RepairCycleWarningReviewStartedEvent(CodetoreumEvent):
    """Emitted when starting to review test warnings.

    Attributes:
        type: Fixed to "repair_cycle.warning_review_started"
        pipeline_run_id: Unique identifier for this pipeline run
        test_type: Type of test being reviewed
        warning_count: Number of warnings to review
    """

    pipeline_run_id: str = ""
    test_type: str = ""
    warning_count: int = 0

    def __post_init__(self) -> None:
        """Validate event after initialization."""
        super().__post_init__()
        if not self.pipeline_run_id:
            raise ValueError("pipeline_run_id is required")
        if not self.test_type:
            raise ValueError("test_type is required")

    def to_dict(self) -> dict:
        """Serialize to dictionary."""
        d = super().to_dict()
        d.update({
            "pipeline_run_id": self.pipeline_run_id,
            "test_type": self.test_type,
            "warning_count": self.warning_count,
        })
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "RepairCycleWarningReviewStartedEvent":
        """Deserialize from dictionary."""
        return cls(
            type=data.get("type", "repair_cycle.warning_review_started"),
            timestamp=data.get("timestamp", ""),
            source=data.get("source", ""),
            correlation_id=data.get("correlation_id"),
            event_id=data.get("event_id") or str(uuid4()),
            pipeline_run_id=data.get("pipeline_run_id", ""),
            test_type=data.get("test_type", ""),
            warning_count=data.get("warning_count", 0),
        )


@dataclass(frozen=True)
class RepairCycleWarningReviewCompletedEvent(CodetoreumEvent):
    """Emitted when warning review is completed.

    Attributes:
        type: Fixed to "repair_cycle.warning_review_completed"
        pipeline_run_id: Unique identifier for this pipeline run
        test_type: Type of test whose warnings were reviewed
        warnings_reviewed: Number of warnings reviewed
    """

    pipeline_run_id: str = ""
    test_type: str = ""
    warnings_reviewed: int = 0

    def __post_init__(self) -> None:
        """Validate event after initialization."""
        super().__post_init__()
        if not self.pipeline_run_id:
            raise ValueError("pipeline_run_id is required")
        if not self.test_type:
            raise ValueError("test_type is required")

    def to_dict(self) -> dict:
        """Serialize to dictionary."""
        d = super().to_dict()
        d.update({
            "pipeline_run_id": self.pipeline_run_id,
            "test_type": self.test_type,
            "warnings_reviewed": self.warnings_reviewed,
        })
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "RepairCycleWarningReviewCompletedEvent":
        """Deserialize from dictionary."""
        return cls(
            type=data.get("type", "repair_cycle.warning_review_completed"),
            timestamp=data.get("timestamp", ""),
            source=data.get("source", ""),
            correlation_id=data.get("correlation_id"),
            event_id=data.get("event_id") or str(uuid4()),
            pipeline_run_id=data.get("pipeline_run_id", ""),
            test_type=data.get("test_type", ""),
            warnings_reviewed=data.get("warnings_reviewed", 0),
        )


@dataclass(frozen=True)
class RepairCycleFastFailEvent(CodetoreumEvent):
    """Emitted when repair cycle stops early (circuit breaker or fast-fail).

    Attributes:
        type: Fixed to "repair_cycle.fast_fail"
        pipeline_run_id: Unique identifier for this pipeline run
        reason: Reason for early termination (e.g., "max_iterations", "circuit_breaker")
        test_type: Type of test when failure occurred (optional)
        iteration: Iteration when failure occurred (optional)
    """

    pipeline_run_id: str = ""
    reason: str = ""
    test_type: Optional[str] = None
    iteration: int = 0

    def __post_init__(self) -> None:
        """Validate event after initialization."""
        super().__post_init__()
        if not self.pipeline_run_id:
            raise ValueError("pipeline_run_id is required")
        if not self.reason:
            raise ValueError("reason is required")

    def to_dict(self) -> dict:
        """Serialize to dictionary."""
        d = super().to_dict()
        d.update({
            "pipeline_run_id": self.pipeline_run_id,
            "reason": self.reason,
            "test_type": self.test_type,
            "iteration": self.iteration,
        })
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "RepairCycleFastFailEvent":
        """Deserialize from dictionary."""
        return cls(
            type=data.get("type", "repair_cycle.fast_fail"),
            timestamp=data.get("timestamp", ""),
            source=data.get("source", ""),
            correlation_id=data.get("correlation_id"),
            event_id=data.get("event_id") or str(uuid4()),
            pipeline_run_id=data.get("pipeline_run_id", ""),
            reason=data.get("reason", ""),
            test_type=data.get("test_type"),
            iteration=data.get("iteration", 0),
        )


@dataclass(frozen=True)
class RepairCycleCompletedEvent(CodetoreumEvent):
    """Emitted when repair cycle completes (successfully or with errors).

    Attributes:
        type: Fixed to "repair_cycle.completed"
        pipeline_run_id: Unique identifier for this pipeline run
        stage_name: Name of the workflow stage
        overall_success: Whether all tests passed
        total_iterations: Total iterations executed across all test types
        total_agent_calls: Total agent executions
        duration_seconds: Total time for cycle
    """

    pipeline_run_id: str = ""
    stage_name: str = ""
    overall_success: bool = False
    total_iterations: int = 0
    total_agent_calls: int = 0
    duration_seconds: float = 0.0

    def __post_init__(self) -> None:
        """Validate event after initialization."""
        super().__post_init__()
        if not self.pipeline_run_id:
            raise ValueError("pipeline_run_id is required")
        if not self.stage_name:
            raise ValueError("stage_name is required")

    def to_dict(self) -> dict:
        """Serialize to dictionary."""
        d = super().to_dict()
        d.update({
            "pipeline_run_id": self.pipeline_run_id,
            "stage_name": self.stage_name,
            "overall_success": self.overall_success,
            "total_iterations": self.total_iterations,
            "total_agent_calls": self.total_agent_calls,
            "duration_seconds": self.duration_seconds,
        })
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "RepairCycleCompletedEvent":
        """Deserialize from dictionary."""
        return cls(
            type=data.get("type", "repair_cycle.completed"),
            timestamp=data.get("timestamp", ""),
            source=data.get("source", ""),
            correlation_id=data.get("correlation_id"),
            event_id=data.get("event_id") or str(uuid4()),
            pipeline_run_id=data.get("pipeline_run_id", ""),
            stage_name=data.get("stage_name", ""),
            overall_success=data.get("overall_success", False),
            total_iterations=data.get("total_iterations", 0),
            total_agent_calls=data.get("total_agent_calls", 0),
            duration_seconds=data.get("duration_seconds", 0.0),
        )
