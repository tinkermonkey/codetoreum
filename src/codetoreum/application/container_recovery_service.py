"""Container recovery application service.

This service orchestrates the recovery/cleanup of containers at orchestrator
startup. It discovers running Codetoreum-labeled containers, assesses each
one for recovery or cleanup, and executes the appropriate action.

The service coordinates with:
- IContainer: For Docker operations (list, inspect, kill)
- IAgentContainerRecoveryService: The port interface being implemented
- IEventStore: For checking execution state
- IEventEmitter: For publishing recovery events
"""

import asyncio
import logging
from datetime import datetime, timezone
from typing import List, Optional

from codetoreum.domain.events.container_recovery_events import (
    ContainerKilledEvent,
    ContainerRecoveredEvent,
    ContainerRecoveryCompletedEvent,
)
from codetoreum.ports.exceptions import ContainerError, EventStoreError, StorageError
from codetoreum.ports.output.container_recovery import (
    ContainerMetadata,
    IAgentContainerRecoveryService,
    RecoveryAssessment,
    RecoveryResult,
)
from codetoreum.ports.output.event_emitter import IEventEmitter
from codetoreum.ports.output.event_store import IEventStore

logger = logging.getLogger(__name__)


class ContainerRecoveryService(IAgentContainerRecoveryService):
    """
    Application service for container recovery.

    Implements the IAgentContainerRecoveryService port interface to manage
    recovery of containers at orchestrator startup. This service ensures:

    1. Running containers are identified via Docker label filtering
    2. Each container's state is assessed for recovery or cleanup
    3. Recovery actions are executed safely
    4. All operations are logged and emitted as domain events

    Thread Safety:
    - This service is async-safe but not thread-safe
    - All operations are sequential for safety
    """

    def __init__(
        self,
        container_service,  # IContainer
        event_store: IEventStore,
        event_emitter: IEventEmitter,
        container_timeout_hours: int = 2,
    ):
        """
        Initialize ContainerRecoveryService.

        Args:
            container_service: Container orchestration adapter (IContainer)
            event_store: Event store for checking execution state
            event_emitter: Event emitter for publishing recovery events
            container_timeout_hours: Hours before a container is considered orphaned
        """
        self.container_service = container_service
        self.event_store = event_store
        self.event_emitter = event_emitter
        self.container_timeout_hours = container_timeout_hours

    async def recover_or_cleanup_containers(self) -> RecoveryResult:
        """
        Execute full recovery/cleanup cycle on startup.

        This is the primary entry point called during orchestrator initialization.
        It coordinates the complete recovery process:
        1. Discovers running Codetoreum containers via label filtering
        2. Assesses each container for recovery or cleanup
        3. Executes recovery actions
        4. Processes orphaned repair results
        5. Emits completion event

        Returns:
            RecoveryResult: Summary of recovery operations

        Raises:
            ContainerError: If Docker API operations fail
            StorageError: If storage operations fail
        """
        start_time = datetime.now(timezone.utc)
        recovered_count = 0
        killed_count = 0
        error_count = 0
        repair_cycles_processed = 0

        try:
            # Step 1: List running containers
            logger.info("Starting container recovery cycle")
            containers = await self.get_running_agent_containers()
            logger.info(f"Found {len(containers)} running Codetoreum containers")

            # Step 2: Assess and execute recovery for each container
            for metadata in containers:
                try:
                    assessment = await self.assess_container(metadata)
                    success = await self.execute_recovery_action(assessment)

                    if success:
                        if assessment.action == "reconnect":
                            recovered_count += 1
                            # Emit recovery event
                            event = ContainerRecoveredEvent(
                                type="container_recovery.recovered",
                                timestamp=datetime.now(timezone.utc).isoformat(),
                                source="container_recovery_service",
                                container_id=metadata.container_id,
                                container_name=metadata.container_name,
                                project_id=metadata.project_id,
                                agent_id=metadata.agent_id,
                                work_item_id=metadata.work_item_id,
                                execution_id=metadata.execution_id,
                                uptime_seconds=self._calculate_uptime_seconds(
                                    metadata.created_at
                                ),
                                recovery_action=(
                                    "reconnect_with_monitoring"
                                    if assessment.with_monitoring
                                    else "reconnect_limited"
                                ),
                            )
                            self.event_emitter.emit(event)
                        else:  # kill
                            killed_count += 1
                            # Emit kill event
                            event = ContainerKilledEvent(
                                type="container_recovery.killed",
                                timestamp=datetime.now(timezone.utc).isoformat(),
                                source="container_recovery_service",
                                container_id=metadata.container_id,
                                container_name=metadata.container_name,
                                project_id=metadata.project_id,
                                agent_id=metadata.agent_id,
                                kill_reason=assessment.reason,
                                uptime_seconds=self._calculate_uptime_seconds(
                                    metadata.created_at
                                ),
                                execution_marked_failed=False,
                            )
                            self.event_emitter.emit(event)
                    else:
                        error_count += 1
                        logger.error(
                            f"Failed to execute recovery action for container {metadata.container_id}"
                        )

                except (ContainerError, StorageError) as e:
                    error_count += 1
                    logger.error(
                        f"Error during recovery of container {metadata.container_id}: {e}",
                        exc_info=True,
                    )

            # Step 3: Process orphaned repair results
            try:
                repair_cycles_processed = await self.process_orphaned_repair_results()
            except StorageError as e:
                logger.warning(f"Failed to process orphaned repair results: {e}")

            # Step 4: Emit completion event
            end_time = datetime.now(timezone.utc)
            duration_seconds = (end_time - start_time).total_seconds()

            completion_event = ContainerRecoveryCompletedEvent(
                type="container_recovery.completed",
                timestamp=datetime.now(timezone.utc).isoformat(),
                source="container_recovery_service",
                containers_recovered=recovered_count,
                containers_killed=killed_count,
                errors_encountered=error_count,
                repair_cycles_processed=repair_cycles_processed,
                started_at=start_time.isoformat(),
                completed_at=end_time.isoformat(),
                duration_seconds=duration_seconds,
            )
            self.event_emitter.emit(completion_event)

            logger.info(
                f"Container recovery cycle completed: "
                f"{recovered_count} recovered, "
                f"{killed_count} killed, "
                f"{error_count} errors, "
                f"{repair_cycles_processed} repair cycles processed"
            )

            return RecoveryResult(
                recovered=recovered_count,
                killed=killed_count,
                errors=error_count,
                repair_cycles_processed=repair_cycles_processed,
                timestamp=end_time.isoformat(),
            )

        except Exception as e:
            logger.error("Unrecoverable error in container recovery: {}", exc_info=True)
            # Return partial result with error tracking
            return RecoveryResult(
                recovered=recovered_count,
                killed=killed_count,
                errors=error_count + 1,
                repair_cycles_processed=repair_cycles_processed,
                timestamp=datetime.now(timezone.utc).isoformat(),
            )

    async def get_running_agent_containers(self) -> List[ContainerMetadata]:
        """
        List running containers with Codetoreum labels.

        Uses Docker label filtering to ONLY return containers with the
        org.codetoreum.type label. This ensures:
        - Unrelated containers (postgres, nginx, etc.) are never returned
        - Query-time protection prevents accidental modifications
        - Label filtering is done at Docker API level

        Returns:
            List[ContainerMetadata]: Containers with valid Codetoreum labels

        Raises:
            ContainerError: If Docker API list operation fails
        """
        # Note: This is implemented in the production adapter
        # The container_service (IContainer) provides the Docker integration
        # but we need a recovery-specific method that returns ContainerMetadata
        # This will be implemented in DockerContainerRecoveryAdapter
        raise NotImplementedError(
            "get_running_agent_containers must be implemented in adapter"
        )

    async def assess_container(
        self, metadata: ContainerMetadata
    ) -> RecoveryAssessment:
        """
        Assess recovery action for a single container.

        Evaluates the container's state to determine whether to reconnect
        with monitoring or kill it for cleanup. Assessment criteria:

        1. Age check: Containers >2 hours old are killed (timeout)
        2. Execution validation: Check if execution exists in work tracker
        3. Agent matching: Verify agent in container matches execution
        4. Monitoring capability: Determine if full monitoring possible

        Args:
            metadata: Container metadata extracted from Docker labels

        Returns:
            RecoveryAssessment: Decision for this container

        Raises:
            ContainerError: If container inspection fails
            StorageError: If execution state lookup fails
        """
        # Note: This is implemented in the production adapter
        raise NotImplementedError("assess_container must be implemented in adapter")

    async def execute_recovery_action(
        self, assessment: RecoveryAssessment
    ) -> bool:
        """
        Execute reconnect or kill action.

        Performs the recovery action determined during assessment.

        Actions:
        - reconnect: Resume monitoring the running container
        - kill: Stop and remove the container for cleanup

        Args:
            assessment: Recovery assessment with determined action

        Returns:
            bool: True if action succeeded, False otherwise

        Raises:
            ContainerError: If Docker API operations fail
        """
        # Note: This is implemented in the production adapter
        raise NotImplementedError(
            "execute_recovery_action must be implemented in adapter"
        )

    async def process_orphaned_repair_results(self) -> int:
        """
        Process completed repair cycle results in storage.

        Handles repair cycle containers that may have completed while
        the orchestrator was offline. Retrieves completed results from
        storage and updates internal state accordingly.

        Returns:
            int: Number of repair cycles processed

        Raises:
            StorageError: If storage operations fail
        """
        # Note: This is implemented in the production adapter
        raise NotImplementedError(
            "process_orphaned_repair_results must be implemented in adapter"
        )

    @staticmethod
    def _calculate_uptime_seconds(created_at: datetime) -> float:
        """Calculate container uptime in seconds."""
        now = datetime.now(timezone.utc)
        delta = now - created_at
        return delta.total_seconds()
