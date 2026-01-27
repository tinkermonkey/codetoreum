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
from datetime import datetime
from typing import Dict, List, Literal, Optional


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
        labels: Complete label dictionary from container for reference
        work_item_id: Work item ID from org.codetoreum.work_item_id label (optional)
        pipeline_run_id: Pipeline run ID from org.codetoreum.pipeline_run_id label (optional)
        execution_id: Execution ID from org.codetoreum.execution_id label (optional)
    """

    container_id: str
    container_name: str
    project_id: str
    agent_id: str
    task_id: str
    created_at: datetime
    labels: Dict[str, str]
    work_item_id: Optional[str] = None
    pipeline_run_id: Optional[str] = None
    execution_id: Optional[str] = None


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
    """

    container_id: str
    action: Literal["reconnect", "kill"]
    reason: str
    with_monitoring: bool
    execution_id: Optional[str] = None


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
    """

    recovered: int
    killed: int
    errors: int
    repair_cycles_processed: int
    timestamp: str


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
