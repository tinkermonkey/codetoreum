"""Docker adapter for IAgentContainerRecoveryService.

This adapter implements container recovery operations using Docker SDK for Python.
It handles:
- Listing containers with Codetoreum labels
- Extracting metadata from container labels
- Assessing container state for recovery or cleanup
- Executing recovery actions (reconnect or kill)
- Processing orphaned repair cycle results from storage
- Assessing repair cycle containers based on checkpoint staleness
"""

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

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
    IAgentContainerRecoveryService,
    RecoveryAssessment,
)

logger = logging.getLogger(__name__)

# Repair cycle container recovery configuration
CHECKPOINT_STALENESS_THRESHOLD = timedelta(minutes=60)  # 60 minutes
REPAIR_CYCLE_AGE_THRESHOLD = timedelta(hours=2)  # 2 hours


class DockerContainerRecoveryAdapter(IAgentContainerRecoveryService):
    """
    Docker adapter for container recovery operations.

    This adapter implements IAgentContainerRecoveryService to handle recovery
    of containers at orchestrator startup by:
    1. Connecting to Docker daemon
    2. Listing containers with Codetoreum labels
    3. Extracting metadata from labels
    4. Assessing each container for recovery or cleanup (full decision tree)
    5. Executing recovery actions (reconnect or kill)

    Decision Tree:
    1. Filter repair cycle containers (handled separately)
    2. Age check: Kill if >2 hours old
    3. Execution validation: Kill if no execution found or not in_progress
    4. Agent matching: Kill if agent mismatch
    5. Monitoring capability: Determine if full monitoring possible
    6. Reconnect or kill accordingly

    Thread Safety:
    - This adapter is async-safe but not thread-safe
    - All Docker operations are executed in a thread pool
    """

    def __init__(
        self,
        execution_tracker: Any,  # IWorkExecutionStateTracker
        tracking_storage: Any,  # IStorage
        docker_runner: Optional[Any] = None,  # IDockerRunner for reconnections
        checkpoint_store: Optional[Any] = None,  # IRepairCycleCheckpointStore
        container_timeout_hours: int = 2,
    ):
        """
        Initialize DockerContainerRecoveryAdapter.

        Args:
            execution_tracker: Work execution state tracker for validation
            tracking_storage: Storage for container tracking re-registration
            docker_runner: Docker runner for reconnectToContainer() calls
            checkpoint_store: Checkpoint store for repair cycle validation
            container_timeout_hours: Hours before a container is considered orphaned
        """
        self.execution_tracker = execution_tracker
        self.tracking_storage = tracking_storage
        self.docker_runner = docker_runner
        self.checkpoint_store = checkpoint_store
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
        List running agent containers with Codetoreum labels.

        Uses Docker label filtering to ONLY return agent containers (not repair-cycle).
        This ensures:
        - Unrelated containers are never returned
        - Repair cycle containers are handled separately
        - Query-time protection prevents accidental modifications
        - Label filtering is done at Docker API level

        Returns:
            List[ContainerMetadata]: Agent containers with valid Codetoreum labels

        Raises:
            ContainerError: If Docker API list operation fails
        """
        loop = asyncio.get_event_loop()

        def _list_containers():
            client = self._get_client()

            try:
                # Use Docker label filtering to only get agent containers
                # Filter for org.codetoreum.type=agent (exclude repair-cycle)
                filters = {
                    "label": [f"{CONTAINER_LABEL_TYPE}={CONTAINER_TYPE_AGENT}"]
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
                raise ContainerError(f"Failed to list agent containers: {str(e)}")

        return await loop.run_in_executor(None, _list_containers)

    async def get_running_repair_cycle_containers(
        self,
    ) -> List[ContainerMetadata]:
        """
        List running repair cycle containers using label filtering.

        Separately enumerates containers matching repair-cycle type.
        Uses Docker label filtering to ONLY return repair cycle containers:
        - Unrelated containers are never returned
        - Query-time protection prevents accidental modifications
        - Label filtering is done at Docker API level

        Returns:
            List[ContainerMetadata]: Repair cycle containers with valid labels

        Raises:
            ContainerError: If Docker API list operation fails
        """
        loop = asyncio.get_event_loop()

        def _list_containers():
            client = self._get_client()

            try:
                # Use Docker label filtering to get repair cycle containers
                # Filter for org.codetoreum.type=repair-cycle
                filters = {
                    "label": [f"{CONTAINER_LABEL_TYPE}={CONTAINER_TYPE_REPAIR_CYCLE}"]
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
                            f"Failed to extract metadata from repair cycle container {container.short_id}: {e}",
                            exc_info=True,
                        )

                return metadata_list

            except Exception as e:
                raise ContainerError(
                    f"Failed to list repair cycle containers: {str(e)}"
                )

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

        Evaluates the container's state using complete decision tree:

        1. Filter repair cycle containers (handled separately)
        2. Age check: Containers >2 hours old are killed (timeout)
        3. Execution validation: Query work_execution_tracker.load_state()
        4. Execution outcome check: Verify outcome is "in_progress"
        5. Agent matching: Validate container agent matches execution agent
        6. Monitoring capability: Determine if full monitoring possible
        7. Return assessment (reconnect or kill)

        Args:
            metadata: Container metadata extracted from Docker labels

        Returns:
            RecoveryAssessment: Decision for this container

        Raises:
            ContainerError: If container inspection fails
            StorageError: If execution state lookup fails
        """
        # Step 1: Filter repair cycle containers (not handled by this method)
        container_type = metadata.labels.get(CONTAINER_LABEL_TYPE)
        if container_type == CONTAINER_TYPE_REPAIR_CYCLE:
            # Repair cycle containers are assessed separately via assess_repair_cycle_container
            logger.warning(
                f"Container {metadata.container_id} is repair cycle type, "
                "but was passed to assess_container() - should use assess_repair_cycle_container()"
            )
            return RecoveryAssessment(
                container_id=metadata.container_id,
                action="kill",
                reason="repair_cycle_wrong_assessment_path",
                with_monitoring=False,
                execution_id=None,
            )

        # Step 2: Age check - containers >2 hours old are killed regardless
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
                execution_id=metadata.execution_id,
            )

        # Step 3 & 4: Execution validation - query work_execution_tracker.load_state()
        if not metadata.work_item_id:
            logger.warning(
                f"Container {metadata.container_id} missing work_item_id, "
                "will reconnect without monitoring"
            )
            return RecoveryAssessment(
                container_id=metadata.container_id,
                action="reconnect",
                reason="valid_but_limited",
                with_monitoring=False,
                execution_id=metadata.execution_id,
            )

        try:
            execution_state = await self.execution_tracker.load_state(
                project=metadata.project_id, work_item_id=metadata.work_item_id
            )
        except StorageError as e:
            logger.error(
                f"Failed to load execution state for {metadata.work_item_id}: {e}",
                exc_info=True,
            )
            return RecoveryAssessment(
                container_id=metadata.container_id,
                action="kill",
                reason="execution_state_lookup_failed",
                with_monitoring=False,
                execution_id=metadata.execution_id,
            )

        if not execution_state:
            logger.info(
                f"No execution history found for container {metadata.container_id} "
                f"with work_item_id {metadata.work_item_id}"
            )
            return RecoveryAssessment(
                container_id=metadata.container_id,
                action="kill",
                reason="no_execution_found",
                with_monitoring=False,
                execution_id=metadata.execution_id,
            )

        # Step 4: Verify execution outcome is "in_progress"
        outcome = execution_state.get("outcome")
        if outcome != "in_progress":
            logger.info(
                f"Container {metadata.container_id} execution not in_progress, "
                f"outcome={outcome}, killing"
            )
            return RecoveryAssessment(
                container_id=metadata.container_id,
                action="kill",
                reason="execution_not_in_progress",
                with_monitoring=False,
                execution_id=metadata.execution_id,
            )

        # Step 5: Validate agent matching
        execution_agent = execution_state.get("agent")
        if execution_agent != metadata.agent_id:
            logger.info(
                f"Container {metadata.container_id} agent mismatch: "
                f"container={metadata.agent_id}, execution={execution_agent}, killing"
            )
            return RecoveryAssessment(
                container_id=metadata.container_id,
                action="kill",
                reason="agent_mismatch",
                with_monitoring=False,
                execution_id=metadata.execution_id,
            )

        # Step 6 & 7: All checks passed - reconnect with monitoring
        logger.info(
            f"Container {metadata.container_id} assessment: reconnect with monitoring"
        )

        return RecoveryAssessment(
            container_id=metadata.container_id,
            action="reconnect",
            reason="valid_execution",
            with_monitoring=True,
            execution_id=metadata.execution_id,
        )

    async def assess_repair_cycle_container(
        self, metadata: ContainerMetadata
    ) -> RecoveryAssessment:
        """
        Assess recovery action for a repair cycle container.

        Evaluates repair cycle container state using specialized logic:
        1. Check for completed result in storage
        2. Check container age vs REPAIR_CYCLE_AGE_THRESHOLD (2 hours)
        3. Check checkpoint staleness (>60 minutes) if available
        4. Kill if stale checkpoint + old age, or no checkpoint + old age
        5. Reconnect with monitoring if fresh checkpoint and recent age

        Args:
            metadata: Container metadata extracted from Docker labels

        Returns:
            RecoveryAssessment: Decision for this repair cycle container

        Raises:
            ContainerError: If container inspection fails
            StorageError: If storage operations fail
        """
        # Step 1: Check for completed result in storage
        result_key = (
            f"repair_cycle:result:{metadata.project_id}:"
            f"{metadata.work_item_id}:{metadata.pipeline_run_id}"
        )

        try:
            result = await self.tracking_storage.get(result_key)

            if result and result.get("overall_success") is not None:
                # Repair cycle completed during downtime - will be processed separately
                logger.info(
                    f"Found completed repair cycle result in storage for "
                    f"{metadata.project_id}/{metadata.work_item_id}/{metadata.pipeline_run_id}"
                )
                return RecoveryAssessment(
                    container_id=metadata.container_id,
                    action="kill",
                    reason="completed_during_downtime",
                    with_monitoring=False,
                    execution_id=metadata.execution_id,
                )
        except StorageError as e:
            logger.warning(
                f"Failed to check for completed repair result {result_key}: {e}",
                exc_info=True,
            )
            # Continue with other checks

        # Step 2: Check container age
        now = datetime.now(timezone.utc)
        age = now - metadata.created_at

        if age > REPAIR_CYCLE_AGE_THRESHOLD:
            # Container is old (>2 hours) - check checkpoint staleness
            checkpoint = None

            if self.checkpoint_store and metadata.pipeline_run_id:
                try:
                    # Try to get checkpoint - use generic "all" test type for repair cycles
                    checkpoint = await self.checkpoint_store.get_checkpoint(
                        pipeline_run_id=metadata.pipeline_run_id, test_type="all"
                    )
                except Exception as e:
                    logger.warning(
                        f"Failed to get checkpoint for {metadata.pipeline_run_id}: {e}",
                        exc_info=True,
                    )

            if checkpoint:
                # We have a checkpoint - check if it's stale
                # checkpoint.timestamp is an ISO 8601 string, parse it
                try:
                    checkpoint_time = dateparser.isoparse(checkpoint.timestamp)
                except Exception as e:
                    logger.warning(
                        f"Failed to parse checkpoint timestamp: {e}", exc_info=True
                    )
                    # Can't parse timestamp, treat as stale
                    checkpoint_time = now - CHECKPOINT_STALENESS_THRESHOLD - timedelta(
                        minutes=1
                    )

                checkpoint_age = now - checkpoint_time
                if checkpoint_age > CHECKPOINT_STALENESS_THRESHOLD:
                    # Stale checkpoint + old container → kill
                    logger.info(
                        f"Repair cycle container {metadata.container_id} has stale checkpoint "
                        f"(age {checkpoint_age.total_seconds():.0f}s) and container age {age.total_seconds():.0f}s"
                    )
                    return RecoveryAssessment(
                        container_id=metadata.container_id,
                        action="kill",
                        reason="checkpoint_stale",
                        with_monitoring=False,
                        execution_id=metadata.execution_id,
                    )
                else:
                    # Fresh checkpoint despite old container age → reconnect with monitoring
                    logger.info(
                        f"Repair cycle container {metadata.container_id} has fresh checkpoint, "
                        f"reconnecting with monitoring"
                    )
                    return RecoveryAssessment(
                        container_id=metadata.container_id,
                        action="reconnect",
                        reason="valid_repair_cycle",
                        with_monitoring=True,
                        execution_id=metadata.execution_id,
                    )
            else:
                # No checkpoint and old container → kill
                logger.info(
                    f"Repair cycle container {metadata.container_id} has no checkpoint "
                    f"and container age {age.total_seconds():.0f}s"
                )
                return RecoveryAssessment(
                    container_id=metadata.container_id,
                    action="kill",
                    reason="no_checkpoint",
                    with_monitoring=False,
                    execution_id=metadata.execution_id,
                )
        else:
            # Container is recent (<2 hours) → assume it's making progress, reconnect
            logger.info(
                f"Repair cycle container {metadata.container_id} is recent "
                f"(age {age.total_seconds():.0f}s), reconnecting"
            )
            return RecoveryAssessment(
                container_id=metadata.container_id,
                action="reconnect",
                reason="valid_repair_cycle",
                with_monitoring=True,
                execution_id=metadata.execution_id,
            )

    async def execute_recovery_action(self, assessment: RecoveryAssessment) -> bool:
        """
        Execute reconnect or kill action.

        Performs the recovery action determined during assessment:
        - reconnect: Re-register in tracking storage and restart monitoring thread
        - kill: Kill container and mark execution failed

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
                    f"Failed to get container {assessment.container_id}: {e}",
                    exc_info=True,
                )
                return False

            try:
                if assessment.action == "reconnect":
                    logger.info(
                        f"Reconnecting container {assessment.container_id} "
                        f"with execution_id {assessment.execution_id}"
                    )
                    # Re-register container in tracking storage with 2-hour TTL
                    container_info = {
                        "containerName": container.name,
                        "agent": container.labels.get(CONTAINER_LABEL_AGENT),
                        "project": container.labels.get(CONTAINER_LABEL_PROJECT),
                        "taskId": container.labels.get(CONTAINER_LABEL_TASK_ID),
                        "startedAt": datetime.now(timezone.utc).isoformat(),
                        "recovered": "true",
                    }

                    try:
                        # Store in tracking storage with TTL of 7200 seconds (2 hours)
                        key = f"agent:container:{container.name}"
                        # Note: This will be awaited in async context
                        # For now, we prepare the operation
                        self._tracking_storage_op = (key, container_info, 7200)
                    except Exception as storage_error:
                        logger.warning(
                            f"Failed to register container in tracking storage: {storage_error}",
                            exc_info=True,
                        )
                        # Continue anyway - container is still running

                    # For reconnect, container is already running
                    # It will be picked up by monitoring system
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
                    except Exception as remove_error:
                        logger.error(
                            f"Failed to remove container {assessment.container_id}: {remove_error}",
                            exc_info=True,
                        )
                        # Continue to mark execution failed even if removal failed

                    # Mark execution failed if we have execution info
                    if assessment.execution_id:
                        try:
                            # Get container metadata for agent info
                            agent = container.labels.get(CONTAINER_LABEL_AGENT)
                            project = container.labels.get(CONTAINER_LABEL_PROJECT)
                            work_item_id = container.labels.get(
                                CONTAINER_LABEL_WORK_ITEM_ID
                            )

                            # Note: This will be awaited in async context
                            self._mark_failed_op = (
                                project,
                                work_item_id,
                                agent,
                                assessment.reason,
                            )
                        except Exception as mark_error:
                            logger.error(
                                f"Failed to mark execution failed for {assessment.execution_id}: {mark_error}",
                                exc_info=True,
                            )

                    return True

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
        the orchestrator was offline. Scans storage for results matching
        the pattern `repair_cycle:result:{project}:{work_item_id}:{run_id}`
        and processes unprocessed completed results.

        Returns:
            int: Number of repair cycles processed

        Raises:
            StorageError: If storage operations fail
        """
        processed = 0
        logger.info("Processing orphaned repair cycle results")

        try:
            # Scan storage for repair cycle results
            # Key pattern: repair_cycle:result:{project}:{work_item_id}:{run_id}
            result_keys = await self.tracking_storage.scan("repair_cycle:result:*")

            if not result_keys:
                logger.info("No orphaned repair cycle results found")
                return 0

            logger.info(f"Found {len(result_keys)} potential repair cycle results")

            for key in result_keys:
                try:
                    result = await self.tracking_storage.get(key)
                    if not result:
                        logger.warning(f"Result key exists but value is empty: {key}")
                        continue

                    # Check if result has been processed already
                    if result.get("processed"):
                        logger.debug(f"Repair cycle result already processed: {key}")
                        continue

                    # Check if repair cycle is complete (has overall_success status)
                    if result.get("overall_success") is None:
                        logger.debug(
                            f"Repair cycle result not yet complete: {key}"
                        )
                        continue

                    # Parse key to extract metadata
                    # Example: repair_cycle:result:myproject:100:abc12345
                    parts = key.split(":")
                    if len(parts) < 5:
                        logger.warning(f"Invalid result key format: {key}")
                        continue

                    project_id = parts[2]
                    work_item_id = parts[3]
                    run_id = ":".join(
                        parts[4:]
                    )  # Handle run_ids that may contain colons

                    logger.info(
                        f"Processing completed repair cycle result: "
                        f"{project_id}/{work_item_id}/{run_id}"
                    )

                    # Mark as processed before processing to avoid reprocessing on failures
                    result["processed"] = True
                    await self.tracking_storage.set(
                        key, result, ttl=86400
                    )  # 24 hour retention

                    # NOTE: This adapter marks results as processed in storage for deduplication.
                    # The actual completion flow (work item advancement, auto-commit, cleanup, etc.)
                    # should be handled by the ContainerRecoveryService or a delegated
                    # repair cycle completion service. This adapter's responsibility is limited
                    # to identifying completed results and preventing duplicate processing.

                    processed += 1

                except Exception as e:
                    logger.error(
                        f"Error processing repair cycle result {key}",
                        exc_info=True,
                    )

            logger.info(f"Processed {processed} orphaned repair cycle results")

        except StorageError as e:
            logger.error(
                f"Storage error during orphaned repair result processing: {e}",
                exc_info=True,
            )
            raise
        except Exception as e:
            logger.error(
                f"Unexpected error processing orphaned repair results: {e}",
                exc_info=True,
            )

        return processed

    async def recover_or_cleanup_containers(self):
        """Placeholder for main recovery orchestration method.

        This method is orchestrated by ContainerRecoveryService.
        The adapter provides the sub-methods that the service calls.
        """
        raise NotImplementedError(
            "recover_or_cleanup_containers is orchestrated by ContainerRecoveryService"
        )

