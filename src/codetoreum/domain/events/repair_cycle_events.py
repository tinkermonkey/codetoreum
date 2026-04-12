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

import logging
import warnings
from dataclasses import dataclass
from uuid import uuid4

from ..repair_cycle_types import (
    CycleResult,
    FailureClassification,
    RepairTestFailure,
    RepairTestType,
    RepairTestWarning,
)
from .adapter_events import CodetoreumEvent

logger = logging.getLogger(__name__)


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
            msg = "stage_name is required"
            raise ValueError(msg)
        if not self.test_types:
            msg = "test_types must not be empty"
            raise ValueError(msg)
        if not self.workflow_run_id:
            msg = "workflow_run_id is required"
            raise ValueError(msg)

    def to_dict(self) -> dict:
        """Serialize to dictionary."""
        d = super().to_dict()
        d.update(
            {
                "stage_name": self.stage_name,
                "test_types": [t.value for t in self.test_types],
                "workflow_run_id": self.workflow_run_id,
            }
        )
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "RepairCycleStartedEvent":
        """Deserialize from dictionary with backward compatibility."""
        test_types = tuple(RepairTestType(t) if isinstance(t, str) else t for t in data.get("test_types", []))
        # Backward compatibility: Support both old and new field names
        if "pipeline_run_id" in data and "workflow_run_id" not in data:
            warnings.warn(
                "Field 'pipeline_run_id' is deprecated and will be removed in v3.0. Use 'workflow_run_id' instead.",
                DeprecationWarning,
                stacklevel=2,
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
            msg = "test_type_index must be >= 1"
            raise ValueError(msg)
        if self.test_cycle_iteration < 1:
            msg = "test_cycle_iteration must be >= 1"
            raise ValueError(msg)
        if self.max_test_cycle_iterations < 1:
            msg = "max_test_cycle_iterations must be >= 1"
            raise ValueError(msg)
        if self.timeout <= 0:
            msg = "timeout must be > 0"
            raise ValueError(msg)
        if not self.workflow_run_id:
            msg = "workflow_run_id is required"
            raise ValueError(msg)

    def to_dict(self) -> dict:
        """Serialize to dictionary."""
        d = super().to_dict()
        d.update(
            {
                "test_type": self.test_type.value,
                "test_type_index": self.test_type_index,
                "test_cycle_iteration": self.test_cycle_iteration,
                "max_test_cycle_iterations": self.max_test_cycle_iterations,
                "timeout": self.timeout,
                "workflow_run_id": self.workflow_run_id,
            }
        )
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "RepairCycleTestExecutionStartedEvent":
        """Deserialize from dictionary with backward compatibility.

        Raises:
            KeyError: If required fields (test_type_index, test_cycle_iteration,
                     max_test_cycle_iterations, timeout, workflow_run_id) are missing.
        """
        test_type = (
            RepairTestType(data.get("test_type")) if isinstance(data.get("test_type"), str) else RepairTestType.UNIT
        )
        # Backward compatibility: Support both old and new field names
        if "pipeline_run_id" in data and "workflow_run_id" not in data:
            warnings.warn(
                "Field 'pipeline_run_id' is deprecated and will be removed in v3.0. Use 'workflow_run_id' instead.",
                DeprecationWarning,
                stacklevel=2,
            )
        workflow_run_id = str(data.get("workflow_run_id") or data.get("pipeline_run_id") or "")
        return cls(
            type=data.get("type", "repair_cycle.test_execution_started"),
            timestamp=data.get("timestamp", ""),
            source=data.get("source", ""),
            correlation_id=data.get("correlation_id"),
            event_id=data.get("event_id") or str(uuid4()),
            test_type=test_type,
            test_type_index=data["test_type_index"],
            test_cycle_iteration=data["test_cycle_iteration"],
            max_test_cycle_iterations=data["max_test_cycle_iterations"],
            timeout=data["timeout"],
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
        agent_name (str): Name of agent that executed tests
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
    agent_name: str = ""
    workflow_run_id: str = ""

    def __post_init__(self) -> None:
        """Validate event after initialization."""
        super().__post_init__()
        if self.test_type_index < 1:
            msg = "test_type_index must be >= 1"
            raise ValueError(msg)
        if self.test_cycle_iteration < 1:
            msg = "test_cycle_iteration must be >= 1"
            raise ValueError(msg)
        if self.passed < 0:
            msg = "passed must be >= 0"
            raise ValueError(msg)
        if self.failed < 0:
            msg = "failed must be >= 0"
            raise ValueError(msg)
        if self.warnings < 0:
            msg = "warnings must be >= 0"
            raise ValueError(msg)
        if not self.agent_name:
            msg = "agent_name is required"
            raise ValueError(msg)
        if not self.workflow_run_id:
            msg = "workflow_run_id is required"
            raise ValueError(msg)

        # Consistency validation: has_failures must match failed > 0
        if self.has_failures != (self.failed > 0):
            msg = f"has_failures ({self.has_failures}) must match failed > 0 ({self.failed > 0})"
            raise ValueError(msg)

        # Consistency validation: failed count must match failures tuple length
        if self.failed != len(self.failures):
            msg = f"failed count ({self.failed}) must match len(failures) ({len(self.failures)})"
            raise ValueError(msg)

    def to_dict(self) -> dict:
        """Serialize to dictionary."""
        d = super().to_dict()
        d.update(
            {
                "test_type": self.test_type.value,
                "test_type_index": self.test_type_index,
                "test_cycle_iteration": self.test_cycle_iteration,
                "passed": self.passed,
                "failed": self.failed,
                "warnings": self.warnings,
                "has_failures": self.has_failures,
                "failures": [{"file": f.file, "test": f.test, "message": f.message} for f in self.failures],
                "agent_name": self.agent_name,
                "workflow_run_id": self.workflow_run_id,
            }
        )
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "RepairCycleTestExecutionCompletedEvent":
        """Deserialize from dictionary with backward compatibility.

        Raises:
            KeyError: If required fields (test_type_index, test_cycle_iteration,
                     failed, workflow_run_id) are missing.
        """
        test_type = (
            RepairTestType(data.get("test_type")) if isinstance(data.get("test_type"), str) else RepairTestType.UNIT
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
                "Field 'pipeline_run_id' is deprecated and will be removed in v3.0. Use 'workflow_run_id' instead.",
                DeprecationWarning,
                stacklevel=2,
            )
        workflow_run_id = str(data.get("workflow_run_id") or data.get("pipeline_run_id") or "")
        return cls(
            type=data.get("type", "repair_cycle.test_execution_completed"),
            timestamp=data.get("timestamp", ""),
            source=data.get("source", ""),
            correlation_id=data.get("correlation_id"),
            event_id=data.get("event_id") or str(uuid4()),
            test_type=test_type,
            test_type_index=data["test_type_index"],
            test_cycle_iteration=data["test_cycle_iteration"],
            passed=data.get("passed", 0),
            failed=data["failed"],
            warnings=data.get("warnings", 0),
            has_failures=data.get("has_failures", False),
            failures=failures,
            agent_name=data.get("agent_name", ""),
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
            msg = "test_type_index must be >= 1"
            raise ValueError(msg)
        if self.test_cycle_iteration < 1:
            msg = "test_cycle_iteration must be >= 1"
            raise ValueError(msg)
        if self.file_count < 1:
            msg = "file_count must be >= 1"
            raise ValueError(msg)
        if self.total_failures < 1:
            msg = "total_failures must be >= 1"
            raise ValueError(msg)
        if not self.workflow_run_id:
            msg = "workflow_run_id is required"
            raise ValueError(msg)

    def to_dict(self) -> dict:
        """Serialize to dictionary."""
        d = super().to_dict()
        d.update(
            {
                "test_type": self.test_type.value,
                "test_type_index": self.test_type_index,
                "test_cycle_iteration": self.test_cycle_iteration,
                "file_count": self.file_count,
                "total_failures": self.total_failures,
                "workflow_run_id": self.workflow_run_id,
            }
        )
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "RepairCycleFixCycleStartedEvent":
        """Deserialize from dictionary with backward compatibility.

        Raises:
            KeyError: If required fields (test_type_index, test_cycle_iteration,
                     file_count, total_failures, workflow_run_id) are missing.
        """
        test_type = (
            RepairTestType(data.get("test_type")) if isinstance(data.get("test_type"), str) else RepairTestType.UNIT
        )
        # Backward compatibility: Support both old and new field names
        if "pipeline_run_id" in data and "workflow_run_id" not in data:
            warnings.warn(
                "Field 'pipeline_run_id' is deprecated and will be removed in v3.0. Use 'workflow_run_id' instead.",
                DeprecationWarning,
                stacklevel=2,
            )
        workflow_run_id = str(data.get("workflow_run_id") or data.get("pipeline_run_id") or "")
        return cls(
            type=data.get("type", "repair_cycle.fix_cycle_started"),
            timestamp=data.get("timestamp", ""),
            source=data.get("source", ""),
            correlation_id=data.get("correlation_id"),
            event_id=data.get("event_id") or str(uuid4()),
            test_type=test_type,
            test_type_index=data["test_type_index"],
            test_cycle_iteration=data["test_cycle_iteration"],
            file_count=data["file_count"],
            total_failures=data["total_failures"],
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
        agent_name (str): Name of agent that will fix the file
        workflow_run_id (str): ID of the workflow run
        timestamp (str): ISO 8601 timestamp when file fix started
    """

    test_file: str = ""
    failure_count: int = 0
    test_type: RepairTestType = RepairTestType.UNIT
    agent_name: str = ""
    workflow_run_id: str = ""

    def __post_init__(self) -> None:
        """Validate event after initialization."""
        super().__post_init__()
        if not self.test_file:
            msg = "test_file is required"
            raise ValueError(msg)
        if self.failure_count < 1:
            msg = "failure_count must be >= 1"
            raise ValueError(msg)
        if not self.agent_name:
            msg = "agent_name is required"
            raise ValueError(msg)
        if not self.workflow_run_id:
            msg = "workflow_run_id is required"
            raise ValueError(msg)

    def to_dict(self) -> dict:
        """Serialize to dictionary."""
        d = super().to_dict()
        d.update(
            {
                "test_file": self.test_file,
                "failure_count": self.failure_count,
                "test_type": self.test_type.value,
                "agent_name": self.agent_name,
                "workflow_run_id": self.workflow_run_id,
            }
        )
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "RepairCycleFileFixStartedEvent":
        """Deserialize from dictionary with backward compatibility.

        Raises:
            KeyError: If required fields (test_file, failure_count,
                     workflow_run_id) are missing.
        """
        test_type = (
            RepairTestType(data.get("test_type")) if isinstance(data.get("test_type"), str) else RepairTestType.UNIT
        )
        # Backward compatibility: Support both old and new field names
        if "pipeline_run_id" in data and "workflow_run_id" not in data:
            warnings.warn(
                "Field 'pipeline_run_id' is deprecated and will be removed in v3.0. Use 'workflow_run_id' instead.",
                DeprecationWarning,
                stacklevel=2,
            )
        workflow_run_id = str(data.get("workflow_run_id") or data.get("pipeline_run_id") or "")
        return cls(
            type=data.get("type", "repair_cycle.file_fix_started"),
            timestamp=data.get("timestamp", ""),
            source=data.get("source", ""),
            correlation_id=data.get("correlation_id"),
            event_id=data.get("event_id") or str(uuid4()),
            test_file=data["test_file"],
            failure_count=data["failure_count"],
            test_type=test_type,
            agent_name=data.get("agent_name", ""),
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
        agent_name (str): Name of agent that attempted to fix the file
        workflow_run_id (str): ID of the workflow run
        timestamp (str): ISO 8601 timestamp when file fix completed
    """

    test_file: str = ""
    failure_count: int = 0
    test_type: RepairTestType = RepairTestType.UNIT
    success: bool = False
    agent_name: str = ""
    workflow_run_id: str = ""

    def __post_init__(self) -> None:
        """Validate event after initialization."""
        super().__post_init__()
        if not self.test_file:
            msg = "test_file is required"
            raise ValueError(msg)
        if self.failure_count < 1:
            msg = "failure_count must be >= 1"
            raise ValueError(msg)
        if not self.agent_name:
            msg = "agent_name is required"
            raise ValueError(msg)
        if not self.workflow_run_id:
            msg = "workflow_run_id is required"
            raise ValueError(msg)

    def to_dict(self) -> dict:
        """Serialize to dictionary."""
        d = super().to_dict()
        d.update(
            {
                "test_file": self.test_file,
                "failure_count": self.failure_count,
                "test_type": self.test_type.value,
                "success": self.success,
                "agent_name": self.agent_name,
                "workflow_run_id": self.workflow_run_id,
            }
        )
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "RepairCycleFileFixCompletedEvent":
        """Deserialize from dictionary with backward compatibility.

        Raises:
            KeyError: If required fields (test_file, failure_count,
                     workflow_run_id) are missing.
        """
        test_type = (
            RepairTestType(data.get("test_type")) if isinstance(data.get("test_type"), str) else RepairTestType.UNIT
        )
        # Backward compatibility: Support both old and new field names
        if "pipeline_run_id" in data and "workflow_run_id" not in data:
            warnings.warn(
                "Field 'pipeline_run_id' is deprecated and will be removed in v3.0. Use 'workflow_run_id' instead.",
                DeprecationWarning,
                stacklevel=2,
            )
        workflow_run_id = str(data.get("workflow_run_id") or data.get("pipeline_run_id") or "")
        return cls(
            type=data.get("type", "repair_cycle.file_fix_completed"),
            timestamp=data.get("timestamp", ""),
            source=data.get("source", ""),
            correlation_id=data.get("correlation_id"),
            event_id=data.get("event_id") or str(uuid4()),
            test_file=data["test_file"],
            failure_count=data["failure_count"],
            test_type=test_type,
            success=data.get("success", False),
            agent_name=data.get("agent_name", ""),
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
        agent_name (str): Name of agent that will review warnings
        workflow_run_id (str): ID of the workflow run
        timestamp (str): ISO 8601 timestamp when warning review started
    """

    source_file: str = ""
    warning_count: int = 0
    test_type: RepairTestType = RepairTestType.UNIT
    warnings: tuple[RepairTestWarning, ...] = ()
    agent_name: str = ""
    workflow_run_id: str = ""

    def __post_init__(self) -> None:
        """Validate event after initialization."""
        super().__post_init__()
        if not self.source_file:
            msg = "source_file is required"
            raise ValueError(msg)
        if self.warning_count < 1:
            msg = "warning_count must be >= 1"
            raise ValueError(msg)
        if not self.agent_name:
            msg = "agent_name is required"
            raise ValueError(msg)
        if not self.workflow_run_id:
            msg = "workflow_run_id is required"
            raise ValueError(msg)

    def to_dict(self) -> dict:
        """Serialize to dictionary."""
        d = super().to_dict()
        d.update(
            {
                "source_file": self.source_file,
                "warning_count": self.warning_count,
                "test_type": self.test_type.value,
                "warnings": [{"file": w.file, "message": w.message} for w in self.warnings],
                "agent_name": self.agent_name,
                "workflow_run_id": self.workflow_run_id,
            }
        )
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "RepairCycleWarningReviewStartedEvent":
        """Deserialize from dictionary with backward compatibility.

        Raises:
            KeyError: If required fields (source_file, warning_count,
                     workflow_run_id) are missing.
        """
        test_type = (
            RepairTestType(data.get("test_type")) if isinstance(data.get("test_type"), str) else RepairTestType.UNIT
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
                "Field 'pipeline_run_id' is deprecated and will be removed in v3.0. Use 'workflow_run_id' instead.",
                DeprecationWarning,
                stacklevel=2,
            )
        workflow_run_id = str(data.get("workflow_run_id") or data.get("pipeline_run_id") or "")
        return cls(
            type=data.get("type", "repair_cycle.warning_review_started"),
            timestamp=data.get("timestamp", ""),
            source=data.get("source", ""),
            correlation_id=data.get("correlation_id"),
            event_id=data.get("event_id") or str(uuid4()),
            source_file=data["source_file"],
            warning_count=data["warning_count"],
            test_type=test_type,
            warnings=warnings_list,
            agent_name=data.get("agent_name", ""),
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
        agent_name (str): Name of agent that reviewed warnings
        workflow_run_id (str): ID of the workflow run
        timestamp (str): ISO 8601 timestamp when warning review completed
    """

    source_file: str = ""
    warning_count: int = 0
    test_type: RepairTestType = RepairTestType.UNIT
    success: bool = False
    agent_name: str = ""
    workflow_run_id: str = ""

    def __post_init__(self) -> None:
        """Validate event after initialization."""
        super().__post_init__()
        if not self.source_file:
            msg = "source_file is required"
            raise ValueError(msg)
        if self.warning_count < 1:
            msg = "warning_count must be >= 1"
            raise ValueError(msg)
        if not self.agent_name:
            msg = "agent_name is required"
            raise ValueError(msg)
        if not self.workflow_run_id:
            msg = "workflow_run_id is required"
            raise ValueError(msg)

    def to_dict(self) -> dict:
        """Serialize to dictionary."""
        d = super().to_dict()
        d.update(
            {
                "source_file": self.source_file,
                "warning_count": self.warning_count,
                "test_type": self.test_type.value,
                "success": self.success,
                "agent_name": self.agent_name,
                "workflow_run_id": self.workflow_run_id,
            }
        )
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "RepairCycleWarningReviewCompletedEvent":
        """Deserialize from dictionary with backward compatibility.

        Raises:
            KeyError: If required fields (source_file, warning_count,
                     workflow_run_id) are missing.
        """
        test_type = (
            RepairTestType(data.get("test_type")) if isinstance(data.get("test_type"), str) else RepairTestType.UNIT
        )
        # Backward compatibility: Support both old and new field names
        if "pipeline_run_id" in data and "workflow_run_id" not in data:
            warnings.warn(
                "Field 'pipeline_run_id' is deprecated and will be removed in v3.0. Use 'workflow_run_id' instead.",
                DeprecationWarning,
                stacklevel=2,
            )
        workflow_run_id = str(data.get("workflow_run_id") or data.get("pipeline_run_id") or "")
        return cls(
            type=data.get("type", "repair_cycle.warning_review_completed"),
            timestamp=data.get("timestamp", ""),
            source=data.get("source", ""),
            correlation_id=data.get("correlation_id"),
            event_id=data.get("event_id") or str(uuid4()),
            source_file=data["source_file"],
            warning_count=data["warning_count"],
            test_type=test_type,
            success=data.get("success", False),
            agent_name=data.get("agent_name", ""),
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
            msg = "test_type_index must be >= 1"
            raise ValueError(msg)
        if self.test_cycle_iterations < 1:
            msg = "test_cycle_iterations must be >= 1"
            raise ValueError(msg)
        if self.files_fixed < 0:
            msg = "files_fixed must be >= 0"
            raise ValueError(msg)
        if self.warnings_reviewed < 0:
            msg = "warnings_reviewed must be >= 0"
            raise ValueError(msg)
        if self.duration_seconds < 0:
            msg = "duration_seconds must be >= 0"
            raise ValueError(msg)
        if not self.workflow_run_id:
            msg = "workflow_run_id is required"
            raise ValueError(msg)

    def to_dict(self) -> dict:
        """Serialize to dictionary."""
        d = super().to_dict()
        d.update(
            {
                "test_type": self.test_type.value,
                "test_type_index": self.test_type_index,
                "passed": self.passed,
                "test_cycle_iterations": self.test_cycle_iterations,
                "files_fixed": self.files_fixed,
                "warnings_reviewed": self.warnings_reviewed,
                "error": self.error,
                "duration_seconds": self.duration_seconds,
                "workflow_run_id": self.workflow_run_id,
            }
        )
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "RepairCycleTestCycleCompletedEvent":
        """Deserialize from dictionary with backward compatibility.

        Raises:
            KeyError: If required fields (test_type_index, test_cycle_iterations,
                     workflow_run_id) are missing.
        """
        test_type = (
            RepairTestType(data.get("test_type")) if isinstance(data.get("test_type"), str) else RepairTestType.UNIT
        )
        # Backward compatibility: Support both old and new field names
        if "pipeline_run_id" in data and "workflow_run_id" not in data:
            warnings.warn(
                "Field 'pipeline_run_id' is deprecated and will be removed in v3.0. Use 'workflow_run_id' instead.",
                DeprecationWarning,
                stacklevel=2,
            )
        workflow_run_id = str(data.get("workflow_run_id") or data.get("pipeline_run_id") or "")
        return cls(
            type=data.get("type", "repair_cycle.test_cycle_completed"),
            timestamp=data.get("timestamp", ""),
            source=data.get("source", ""),
            correlation_id=data.get("correlation_id"),
            event_id=data.get("event_id") or str(uuid4()),
            test_type=test_type,
            test_type_index=data["test_type_index"],
            passed=data.get("passed", False),
            test_cycle_iterations=data["test_cycle_iterations"],
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
            msg = "reason is required"
            raise ValueError(msg)
        if not self.workflow_run_id:
            msg = "workflow_run_id is required"
            raise ValueError(msg)

    def to_dict(self) -> dict:
        """Serialize to dictionary."""
        d = super().to_dict()
        d.update(
            {
                "test_type": self.test_type.value,
                "reason": self.reason,
                "workflow_run_id": self.workflow_run_id,
            }
        )
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "RepairCycleFastFailEvent":
        """Deserialize from dictionary with backward compatibility."""
        test_type = (
            RepairTestType(data.get("test_type")) if isinstance(data.get("test_type"), str) else RepairTestType.UNIT
        )
        # Backward compatibility: Support both old and new field names
        if "pipeline_run_id" in data and "workflow_run_id" not in data:
            warnings.warn(
                "Field 'pipeline_run_id' is deprecated and will be removed in v3.0. Use 'workflow_run_id' instead.",
                DeprecationWarning,
                stacklevel=2,
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
            msg = "workflow_run_id is required"
            raise ValueError(msg)
        if not self.test_type:
            msg = "test_type is required"
            raise ValueError(msg)
        if self.iteration < 1:
            msg = "iteration must be >= 1"
            raise ValueError(msg)
        if self.elapsed_time < 0:
            msg = "elapsed_time must be >= 0"
            raise ValueError(msg)
        if self.agent_calls_so_far < 0:
            msg = "agent_calls_so_far must be >= 0"
            raise ValueError(msg)

    def to_dict(self) -> dict:
        """Serialize to dictionary."""
        d = super().to_dict()
        d.update(
            {
                "workflow_run_id": self.workflow_run_id,
                "test_type": self.test_type.value,  # Serialize enum as string
                "iteration": self.iteration,
                "elapsed_time": self.elapsed_time,
                "agent_calls_so_far": self.agent_calls_so_far,
            }
        )
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "RepairCycleResumedEvent":
        """Deserialize from dictionary with backward compatibility.

        Raises:
            KeyError: If required fields (workflow_run_id, iteration) are missing.
        """
        # Backward compatibility: Support both old and new field names
        if "pipeline_run_id" in data and "workflow_run_id" not in data:
            warnings.warn(
                "Field 'pipeline_run_id' is deprecated and will be removed in v3.0. Use 'workflow_run_id' instead.",
                DeprecationWarning,
                stacklevel=2,
            )
        workflow_run_id = str(data.get("workflow_run_id") or data.get("pipeline_run_id") or "")

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
            iteration=data["iteration"],
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
        test_type (RepairTestType): Type of test being executed (UNIT, INTEGRATION, E2E)
        iteration (int): Current iteration number (1-based)
        error_type (str): Type of error (e.g., "ConnectionError")
        error_message (str): Error message details
        checkpoint_store_type (str): Type of checkpoint store (e.g., "RedisCheckpointStore")
        timestamp (str): ISO 8601 timestamp when checkpoint failed
    """

    workflow_run_id: str = ""
    test_type: RepairTestType = RepairTestType.UNIT
    iteration: int = 0
    error_type: str = ""
    error_message: str = ""
    checkpoint_store_type: str = ""

    def __post_init__(self) -> None:
        """Validate event after initialization."""
        super().__post_init__()
        if not self.workflow_run_id:
            msg = "workflow_run_id is required"
            raise ValueError(msg)
        if not self.test_type:
            msg = "test_type is required"
            raise ValueError(msg)
        if self.iteration < 1:
            msg = "iteration must be >= 1"
            raise ValueError(msg)
        if not self.error_type:
            msg = "error_type is required"
            raise ValueError(msg)
        if not self.error_message:
            msg = "error_message is required"
            raise ValueError(msg)

    def to_dict(self) -> dict:
        """Serialize to dictionary."""
        d = super().to_dict()
        d.update(
            {
                "workflow_run_id": self.workflow_run_id,
                "test_type": self.test_type.value,
                "iteration": self.iteration,
                "error_type": self.error_type,
                "error_message": self.error_message,
                "checkpoint_store_type": self.checkpoint_store_type,
            }
        )
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "RepairCycleCheckpointFailedEvent":
        """Deserialize from dictionary with backward compatibility."""
        # Backward compatibility: Support both old and new field names
        if "pipeline_run_id" in data and "workflow_run_id" not in data:
            warnings.warn(
                "Field 'pipeline_run_id' is deprecated and will be removed in v3.0. Use 'workflow_run_id' instead.",
                DeprecationWarning,
                stacklevel=2,
            )
        workflow_run_id = data.get("workflow_run_id") or data.get("pipeline_run_id", "")

        # Handle test_type with explicit logging for missing values
        if isinstance(data.get("test_type"), str):
            test_type = RepairTestType(data.get("test_type"))
        else:
            if "test_type" not in data:
                logger.warning(
                    "Missing 'test_type' in RepairCycleCheckpointFailedEvent deserialization, defaulting to UNIT. "
                    "This may indicate data corruption or incomplete event data."
                )
            test_type = RepairTestType.UNIT
        return cls(
            type=data.get("type", "repair_cycle.checkpoint_failed"),
            timestamp=data.get("timestamp", ""),
            source=data.get("source", ""),
            correlation_id=data.get("correlation_id"),
            event_id=data.get("event_id") or str(uuid4()),
            workflow_run_id=workflow_run_id,
            test_type=test_type,
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
            msg = "operation is required"
            raise ValueError(msg)
        if not self.error_type:
            msg = "error_type is required"
            raise ValueError(msg)
        if not self.error_message:
            msg = "error_message is required"
            raise ValueError(msg)
        if self.consecutive_failures < 0:
            msg = "consecutive_failures must be >= 0"
            raise ValueError(msg)

    def to_dict(self) -> dict:
        """Serialize to dictionary."""
        d = super().to_dict()
        d.update(
            {
                "operation": self.operation,
                "error_type": self.error_type,
                "error_message": self.error_message,
                "consecutive_failures": self.consecutive_failures,
                "circuit_breaker_open": self.circuit_breaker_open,
                "workflow_run_id": self.workflow_run_id,
            }
        )
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "RepairCycleMetricsBackendFailedEvent":
        """Deserialize from dictionary with backward compatibility."""
        # Backward compatibility: Support both old and new field names
        if "pipeline_run_id" in data and "workflow_run_id" not in data:
            warnings.warn(
                "Field 'pipeline_run_id' is deprecated and will be removed in v3.0. Use 'workflow_run_id' instead.",
                DeprecationWarning,
                stacklevel=2,
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
        commit_history (Tuple[str, ...]): Ordered git commit SHAs produced during
            the cycle, one per sub-task execution that made file changes.
    """

    overall_success: bool = False
    test_results: tuple[CycleResult, ...] = ()
    total_agent_calls: int = 0
    duration_seconds: float = 0.0
    workflow_run_id: str = ""
    commit_history: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        """Validate event after initialization."""
        super().__post_init__()
        if not self.test_results:
            msg = "test_results must not be empty"
            raise ValueError(msg)
        if self.total_agent_calls < 0:
            msg = "total_agent_calls must be >= 0"
            raise ValueError(msg)
        if self.duration_seconds < 0:
            msg = "duration_seconds must be >= 0"
            raise ValueError(msg)
        if not self.workflow_run_id:
            msg = "workflow_run_id is required"
            raise ValueError(msg)

    def to_dict(self) -> dict:
        """Serialize to dictionary."""
        d = super().to_dict()
        d.update(
            {
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
                "commit_history": list(self.commit_history),
            }
        )
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "RepairCycleCompletedEvent":
        """Deserialize from dictionary with backward compatibility."""
        from ..repair_cycle_types import RepairTestResult

        test_results = []
        for tr in data.get("test_results", []):
            test_type = (
                RepairTestType(tr.get("test_type")) if isinstance(tr.get("test_type"), str) else RepairTestType.UNIT
            )
            final_result = None
            if tr.get("final_result"):
                fr = tr.get("final_result")
                final_test_type = (
                    RepairTestType(fr.get("test_type")) if isinstance(fr.get("test_type"), str) else RepairTestType.UNIT
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
                "Field 'pipeline_run_id' is deprecated and will be removed in v3.0. Use 'workflow_run_id' instead.",
                DeprecationWarning,
                stacklevel=2,
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
            commit_history=tuple(data.get("commit_history", [])),
        )


@dataclass(frozen=True)
class SystemicAnalysisStartedEvent(CodetoreumEvent):
    """Emitted when systemic analysis of failures begins.

    **Immutability**: This is an immutable event (frozen dataclass). All fields
    are read-only after construction to maintain event sourcing audit trail
    integrity. Attempting to modify any field will raise `FrozenInstanceError`.

    Attributes:
        type (str): Fixed to "repair_cycle.systemic_analysis_started"
        work_item_id (str): ID of the work item being analyzed
        workflow_run_id (str): ID of the workflow run
        failure_count (int): Number of failures that triggered analysis
        timestamp (str): ISO 8601 timestamp when analysis started
    """

    work_item_id: str = ""
    workflow_run_id: str = ""
    failure_count: int = 0

    def __post_init__(self) -> None:
        """Validate event after initialization."""
        super().__post_init__()
        if not self.work_item_id:
            msg = "work_item_id is required"
            raise ValueError(msg)
        if not self.workflow_run_id:
            msg = "workflow_run_id is required"
            raise ValueError(msg)

    def to_dict(self) -> dict:
        """Serialize to dictionary."""
        d = super().to_dict()
        d.update(
            {
                "work_item_id": self.work_item_id,
                "workflow_run_id": self.workflow_run_id,
                "failure_count": self.failure_count,
            }
        )
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "SystemicAnalysisStartedEvent":
        """Deserialize from dictionary with backward compatibility.

        Raises:
            ValueError: If required fields (work_item_id, workflow_run_id) are missing.
        """
        return cls(
            type=data.get("type", "repair_cycle.systemic_analysis_started"),
            timestamp=data.get("timestamp", ""),
            source=data.get("source", ""),
            correlation_id=data.get("correlation_id"),
            event_id=data.get("event_id") or str(uuid4()),
            work_item_id=data.get("work_item_id", ""),
            workflow_run_id=data.get("workflow_run_id", ""),
            failure_count=data.get("failure_count", 0),
        )


@dataclass(frozen=True)
class SystemicAnalysisCompletedEvent(CodetoreumEvent):
    """Emitted when systemic analysis of failures completes with classification.

    **Immutability**: This is an immutable event (frozen dataclass). All fields
    are read-only after construction to maintain event sourcing audit trail
    integrity. Attempting to modify any field will raise `FrozenInstanceError`.

    Attributes:
        type (str): Fixed to "repair_cycle.systemic_analysis_completed"
        classification (str): Classification of root cause (FailureClassification enum value)
        confidence (float): Confidence level of classification (0.0 to 1.0)
        reasoning (str): Explanation of the classification reasoning
        recommended_action (str): Recommended action to resolve the issue
        work_item_id (str): ID of the work item that was analyzed
        workflow_run_id (str): ID of the workflow run
        failure_count (int): Number of failures that were analyzed
        timestamp (str): ISO 8601 timestamp when analysis completed
    """

    classification: str = FailureClassification.CODE_DEFECT.value
    confidence: float = 0.0
    reasoning: str = ""
    recommended_action: str = ""
    work_item_id: str = ""
    workflow_run_id: str = ""
    failure_count: int = 0

    def __post_init__(self) -> None:
        """Validate event after initialization."""
        super().__post_init__()
        if type(self.classification) is not str:
            msg = "classification must be a string"
            raise ValueError(msg)
        # Validate that classification is a valid FailureClassification value
        valid_values = {fc.value for fc in FailureClassification}
        if self.classification not in valid_values:
            msg = f"classification '{self.classification}' is not a valid FailureClassification"
            raise ValueError(msg)
        if not 0.0 <= self.confidence <= 1.0:
            msg = "confidence must be between 0.0 and 1.0"
            raise ValueError(msg)
        if not self.work_item_id:
            msg = "work_item_id is required"
            raise ValueError(msg)
        if not self.workflow_run_id:
            msg = "workflow_run_id is required"
            raise ValueError(msg)

    def to_dict(self) -> dict:
        """Serialize to dictionary."""
        d = super().to_dict()
        d.update(
            {
                "classification": self.classification,
                "confidence": self.confidence,
                "reasoning": self.reasoning,
                "recommended_action": self.recommended_action,
                "work_item_id": self.work_item_id,
                "workflow_run_id": self.workflow_run_id,
                "failure_count": self.failure_count,
            }
        )
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "SystemicAnalysisCompletedEvent":
        """Deserialize from dictionary with backward compatibility.

        Raises:
            ValueError: If required fields (work_item_id, workflow_run_id) are missing.
        """
        classification_value = data.get("classification")
        if isinstance(classification_value, str):
            # Validate that the string is a valid FailureClassification value
            try:
                # Attempt to construct the enum to validate the value exists
                FailureClassification(classification_value)
                classification = classification_value
            except ValueError:
                # Invalid or unknown classification string (e.g., corrupted event store,
                # future enum value) - safely default to CODE_DEFECT
                logger.warning(
                    "Invalid classification value during deserialization: %s. " "Defaulting to CODE_DEFECT.",
                    classification_value,
                )
                classification = FailureClassification.CODE_DEFECT.value
        elif isinstance(classification_value, FailureClassification):
            # Handle migration from old enum format
            classification = classification_value.value
        else:
            classification = FailureClassification.CODE_DEFECT.value

        return cls(
            type=data.get("type", "repair_cycle.systemic_analysis_completed"),
            timestamp=data.get("timestamp", ""),
            source=data.get("source", ""),
            correlation_id=data.get("correlation_id"),
            event_id=data.get("event_id") or str(uuid4()),
            classification=classification,
            confidence=data.get("confidence", 0.0),
            reasoning=data.get("reasoning", ""),
            recommended_action=data.get("recommended_action", ""),
            work_item_id=data.get("work_item_id", ""),
            workflow_run_id=data.get("workflow_run_id", ""),
            failure_count=data.get("failure_count", 0),
        )


@dataclass(frozen=True)
class SystemicFixStartedEvent(CodetoreumEvent):
    """Emitted when a systemic fix operation begins.

    Signals the start of a holistic fix attempt that addresses a cross-cutting
    root cause affecting multiple files identified by systemic analysis.

    **Immutability**: This is an immutable event (frozen dataclass). All fields
    are read-only after construction to maintain event sourcing audit trail
    integrity. Attempting to modify any field will raise `FrozenInstanceError`.

    Attributes:
        type (str): Fixed to "repair_cycle.systemic_fix_started"
        work_item_id (str): ID of the work item being fixed
        workflow_run_id (str): ID of the workflow run
        root_cause_classification (str): Classification of the root cause (FailureClassification enum value)
        confidence (float): Confidence in the classification (0.0 to 1.0)
        affected_file_count (int): Number of files affected by the issue
        failure_count (int): Number of failures being addressed
        timestamp (str): ISO 8601 timestamp when systemic fix started
    """

    work_item_id: str = ""
    workflow_run_id: str = ""
    root_cause_classification: str = FailureClassification.CODE_DEFECT.value
    confidence: float = 0.0
    affected_file_count: int = 0
    failure_count: int = 0

    def __post_init__(self) -> None:
        """Validate event after initialization."""
        super().__post_init__()
        if not self.work_item_id:
            msg = "work_item_id is required"
            raise ValueError(msg)
        if not self.workflow_run_id:
            msg = "workflow_run_id is required"
            raise ValueError(msg)
        # Validate that root_cause_classification is a string
        if not isinstance(self.root_cause_classification, str):
            msg = "root_cause_classification must be a string"
            raise ValueError(msg)
        # Validate classification value
        valid_values = {fc.value for fc in FailureClassification}
        if self.root_cause_classification not in valid_values:
            msg = f"root_cause_classification '{self.root_cause_classification}' is not a valid FailureClassification"
            raise ValueError(msg)
        if not 0.0 <= self.confidence <= 1.0:
            msg = "confidence must be between 0.0 and 1.0"
            raise ValueError(msg)

    def to_dict(self) -> dict:
        """Serialize to dictionary."""
        d = super().to_dict()
        d.update(
            {
                "work_item_id": self.work_item_id,
                "workflow_run_id": self.workflow_run_id,
                "root_cause_classification": self.root_cause_classification,
                "confidence": self.confidence,
                "affected_file_count": self.affected_file_count,
                "failure_count": self.failure_count,
            }
        )
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "SystemicFixStartedEvent":
        """Deserialize from dictionary with backward compatibility.

        Raises:
            ValueError: If required fields are missing.
        """
        classification_value = data.get("root_cause_classification")
        if isinstance(classification_value, str):
            # Validate that the string is a valid FailureClassification value
            try:
                # Attempt to construct the enum to validate the value exists
                FailureClassification(classification_value)
                root_cause_classification = classification_value
            except ValueError:
                # Invalid or unknown classification string - safely default to CODE_DEFECT
                logger.warning(
                    "Invalid classification value during deserialization: %s. Defaulting to CODE_DEFECT.",
                    classification_value,
                )
                root_cause_classification = FailureClassification.CODE_DEFECT.value
        elif isinstance(classification_value, FailureClassification):
            # Handle migration from old enum format
            root_cause_classification = classification_value.value
        else:
            root_cause_classification = FailureClassification.CODE_DEFECT.value

        return cls(
            type=data.get("type", "repair_cycle.systemic_fix_started"),
            timestamp=data.get("timestamp", ""),
            source=data.get("source", ""),
            correlation_id=data.get("correlation_id"),
            event_id=data.get("event_id") or str(uuid4()),
            work_item_id=data.get("work_item_id", ""),
            workflow_run_id=data.get("workflow_run_id", ""),
            root_cause_classification=root_cause_classification,
            confidence=data.get("confidence", 0.0),
            affected_file_count=data.get("affected_file_count", 0),
            failure_count=data.get("failure_count", 0),
        )


@dataclass(frozen=True)
class SystemicFixCompletedEvent(CodetoreumEvent):
    """Emitted when a systemic fix operation completes.

    Signals completion of a holistic fix attempt that addressed a cross-cutting
    root cause. Records which files were modified and whether the fix succeeded.

    **Immutability**: This is an immutable event (frozen dataclass). All fields
    are read-only after construction to maintain event sourcing audit trail
    integrity. Attempting to modify any field will raise `FrozenInstanceError`.

    Attributes:
        type (str): Fixed to "repair_cycle.systemic_fix_completed"
        work_item_id (str): ID of the work item that was fixed
        workflow_run_id (str): ID of the workflow run
        success (bool): Whether the systemic fix successfully addressed the root cause
        files_modified (tuple[str, ...]): Files modified by the systemic fix
        root_cause_addressed (str): Description of what root cause was addressed
        duration_seconds (float): Time taken to apply the systemic fix
        timestamp (str): ISO 8601 timestamp when systemic fix completed
    """

    work_item_id: str = ""
    workflow_run_id: str = ""
    success: bool = False
    files_modified: tuple[str, ...] = ()
    root_cause_addressed: str = ""
    duration_seconds: float = 0.0

    def __post_init__(self) -> None:
        """Validate event after initialization."""
        super().__post_init__()
        if not self.work_item_id:
            msg = "work_item_id is required"
            raise ValueError(msg)
        if not self.workflow_run_id:
            msg = "workflow_run_id is required"
            raise ValueError(msg)
        # Coerce list to tuple for files_modified
        if not isinstance(self.files_modified, tuple):
            object.__setattr__(self, "files_modified", tuple(self.files_modified))

    def to_dict(self) -> dict:
        """Serialize to dictionary."""
        d = super().to_dict()
        d.update(
            {
                "work_item_id": self.work_item_id,
                "workflow_run_id": self.workflow_run_id,
                "success": self.success,
                "files_modified": list(self.files_modified),  # Serialize as list for JSON compatibility
                "root_cause_addressed": self.root_cause_addressed,
                "duration_seconds": self.duration_seconds,
            }
        )
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "SystemicFixCompletedEvent":
        """Deserialize from dictionary with backward compatibility.

        Raises:
            ValueError: If required fields are missing.
        """
        files_modified = data.get("files_modified", [])
        if not isinstance(files_modified, (list, tuple)):
            files_modified = []
        return cls(
            type=data.get("type", "repair_cycle.systemic_fix_completed"),
            timestamp=data.get("timestamp", ""),
            source=data.get("source", ""),
            correlation_id=data.get("correlation_id"),
            event_id=data.get("event_id") or str(uuid4()),
            work_item_id=data.get("work_item_id", ""),
            workflow_run_id=data.get("workflow_run_id", ""),
            success=data.get("success", False),
            files_modified=tuple(files_modified),
            root_cause_addressed=data.get("root_cause_addressed", ""),
            duration_seconds=data.get("duration_seconds", 0.0),
        )


@dataclass(frozen=True)
class EnvironmentRebuildStartedEvent(CodetoreumEvent):
    """Emitted when environment rebuild begins.

    **Immutability**: This is an immutable event (frozen dataclass). All fields
    are read-only after construction to maintain event sourcing audit trail
    integrity. Attempting to modify any field will raise `FrozenInstanceError`.

    Attributes:
        type (str): Fixed to "repair_cycle.environment_rebuild_started"
        work_item_id (str): ID of the work item being repaired
        workflow_run_id (str): ID of the workflow run
        test_type (RepairTestType): Type of test being executed (UNIT, INTEGRATION, E2E)
        iteration (int): Current iteration number within the test cycle
        timestamp (str): ISO 8601 timestamp when rebuild started
    """

    work_item_id: str = ""
    workflow_run_id: str = ""
    test_type: RepairTestType = RepairTestType.UNIT
    iteration: int = 0

    def __post_init__(self) -> None:
        """Validate event after initialization."""
        super().__post_init__()
        if not self.work_item_id:
            msg = "work_item_id is required"
            raise ValueError(msg)
        if not self.workflow_run_id:
            msg = "workflow_run_id is required"
            raise ValueError(msg)
        # Convert string to enum if needed (backward compatibility)
        if isinstance(self.test_type, str):
            if not self.test_type:
                msg = "test_type is required"
                raise ValueError(msg)
            object.__setattr__(self, "test_type", RepairTestType(self.test_type))
        if self.iteration < 1:
            msg = "iteration must be >= 1"
            raise ValueError(msg)

    def to_dict(self) -> dict:
        """Serialize to dictionary."""
        d = super().to_dict()
        d.update(
            {
                "work_item_id": self.work_item_id,
                "workflow_run_id": self.workflow_run_id,
                "test_type": self.test_type.value,
                "iteration": self.iteration,
            }
        )
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "EnvironmentRebuildStartedEvent":
        """Deserialize from dictionary with backward compatibility.

        Raises:
            KeyError: If required fields (work_item_id, workflow_run_id, test_type, iteration) are missing.
        """
        test_type = (
            RepairTestType(data.get("test_type")) if isinstance(data.get("test_type"), str) else RepairTestType.UNIT
        )
        return cls(
            type=data.get("type", "repair_cycle.environment_rebuild_started"),
            timestamp=data.get("timestamp", ""),
            source=data.get("source", ""),
            correlation_id=data.get("correlation_id"),
            event_id=data.get("event_id") or str(uuid4()),
            work_item_id=data["work_item_id"],
            workflow_run_id=data["workflow_run_id"],
            test_type=test_type,
            iteration=data["iteration"],
        )


@dataclass(frozen=True)
class EnvironmentRebuildCompletedEvent(CodetoreumEvent):
    """Emitted when environment rebuild completes.

    **Immutability**: This is an immutable event (frozen dataclass). All fields
    are read-only after construction to maintain event sourcing audit trail
    integrity. Attempting to modify any field will raise `FrozenInstanceError`.

    Attributes:
        type (str): Fixed to "repair_cycle.environment_rebuild_completed"
        work_item_id (str): ID of the work item being repaired
        workflow_run_id (str): ID of the workflow run
        test_type (RepairTestType): Type of test being executed (UNIT, INTEGRATION, E2E)
        iteration (int): Current iteration number within the test cycle
        success (bool): Whether the rebuild was successful
        duration_seconds (float): Time taken to rebuild the environment
        actions_taken (tuple[str, ...]): List of actions performed during rebuild
        error (str | None): Error message if rebuild failed, None if successful
        timestamp (str): ISO 8601 timestamp when rebuild completed
    """

    work_item_id: str = ""
    workflow_run_id: str = ""
    test_type: RepairTestType = RepairTestType.UNIT
    iteration: int = 0
    success: bool = False
    duration_seconds: float = 0.0
    actions_taken: tuple[str, ...] = ()
    error: str | None = None

    def __post_init__(self) -> None:
        """Validate event after initialization."""
        super().__post_init__()
        if not self.work_item_id:
            msg = "work_item_id is required"
            raise ValueError(msg)
        if not self.workflow_run_id:
            msg = "workflow_run_id is required"
            raise ValueError(msg)
        # Convert string to enum if needed (backward compatibility)
        if isinstance(self.test_type, str):
            if not self.test_type:
                msg = "test_type is required"
                raise ValueError(msg)
            object.__setattr__(self, "test_type", RepairTestType(self.test_type))
        if self.iteration < 1:
            msg = "iteration must be >= 1"
            raise ValueError(msg)
        if self.duration_seconds < 0:
            msg = "duration_seconds must be non-negative"
            raise ValueError(msg)
        if not isinstance(self.actions_taken, tuple):
            object.__setattr__(self, "actions_taken", tuple(self.actions_taken))

        # Consistency check: success state must align with error
        if self.success and self.error is not None:
            msg = f"success=True but error is set: '{self.error}' (contradiction)"
            raise ValueError(msg)

        # Consistency check: failure without explanation is a data quality gap
        if not self.success and self.error is None:
            msg = "success=False but error is not set (failure must have explanation for audit trail)"
            raise ValueError(msg)

    def to_dict(self) -> dict:
        """Serialize to dictionary."""
        d = super().to_dict()
        d.update(
            {
                "work_item_id": self.work_item_id,
                "workflow_run_id": self.workflow_run_id,
                "test_type": self.test_type.value,
                "iteration": self.iteration,
                "success": self.success,
                "duration_seconds": self.duration_seconds,
                "actions_taken": list(self.actions_taken),
                "error": self.error,
            }
        )
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "EnvironmentRebuildCompletedEvent":
        """Deserialize from dictionary with backward compatibility.

        Raises:
            KeyError: If required fields (work_item_id, workflow_run_id, test_type, iteration) are missing.
        """
        test_type = (
            RepairTestType(data.get("test_type")) if isinstance(data.get("test_type"), str) else RepairTestType.UNIT
        )
        actions_taken = data.get("actions_taken", [])
        if not isinstance(actions_taken, (list, tuple)):
            actions_taken = []
        return cls(
            type=data.get("type", "repair_cycle.environment_rebuild_completed"),
            timestamp=data.get("timestamp", ""),
            source=data.get("source", ""),
            correlation_id=data.get("correlation_id"),
            event_id=data.get("event_id") or str(uuid4()),
            work_item_id=data["work_item_id"],
            workflow_run_id=data["workflow_run_id"],
            test_type=test_type,
            iteration=data["iteration"],
            success=data.get("success", False),
            duration_seconds=data.get("duration_seconds", 0.0),
            actions_taken=tuple(actions_taken),
            error=data.get("error"),
        )


@dataclass(frozen=True)
class EnvironmentVerificationStartedEvent(CodetoreumEvent):
    """Emitted when environment verification begins.

    **Immutability**: This is an immutable event (frozen dataclass). All fields
    are read-only after construction to maintain event sourcing audit trail
    integrity. Attempting to modify any field will raise `FrozenInstanceError`.

    Attributes:
        type (str): Fixed to "repair_cycle.environment_verification_started"
        work_item_id (str): ID of the work item being repaired
        workflow_run_id (str): ID of the workflow run
        test_type (RepairTestType): Type of test being executed (UNIT, INTEGRATION, E2E)
        iteration (int): Current iteration number within the test cycle
        timestamp (str): ISO 8601 timestamp when verification started
    """

    work_item_id: str = ""
    workflow_run_id: str = ""
    test_type: RepairTestType = RepairTestType.UNIT
    iteration: int = 0

    def __post_init__(self) -> None:
        """Validate event after initialization."""
        super().__post_init__()
        if not self.work_item_id:
            msg = "work_item_id is required"
            raise ValueError(msg)
        if not self.workflow_run_id:
            msg = "workflow_run_id is required"
            raise ValueError(msg)
        # Convert string to enum if needed (backward compatibility)
        if isinstance(self.test_type, str):
            if not self.test_type:
                msg = "test_type is required"
                raise ValueError(msg)
            object.__setattr__(self, "test_type", RepairTestType(self.test_type))
        if self.iteration < 1:
            msg = "iteration must be >= 1"
            raise ValueError(msg)

    def to_dict(self) -> dict:
        """Serialize to dictionary."""
        d = super().to_dict()
        d.update(
            {
                "work_item_id": self.work_item_id,
                "workflow_run_id": self.workflow_run_id,
                "test_type": self.test_type.value,
                "iteration": self.iteration,
            }
        )
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "EnvironmentVerificationStartedEvent":
        """Deserialize from dictionary with backward compatibility.

        Raises:
            KeyError: If required fields (work_item_id, workflow_run_id, test_type, iteration) are missing.
        """
        test_type = (
            RepairTestType(data.get("test_type")) if isinstance(data.get("test_type"), str) else RepairTestType.UNIT
        )
        return cls(
            type=data.get("type", "repair_cycle.environment_verification_started"),
            timestamp=data.get("timestamp", ""),
            source=data.get("source", ""),
            correlation_id=data.get("correlation_id"),
            event_id=data.get("event_id") or str(uuid4()),
            work_item_id=data["work_item_id"],
            workflow_run_id=data["workflow_run_id"],
            test_type=test_type,
            iteration=data["iteration"],
        )


@dataclass(frozen=True)
class EnvironmentVerificationCompletedEvent(CodetoreumEvent):
    """Emitted when environment verification completes.

    **Immutability**: This is an immutable event (frozen dataclass). All fields
    are read-only after construction to maintain event sourcing audit trail
    integrity. Attempting to modify any field will raise `FrozenInstanceError`.

    Attributes:
        type (str): Fixed to "repair_cycle.environment_verification_completed"
        work_item_id (str): ID of the work item being repaired
        workflow_run_id (str): ID of the workflow run
        test_type (RepairTestType): Type of test being executed (UNIT, INTEGRATION, E2E)
        iteration (int): Current iteration number within the test cycle
        healthy (bool): Whether the environment passed all verification checks
        checks_passed (tuple[str, ...]): Verification checks that passed
        checks_failed (tuple[str, ...]): Verification checks that failed
        duration_seconds (float): Time taken to verify the environment
        timestamp (str): ISO 8601 timestamp when verification completed
    """

    work_item_id: str = ""
    workflow_run_id: str = ""
    test_type: RepairTestType = RepairTestType.UNIT
    iteration: int = 0
    healthy: bool = False
    checks_passed: tuple[str, ...] = ()
    checks_failed: tuple[str, ...] = ()
    duration_seconds: float = 0.0

    def __post_init__(self) -> None:
        """Validate event after initialization."""
        super().__post_init__()
        if not self.work_item_id:
            msg = "work_item_id is required"
            raise ValueError(msg)
        if not self.workflow_run_id:
            msg = "workflow_run_id is required"
            raise ValueError(msg)
        # Convert string to enum if needed (backward compatibility)
        if isinstance(self.test_type, str):
            if not self.test_type:
                msg = "test_type is required"
                raise ValueError(msg)
            object.__setattr__(self, "test_type", RepairTestType(self.test_type))
        if self.iteration < 1:
            msg = "iteration must be >= 1"
            raise ValueError(msg)
        if self.duration_seconds < 0:
            msg = "duration_seconds must be non-negative"
            raise ValueError(msg)
        if not isinstance(self.checks_passed, tuple):
            object.__setattr__(self, "checks_passed", tuple(self.checks_passed))
        if not isinstance(self.checks_failed, tuple):
            object.__setattr__(self, "checks_failed", tuple(self.checks_failed))

        # Consistency check: healthy state must align with checks_failed
        if self.healthy and self.checks_failed:
            msg = f"healthy=True but checks_failed is non-empty: {self.checks_failed} (contradiction)"
            raise ValueError(msg)

    def to_dict(self) -> dict:
        """Serialize to dictionary."""
        d = super().to_dict()
        d.update(
            {
                "work_item_id": self.work_item_id,
                "workflow_run_id": self.workflow_run_id,
                "test_type": self.test_type.value,
                "iteration": self.iteration,
                "healthy": self.healthy,
                "checks_passed": list(self.checks_passed),
                "checks_failed": list(self.checks_failed),
                "duration_seconds": self.duration_seconds,
            }
        )
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "EnvironmentVerificationCompletedEvent":
        """Deserialize from dictionary with backward compatibility.

        Raises:
            KeyError: If required fields (work_item_id, workflow_run_id, test_type, iteration) are missing.
        """
        test_type = (
            RepairTestType(data.get("test_type")) if isinstance(data.get("test_type"), str) else RepairTestType.UNIT
        )
        checks_passed = data.get("checks_passed", [])
        checks_failed = data.get("checks_failed", [])
        if not isinstance(checks_passed, (list, tuple)):
            checks_passed = []
        if not isinstance(checks_failed, (list, tuple)):
            checks_failed = []
        return cls(
            type=data.get("type", "repair_cycle.environment_verification_completed"),
            timestamp=data.get("timestamp", ""),
            source=data.get("source", ""),
            correlation_id=data.get("correlation_id"),
            event_id=data.get("event_id") or str(uuid4()),
            work_item_id=data["work_item_id"],
            workflow_run_id=data["workflow_run_id"],
            test_type=test_type,
            iteration=data["iteration"],
            healthy=data.get("healthy", False),
            checks_passed=tuple(checks_passed),
            checks_failed=tuple(checks_failed),
            duration_seconds=data.get("duration_seconds", 0.0),
        )


@dataclass(frozen=True)
class EnvironmentRebuildExhaustedEvent(CodetoreumEvent):
    """Emitted when environment rebuild attempts are exhausted.

    This terminal event indicates that the environment rebuild/verification
    process failed to achieve a healthy state after max_env_rebuilds attempts,
    making continued repair impossible without external intervention.

    This is a named failure outcome per specification, surfacing the
    ENV_REBUILD_EXHAUSTED terminal condition as both an event and a structured
    failure record.

    **Immutability**: This is an immutable event (frozen dataclass). All fields
    are read-only after construction to maintain event sourcing audit trail
    integrity. Attempting to modify any field will raise `FrozenInstanceError`.

    Attributes:
        type (str): Fixed to "repair_cycle.environment_rebuild_exhausted"
        work_item_id (str): ID of the work item being repaired
        workflow_run_id (str): ID of the workflow run
        test_type (RepairTestType): Type of test being executed (UNIT, INTEGRATION, E2E)
        iteration (int): Current iteration number within the test cycle
        max_attempts (int): Maximum rebuild attempts configured
        error_message (str): Description of why rebuild failed
        timestamp (str): ISO 8601 timestamp when exhaustion occurred
    """

    work_item_id: str = ""
    workflow_run_id: str = ""
    test_type: RepairTestType = RepairTestType.UNIT
    iteration: int = 0
    max_attempts: int = 0
    error_message: str = ""

    def __post_init__(self) -> None:
        """Validate event after initialization."""
        super().__post_init__()
        if not self.work_item_id:
            msg = "work_item_id is required"
            raise ValueError(msg)
        if not self.workflow_run_id:
            msg = "workflow_run_id is required"
            raise ValueError(msg)
        # Convert string to enum if needed (backward compatibility)
        if isinstance(self.test_type, str):
            if not self.test_type:
                msg = "test_type is required"
                raise ValueError(msg)
            object.__setattr__(self, "test_type", RepairTestType(self.test_type))
        if self.iteration < 1:
            msg = "iteration must be >= 1"
            raise ValueError(msg)
        if self.max_attempts <= 0:
            msg = "max_attempts must be > 0"
            raise ValueError(msg)
        if not self.error_message:
            msg = "error_message is required"
            raise ValueError(msg)

    def to_dict(self) -> dict:
        """Serialize to dictionary."""
        d = super().to_dict()
        d.update(
            {
                "work_item_id": self.work_item_id,
                "workflow_run_id": self.workflow_run_id,
                "test_type": self.test_type.value,
                "iteration": self.iteration,
                "max_attempts": self.max_attempts,
                "error_message": self.error_message,
            }
        )
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "EnvironmentRebuildExhaustedEvent":
        """Deserialize from dictionary with backward compatibility.

        Raises:
            KeyError: If required fields (work_item_id, workflow_run_id, test_type, iteration, max_attempts, error_message) are missing.
        """
        # Convert test_type to enum if needed
        test_type_value = data["test_type"]
        if isinstance(test_type_value, str):
            test_type = RepairTestType(test_type_value)
        else:
            test_type = test_type_value

        return cls(
            type=data.get("type", "repair_cycle.environment_rebuild_exhausted"),
            timestamp=data.get("timestamp", ""),
            source=data.get("source", ""),
            correlation_id=data.get("correlation_id"),
            event_id=data.get("event_id") or str(uuid4()),
            work_item_id=data["work_item_id"],
            workflow_run_id=data["workflow_run_id"],
            test_type=test_type,
            iteration=data["iteration"],
            max_attempts=data["max_attempts"],
            error_message=data["error_message"],
        )
