"""Docker adapter for IAgentContainerRecoveryService.

This adapter implements container recovery operations using Docker SDK for Python.
It handles:
- Listing containers with Codetoreum labels
- Extracting metadata from container labels
- Assessing container state for recovery or cleanup
- Executing recovery actions (reconnect or kill)
"""

import asyncio
import logging
from datetime import datetime, timezone
from typing import Dict, List, Optional

from dateutil import parser as dateparser

from codetoreum.domain.types import (
    CONTAINER_LABEL_AGENT,
    CONTAINER_LABEL_EXECUTION_ID,
    CONTAINER_LABEL_PIPELINE_RUN_ID,
    CONTAINER_LABEL_PROJECT,
    CONTAINER_LABEL_TASK_ID,
    CONTAINER_LABEL_TYPE,
    CONTAINER_LABEL_WORK_ITEM_ID,
    CONTAINER_TYPE_AGENT,
    CONTAINER_TYPE_REPAIR_CYCLE,
)
from codetoreum.ports.exceptions import ContainerError, StorageError
from codetoreum.ports.output.container_recovery import (
    ContainerMetadata,
    RecoveryAssessment,
)
from codetoreum.ports.output.event_store import IEventStore

logger = logging.getLogger(__name__)


class DockerContainerRecoveryAdapter:
    """
    Docker adapter for container recovery operations.

    This adapter implements the recovery logic by:
    1. Connecting to Docker daemon
    2. Listing containers with Codetoreum labels
    3. Extracting metadata from labels
    4. Assessing each container for recovery or cleanup
    5. Executing recovery actions

    Thread Safety:
    - This adapter is async-safe but not thread-safe
    - All Docker operations are executed in a thread pool
    """

    def __init__(self, event_store: IEventStore, container_timeout_hours: int = 2):
        """
        Initialize DockerContainerRecoveryAdapter.

        Args:
            event_store: Event store for checking execution state
            container_timeout_hours: Hours before a container is considered orphaned
        """
        self.event_store = event_store
        self.container_timeout_hours = container_timeout_hours
        self._docker_client = None

    def _get_client(self):
        """Get or create Docker client."""
        if self._docker_client is None:
            try:
                import docker

                self._docker_client = docker.from_env()
            except Exception as e:
                raise ContainerError(f"Failed to connect to Docker: {str(e)}")

        return self._docker_client

    async def get_running_agent_containers(self) -> List[ContainerMetadata]:
        """
        List running containers with Codetoreum labels.

        Uses Docker label filtering to ONLY return containers with the
        org.codetoreum.type label. This ensures:
        - Unrelated containers are never returned
        - Query-time protection prevents accidental modifications
        - Label filtering is done at Docker API level

        Returns:
            List[ContainerMetadata]: Containers with valid Codetoreum labels

        Raises:
            ContainerError: If Docker API list operation fails
        """
        loop = asyncio.get_event_loop()

        def _list_containers():
            client = self._get_client()

            try:
                # Use Docker label filtering to only get Codetoreum containers
                # Filters containers with org.codetoreum.type label
                filters = {
                    "label": f"{CONTAINER_LABEL_TYPE}",
                }

                containers = client.containers.list(filters=filters, all=False)
                metadata_list = []

                for container in containers:
                    try:
                        metadata = self._extract_metadata(container)
                        if metadata:
                            metadata_list.append(metadata)
                    except Exception as e:
                        logger.warning(
                            f"Failed to extract metadata from container {container.short_id}: {e}",
                            exc_info=True,
                        )

                return metadata_list

            except Exception as e:
                raise ContainerError(f"Failed to list containers: {str(e)}")

        return await loop.run_in_executor(None, _list_containers)

    def _extract_metadata(self, container) -> Optional[ContainerMetadata]:
        """
        Extract metadata from container labels.

        Args:
            container: Docker container object

        Returns:
            ContainerMetadata if all required labels present, None otherwise
        """
        labels = container.attrs.get("Config", {}).get("Labels", {})

        # Check for required labels
        container_type = labels.get(CONTAINER_LABEL_TYPE)
        if not container_type:
            logger.warning(
                f"Container {container.short_id} missing {CONTAINER_LABEL_TYPE} label"
            )
            return None

        # Validate container type
        if container_type not in (CONTAINER_TYPE_AGENT, CONTAINER_TYPE_REPAIR_CYCLE):
            logger.warning(
                f"Container {container.short_id} has invalid type: {container_type}"
            )
            return None

        # Extract required labels
        project_id = labels.get(CONTAINER_LABEL_PROJECT)
        agent_id = labels.get(CONTAINER_LABEL_AGENT)
        task_id = labels.get(CONTAINER_LABEL_TASK_ID)

        if not (project_id and agent_id and task_id):
            logger.warning(
                f"Container {container.short_id} missing required labels. "
                f"project_id={project_id}, agent_id={agent_id}, task_id={task_id}"
            )
            return None

        # Parse created_at
        try:
            created_at = dateparser.isoparse(container.attrs["Created"])
        except Exception as e:
            logger.warning(
                f"Failed to parse created_at for container {container.short_id}: {e}"
            )
            created_at = datetime.now(timezone.utc)

        # Extract optional labels
        work_item_id = labels.get(CONTAINER_LABEL_WORK_ITEM_ID)
        pipeline_run_id = labels.get(CONTAINER_LABEL_PIPELINE_RUN_ID)
        execution_id = labels.get(CONTAINER_LABEL_EXECUTION_ID)

        return ContainerMetadata(
            container_id=container.id,
            container_name=container.name,
            project_id=project_id,
            agent_id=agent_id,
            task_id=task_id,
            created_at=created_at,
            labels=labels,
            work_item_id=work_item_id,
            pipeline_run_id=pipeline_run_id,
            execution_id=execution_id,
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
        # Step 1: Age check
        now = datetime.now(timezone.utc)
        age_seconds = (now - metadata.created_at).total_seconds()
        age_hours = age_seconds / 3600

        if age_hours > self.container_timeout_hours:
            logger.info(
                f"Container {metadata.container_id} is {age_hours:.1f} hours old, "
                f"exceeds {self.container_timeout_hours}h timeout"
            )
            return RecoveryAssessment(
                container_id=metadata.container_id,
                action="kill",
                reason="container_timeout",
                with_monitoring=False,
                execution_id=None,
            )

        # Step 2: Execution validation
        # Check if execution exists in event store by trying to retrieve events for it
        execution_found = False
        if metadata.execution_id:
            try:
                # Try to find events for this execution
                # We're checking if the execution was ever tracked in the system
                execution_found = await self._check_execution_exists(
                    metadata.execution_id
                )
            except StorageError as e:
                logger.warning(
                    f"Failed to check execution state for {metadata.execution_id}: {e}"
                )
                # If we can't check, kill to be safe
                return RecoveryAssessment(
                    container_id=metadata.container_id,
                    action="kill",
                    reason="no_execution_found",
                    with_monitoring=False,
                    execution_id=None,
                )

        if not execution_found:
            logger.warning(
                f"No execution found for container {metadata.container_id} "
                f"with execution_id {metadata.execution_id}"
            )
            return RecoveryAssessment(
                container_id=metadata.container_id,
                action="kill",
                reason="no_execution_found",
                with_monitoring=False,
                execution_id=None,
            )

        # Step 3: Agent matching
        # In the current implementation, we can't fully validate agent matching
        # without access to the work tracker. Accept the container if it has
        # valid execution state.

        # Step 4: Monitoring capability
        with_monitoring = bool(metadata.work_item_id)

        logger.info(
            f"Container {metadata.container_id} assessment: reconnect "
            f"(with_monitoring={with_monitoring})"
        )

        return RecoveryAssessment(
            container_id=metadata.container_id,
            action="reconnect",
            reason="execution_in_progress",
            with_monitoring=with_monitoring,
            execution_id=metadata.execution_id,
        )

    async def execute_recovery_action(self, assessment: RecoveryAssessment) -> bool:
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
        loop = asyncio.get_event_loop()

        def _execute():
            client = self._get_client()

            try:
                container = client.containers.get(assessment.container_id)
            except Exception as e:
                logger.error(
                    f"Failed to get container {assessment.container_id}: {e}"
                )
                return False

            try:
                if assessment.action == "reconnect":
                    logger.info(
                        f"Reconnecting container {assessment.container_id} "
                        f"with execution_id {assessment.execution_id}"
                    )
                    # For reconnect, we just return success since the container is
                    # already running and will be picked up by the monitoring system
                    return True

                elif assessment.action == "kill":
                    logger.info(
                        f"Killing container {assessment.container_id} "
                        f"(reason: {assessment.reason})"
                    )
                    try:
                        # Kill the container with SIGKILL
                        container.kill()
                    except Exception as kill_error:
                        logger.warning(
                            f"Failed to kill container {assessment.container_id}: {kill_error}"
                        )

                    # Remove the container
                    try:
                        container.remove(force=True)
                        logger.info(f"Removed container {assessment.container_id}")
                        return True
                    except Exception as remove_error:
                        logger.error(
                            f"Failed to remove container {assessment.container_id}: {remove_error}",
                            exc_info=True,
                        )
                        return False

            except Exception as e:
                logger.error(
                    f"Unexpected error executing recovery action: {e}", exc_info=True
                )
                return False

        return await loop.run_in_executor(None, _execute)

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
        # Note: This is a stub implementation that processes repair cycle results
        # The actual implementation depends on how repair cycle results are stored
        # For now, we return 0 as no repair cycles are processed
        logger.info("Processing orphaned repair cycle results")
        return 0

    async def _check_execution_exists(self, execution_id: str) -> bool:
        """
        Check if an execution exists in the event store.

        Args:
            execution_id: Execution ID to check

        Returns:
            bool: True if execution exists, False otherwise

        Raises:
            StorageError: If event store lookup fails
        """
        # Query event store for any events related to this execution
        try:
            # Try to retrieve events for this execution
            # This is a simplified check - in production, you'd query the actual
            # event store with proper aggregation
            events = await self.event_store.get_events(
                aggregate_id=execution_id, limit=1
            )
            return len(events) > 0
        except Exception as e:
            logger.warning(f"Failed to check execution {execution_id}: {e}")
            raise StorageError(f"Failed to check execution state: {str(e)}")
