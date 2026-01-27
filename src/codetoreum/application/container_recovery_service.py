"""Container recovery application service.

This service orchestrates the recovery/cleanup of containers at orchestrator
startup. It discovers running Codetoreum-labeled containers, assesses each
one for recovery or cleanup, and executes the appropriate action.

The service coordinates with:
- IAgentContainerRecoveryService: Port interface implementation (adapter)
- IWorkExecutionStateTracker: For querying execution state
- IStorage: For tracking container re-registration
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
from codetoreum.ports.exceptions import ContainerError, StorageError
from codetoreum.ports.output.container_recovery import (
    ContainerMetadata,
    RecoveryAssessment,
    RecoveryResult,
)
from codetoreum.ports.output.event_emitter import IEventEmitter

logger = logging.getLogger(__name__)


class ContainerRecoveryService:
    """
    Application service for container recovery.

    Implements the IAgentContainerRecoveryService port interface to manage
    recovery of containers at orchestrator startup. This service ensures:

    1. Running containers are identified via Docker label filtering
    2. Each container's state is assessed for recovery or cleanup
    3. Recovery actions are executed safely
    4. All operations are logged and emitted as domain events

    The service delegates actual implementation to a recovery service adapter
    (e.g., DockerContainerRecoveryAdapter) which handles the port interface
    methods: get_running_agent_containers, assess_container, etc.

    Thread Safety:
    - This service is async-safe but not thread-safe
    - Container processing uses bounded parallelism (semaphore)
    """

    BATCH_SIZE = 10  # Bounded parallelism for container processing
    TRACKING_STORAGE_TTL = 7200  # 2 hours in seconds

    def __init__(
        self,
        recovery_adapter,  # IAgentContainerRecoveryService implementation
        event_emitter: IEventEmitter,
        container_timeout_hours: int = 2,
    ):
        """
        Initialize ContainerRecoveryService.

        Args:
            recovery_adapter: Recovery adapter implementing IAgentContainerRecoveryService
            event_emitter: Event emitter for publishing recovery events
            container_timeout_hours: Hours before a container is considered orphaned
        """
        self.recovery_adapter = recovery_adapter
        self.event_emitter = event_emitter
        self.container_timeout_hours = container_timeout_hours

    async def recover_or_cleanup_containers(self) -> RecoveryResult:
        """
        Execute full recovery/cleanup cycle on startup.

        This is the primary entry point called during orchestrator initialization.
        It coordinates the complete recovery process:
        1. Discovers running Codetoreum containers via label filtering
        2. Assesses each container for recovery or cleanup
        3. Executes recovery actions with bounded parallelism
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
            containers = await self.recovery_adapter.get_running_agent_containers()
            logger.info(f"Found {len(containers)} running Codetoreum containers")

            # Step 2: Assess and execute recovery for each container with bounded parallelism
            semaphore = asyncio.Semaphore(self.BATCH_SIZE)

            async def process_container(metadata: ContainerMetadata):
                """Process a single container with semaphore-bounded parallelism."""
                async with semaphore:
                    try:
                        assessment = await self.recovery_adapter.assess_container(
                            metadata
                        )
                        success = await self.recovery_adapter.execute_recovery_action(
                            assessment
                        )

                        if success:
                            if assessment.action == "reconnect":
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
                                return ("reconnect", True)
                            else:  # kill
                                # Emit kill event
                                event = ContainerKilledEvent(
                                    type="container_recovery.killed",
                                    timestamp=datetime.now(timezone.utc).isoformat(),
                                    source="container_recovery_service",
                                    container_id=metadata.container_id,
                                    container_name=metadata.container_name,
                                    project_id=metadata.project_id,
                                    agent_id=metadata.agent_id,
                                    work_item_id=metadata.work_item_id,
                                    kill_reason=assessment.reason,
                                    uptime_seconds=self._calculate_uptime_seconds(
                                        metadata.created_at
                                    ),
                                    execution_marked_failed=False,
                                )
                                self.event_emitter.emit(event)
                                return ("kill", True)
                        else:
                            logger.error(
                                f"Failed to execute recovery action for container {metadata.container_id}"
                            )
                            return ("error", False)

                    except (ContainerError, StorageError) as e:
                        logger.error(
                            f"Error during recovery of container {metadata.container_id}: {e}",
                            exc_info=True,
                        )
                        return ("error", False)

            # Process containers with bounded parallelism
            results = await asyncio.gather(
                *[process_container(c) for c in containers], return_exceptions=False
            )

            # Count results
            for action, success in results:
                if action == "reconnect" and success:
                    recovered_count += 1
                elif action == "kill" and success:
                    killed_count += 1
                elif action == "error":
                    error_count += 1

            # Step 3: Process orphaned repair results
            try:
                repair_cycles_processed = (
                    await self.recovery_adapter.process_orphaned_repair_results()
                )
            except StorageError as e:
                logger.warning(
                    f"Failed to process orphaned repair results: {e}", exc_info=True
                )

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
            logger.error(
                f"Unrecoverable error in container recovery: {e}", exc_info=True
            )
            # Return partial result with error tracking
            return RecoveryResult(
                recovered=recovered_count,
                killed=killed_count,
                errors=error_count + 1,
                repair_cycles_processed=repair_cycles_processed,
                timestamp=datetime.now(timezone.utc).isoformat(),
            )


    @staticmethod
    def _calculate_uptime_seconds(created_at: datetime) -> float:
        """Calculate container uptime in seconds."""
        now = datetime.now(timezone.utc)
        delta = now - created_at
        return delta.total_seconds()
