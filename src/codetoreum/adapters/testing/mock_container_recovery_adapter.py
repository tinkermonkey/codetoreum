"""Mock container recovery adapter for testing and simulation.

This adapter provides deterministic, controlled container recovery behavior
for use in unit tests, integration tests, and simulation mode.
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional

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
        self.containers: List[ContainerMetadata] = []  # Agent containers
        self.repair_cycle_containers: List[ContainerMetadata] = []  # Repair cycle containers
        self.assessments: Dict[str, RecoveryAssessment] = {}
        self.failed_actions: set = set()
        self.executed_actions: List[RecoveryAssessment] = []
        self.repair_cycles_to_process: int = 0

    def add_container(
        self,
        container_id: str,
        container_name: str,
        project_id: str,
        agent_id: str,
        task_id: str,
        work_item_id: Optional[str] = None,
        execution_id: Optional[str] = None,
        created_at: Optional[datetime] = None,
        age_hours: Optional[float] = None,
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
            created_at: Optional creation timestamp (defaults to now)
            age_hours: Optional age in hours (used instead of created_at)

        Returns:
            ContainerMetadata: The created metadata object
        """
        if created_at is None:
            if age_hours is not None:
                created_at = datetime.now(timezone.utc) - timedelta(hours=age_hours)
            else:
                created_at = datetime.now(timezone.utc)

        metadata = ContainerMetadata(
            container_id=container_id,
            container_name=container_name,
            project_id=project_id,
            agent_id=agent_id,
            task_id=task_id,
            created_at=created_at,
            labels={
                "org.codetoreum.type": CONTAINER_TYPE_AGENT,
                "org.codetoreum.project": project_id,
                "org.codetoreum.agent": agent_id,
                "org.codetoreum.task_id": task_id,
            },
            work_item_id=work_item_id,
            execution_id=execution_id,
        )

        self.containers.append(metadata)
        return metadata

    def add_repair_cycle_container(
        self,
        container_id: str,
        container_name: str,
        project_id: str,
        agent_id: str,
        task_id: str,
        work_item_id: Optional[str] = None,
        execution_id: Optional[str] = None,
        created_at: Optional[datetime] = None,
        age_hours: Optional[float] = None,
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
                created_at = datetime.now(timezone.utc) - timedelta(hours=age_hours)
            else:
                created_at = datetime.now(timezone.utc)

        metadata = ContainerMetadata(
            container_id=container_id,
            container_name=container_name,
            project_id=project_id,
            agent_id=agent_id,
            task_id=task_id,
            created_at=created_at,
            labels={
                "org.codetoreum.type": CONTAINER_TYPE_REPAIR_CYCLE,
                "org.codetoreum.project": project_id,
                "org.codetoreum.agent": agent_id,
                "org.codetoreum.task_id": task_id,
            },
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
        execution_id: Optional[str] = None,
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

    async def get_running_agent_containers(self) -> List[ContainerMetadata]:
        """
        Return mock agent containers.

        Returns:
            List[ContainerMetadata]: Configured mock agent containers
        """
        logger.debug(f"Mock adapter returning {len(self.containers)} agent containers")
        return self.containers

    async def get_running_repair_cycle_containers(self) -> List[ContainerMetadata]:
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
            ValueError: If container not found in assessments and no default set
        """
        assessment = self.assessments.get(
            metadata.container_id,
            RecoveryAssessment(
                container_id=metadata.container_id,
                action="reconnect",
                reason="default_recovery",
                with_monitoring=bool(metadata.work_item_id),
                execution_id=metadata.execution_id,
            ),
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
            ValueError: If container not found in assessments and no default set
        """
        assessment = self.assessments.get(
            metadata.container_id,
            RecoveryAssessment(
                container_id=metadata.container_id,
                action="reconnect",
                reason="default_repair_cycle_recovery",
                with_monitoring=bool(metadata.work_item_id),
                execution_id=metadata.execution_id,
            ),
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
        """
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
        """
        logger.debug(f"Mock processing {self.repair_cycles_to_process} repair cycles")
        return self.repair_cycles_to_process

    async def recover_or_cleanup_containers(self):
        """Placeholder for main recovery interface method."""
        # This is implemented by ContainerRecoveryService orchestrator
        # The mock adapter provides the sub-methods
        raise NotImplementedError(
            "recover_or_cleanup_containers is orchestrated by ContainerRecoveryService"
        )

    def reset(self) -> None:
        """Reset all mock state."""
        self.containers = []
        self.repair_cycle_containers = []
        self.assessments = {}
        self.failed_actions = set()
        self.executed_actions = []
        self.repair_cycles_to_process = 0
