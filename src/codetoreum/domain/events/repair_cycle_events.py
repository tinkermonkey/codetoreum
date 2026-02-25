"""Repair cycle domain events for iterative test-driven code fixing.

Events track the lifecycle of the repair cycle where AI agents iteratively
execute tests, identify failures/warnings, and fix issues until tests pass
or max iterations are reached.

The repair cycle executes test types in order (UNIT → INTEGRATION → E2E),
and for each test type, runs up to max_iterations cycles of:
1. Execute test (RepairCycleTestExecutionStarted → RepairCycleTestExecutionCompleted)
2. If failures, agent fixes issues (RepairCycleFixCycleStarted → file fix events)
3. If warnings and review enabled, agent reviews (RepairCycleWarningReviewStarted → RepairCycleWarningReviewCompleted)
4. Validate fixes by re-running tests

**Immutability**: All events are immutable (frozen dataclasses) to maintain
event sourcing audit trail integrity. Events represent immutable facts
about test execution and repair steps—they cannot be modified after creation.
"""

import warnings
from dataclasses import dataclass
from uuid import uuid4

from ..repair_cycle_types import (
    CycleResult,
    RepairTestFailure,
    RepairTestType,
    RepairTestWarning,
)
from .adapter_events import CodetoreumEvent


@dataclass(frozen=True)
class RepairCycleStartedEvent(CodetoreumEvent):
    """Emitted when repair cycle starts.

    **Immutability**: This is an immutable event (frozen dataclass). All fields
    are read-only after construction to maintain event sourcing audit trail
    integrity. Attempting to modify any field will raise `FrozenInstanceError`.

    Attributes:
        type (str): Fixed to "repair_cycle.started"
        stage_name (str): Name of the workflow stage (e.g., "fix_failures")
        test_types (Tuple[RepairTestType, ...]): Test types to execute in order
        workflow_run_id (str): ID of the workflow run
        timestamp (str): ISO 8601 timestamp when cycle started
    """

    stage_name: str = ""
    test_types: tuple[RepairTestType, ...] = ()
    workflow_run_id: str = ""

    def __post_init__(self) -> None:
        """Validate event after initialization."""
        super().__post_init__()
        if not self.stage_name:
            raise ValueError("stage_name is required")
        if not self.test_types:
            raise ValueError("test_types must not be empty")
        if not self.workflow_run_id:
            raise ValueError("workflow_run_id is required")

    def to_dict(self) -> dict:
        """Serialize to dictionary."""
        d = super().to_dict()
        d.update({
            "stage_name": self.stage_name,
            "test_types": [t.value for t in self.test_types],
            "workflow_run_id": self.workflow_run_id,
        })
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "RepairCycleStartedEvent":
        """Deserialize from dictionary with backward compatibility."""
        test_types = tuple(
            RepairTestType(t) if isinstance(t, str) else t
            for t in data.get("test_types", [])
        )
        # Backward compatibility: Support both old and new field names
        if "pipeline_run_id" in data and "workflow_run_id" not in data:
            warnings.warn(
                "Field 'pipeline_run_id' is deprecated and will be removed in v3.0. "
                "Use 'workflow_run_id' instead.",
                DeprecationWarning,
                stacklevel=2
            )
        workflow_run_id = data.get("workflow_run_id") or data.get("pipeline_run_id", "")
        return cls(
            type=data.get("type", "repair_cycle.started"),
            timestamp=data.get("timestamp", ""),
            source=data.get("source", ""),
            correlation_id=data.get("correlation_id"),
            event_id=data.get("event_id") or str(uuid4()),
            stage_name=data.get("stage_name", ""),
            test_types=test_types,
            workflow_run_id=workflow_run_id,
        )


@dataclass(frozen=True)
class RepairCycleTestExecutionStartedEvent(CodetoreumEvent):
    """Emitted before test execution within repair cycle (FR-1.6).

    **Immutability**: This is an immutable event (frozen dataclass). All fields
    are read-only after construction to maintain event sourcing audit trail
    integrity. Attempting to modify any field will raise `FrozenInstanceError`.

    Attributes:
        type (str): Fixed to "repair_cycle.test_execution_started"
        test_type (RepairTestType): Type of test being executed (UNIT, INTEGRATION, E2E)
        test_type_index (int): Position in test type sequence (1st, 2nd, 3rd)
        test_cycle_iteration (int): Current iteration number (1-based)
        max_test_cycle_iterations (int): Maximum iterations allowed
        timeout (int): Timeout in seconds for this test execution
        workflow_run_id (str): ID of the workflow run
        timestamp (str): ISO 8601 timestamp when test execution started
    """

    test_type: RepairTestType = RepairTestType.UNIT
    test_type_index: int = 0
    test_cycle_iteration: int = 0
    max_test_cycle_iterations: int = 0
    timeout: int = 0
    workflow_run_id: str = ""

    def __post_init__(self) -> None:
        """Validate event after initialization."""
        super().__post_init__()
        if self.test_type_index < 1:
            raise ValueError("test_type_index must be >= 1")
        if self.test_cycle_iteration < 1:
            raise ValueError("test_cycle_iteration must be >= 1")
        if self.max_test_cycle_iterations < 1:
            raise ValueError("max_test_cycle_iterations must be >= 1")
        if self.timeout <= 0:
            raise ValueError("timeout must be > 0")
        if not self.workflow_run_id:
            raise ValueError("workflow_run_id is required")

    def to_dict(self) -> dict:
        """Serialize to dictionary."""
        d = super().to_dict()
        d.update({
            "test_type": self.test_type.value,
            "test_type_index": self.test_type_index,
            "test_cycle_iteration": self.test_cycle_iteration,
            "max_test_cycle_iterations": self.max_test_cycle_iterations,
            "timeout": self.timeout,
            "workflow_run_id": self.workflow_run_id,
        })
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "RepairCycleTestExecutionStartedEvent":
        """Deserialize from dictionary with backward compatibility."""
        test_type = (
            RepairTestType(data.get("test_type"))
            if isinstance(data.get("test_type"), str)
            else RepairTestType.UNIT
        )
        # Backward compatibility: Support both old and new field names
        if "pipeline_run_id" in data and "workflow_run_id" not in data:
            warnings.warn(
                "Field 'pipeline_run_id' is deprecated and will be removed in v3.0. "
                "Use 'workflow_run_id' instead.",
                DeprecationWarning,
                stacklevel=2
            )
        workflow_run_id = data.get("workflow_run_id") or data.get("pipeline_run_id", "")
        return cls(
            type=data.get("type", "repair_cycle.test_execution_started"),
            timestamp=data.get("timestamp", ""),
            source=data.get("source", ""),
            correlation_id=data.get("correlation_id"),
            event_id=data.get("event_id") or str(uuid4()),
            test_type=test_type,
            test_type_index=data.get("test_type_index", 0),
            test_cycle_iteration=data.get("test_cycle_iteration", 0),
            max_test_cycle_iterations=data.get("max_test_cycle_iterations", 0),
            timeout=data.get("timeout", 0),
            workflow_run_id=workflow_run_id,
        )


@dataclass(frozen=True)
class RepairCycleTestExecutionCompletedEvent(CodetoreumEvent):
    """Emitted after test execution completes (FR-1.7).

    **Immutability**: This is an immutable event (frozen dataclass). All fields
    are read-only after construction to maintain event sourcing audit trail
    integrity. Attempting to modify any field will raise `FrozenInstanceError`.

    Attributes:
        type (str): Fixed to "repair_cycle.test_execution_completed"
        test_type (RepairTestType): Type of test that was executed
        test_type_index (int): Position in test type sequence
        test_cycle_iteration (int): Current iteration number
        passed (int): Number of tests that passed
        failed (int): Number of tests that failed
        warnings (int): Number of warnings found
        has_failures (bool): True if any tests failed
        failures (Tuple[RepairTestFailure, ...]): Details of each failure
        workflow_run_id (str): ID of the workflow run
        timestamp (str): ISO 8601 timestamp when test execution completed
    """

    test_type: RepairTestType = RepairTestType.UNIT
    test_type_index: int = 0
    test_cycle_iteration: int = 0
    passed: int = 0
    failed: int = 0
    warnings: int = 0
    has_failures: bool = False
    failures: tuple[RepairTestFailure, ...] = ()
    workflow_run_id: str = ""

    def __post_init__(self) -> None:
        """Validate event after initialization."""
        super().__post_init__()
        if self.test_type_index < 1:
            raise ValueError("test_type_index must be >= 1")
        if self.test_cycle_iteration < 1:
            raise ValueError("test_cycle_iteration must be >= 1")
        if self.passed < 0:
            raise ValueError("passed must be >= 0")
        if self.failed < 0:
            raise ValueError("failed must be >= 0")
        if self.warnings < 0:
            raise ValueError("warnings must be >= 0")
        if not self.workflow_run_id:
            raise ValueError("workflow_run_id is required")

        # Consistency validation: has_failures must match failed > 0
        if self.has_failures != (self.failed > 0):
            raise ValueError(
                f"has_failures ({self.has_failures}) must match failed > 0 ({self.failed > 0})"
            )

        # Consistency validation: failed count must match failures tuple length
        if self.failed != len(self.failures):
            raise ValueError(
                f"failed count ({self.failed}) must match len(failures) ({len(self.failures)})"
            )

    def to_dict(self) -> dict:
        """Serialize to dictionary."""
        d = super().to_dict()
        d.update({
            "test_type": self.test_type.value,
            "test_type_index": self.test_type_index,
            "test_cycle_iteration": self.test_cycle_iteration,
            "passed": self.passed,
            "failed": self.failed,
            "warnings": self.warnings,
            "has_failures": self.has_failures,
            "failures": [
                {"file": f.file, "test": f.test, "message": f.message}
                for f in self.failures
            ],
            "workflow_run_id": self.workflow_run_id,
        })
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "RepairCycleTestExecutionCompletedEvent":
        """Deserialize from dictionary with backward compatibility."""
        test_type = (
            RepairTestType(data.get("test_type"))
            if isinstance(data.get("test_type"), str)
            else RepairTestType.UNIT
        )
        failures = tuple(
            RepairTestFailure(
                file=f.get("file", ""),
                test=f.get("test", ""),
                message=f.get("message", ""),
            )
            for f in data.get("failures", [])
        )
        # Backward compatibility: Support both old and new field names
        if "pipeline_run_id" in data and "workflow_run_id" not in data:
            warnings.warn(
                "Field 'pipeline_run_id' is deprecated and will be removed in v3.0. "
                "Use 'workflow_run_id' instead.",
                DeprecationWarning,
                stacklevel=2
            )
        workflow_run_id = data.get("workflow_run_id") or data.get("pipeline_run_id", "")
        return cls(
            type=data.get("type", "repair_cycle.test_execution_completed"),
            timestamp=data.get("timestamp", ""),
            source=data.get("source", ""),
            correlation_id=data.get("correlation_id"),
            event_id=data.get("event_id") or str(uuid4()),
            test_type=test_type,
            test_type_index=data.get("test_type_index", 0),
            test_cycle_iteration=data.get("test_cycle_iteration", 0),
            passed=data.get("passed", 0),
            failed=data.get("failed", 0),
            warnings=data.get("warnings", 0),
            has_failures=data.get("has_failures", False),
            failures=failures,
            workflow_run_id=workflow_run_id,
        )


@dataclass(frozen=True)
class RepairCycleFixCycleStartedEvent(CodetoreumEvent):
    """Emitted when fix cycle starts after test failures (FR-3.2).

    **Immutability**: This is an immutable event (frozen dataclass). All fields
    are read-only after construction to maintain event sourcing audit trail
    integrity. Attempting to modify any field will raise `FrozenInstanceError`.

    Attributes:
        type (str): Fixed to "repair_cycle.fix_cycle_started"
        test_type (RepairTestType): Type of test that failed
        test_type_index (int): Position in test type sequence
        test_cycle_iteration (int): Current iteration number
        file_count (int): Number of files with failures to fix
        total_failures (int): Total number of failures across all files
        workflow_run_id (str): ID of the workflow run
        timestamp (str): ISO 8601 timestamp when fix cycle started
    """

    test_type: RepairTestType = RepairTestType.UNIT
    test_type_index: int = 0
    test_cycle_iteration: int = 0
    file_count: int = 0
    total_failures: int = 0
    workflow_run_id: str = ""

    def __post_init__(self) -> None:
        """Validate event after initialization."""
        super().__post_init__()
        if self.test_type_index < 1:
            raise ValueError("test_type_index must be >= 1")
        if self.test_cycle_iteration < 1:
            raise ValueError("test_cycle_iteration must be >= 1")
        if self.file_count < 1:
            raise ValueError("file_count must be >= 1")
        if self.total_failures < 1:
            raise ValueError("total_failures must be >= 1")
        if not self.workflow_run_id:
            raise ValueError("workflow_run_id is required")

    def to_dict(self) -> dict:
        """Serialize to dictionary."""
        d = super().to_dict()
        d.update({
            "test_type": self.test_type.value,
            "test_type_index": self.test_type_index,
            "test_cycle_iteration": self.test_cycle_iteration,
            "file_count": self.file_count,
            "total_failures": self.total_failures,
            "workflow_run_id": self.workflow_run_id,
        })
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "RepairCycleFixCycleStartedEvent":
        """Deserialize from dictionary with backward compatibility."""
        test_type = (
            RepairTestType(data.get("test_type"))
            if isinstance(data.get("test_type"), str)
            else RepairTestType.UNIT
        )
        # Backward compatibility: Support both old and new field names
        if "pipeline_run_id" in data and "workflow_run_id" not in data:
            warnings.warn(
                "Field 'pipeline_run_id' is deprecated and will be removed in v3.0. "
                "Use 'workflow_run_id' instead.",
                DeprecationWarning,
                stacklevel=2
            )
        workflow_run_id = data.get("workflow_run_id") or data.get("pipeline_run_id", "")
        return cls(
            type=data.get("type", "repair_cycle.fix_cycle_started"),
            timestamp=data.get("timestamp", ""),
            source=data.get("source", ""),
            correlation_id=data.get("correlation_id"),
            event_id=data.get("event_id") or str(uuid4()),
            test_type=test_type,
            test_type_index=data.get("test_type_index", 0),
            test_cycle_iteration=data.get("test_cycle_iteration", 0),
            file_count=data.get("file_count", 0),
            total_failures=data.get("total_failures", 0),
            workflow_run_id=workflow_run_id,
        )


@dataclass(frozen=True)
class RepairCycleFileFixStartedEvent(CodetoreumEvent):
    """Emitted before fixing a specific file (FR-3.3).

    **Immutability**: This is an immutable event (frozen dataclass). All fields
    are read-only after construction to maintain event sourcing audit trail
    integrity. Attempting to modify any field will raise `FrozenInstanceError`.

    Attributes:
        type (str): Fixed to "repair_cycle.file_fix_started"
        test_file (str): Path to the test file with failures
        failure_count (int): Number of failures in this file
        test_type (RepairTestType): Type of test that failed
        workflow_run_id (str): ID of the workflow run
        timestamp (str): ISO 8601 timestamp when file fix started
    """

    test_file: str = ""
    failure_count: int = 0
    test_type: RepairTestType = RepairTestType.UNIT
    workflow_run_id: str = ""

    def __post_init__(self) -> None:
        """Validate event after initialization."""
        super().__post_init__()
        if not self.test_file:
            raise ValueError("test_file is required")
        if self.failure_count < 1:
            raise ValueError("failure_count must be >= 1")
        if not self.workflow_run_id:
            raise ValueError("workflow_run_id is required")

    def to_dict(self) -> dict:
        """Serialize to dictionary."""
        d = super().to_dict()
        d.update({
            "test_file": self.test_file,
            "failure_count": self.failure_count,
            "test_type": self.test_type.value,
            "workflow_run_id": self.workflow_run_id,
        })
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "RepairCycleFileFixStartedEvent":
        """Deserialize from dictionary with backward compatibility."""
        test_type = (
            RepairTestType(data.get("test_type"))
            if isinstance(data.get("test_type"), str)
            else RepairTestType.UNIT
        )
        # Backward compatibility: Support both old and new field names
        if "pipeline_run_id" in data and "workflow_run_id" not in data:
            warnings.warn(
                "Field 'pipeline_run_id' is deprecated and will be removed in v3.0. "
                "Use 'workflow_run_id' instead.",
                DeprecationWarning,
                stacklevel=2
            )
        workflow_run_id = data.get("workflow_run_id") or data.get("pipeline_run_id", "")
        return cls(
            type=data.get("type", "repair_cycle.file_fix_started"),
            timestamp=data.get("timestamp", ""),
            source=data.get("source", ""),
            correlation_id=data.get("correlation_id"),
            event_id=data.get("event_id") or str(uuid4()),
            test_file=data.get("test_file", ""),
            failure_count=data.get("failure_count", 0),
            test_type=test_type,
            workflow_run_id=workflow_run_id,
        )


@dataclass(frozen=True)
class RepairCycleFileFixCompletedEvent(CodetoreumEvent):
    """Emitted after fixing a specific file (FR-3.5).

    **Immutability**: This is an immutable event (frozen dataclass). All fields
    are read-only after construction to maintain event sourcing audit trail
    integrity. Attempting to modify any field will raise `FrozenInstanceError`.

    Attributes:
        type (str): Fixed to "repair_cycle.file_fix_completed"
        test_file (str): Path to the test file
        failure_count (int): Number of failures that were in this file
        test_type (RepairTestType): Type of test
        success (bool): True if fix was successful
        workflow_run_id (str): ID of the workflow run
        timestamp (str): ISO 8601 timestamp when file fix completed
    """

    test_file: str = ""
    failure_count: int = 0
    test_type: RepairTestType = RepairTestType.UNIT
    success: bool = False
    workflow_run_id: str = ""

    def __post_init__(self) -> None:
        """Validate event after initialization."""
        super().__post_init__()
        if not self.test_file:
            raise ValueError("test_file is required")
        if self.failure_count < 1:
            raise ValueError("failure_count must be >= 1")
        if not self.workflow_run_id:
            raise ValueError("workflow_run_id is required")

    def to_dict(self) -> dict:
        """Serialize to dictionary."""
        d = super().to_dict()
        d.update({
            "test_file": self.test_file,
            "failure_count": self.failure_count,
            "test_type": self.test_type.value,
            "success": self.success,
            "workflow_run_id": self.workflow_run_id,
        })
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "RepairCycleFileFixCompletedEvent":
        """Deserialize from dictionary with backward compatibility."""
        test_type = (
            RepairTestType(data.get("test_type"))
            if isinstance(data.get("test_type"), str)
            else RepairTestType.UNIT
        )
        # Backward compatibility: Support both old and new field names
        if "pipeline_run_id" in data and "workflow_run_id" not in data:
            warnings.warn(
                "Field 'pipeline_run_id' is deprecated and will be removed in v3.0. "
                "Use 'workflow_run_id' instead.",
                DeprecationWarning,
                stacklevel=2
            )
        workflow_run_id = data.get("workflow_run_id") or data.get("pipeline_run_id", "")
        return cls(
            type=data.get("type", "repair_cycle.file_fix_completed"),
            timestamp=data.get("timestamp", ""),
            source=data.get("source", ""),
            correlation_id=data.get("correlation_id"),
            event_id=data.get("event_id") or str(uuid4()),
            test_file=data.get("test_file", ""),
            failure_count=data.get("failure_count", 0),
            test_type=test_type,
            success=data.get("success", False),
            workflow_run_id=workflow_run_id,
        )


@dataclass(frozen=True)
class RepairCycleWarningReviewStartedEvent(CodetoreumEvent):
    """Emitted before reviewing warnings for a file (FR-5.4).

    **Immutability**: This is an immutable event (frozen dataclass). All fields
    are read-only after construction to maintain event sourcing audit trail
    integrity. Attempting to modify any field will raise `FrozenInstanceError`.

    Attributes:
        type (str): Fixed to "repair_cycle.warning_review_started"
        source_file (str): Path to the source file with warnings
        warning_count (int): Number of warnings found in file
        test_type (RepairTestType): Type of test that found warnings
        warnings (Tuple[RepairTestWarning, ...]): Details of each warning
        workflow_run_id (str): ID of the workflow run
        timestamp (str): ISO 8601 timestamp when warning review started
    """

    source_file: str = ""
    warning_count: int = 0
    test_type: RepairTestType = RepairTestType.UNIT
    warnings: tuple[RepairTestWarning, ...] = ()
    workflow_run_id: str = ""

    def __post_init__(self) -> None:
        """Validate event after initialization."""
        super().__post_init__()
        if not self.source_file:
            raise ValueError("source_file is required")
        if self.warning_count < 1:
            raise ValueError("warning_count must be >= 1")
        if not self.workflow_run_id:
            raise ValueError("workflow_run_id is required")

    def to_dict(self) -> dict:
        """Serialize to dictionary."""
        d = super().to_dict()
        d.update({
            "source_file": self.source_file,
            "warning_count": self.warning_count,
            "test_type": self.test_type.value,
            "warnings": [
                {"file": w.file, "message": w.message}
                for w in self.warnings
            ],
            "workflow_run_id": self.workflow_run_id,
        })
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "RepairCycleWarningReviewStartedEvent":
        """Deserialize from dictionary with backward compatibility."""
        test_type = (
            RepairTestType(data.get("test_type"))
            if isinstance(data.get("test_type"), str)
            else RepairTestType.UNIT
        )
        warnings_list = tuple(
            RepairTestWarning(
                file=w.get("file", ""),
                message=w.get("message", ""),
            )
            for w in data.get("warnings", [])
        )
        # Backward compatibility: Support both old and new field names
        if "pipeline_run_id" in data and "workflow_run_id" not in data:
            warnings.warn(
                "Field 'pipeline_run_id' is deprecated and will be removed in v3.0. "
                "Use 'workflow_run_id' instead.",
                DeprecationWarning,
                stacklevel=2
            )
        workflow_run_id = data.get("workflow_run_id") or data.get("pipeline_run_id", "")
        return cls(
            type=data.get("type", "repair_cycle.warning_review_started"),
            timestamp=data.get("timestamp", ""),
            source=data.get("source", ""),
            correlation_id=data.get("correlation_id"),
            event_id=data.get("event_id") or str(uuid4()),
            source_file=data.get("source_file", ""),
            warning_count=data.get("warning_count", 0),
            test_type=test_type,
            warnings=warnings_list,
            workflow_run_id=workflow_run_id,
        )


@dataclass(frozen=True)
class RepairCycleWarningReviewCompletedEvent(CodetoreumEvent):
    """Emitted after warning review completes (FR-5.6).

    **Immutability**: This is an immutable event (frozen dataclass). All fields
    are read-only after construction to maintain event sourcing audit trail
    integrity. Attempting to modify any field will raise `FrozenInstanceError`.

    Attributes:
        type (str): Fixed to "repair_cycle.warning_review_completed"
        source_file (str): Path to the source file
        warning_count (int): Number of warnings that were reviewed
        test_type (RepairTestType): Type of test
        success (bool): True if warning review was successful
        workflow_run_id (str): ID of the workflow run
        timestamp (str): ISO 8601 timestamp when warning review completed
    """

    source_file: str = ""
    warning_count: int = 0
    test_type: RepairTestType = RepairTestType.UNIT
    success: bool = False
    workflow_run_id: str = ""

    def __post_init__(self) -> None:
        """Validate event after initialization."""
        super().__post_init__()
        if not self.source_file:
            raise ValueError("source_file is required")
        if self.warning_count < 1:
            raise ValueError("warning_count must be >= 1")
        if not self.workflow_run_id:
            raise ValueError("workflow_run_id is required")

    def to_dict(self) -> dict:
        """Serialize to dictionary."""
        d = super().to_dict()
        d.update({
            "source_file": self.source_file,
            "warning_count": self.warning_count,
            "test_type": self.test_type.value,
            "success": self.success,
            "workflow_run_id": self.workflow_run_id,
        })
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "RepairCycleWarningReviewCompletedEvent":
        """Deserialize from dictionary with backward compatibility."""
        test_type = (
            RepairTestType(data.get("test_type"))
            if isinstance(data.get("test_type"), str)
            else RepairTestType.UNIT
        )
        # Backward compatibility: Support both old and new field names
        if "pipeline_run_id" in data and "workflow_run_id" not in data:
            warnings.warn(
                "Field 'pipeline_run_id' is deprecated and will be removed in v3.0. "
                "Use 'workflow_run_id' instead.",
                DeprecationWarning,
                stacklevel=2
            )
        workflow_run_id = data.get("workflow_run_id") or data.get("pipeline_run_id", "")
        return cls(
            type=data.get("type", "repair_cycle.warning_review_completed"),
            timestamp=data.get("timestamp", ""),
            source=data.get("source", ""),
            correlation_id=data.get("correlation_id"),
            event_id=data.get("event_id") or str(uuid4()),
            source_file=data.get("source_file", ""),
            warning_count=data.get("warning_count", 0),
            test_type=test_type,
            success=data.get("success", False),
            workflow_run_id=workflow_run_id,
        )


@dataclass(frozen=True)
class RepairCycleTestCycleCompletedEvent(CodetoreumEvent):
    """Emitted when test type cycle completes (FR-4.4).

    **Immutability**: This is an immutable event (frozen dataclass). All fields
    are read-only after construction to maintain event sourcing audit trail
    integrity. Attempting to modify any field will raise `FrozenInstanceError`.

    Attributes:
        type (str): Fixed to "repair_cycle.test_cycle_completed"
        test_type (RepairTestType): Type of test that completed
        test_type_index (int): Position in test type sequence
        passed (bool): True if test cycle passed (all tests passed)
        test_cycle_iterations (int): Number of iterations executed
        files_fixed (int): Number of unique files fixed during this cycle
        warnings_reviewed (int): Number of warnings reviewed and addressed
        error (Optional[str]): Error message if cycle failed, None if successful
        duration_seconds (float): Total time spent on this test type cycle
        workflow_run_id (str): ID of the workflow run
        timestamp (str): ISO 8601 timestamp when test cycle completed
    """

    test_type: RepairTestType = RepairTestType.UNIT
    test_type_index: int = 0
    passed: bool = False
    test_cycle_iterations: int = 0
    files_fixed: int = 0
    warnings_reviewed: int = 0
    error: str | None = None
    duration_seconds: float = 0.0
    workflow_run_id: str = ""

    def __post_init__(self) -> None:
        """Validate event after initialization."""
        super().__post_init__()
        if self.test_type_index < 1:
            raise ValueError("test_type_index must be >= 1")
        if self.test_cycle_iterations < 1:
            raise ValueError("test_cycle_iterations must be >= 1")
        if self.files_fixed < 0:
            raise ValueError("files_fixed must be >= 0")
        if self.warnings_reviewed < 0:
            raise ValueError("warnings_reviewed must be >= 0")
        if self.duration_seconds < 0:
            raise ValueError("duration_seconds must be >= 0")
        if not self.workflow_run_id:
            raise ValueError("workflow_run_id is required")

    def to_dict(self) -> dict:
        """Serialize to dictionary."""
        d = super().to_dict()
        d.update({
            "test_type": self.test_type.value,
            "test_type_index": self.test_type_index,
            "passed": self.passed,
            "test_cycle_iterations": self.test_cycle_iterations,
            "files_fixed": self.files_fixed,
            "warnings_reviewed": self.warnings_reviewed,
            "error": self.error,
            "duration_seconds": self.duration_seconds,
            "workflow_run_id": self.workflow_run_id,
        })
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "RepairCycleTestCycleCompletedEvent":
        """Deserialize from dictionary with backward compatibility."""
        test_type = (
            RepairTestType(data.get("test_type"))
            if isinstance(data.get("test_type"), str)
            else RepairTestType.UNIT
        )
        # Backward compatibility: Support both old and new field names
        if "pipeline_run_id" in data and "workflow_run_id" not in data:
            warnings.warn(
                "Field 'pipeline_run_id' is deprecated and will be removed in v3.0. "
                "Use 'workflow_run_id' instead.",
                DeprecationWarning,
                stacklevel=2
            )
        workflow_run_id = data.get("workflow_run_id") or data.get("pipeline_run_id", "")
        return cls(
            type=data.get("type", "repair_cycle.test_cycle_completed"),
            timestamp=data.get("timestamp", ""),
            source=data.get("source", ""),
            correlation_id=data.get("correlation_id"),
            event_id=data.get("event_id") or str(uuid4()),
            test_type=test_type,
            test_type_index=data.get("test_type_index", 0),
            passed=data.get("passed", False),
            test_cycle_iterations=data.get("test_cycle_iterations", 0),
            files_fixed=data.get("files_fixed", 0),
            warnings_reviewed=data.get("warnings_reviewed", 0),
            error=data.get("error"),
            duration_seconds=data.get("duration_seconds", 0.0),
            workflow_run_id=workflow_run_id,
        )


@dataclass(frozen=True)
class RepairCycleFastFailEvent(CodetoreumEvent):
    """Emitted when fast-fail is triggered (FR-6.2).

    **Immutability**: This is an immutable event (frozen dataclass). All fields
    are read-only after construction to maintain event sourcing audit trail
    integrity. Attempting to modify any field will raise `FrozenInstanceError`.

    Attributes:
        type (str): Fixed to "repair_cycle.fast_fail"
        test_type (RepairTestType): Type of test that triggered fast-fail
        reason (str): Reason for fast-fail (e.g., "max_iterations_exceeded")
        workflow_run_id (str): ID of the workflow run
        timestamp (str): ISO 8601 timestamp when fast-fail was triggered
    """

    test_type: RepairTestType = RepairTestType.UNIT
    reason: str = ""
    workflow_run_id: str = ""

    def __post_init__(self) -> None:
        """Validate event after initialization."""
        super().__post_init__()
        if not self.reason:
            raise ValueError("reason is required")
        if not self.workflow_run_id:
            raise ValueError("workflow_run_id is required")

    def to_dict(self) -> dict:
        """Serialize to dictionary."""
        d = super().to_dict()
        d.update({
            "test_type": self.test_type.value,
            "reason": self.reason,
            "workflow_run_id": self.workflow_run_id,
        })
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "RepairCycleFastFailEvent":
        """Deserialize from dictionary with backward compatibility."""
        test_type = (
            RepairTestType(data.get("test_type"))
            if isinstance(data.get("test_type"), str)
            else RepairTestType.UNIT
        )
        # Backward compatibility: Support both old and new field names
        if "pipeline_run_id" in data and "workflow_run_id" not in data:
            warnings.warn(
                "Field 'pipeline_run_id' is deprecated and will be removed in v3.0. "
                "Use 'workflow_run_id' instead.",
                DeprecationWarning,
                stacklevel=2
            )
        workflow_run_id = data.get("workflow_run_id") or data.get("pipeline_run_id", "")
        return cls(
            type=data.get("type", "repair_cycle.fast_fail"),
            timestamp=data.get("timestamp", ""),
            source=data.get("source", ""),
            correlation_id=data.get("correlation_id"),
            event_id=data.get("event_id") or str(uuid4()),
            test_type=test_type,
            reason=data.get("reason", ""),
            workflow_run_id=workflow_run_id,
        )


@dataclass(frozen=True)
class RepairCycleResumedEvent(CodetoreumEvent):
    """Emitted when repair cycle resumes from a checkpoint.

    **Immutability**: This is an immutable event (frozen dataclass). All fields
    are read-only after construction to maintain event sourcing audit trail
    integrity. Attempting to modify any field will raise `FrozenInstanceError`.

    Attributes:
        type: Fixed to "repair_cycle.resumed"
        workflow_run_id: Unique identifier for this workflow run
        test_type: Test type being resumed (RepairTestType enum for type safety)
        iteration: Iteration number being resumed from
        elapsed_time: Time already spent on this cycle
        agent_calls_so_far: Number of agent calls already made
    """

    workflow_run_id: str = ""
    test_type: RepairTestType = RepairTestType.UNIT
    iteration: int = 0
    elapsed_time: float = 0.0
    agent_calls_so_far: int = 0

    def __post_init__(self) -> None:
        """Validate event after initialization."""
        super().__post_init__()
        if not self.workflow_run_id:
            raise ValueError("workflow_run_id is required")
        if not self.test_type:
            raise ValueError("test_type is required")
        if self.iteration < 1:
            raise ValueError("iteration must be >= 1")
        if self.elapsed_time < 0:
            raise ValueError("elapsed_time must be >= 0")
        if self.agent_calls_so_far < 0:
            raise ValueError("agent_calls_so_far must be >= 0")

    def to_dict(self) -> dict:
        """Serialize to dictionary."""
        d = super().to_dict()
        d.update({
            "workflow_run_id": self.workflow_run_id,
            "test_type": self.test_type.value,  # Serialize enum as string
            "iteration": self.iteration,
            "elapsed_time": self.elapsed_time,
            "agent_calls_so_far": self.agent_calls_so_far,
        })
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "RepairCycleResumedEvent":
        """Deserialize from dictionary with backward compatibility."""
        # Backward compatibility: Support both old and new field names
        if "pipeline_run_id" in data and "workflow_run_id" not in data:
            warnings.warn(
                "Field 'pipeline_run_id' is deprecated and will be removed in v3.0. "
                "Use 'workflow_run_id' instead.",
                DeprecationWarning,
                stacklevel=2
            )
        workflow_run_id = data.get("workflow_run_id") or data.get("pipeline_run_id", "")

        # Deserialize test_type enum
        test_type_str = data.get("test_type", "UNIT")
        test_type = RepairTestType(test_type_str) if test_type_str else RepairTestType.UNIT

        return cls(
            type=data.get("type", "repair_cycle.resumed"),
            timestamp=data.get("timestamp", ""),
            source=data.get("source", ""),
            correlation_id=data.get("correlation_id"),
            event_id=data.get("event_id") or str(uuid4()),
            workflow_run_id=workflow_run_id,
            test_type=test_type,
            iteration=data.get("iteration", 0),
            elapsed_time=data.get("elapsed_time", 0.0),
            agent_calls_so_far=data.get("agent_calls_so_far", 0),
        )


@dataclass(frozen=True)
class RepairCycleCheckpointFailedEvent(CodetoreumEvent):
    """Emitted when checkpoint save fails (recovery may not be possible).

    **Immutability**: This is an immutable event (frozen dataclass). All fields
    are read-only after construction to maintain event sourcing audit trail
    integrity. Attempting to modify any field will raise `FrozenInstanceError`.

    Attributes:
        type (str): Fixed to "repair_cycle.checkpoint_failed"
        workflow_run_id (str): ID of the workflow run
        test_type (str): RepairTestType value
        iteration (int): Current iteration number (1-based)
        error_type (str): Type of error (e.g., "ConnectionError")
        error_message (str): Error message details
        checkpoint_store_type (str): Type of checkpoint store (e.g., "RedisCheckpointStore")
        timestamp (str): ISO 8601 timestamp when checkpoint failed
    """

    workflow_run_id: str = ""
    test_type: str = ""
    iteration: int = 0
    error_type: str = ""
    error_message: str = ""
    checkpoint_store_type: str = ""

    def __post_init__(self) -> None:
        """Validate event after initialization."""
        super().__post_init__()
        if not self.workflow_run_id:
            raise ValueError("workflow_run_id is required")
        if not self.test_type:
            raise ValueError("test_type is required")
        if self.iteration < 0:
            raise ValueError("iteration must be >= 0")
        if not self.error_type:
            raise ValueError("error_type is required")
        if not self.error_message:
            raise ValueError("error_message is required")

    def to_dict(self) -> dict:
        """Serialize to dictionary."""
        d = super().to_dict()
        d.update({
            "workflow_run_id": self.workflow_run_id,
            "test_type": self.test_type,
            "iteration": self.iteration,
            "error_type": self.error_type,
            "error_message": self.error_message,
            "checkpoint_store_type": self.checkpoint_store_type,
        })
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "RepairCycleCheckpointFailedEvent":
        """Deserialize from dictionary with backward compatibility."""
        # Backward compatibility: Support both old and new field names
        if "pipeline_run_id" in data and "workflow_run_id" not in data:
            warnings.warn(
                "Field 'pipeline_run_id' is deprecated and will be removed in v3.0. "
                "Use 'workflow_run_id' instead.",
                DeprecationWarning,
                stacklevel=2
            )
        workflow_run_id = data.get("workflow_run_id") or data.get("pipeline_run_id", "")
        return cls(
            type=data.get("type", "repair_cycle.checkpoint_failed"),
            timestamp=data.get("timestamp", ""),
            source=data.get("source", ""),
            correlation_id=data.get("correlation_id"),
            event_id=data.get("event_id") or str(uuid4()),
            workflow_run_id=workflow_run_id,
            test_type=data.get("test_type", ""),
            iteration=data.get("iteration", 0),
            error_type=data.get("error_type", ""),
            error_message=data.get("error_message", ""),
            checkpoint_store_type=data.get("checkpoint_store_type", ""),
        )


@dataclass(frozen=True)
class RepairCycleMetricsBackendFailedEvent(CodetoreumEvent):
    """Emitted when metrics backend fails (critical observability degradation).

    **Immutability**: This is an immutable event (frozen dataclass). All fields
    are read-only after construction to maintain event sourcing audit trail
    integrity. Attempting to modify any field will raise `FrozenInstanceError`.

    Attributes:
        type (str): Fixed to "repair_cycle.metrics_backend_failed"
        operation (str): Operation that failed (e.g., "repair_cycle_started")
        error_type (str): Type of error (e.g., "ConnectionError")
        error_message (str): Error message details
        consecutive_failures (int): Number of consecutive failures so far
        circuit_breaker_open (bool): True if circuit breaker is now open
        workflow_run_id (str): ID of the workflow run (may be empty if unknown)
        timestamp (str): ISO 8601 timestamp when backend failure occurred
    """

    operation: str = ""
    error_type: str = ""
    error_message: str = ""
    consecutive_failures: int = 0
    circuit_breaker_open: bool = False
    workflow_run_id: str = ""

    def __post_init__(self) -> None:
        """Validate event after initialization."""
        super().__post_init__()
        if not self.operation:
            raise ValueError("operation is required")
        if not self.error_type:
            raise ValueError("error_type is required")
        if not self.error_message:
            raise ValueError("error_message is required")
        if self.consecutive_failures < 0:
            raise ValueError("consecutive_failures must be >= 0")

    def to_dict(self) -> dict:
        """Serialize to dictionary."""
        d = super().to_dict()
        d.update({
            "operation": self.operation,
            "error_type": self.error_type,
            "error_message": self.error_message,
            "consecutive_failures": self.consecutive_failures,
            "circuit_breaker_open": self.circuit_breaker_open,
            "workflow_run_id": self.workflow_run_id,
        })
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "RepairCycleMetricsBackendFailedEvent":
        """Deserialize from dictionary with backward compatibility."""
        # Backward compatibility: Support both old and new field names
        if "pipeline_run_id" in data and "workflow_run_id" not in data:
            warnings.warn(
                "Field 'pipeline_run_id' is deprecated and will be removed in v3.0. "
                "Use 'workflow_run_id' instead.",
                DeprecationWarning,
                stacklevel=2
            )
        workflow_run_id = data.get("workflow_run_id") or data.get("pipeline_run_id", "")
        return cls(
            type=data.get("type", "repair_cycle.metrics_backend_failed"),
            timestamp=data.get("timestamp", ""),
            source=data.get("source", ""),
            correlation_id=data.get("correlation_id"),
            event_id=data.get("event_id") or str(uuid4()),
            operation=data.get("operation", ""),
            error_type=data.get("error_type", ""),
            error_message=data.get("error_message", ""),
            consecutive_failures=data.get("consecutive_failures", 0),
            circuit_breaker_open=data.get("circuit_breaker_open", False),
            workflow_run_id=workflow_run_id,
        )


@dataclass(frozen=True)
class RepairCycleCompletedEvent(CodetoreumEvent):
    """Emitted when entire repair cycle completes (FR-9.1).

    **Immutability**: This is an immutable event (frozen dataclass). All fields
    are read-only after construction to maintain event sourcing audit trail
    integrity. Attempting to modify any field will raise `FrozenInstanceError`.

    Attributes:
        type (str): Fixed to "repair_cycle.completed"
        overall_success (bool): True if all tests passed
        test_results (Tuple[CycleResult, ...]): Results for each test type
        total_agent_calls (int): Total agent calls made during entire cycle
        duration_seconds (float): Total time spent on entire repair cycle
        workflow_run_id (str): ID of the workflow run
        timestamp (str): ISO 8601 timestamp when repair cycle completed
    """

    overall_success: bool = False
    test_results: tuple[CycleResult, ...] = ()
    total_agent_calls: int = 0
    duration_seconds: float = 0.0
    workflow_run_id: str = ""

    def __post_init__(self) -> None:
        """Validate event after initialization."""
        super().__post_init__()
        if not self.test_results:
            raise ValueError("test_results must not be empty")
        if self.total_agent_calls < 0:
            raise ValueError("total_agent_calls must be >= 0")
        if self.duration_seconds < 0:
            raise ValueError("duration_seconds must be >= 0")
        if not self.workflow_run_id:
            raise ValueError("workflow_run_id is required")

    def to_dict(self) -> dict:
        """Serialize to dictionary."""
        d = super().to_dict()
        d.update({
            "overall_success": self.overall_success,
            "test_results": [
                {
                    "test_type": r.test_type.value,
                    "passed": r.passed,
                    "iterations": r.iterations,
                    "files_fixed": r.files_fixed,
                    "warnings_reviewed": r.warnings_reviewed,
                    "duration_seconds": r.duration_seconds,
                    "error": r.error,
                }
                for r in self.test_results
            ],
            "total_agent_calls": self.total_agent_calls,
            "duration_seconds": self.duration_seconds,
            "workflow_run_id": self.workflow_run_id,
        })
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "RepairCycleCompletedEvent":
        """Deserialize from dictionary with backward compatibility."""
        from ..repair_cycle_types import RepairTestResult

        test_results = []
        for tr in data.get("test_results", []):
            test_type = (
                RepairTestType(tr.get("test_type"))
                if isinstance(tr.get("test_type"), str)
                else RepairTestType.UNIT
            )
            final_result = None
            if tr.get("final_result"):
                fr = tr.get("final_result")
                final_test_type = (
                    RepairTestType(fr.get("test_type"))
                    if isinstance(fr.get("test_type"), str)
                    else RepairTestType.UNIT
                )
                failures = tuple(
                    RepairTestFailure(
                        file=f.get("file", ""),
                        test=f.get("test", ""),
                        message=f.get("message", ""),
                    )
                    for f in fr.get("failures", [])
                )
                warning_list = tuple(
                    RepairTestWarning(
                        file=w.get("file", ""),
                        message=w.get("message", ""),
                    )
                    for w in fr.get("warning_list", [])
                )
                final_result = RepairTestResult(
                    test_type=final_test_type,
                    iteration=fr.get("iteration", 0),
                    passed=fr.get("passed", 0),
                    failed=fr.get("failed", 0),
                    warnings=fr.get("warnings", 0),
                    failures=failures,
                    warning_list=warning_list,
                    raw_output=fr.get("raw_output", ""),
                    timestamp=fr.get("timestamp", ""),
                )

            cycle_result = CycleResult(
                test_type=test_type,
                passed=tr.get("passed", False),
                iterations=tr.get("iterations", 0),
                final_result=final_result,
                error=tr.get("error"),
                files_fixed=tr.get("files_fixed", 0),
                warnings_reviewed=tr.get("warnings_reviewed", 0),
                duration_seconds=tr.get("duration_seconds", 0.0),
            )
            test_results.append(cycle_result)

        # Backward compatibility: Support both old and new field names
        if "pipeline_run_id" in data and "workflow_run_id" not in data:
            warnings.warn(
                "Field 'pipeline_run_id' is deprecated and will be removed in v3.0. "
                "Use 'workflow_run_id' instead.",
                DeprecationWarning,
                stacklevel=2
            )
        workflow_run_id = data.get("workflow_run_id") or data.get("pipeline_run_id", "")
        return cls(
            type=data.get("type", "repair_cycle.completed"),
            timestamp=data.get("timestamp", ""),
            source=data.get("source", ""),
            correlation_id=data.get("correlation_id"),
            event_id=data.get("event_id") or str(uuid4()),
            overall_success=data.get("overall_success", False),
            test_results=tuple(test_results),
            total_agent_calls=data.get("total_agent_calls", 0),
            duration_seconds=data.get("duration_seconds", 0.0),
            workflow_run_id=workflow_run_id,
        )
