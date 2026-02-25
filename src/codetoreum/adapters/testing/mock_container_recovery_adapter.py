"""Mock container recovery adapter for testing and simulation.

This adapter provides deterministic, controlled container recovery behavior
for use in unit tests, integration tests, and simulation mode.
"""

import logging
from datetime import UTC, datetime, timedelta
from types import MappingProxyType

from codetoreum.domain.types import CONTAINER_TYPE_AGENT, CONTAINER_TYPE_REPAIR_CYCLE
from codetoreum.ports.output.container_recovery import (
    ContainerMetadata,
    IAgentContainerRecoveryService,
    RecoveryAssessment,
)

logger = logging.getLogger(__name__)


class MockContainerRecoveryAdapter(IAgentContainerRecoveryService):
    """
    Mock adapter for container recovery operations.

    This adapter provides:
    - Deterministic behavior for testing
    - Controllable container lists
    - Configurable recovery assessments
    - No actual Docker dependency

    Attributes:
        containers: List of containers to return from get_running_agent_containers
        assessments: Dict mapping container_id to assessment decision
        failed_actions: Set of container_ids where execute_recovery_action should fail
    """

    def __init__(self):
        """Initialize MockContainerRecoveryAdapter."""
        self.containers: list[ContainerMetadata] = []  # Agent containers
        self.repair_cycle_containers: list[ContainerMetadata] = []  # Repair cycle containers
        self.assessments: dict[str, RecoveryAssessment] = {}
        self.failed_actions: set = set()
        self.executed_actions: list[RecoveryAssessment] = []
        self.repair_cycles_to_process: int = 0
        self.docker_failure_after_count: int | None = None  # Simulate Docker failure after N containers
        self.docker_failure_counter: int = 0  # Current count of processed containers
        self.assessment_exceptions: dict[str, Exception] = {}  # Exceptions to raise during assessment
        self.checkpoint_store_failures: set = set()  # Container IDs that cause checkpoint store failure
        self.malformed_storage_keys: list[str] = []  # Malformed keys to simulate storage issues

    def add_container(
        self,
        container_id: str,
        container_name: str,
        project_id: str,
        agent_id: str,
        task_id: str,
        work_item_id: str | None = None,
        execution_id: str | None = None,
        workflow_run_id: str | None = None,
        created_at: datetime | None = None,
        age_hours: float | None = None,
        container_type: str = CONTAINER_TYPE_AGENT,
    ) -> ContainerMetadata:
        """
        Add a mock container to the adapter.

        Args:
            container_id: Docker container ID
            container_name: Container name
            project_id: Project ID
            agent_id: Agent ID
            task_id: Task ID
            work_item_id: Optional work item ID
            execution_id: Optional execution ID
            workflow_run_id: Optional pipeline run ID
            created_at: Optional creation timestamp (defaults to now)
            age_hours: Optional age in hours (used instead of created_at)
            container_type: Container type (agent or repair-cycle)

        Returns:
            ContainerMetadata: The created metadata object
        """
        if created_at is None:
            if age_hours is not None:
                created_at = datetime.now(UTC) - timedelta(hours=age_hours)
            else:
                created_at = datetime.now(UTC)

        metadata = ContainerMetadata(
            container_id=container_id,
            container_name=container_name,
            project_id=project_id,
            agent_id=agent_id,
            task_id=task_id,
            created_at=created_at,
            labels=MappingProxyType({
                "org.codetoreum.type": container_type,
                "org.codetoreum.project": project_id,
                "org.codetoreum.agent": agent_id,
                "org.codetoreum.task_id": task_id,
            }),
            work_item_id=work_item_id,
            execution_id=execution_id,
            workflow_run_id=workflow_run_id,
        )

        if container_type == CONTAINER_TYPE_REPAIR_CYCLE:
            self.repair_cycle_containers.append(metadata)
        else:
            self.containers.append(metadata)
        return metadata

    def add_repair_cycle_container(
        self,
        container_id: str,
        container_name: str,
        project_id: str,
        agent_id: str,
        task_id: str,
        work_item_id: str | None = None,
        execution_id: str | None = None,
        created_at: datetime | None = None,
        age_hours: float | None = None,
    ) -> ContainerMetadata:
        """
        Add a mock repair cycle container to the adapter.

        Args:
            container_id: Docker container ID
            container_name: Container name
            project_id: Project ID
            agent_id: Agent ID (repair agent)
            task_id: Task ID
            work_item_id: Optional work item ID
            execution_id: Optional execution ID
            created_at: Optional creation timestamp (defaults to now)
            age_hours: Optional age in hours (used instead of created_at)

        Returns:
            ContainerMetadata: The created metadata object
        """
        if created_at is None:
            if age_hours is not None:
                created_at = datetime.now(UTC) - timedelta(hours=age_hours)
            else:
                created_at = datetime.now(UTC)

        metadata = ContainerMetadata(
            container_id=container_id,
            container_name=container_name,
            project_id=project_id,
            agent_id=agent_id,
            task_id=task_id,
            created_at=created_at,
            labels=MappingProxyType({
                "org.codetoreum.type": CONTAINER_TYPE_REPAIR_CYCLE,
                "org.codetoreum.project": project_id,
                "org.codetoreum.agent": agent_id,
                "org.codetoreum.task_id": task_id,
            }),
            work_item_id=work_item_id,
            execution_id=execution_id,
        )

        self.repair_cycle_containers.append(metadata)
        return metadata

    def set_assessment(
        self,
        container_id: str,
        action: str,
        reason: str,
        with_monitoring: bool = False,
        execution_id: str | None = None,
    ) -> None:
        """
        Set the recovery assessment for a container.

        Args:
            container_id: Docker container ID
            action: Recovery action ("reconnect" or "kill")
            reason: Reason for the decision
            with_monitoring: Whether to enable full monitoring (for reconnect)
            execution_id: Execution ID (for reconnect)
        """
        self.assessments[container_id] = RecoveryAssessment(
            container_id=container_id,
            action=action,
            reason=reason,
            with_monitoring=with_monitoring,
            execution_id=execution_id,
        )

    def set_action_failure(self, container_id: str) -> None:
        """
        Mark a container's recovery action as failing.

        Args:
            container_id: Docker container ID
        """
        self.failed_actions.add(container_id)

    async def get_running_agent_containers(self) -> list[ContainerMetadata]:
        """
        Return mock agent containers.

        Returns:
            List[ContainerMetadata]: Configured mock agent containers
        """
        logger.debug(f"Mock adapter returning {len(self.containers)} agent containers")
        return self.containers

    async def get_running_repair_cycle_containers(self) -> list[ContainerMetadata]:
        """
        Return mock repair cycle containers.

        Returns:
            List[ContainerMetadata]: Configured mock repair cycle containers
        """
        logger.debug(
            f"Mock adapter returning {len(self.repair_cycle_containers)} repair cycle containers"
        )
        return self.repair_cycle_containers

    async def assess_container(
        self, metadata: ContainerMetadata
    ) -> RecoveryAssessment:
        """
        Return pre-configured assessment for a container.

        Args:
            metadata: Container metadata

        Returns:
            RecoveryAssessment: Pre-configured assessment, or default reconnect

        Raises:
            Exception: If configured to raise an exception for this container
        """
        # Check if this container should raise an exception
        if metadata.container_id in self.assessment_exceptions:
            raise self.assessment_exceptions[metadata.container_id]

        # Check if Docker failure threshold reached
        if (self.docker_failure_after_count is not None and
                self.docker_failure_counter >= self.docker_failure_after_count):
            from codetoreum.ports.exceptions import ContainerError
            msg = f"Docker daemon unavailable (simulated failure after {self.docker_failure_after_count} containers)"
            raise ContainerError(
                msg,
                error_code="ERR_DOCKER_CONNECTION_FAILED"
            )

        self.docker_failure_counter += 1

        if metadata.container_id in self.assessments:
            assessment = self.assessments[metadata.container_id]
        # Default: reconnect if execution_id present, otherwise kill
        elif metadata.execution_id:
            assessment = RecoveryAssessment(
                container_id=metadata.container_id,
                action="reconnect",
                reason="default_recovery",
                with_monitoring=bool(metadata.work_item_id),
                execution_id=metadata.execution_id,
            )
        else:
            assessment = RecoveryAssessment(
                container_id=metadata.container_id,
                action="kill",
                reason="no_execution_found",
                with_monitoring=False,
                execution_id=None,
            )

        logger.debug(
            f"Mock assess container {metadata.container_id}: {assessment.action}"
        )
        return assessment

    async def assess_repair_cycle_container(
        self, metadata: ContainerMetadata
    ) -> RecoveryAssessment:
        """
        Return pre-configured assessment for a repair cycle container.

        Args:
            metadata: Container metadata

        Returns:
            RecoveryAssessment: Pre-configured assessment, or default reconnect

        Raises:
            StorageError: If checkpoint store is unavailable
        """
        # Check if checkpoint store should fail for this container
        if metadata.container_id in self.checkpoint_store_failures:
            from codetoreum.ports.exceptions import StorageError
            msg = f"Checkpoint store unavailable for {metadata.container_id}"
            raise StorageError(
                msg,
                error_code="ERR_CHECKPOINT_STORE_UNAVAILABLE"
            )

        if metadata.container_id in self.assessments:
            assessment = self.assessments[metadata.container_id]
        # Default: reconnect if execution_id present, otherwise kill
        elif metadata.execution_id:
            assessment = RecoveryAssessment(
                container_id=metadata.container_id,
                action="reconnect",
                reason="default_repair_cycle_recovery",
                with_monitoring=bool(metadata.work_item_id),
                execution_id=metadata.execution_id,
            )
        else:
            assessment = RecoveryAssessment(
                container_id=metadata.container_id,
                action="kill",
                reason="no_checkpoint",
                with_monitoring=False,
                execution_id=None,
            )

        logger.debug(
            f"Mock assess repair cycle container {metadata.container_id}: {assessment.action}"
        )
        return assessment

    async def execute_recovery_action(self, assessment: RecoveryAssessment) -> bool:
        """
        Execute recovery action with mock behavior.

        Args:
            assessment: Recovery assessment with determined action

        Returns:
            bool: False if container_id is in failed_actions, True otherwise

        Raises:
            ContainerError: If Docker failure threshold is reached
        """
        # Check if Docker failure threshold reached
        if (self.docker_failure_after_count is not None and
                self.docker_failure_counter > self.docker_failure_after_count):
            from codetoreum.ports.exceptions import ContainerError
            msg = "Docker daemon unavailable (simulated failure)"
            raise ContainerError(
                msg,
                error_code="ERR_DOCKER_CONNECTION_FAILED"
            )

        self.executed_actions.append(assessment)

        if assessment.container_id in self.failed_actions:
            logger.warning(
                f"Mock execute action failed for {assessment.container_id} "
                f"(configured to fail)"
            )
            return False

        logger.debug(
            f"Mock execute action succeeded for {assessment.container_id}: "
            f"{assessment.action}"
        )
        return True

    async def process_orphaned_repair_results(self) -> int:
        """
        Return configured number of repair cycles processed.

        Returns:
            int: Number of repair cycles (from repair_cycles_to_process)

        Raises:
            StorageError: If storage has malformed keys
        """
        # Simulate processing malformed storage keys
        if self.malformed_storage_keys:
            logger.warning(
                f"Found {len(self.malformed_storage_keys)} malformed storage keys, "
                f"skipping them"
            )

        logger.debug(f"Mock processing {self.repair_cycles_to_process} repair cycles")
        return self.repair_cycles_to_process

    async def recover_or_cleanup_containers(self) -> "RecoveryResult":
        """Execute full recovery/cleanup cycle - DEPRECATED.

        This method is kept for interface compatibility but should not be called directly.
        The recovery orchestration logic has been moved to ContainerRecoveryService.

        Returns:
            RecoveryResult: Placeholder result (not used)

        Raises:
            NotImplementedError: This method should be called through ContainerRecoveryService
        """
        msg = (
            "recover_or_cleanup_containers is orchestrated by ContainerRecoveryService. "
            "Call the service instead of invoking this method directly."
        )
        raise NotImplementedError(
            msg
        )

    def reset(self) -> None:
        """Reset all mock state."""
        self.containers = []
        self.repair_cycle_containers = []
        self.assessments = {}
        self.failed_actions = set()
        self.executed_actions = []
        self.repair_cycles_to_process = 0
        self.docker_failure_after_count = None
        self.docker_failure_counter = 0
        self.assessment_exceptions = {}
        self.checkpoint_store_failures = set()
        self.malformed_storage_keys = []

    def set_docker_failure_after_count(self, count: int) -> None:
        """
        Simulate Docker API failure after processing N containers.

        Args:
            count: Number of containers to process before simulating Docker failure
        """
        self.docker_failure_after_count = count
        self.docker_failure_counter = 0

    def set_assessment_exception(self, container_id: str, exception: Exception) -> None:
        """
        Configure assessment to raise an exception for a specific container.

        Args:
            container_id: Container ID that will raise exception
            exception: Exception to raise during assessment
        """
        self.assessment_exceptions[container_id] = exception

    def set_checkpoint_store_failure(self, container_id: str) -> None:
        """
        Configure checkpoint store to fail for a specific container.

        Args:
            container_id: Container ID that will cause checkpoint store failure
        """
        self.checkpoint_store_failures.add(container_id)

    def add_malformed_storage_key(self, key: str) -> None:
        """
        Add a malformed storage key to simulate storage issues.

        Args:
            key: Malformed key that doesn't match expected patterns
        """
        self.malformed_storage_keys.append(key)
