"""IAgentContainerRecoveryService output port interface.

This module defines the port interface for container recovery operations.
The recovery service runs at orchestrator startup to detect, assess, and manage
orphaned Docker containers from prior execution sessions.

Design Principles:
- Label-based identification only (no container name parsing)
- Docker label filtering for query-time protection of unrelated containers
- Immutable dataclasses for audit trail integrity
- Clear separation of assessment and action execution
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from types import MappingProxyType
from typing import List, Literal, Optional

from codetoreum.domain.types import (
    CONTAINER_LABEL_AGENT,
    CONTAINER_LABEL_PROJECT,
    CONTAINER_LABEL_TYPE,
)

# ============================================================================
# Data Models
# ============================================================================


@dataclass(frozen=True)
class ContainerMetadata:
    """Immutable container metadata extracted from Docker labels.

    This dataclass represents the complete metadata extracted from a running
    container's Docker labels. It is frozen (immutable) to maintain audit trail
    integrity when passed through recovery operations.

    Attributes:
        container_id: Docker container ID (short or long form)
        container_name: Human-readable container name (for logging only, not parsed)
        project_id: Project identifier from org.codetoreum.project label
        agent_id: Agent identifier from org.codetoreum.agent label
        task_id: Task identifier from org.codetoreum.task_id label
        created_at: Container creation timestamp from Docker API
        labels: Complete label mapping from container for reference (immutable MappingProxyType)
        work_item_id: Work item ID from org.codetoreum.work_item_id label (optional)
        workflow_run_id: Pipeline run ID from org.codetoreum.workflow_run_id label (optional)
        execution_id: Execution ID from org.codetoreum.execution_id label (optional)

    Validation Rules:
        - container_id must be non-empty and non-whitespace (required)
        - container_name must be non-empty and non-whitespace (required)
        - project_id must be non-empty and non-whitespace (required)
        - agent_id must be non-empty and non-whitespace (required)
        - task_id must be non-empty and non-whitespace (required)
        - created_at must be a valid datetime object (not in the future)
        - labels must contain required keys: CONTAINER_LABEL_TYPE, CONTAINER_LABEL_PROJECT, CONTAINER_LABEL_AGENT
        - labels must be a MappingProxyType (immutable)
        - Optional fields can be None or non-empty strings
    """

    container_id: str
    container_name: str
    project_id: str
    agent_id: str
    task_id: str
    created_at: datetime
    labels: MappingProxyType
    work_item_id: Optional[str] = None
    workflow_run_id: Optional[str] = None
    execution_id: Optional[str] = None

    def __post_init__(self) -> None:
        """Validate container metadata after initialization."""
        if not self.container_id or not self.container_id.strip():
            raise ValueError("container_id is required and must be non-empty")
        if not self.container_name or not self.container_name.strip():
            raise ValueError("container_name is required and must be non-empty")
        if not self.project_id or not self.project_id.strip():
            raise ValueError("project_id is required and must be non-empty")
        if not self.agent_id or not self.agent_id.strip():
            raise ValueError("agent_id is required and must be non-empty")
        if not self.task_id or not self.task_id.strip():
            raise ValueError("task_id is required and must be non-empty")
        if not isinstance(self.created_at, datetime):
            raise ValueError("created_at must be a valid datetime object")
        if self.created_at > datetime.now(timezone.utc):
            raise ValueError("created_at cannot be in the future")
        if not isinstance(self.labels, MappingProxyType):
            raise ValueError("labels must be a MappingProxyType (immutable mapping)")
        # Validate required labels
        required_labels = {CONTAINER_LABEL_TYPE, CONTAINER_LABEL_PROJECT, CONTAINER_LABEL_AGENT}
        missing = required_labels - set(self.labels.keys())
        if missing:
            raise ValueError(f"Missing required labels: {missing}")
        # Validate optional fields if provided
        if self.work_item_id is not None and not self.work_item_id.strip():
            raise ValueError("work_item_id must be non-empty if provided")
        if self.workflow_run_id is not None and not self.workflow_run_id.strip():
            raise ValueError("workflow_run_id must be non-empty if provided")
        if self.execution_id is not None and not self.execution_id.strip():
            raise ValueError("execution_id must be non-empty if provided")


@dataclass(frozen=True)
class RecoveryAssessment:
    """Immutable assessment result for a single container.

    This dataclass represents the outcome of assessing a single container
    during the recovery cycle. It is frozen (immutable) to maintain audit
    trail integrity.

    The assessment determines whether to reconnect (resume monitoring) or
    kill (clean up) the container based on:
    - Container age (timeout if >2 hours old)
    - Execution state validation
    - Agent capability matching

    Attributes:
        container_id: Docker container ID being assessed
        action: Recovery action - "reconnect" to resume monitoring or "kill" to cleanup
        reason: Human-readable reason for the assessment decision
        with_monitoring: Whether to enable full monitoring on reconnect
                        (true if work_item_id present, false for limited reconnect)
        execution_id: Execution ID if reconnecting (None if killing)

    Validation Rules:
        - container_id must be non-empty and non-whitespace (required)
        - action must be one of: "reconnect" or "kill"
        - reason must be non-empty and non-whitespace (required)
        - with_monitoring must be a boolean
        - execution_id must be non-empty string (no whitespace-only) if provided, or None
        - If action is "reconnect", execution_id is required (not None, not empty)
        - If action is "kill", execution_id must be None
    """

    container_id: str
    action: Literal["reconnect", "kill"]
    reason: str
    with_monitoring: bool
    execution_id: Optional[str] = None

    def __post_init__(self) -> None:
        """Validate recovery assessment after initialization."""
        if not self.container_id or not self.container_id.strip():
            raise ValueError("container_id is required and must be non-empty")
        if self.action not in ("reconnect", "kill"):
            raise ValueError('action must be one of: "reconnect", "kill"')
        if not self.reason or not self.reason.strip():
            raise ValueError("reason is required and must be non-empty")
        if not isinstance(self.with_monitoring, bool):
            raise ValueError("with_monitoring must be a boolean")
        # Validate execution_id if provided
        if self.execution_id is not None and not self.execution_id.strip():
            raise ValueError("execution_id must be non-empty if provided")
        # Validate logical consistency: reconnect requires execution_id
        if self.action == "reconnect" and not self.execution_id:
            raise ValueError("execution_id is required when action is 'reconnect'")
        # Kill action must not have execution_id
        if self.action == "kill" and self.execution_id is not None:
            raise ValueError("execution_id must be None when action is 'kill'")


@dataclass(frozen=True)
class RecoveryResult:
    """Immutable result from recovery operation.

    This dataclass summarizes the outcome of a complete recovery/cleanup cycle
    at orchestrator startup. It is frozen (immutable) to maintain audit trail
    integrity.

    Attributes:
        recovered: Number of containers successfully reconnected
        killed: Number of containers successfully killed/cleaned up
        errors: Number of containers where recovery failed
        repair_cycles_processed: Number of completed repair cycle results processed
        timestamp: ISO 8601 timestamp when recovery completed

    Validation Rules:
        - recovered must be >= 0 (non-negative integer)
        - killed must be >= 0 (non-negative integer)
        - errors must be >= 0 (non-negative integer)
        - repair_cycles_processed must be >= 0 (non-negative integer)
        - timestamp must be a non-empty ISO 8601 formatted string
        - timestamp must be within reasonable bounds (not more than 1 minute in future, not more than 1 year in past)
        - At least one operation must have been performed (recovered + killed + errors > 0
          OR repair_cycles_processed > 0, unless all containers were already processed)
    """

    recovered: int
    killed: int
    errors: int
    repair_cycles_processed: int
    timestamp: str

    def __post_init__(self) -> None:
        """Validate recovery result after initialization."""
        if self.recovered < 0:
            raise ValueError("recovered must be >= 0")
        if self.killed < 0:
            raise ValueError("killed must be >= 0")
        if self.errors < 0:
            raise ValueError("errors must be >= 0")
        if self.repair_cycles_processed < 0:
            raise ValueError("repair_cycles_processed must be >= 0")
        if not self.timestamp:
            raise ValueError("timestamp is required and must be non-empty")
        # Validate ISO 8601 timestamp format and reasonable bounds
        try:
            parsed_dt = datetime.fromisoformat(self.timestamp)
        except (ValueError, TypeError) as e:
            raise ValueError(
                f"timestamp must be a valid ISO 8601 datetime string, got: {self.timestamp}"
            ) from e

        # Validate timestamp is within reasonable bounds
        now = datetime.now(timezone.utc)
        # Allow 1 minute grace for clock skew
        if parsed_dt > now.replace(microsecond=0) + timedelta(minutes=1):
            raise ValueError("timestamp cannot be more than 1 minute in the future")
        # Allow up to 1 year in the past
        one_year_ago = now - timedelta(days=365)
        if parsed_dt < one_year_ago:
            raise ValueError("timestamp cannot be more than 1 year in the past")


# ============================================================================
# Port Interface
# ============================================================================


class IAgentContainerRecoveryService(ABC):
    """Port interface for container recovery operations.

    The container recovery service is responsible for detecting and managing
    orphaned Docker containers at orchestrator startup. This ensures resources
    are cleaned up and previously interrupted work can be resumed if appropriate.

    Recovery Process:
    1. List running containers using Docker label filtering (org.codetoreum.type)
    2. For each container:
       - Extract metadata from labels (required labels validated)
       - Assess recovery action based on age, execution state, and configuration
       - Execute action (reconnect or kill)
    3. Process any orphaned repair cycle results in storage
    4. Return summary of recovery operations

    Safety Guarantees:
    - Containers without org.codetoreum.type label are NEVER queried or touched
    - Docker label filtering provides query-time protection for unrelated containers
    - Containers with missing required labels are killed (unmanaged cleanup)
    - All operations logged with container context for audit trail
    """

    @abstractmethod
    async def recover_or_cleanup_containers(self) -> RecoveryResult:
        """Execute full recovery/cleanup cycle on startup.

        This is the primary entry point called during orchestrator initialization.
        It coordinates the complete recovery process:
        1. Discovers running Codetoreum containers via label filtering
        2. Assesses each container for recovery or cleanup
        3. Executes recovery actions
        4. Processes orphaned repair results

        Returns:
            RecoveryResult: Summary of recovery operations (recovered, killed, errors counts)

        Raises:
            ContainerError: If Docker API operations fail
            StorageError: If storage operations fail
        """
        pass

    @abstractmethod
    async def get_running_agent_containers(self) -> List[ContainerMetadata]:
        """List running containers with Codetoreum labels.

        Uses Docker label filtering to ONLY return containers with the
        org.codetoreum.type label. This ensures:
        - Unrelated containers (postgres, nginx, etc.) are never returned
        - Query-time protection prevents accidental modifications
        - Label filtering is done at Docker API level, not post-query

        Returns:
            List[ContainerMetadata]: Containers with valid Codetoreum labels
                                     and required fields present

        Raises:
            ContainerError: If Docker API list operation fails
        """
        pass

    @abstractmethod
    async def assess_container(
        self, metadata: ContainerMetadata
    ) -> RecoveryAssessment:
        """Assess recovery action for a single container.

        Evaluates the container's state to determine whether to reconnect
        with monitoring or kill it for cleanup. Assessment criteria:

        1. Age check: Containers >2 hours old are killed (timeout)
        2. Execution validation: Check if execution exists in work tracker
        3. Agent matching: Verify agent in container matches execution
        4. Monitoring capability: Determine if full monitoring possible

        Arguments:
            metadata: Container metadata extracted from Docker labels

        Returns:
            RecoveryAssessment: Decision for this container

        Raises:
            ContainerError: If container inspection fails
            StorageError: If execution state lookup fails
        """
        pass

    @abstractmethod
    async def execute_recovery_action(
        self, assessment: RecoveryAssessment
    ) -> bool:
        """Execute reconnect or kill action.

        Performs the recovery action determined during assessment.

        Actions:
        - reconnect: Resume monitoring the running container
        - kill: Stop and remove the container for cleanup

        Arguments:
            assessment: Recovery assessment with determined action

        Returns:
            bool: True if action succeeded, False otherwise

        Raises:
            ContainerError: If Docker API operations fail
        """
        pass

    @abstractmethod
    async def get_running_repair_cycle_containers(self) -> List[ContainerMetadata]:
        """List running repair cycle containers using label filtering.

        Uses Docker label filtering to ONLY return containers with the
        org.codetoreum.type=repair-cycle label. This separate enumeration
        from agent containers enables specialized recovery logic for repair
        cycle containers, which have different lifecycle management.

        Returns:
            List[ContainerMetadata]: Containers with repair-cycle label

        Raises:
            ContainerError: If Docker API list operation fails
        """
        pass

    @abstractmethod
    async def assess_repair_cycle_container(
        self, metadata: ContainerMetadata
    ) -> RecoveryAssessment:
        """Assess recovery action for a repair cycle container.

        Evaluates repair cycle container state using specialized logic:
        1. Checks for completed results in storage (kills if found)
        2. Checks container age vs 2-hour threshold
        3. If old, checks checkpoint staleness (>60 minutes)
        4. Returns decision (kill stale/old, reconnect fresh)

        Repair cycle containers have different assessment criteria than
        agent containers due to checkpoint-based progress tracking.

        Arguments:
            metadata: Container metadata extracted from Docker labels

        Returns:
            RecoveryAssessment: Decision for this container

        Raises:
            ContainerError: If container inspection fails
            StorageError: If storage/checkpoint lookup fails
        """
        pass

    @abstractmethod
    async def process_orphaned_repair_results(self) -> int:
        """Process completed repair cycle results in storage.

        Handles repair cycle containers that may have completed while
        the orchestrator was offline. Retrieves completed results from
        storage and updates internal state accordingly.

        Returns:
            int: Number of repair cycles processed

        Raises:
            StorageError: If storage operations fail
        """
        pass
