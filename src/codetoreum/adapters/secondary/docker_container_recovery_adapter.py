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
from datetime import UTC, datetime, timedelta
from types import MappingProxyType
from typing import Any, Protocol

import docker
from dateutil import parser as dateparser

from codetoreum.domain.types import (
    CONTAINER_LABEL_AGENT,
    CONTAINER_LABEL_EXECUTION_ID,
    CONTAINER_LABEL_PROJECT,
    CONTAINER_LABEL_TASK_ID,
    CONTAINER_LABEL_TYPE,
    CONTAINER_LABEL_WORK_ITEM_ID,
    CONTAINER_LABEL_WORKFLOW_RUN_ID,
    CONTAINER_TYPE_AGENT,
    CONTAINER_TYPE_REPAIR_CYCLE,
)
from codetoreum.infrastructure.error_ids import ErrorRegistry
from codetoreum.infrastructure.observability.instrumentation import (
    instrument_async_function,
)
from codetoreum.ports.exceptions import ContainerError, StorageError
from codetoreum.ports.output.container_recovery import (
    ContainerMetadata,
    IAgentContainerRecoveryService,
    RecoveryAssessment,
)
from codetoreum.ports.output.container_recovery_tracking_store import (
    IContainerRecoveryTrackingStore,
)
from codetoreum.ports.output.repair_cycle_checkpoint_store import (
    IRepairCycleCheckpointStore,
)
from codetoreum.ports.output.work_execution_state_tracker import (
    IWorkExecutionStateTracker,
)

# Additional label for tracking containers with timestamp parse failures
CONTAINER_LABEL_TIMESTAMP_FALLBACK = "codetoreum.timestamp_fallback"

# Import Docker SDK exceptions for proper error handling
try:
    from docker.errors import DockerException
    from docker.errors import NotFound as DockerNotFound
except ImportError:
    # Provide fallback classes if docker is not installed
    class DockerNotFound(Exception):  # type: ignore
        """Fallback DockerNotFound when docker SDK is not available."""

    class DockerException(Exception):  # type: ignore
        """Fallback DockerException when docker SDK is not available."""


logger = logging.getLogger(__name__)

# Repair cycle container recovery configuration
CHECKPOINT_STALENESS_THRESHOLD = timedelta(minutes=60)  # 60 minutes
REPAIR_CYCLE_AGE_THRESHOLD = timedelta(hours=2)  # 2 hours


# Protocol types for injected dependencies
class IDockerRunner(Protocol):
    """Protocol for Docker runner operations."""

    async def reconnect_to_container(
        self,
        container_name: str,
        project: str,
        work_item_id: str,
        agent: str,
        task_id: str,
    ) -> None:
        """Reconnect to a running container and restart monitoring."""
        ...


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

    Dual-State Concern:
    - The Redis-backed `tracking_storage` (IContainerRecoveryTrackingStore) is a
      fast recovery-loop hint store, not the source of truth.
    - Canonical execution state lives in the event-sourced ExecutionService.
    - This adapter uses the hint store to make quick reconnect-vs-kill decisions
      at startup without replaying the full event stream.

    Thread Safety:
    - This adapter is async-safe but not thread-safe
    - All Docker operations are executed in a thread pool
    """

    def __init__(
        self,
        execution_tracker: IWorkExecutionStateTracker,
        tracking_storage: IContainerRecoveryTrackingStore,
        docker_runner: IDockerRunner | None = None,
        checkpoint_store: IRepairCycleCheckpointStore | None = None,
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
                self._docker_client = docker.from_env()
            except ImportError as e:
                msg = f"Docker SDK not installed: {e!s}"
                raise ContainerError(msg)
            except DockerException as e:
                msg = f"Failed to connect to Docker daemon: {e!s}"
                raise ContainerError(msg)
            except Exception as e:
                logger.error(
                    f"UNEXPECTED error connecting to Docker: {e}",
                    exc_info=True,
                    extra={
                        "error_id": ErrorRegistry.ERR_CONTAINER_ERROR,
                        "error_type": "unexpected",
                    },
                )
                msg = f"Unexpected error connecting to Docker: {e!s}"
                raise ContainerError(msg)

        return self._docker_client

    @instrument_async_function(
        name="container_recovery.get_running_agent_containers",
        attributes={
            "service": "docker_container_recovery_adapter",
            "operation": "list_agent_containers",
        },
        capture_result=False,
    )
    async def get_running_agent_containers(self) -> list[ContainerMetadata]:
        """
        List running agent containers with Codetoreum labels.

        Creates a span named "container_recovery.get_running_agent_containers" with service
        and operation attributes.

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
                filters = {"label": [f"{CONTAINER_LABEL_TYPE}={CONTAINER_TYPE_AGENT}"]}

                containers = client.containers.list(filters=filters, all=False)
                metadata_list = []

                for container in containers:
                    try:
                        metadata = self._extract_metadata(container)
                        if metadata:
                            metadata_list.append(metadata)
                    except (KeyError, AttributeError, ValueError, TypeError) as e:
                        logger.warning(
                            f"Failed to extract metadata from container {container.short_id}: {e}",
                            exc_info=True,
                            extra={
                                "error_id": ErrorRegistry.ERR_CONTAINER_ERROR,
                                "error_type": "expected",
                            },
                        )
                    except Exception as e:
                        logger.error(
                            f"UNEXPECTED error extracting metadata from container {container.short_id}: {e}",
                            exc_info=True,
                            extra={
                                "error_id": ErrorRegistry.ERR_CONTAINER_ERROR,
                                "error_type": "unexpected",
                            },
                        )

                return metadata_list

            except Exception as e:
                msg = f"Failed to list agent containers: {e!s}"
                raise ContainerError(msg)

        return await loop.run_in_executor(None, _list_containers)

    @instrument_async_function(
        name="container_recovery.get_running_repair_cycle_containers",
        attributes={
            "service": "docker_container_recovery_adapter",
            "operation": "list_repair_cycle_containers",
        },
        capture_result=False,
    )
    async def get_running_repair_cycle_containers(
        self,
    ) -> list[ContainerMetadata]:
        """
        List running repair cycle containers using label filtering.

        Creates a span named "container_recovery.get_running_repair_cycle_containers" with
        service and operation attributes.

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
                filters = {"label": [f"{CONTAINER_LABEL_TYPE}={CONTAINER_TYPE_REPAIR_CYCLE}"]}

                containers = client.containers.list(filters=filters, all=False)
                metadata_list = []

                for container in containers:
                    try:
                        metadata = self._extract_metadata(container)
                        if metadata:
                            metadata_list.append(metadata)
                    except (KeyError, AttributeError, ValueError, TypeError) as e:
                        logger.warning(
                            f"Failed to extract metadata from repair cycle container {container.short_id}: {e}",
                            exc_info=True,
                            extra={
                                "error_id": ErrorRegistry.ERR_CONTAINER_ERROR,
                                "error_type": "expected",
                            },
                        )
                    except Exception as e:
                        logger.error(
                            f"UNEXPECTED error extracting metadata from repair cycle container {container.short_id}: {e}",
                            exc_info=True,
                            extra={
                                "error_id": ErrorRegistry.ERR_CONTAINER_ERROR,
                                "error_type": "unexpected",
                            },
                        )

                return metadata_list

            except Exception as e:
                msg = f"Failed to list repair cycle containers: {e!s}"
                raise ContainerError(msg)

        return await loop.run_in_executor(None, _list_containers)

    def _extract_metadata(self, container) -> ContainerMetadata | None:
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
            logger.warning(f"Container {container.short_id} missing {CONTAINER_LABEL_TYPE} label")
            return None

        # Validate container type
        if container_type not in (CONTAINER_TYPE_AGENT, CONTAINER_TYPE_REPAIR_CYCLE):
            logger.warning(f"Container {container.short_id} has invalid type: {container_type}")
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
        created_at = None
        try:
            created_at = dateparser.isoparse(container.attrs["Created"])
        except (ValueError, TypeError, KeyError) as e:
            logger.error(
                f"Failed to parse created_at timestamp for container {container.short_id}: {e}. "
                f"Using current time as fallback - age-based recovery decisions will be incorrect. "
                f"Raw timestamp value: {container.attrs.get('Created', 'MISSING')}",
                exc_info=True,
                extra={
                    "error_id": ErrorRegistry.ERR_CONTAINER_ERROR,
                    "error_type": "expected",
                    "container_id": container.short_id,
                    "raw_created": container.attrs.get("Created", "MISSING"),
                    "impact": "age_based_recovery_decisions_may_be_incorrect",
                },
            )
        except Exception as e:
            logger.error(
                f"UNEXPECTED error parsing created_at for container {container.short_id}: {e}. "
                f"Using current time as fallback - age-based recovery decisions will be incorrect.",
                exc_info=True,
                extra={
                    "error_id": ErrorRegistry.ERR_CONTAINER_ERROR,
                    "error_type": "unexpected",
                    "container_id": container.short_id,
                    "raw_created": container.attrs.get("Created", "MISSING"),
                    "impact": "age_based_recovery_decisions_may_be_incorrect",
                },
            )
        finally:
            # Use current time as fallback if parsing failed
            if created_at is None:
                created_at = datetime.now(UTC)
                # Log container for operator visibility and priority cleanup
                # Note: Docker doesn't support updating labels on running containers,
                # so operators must manually verify container age if it persists
                logger.warning(
                    f"Container {container.short_id} timestamp parse failed - priority cleanup recommended. "
                    f"Operators should manually verify container age if it persists beyond expected lifetime.",
                    extra={
                        "container_id": container.short_id,
                        "fallback_timestamp_used": True,
                        "mitigation": "priority_cleanup_recommended",
                    },
                )

        # Extract optional labels
        work_item_id = labels.get(CONTAINER_LABEL_WORK_ITEM_ID)
        workflow_run_id = labels.get(CONTAINER_LABEL_WORKFLOW_RUN_ID)
        execution_id = labels.get(CONTAINER_LABEL_EXECUTION_ID)

        return ContainerMetadata(
            container_id=container.id,
            container_name=container.name,
            project_id=project_id,
            agent_id=agent_id,
            task_id=task_id,
            created_at=created_at,
            labels=MappingProxyType(labels),
            work_item_id=work_item_id,
            workflow_run_id=workflow_run_id,
            execution_id=execution_id,
        )

    @instrument_async_function(
        name="container_recovery.assess_container",
        attributes={
            "service": "docker_container_recovery_adapter",
            "operation": "assess_container",
        },
        capture_args=True,
        capture_result=False,
    )
    async def assess_container(self, metadata: ContainerMetadata) -> RecoveryAssessment:
        """
        Assess recovery action for a single container.

        Creates a span named "container_recovery.assess_container" with service and operation
        attributes. Captures container ID and assessment parameters.

        See class docstring for complete decision tree.

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
        now = datetime.now(UTC)
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

        # Step 3 & 4: Execution validation - query work_execution_tracker.load_state()
        if not metadata.work_item_id:
            logger.warning(
                f"Container {metadata.container_id} missing work_item_id, "
                "cannot reconnect without execution tracking, killing"
            )
            return RecoveryAssessment(
                container_id=metadata.container_id,
                action="kill",
                reason="incomplete_metadata",
                with_monitoring=False,
                execution_id=None,
            )

        try:
            execution_state = await self.execution_tracker.load_state(
                project=metadata.project_id, work_item_id=metadata.work_item_id
            )
        except StorageError as e:
            logger.error(
                f"Failed to load execution state for {metadata.work_item_id}: {e}",
                exc_info=True,
                extra={"error_id": ErrorRegistry.ERR_STORAGE_ERROR},
            )
            return RecoveryAssessment(
                container_id=metadata.container_id,
                action="kill",
                reason="execution_state_lookup_failed",
                with_monitoring=False,
                execution_id=None,
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
                execution_id=None,
            )

        # Step 4: Verify execution outcome is "in_progress"
        outcome = execution_state.get("outcome")
        if outcome != "in_progress":
            logger.info(f"Container {metadata.container_id} execution not in_progress, outcome={outcome}, killing")
            return RecoveryAssessment(
                container_id=metadata.container_id,
                action="kill",
                reason="execution_not_in_progress",
                with_monitoring=False,
                execution_id=None,
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
                execution_id=None,
            )

        # Step 6 & 7: All checks passed - reconnect with monitoring
        logger.info(f"Container {metadata.container_id} assessment: reconnect with monitoring")

        return RecoveryAssessment(
            container_id=metadata.container_id,
            action="reconnect",
            reason="valid_execution",
            with_monitoring=True,
            execution_id=metadata.execution_id,
        )

    @instrument_async_function(
        name="container_recovery.assess_repair_cycle_container",
        attributes={
            "service": "docker_container_recovery_adapter",
            "operation": "assess_repair_cycle_container",
        },
        capture_args=True,
        capture_result=False,
    )
    async def assess_repair_cycle_container(self, metadata: ContainerMetadata) -> RecoveryAssessment:
        """
        Assess recovery action for a repair cycle container.

        Creates a span named "container_recovery.assess_repair_cycle_container" with service
        and operation attributes. Captures container ID and assessment parameters.

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
        result_key = f"repair_cycle:result:{metadata.project_id}:{metadata.work_item_id}:{metadata.workflow_run_id}"

        try:
            result = await self.tracking_storage.get(result_key)

            if result and result.get("overall_success") is not None:
                # Repair cycle completed during downtime - will be processed separately
                logger.info(
                    f"Found completed repair cycle result in storage for "
                    f"{metadata.project_id}/{metadata.work_item_id}/{metadata.workflow_run_id}"
                )
                return RecoveryAssessment(
                    container_id=metadata.container_id,
                    action="kill",
                    reason="completed_during_downtime",
                    with_monitoring=False,
                    execution_id=None,
                )
        except StorageError:
            # Storage failures during recovery assessment are serious - they could mean:
            # 1. Completed repair work is invisible and may be lost/redone
            # 2. Container may be killed when it should be kept
            # 3. Storage system is degraded/unavailable
            logger.error(
                f"STORAGE UNAVAILABLE during repair cycle recovery assessment for {result_key}. "
                f"This may result in lost repair work or incorrect recovery decisions. "
                f"Container {metadata.container_id} will be assessed based on age/checkpoint only. "
                f"Operators should verify storage health and check for orphaned repair results.",
                exc_info=True,
                extra={
                    "error_id": ErrorRegistry.ERR_CONTAINER_ERROR,
                    "storage_key": result_key,
                    "container_id": metadata.container_id,
                    "project_id": metadata.project_id,
                    "work_item_id": metadata.work_item_id,
                    "workflow_run_id": metadata.workflow_run_id,
                    "impact": "potential_data_loss_or_incorrect_recovery",
                    "mitigation": "verify_storage_health_and_check_orphaned_results",
                },
            )
            # Continue with age-based and checkpoint-based checks, but log the degraded state
            # Note: In the future, this should emit a metric or alert for operator visibility

        # Step 2: Check container age
        now = datetime.now(UTC)
        age = now - metadata.created_at

        if age > REPAIR_CYCLE_AGE_THRESHOLD:
            # Container is old (>2 hours) - check checkpoint staleness
            checkpoint = None

            if self.checkpoint_store and metadata.workflow_run_id:
                try:
                    # Try to get checkpoint - use generic "all" test type for repair cycles
                    checkpoint = await self.checkpoint_store.get_checkpoint(
                        workflow_run_id=metadata.workflow_run_id, test_type="all"
                    )
                except (KeyError, AttributeError, ValueError) as e:
                    logger.warning(
                        f"Failed to get checkpoint for {metadata.workflow_run_id}: {e}",
                        exc_info=True,
                        extra={
                            "error_id": ErrorRegistry.ERR_CHECKPOINT_ERROR,
                            "error_type": "expected",
                        },
                    )
                except Exception as e:
                    logger.error(
                        f"UNEXPECTED error getting checkpoint for {metadata.workflow_run_id}: {e}",
                        exc_info=True,
                        extra={
                            "error_id": ErrorRegistry.ERR_CHECKPOINT_ERROR,
                            "error_type": "unexpected",
                        },
                    )

            if checkpoint:
                # We have a checkpoint - check if it's stale
                # checkpoint.timestamp is an ISO 8601 string, parse it
                try:
                    checkpoint_time = dateparser.isoparse(checkpoint.timestamp)
                except (ValueError, TypeError, AttributeError) as e:
                    logger.error(
                        f"Failed to parse checkpoint timestamp for repair cycle {metadata.workflow_run_id}: {e}. "
                        f"Treating checkpoint as stale and will kill container. "
                        f"Raw timestamp value: {getattr(checkpoint, 'timestamp', 'MISSING')}",
                        exc_info=True,
                        extra={
                            "error_id": ErrorRegistry.ERR_CHECKPOINT_ERROR,
                            "error_type": "expected",
                            "container_id": metadata.container_id,
                            "workflow_run_id": metadata.workflow_run_id,
                            "raw_checkpoint_timestamp": getattr(checkpoint, "timestamp", "MISSING"),
                            "impact": "checkpoint_treated_as_stale_will_kill_container",
                        },
                    )
                    # Can't parse timestamp, treat as stale
                    checkpoint_time = now - CHECKPOINT_STALENESS_THRESHOLD - timedelta(minutes=1)
                except Exception as e:
                    logger.error(
                        f"UNEXPECTED error parsing checkpoint timestamp for repair cycle {metadata.workflow_run_id}: {e}. "
                        f"Treating checkpoint as stale and will kill container.",
                        exc_info=True,
                        extra={
                            "error_id": ErrorRegistry.ERR_CHECKPOINT_ERROR,
                            "error_type": "unexpected",
                            "container_id": metadata.container_id,
                            "workflow_run_id": metadata.workflow_run_id,
                            "raw_checkpoint_timestamp": getattr(checkpoint, "timestamp", "MISSING"),
                            "impact": "checkpoint_treated_as_stale_will_kill_container",
                        },
                    )
                    # Can't parse timestamp, treat as stale
                    checkpoint_time = now - CHECKPOINT_STALENESS_THRESHOLD - timedelta(minutes=1)

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
                        execution_id=None,
                    )
                # Fresh checkpoint despite old container age → reconnect with monitoring
                logger.info(
                    f"Repair cycle container {metadata.container_id} has fresh checkpoint, reconnecting with monitoring"
                )
                return RecoveryAssessment(
                    container_id=metadata.container_id,
                    action="reconnect",
                    reason="valid_repair_cycle",
                    with_monitoring=True,
                    execution_id=metadata.execution_id,
                )
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
                execution_id=None,
            )
        # Container is recent (<2 hours) → assume it's making progress, reconnect
        logger.info(
            f"Repair cycle container {metadata.container_id} is recent (age {age.total_seconds():.0f}s), reconnecting"
        )
        return RecoveryAssessment(
            container_id=metadata.container_id,
            action="reconnect",
            reason="valid_repair_cycle",
            with_monitoring=True,
            execution_id=metadata.execution_id,
        )

    @instrument_async_function(
        name="container_recovery.execute_recovery_action",
        attributes={
            "service": "docker_container_recovery_adapter",
            "operation": "execute_recovery_action",
        },
        capture_args=True,
        capture_result=False,
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

        def _get_container():
            """Get container synchronously."""
            client = self._get_client()
            try:
                return client.containers.get(assessment.container_id)
            except DockerNotFound as e:
                logger.warning(
                    f"Container {assessment.container_id} not found: {e}",
                    exc_info=True,
                    extra={
                        "error_id": ErrorRegistry.ERR_CONTAINER_NOT_FOUND,
                        "error_type": "expected",
                    },
                )
                return None
            except Exception as e:
                logger.error(
                    f"UNEXPECTED error getting container {assessment.container_id}: {e}",
                    exc_info=True,
                    extra={
                        "error_id": ErrorRegistry.ERR_CONTAINER_ERROR,
                        "error_type": "unexpected",
                    },
                )
                return None

        try:
            # Get container in executor
            container = await loop.run_in_executor(None, _get_container)
            if container is None:
                return False

            if assessment.action == "reconnect":
                logger.info(
                    f"Reconnecting container {assessment.container_id} with execution_id {assessment.execution_id}"
                )

                # Re-register container in tracking storage with 2-hour TTL
                container_info = {
                    "containerName": container.name,
                    "agent": container.labels.get(CONTAINER_LABEL_AGENT),
                    "project": container.labels.get(CONTAINER_LABEL_PROJECT),
                    "taskId": container.labels.get(CONTAINER_LABEL_TASK_ID),
                    "startedAt": datetime.now(UTC).isoformat(),
                    "recovered": "true",
                }

                try:
                    # Store in tracking storage with TTL of 7200 seconds (2 hours)
                    key = f"agent:container:{container.name}"
                    await self.tracking_storage.set(key, container_info, ttl=7200)
                    logger.debug(f"Registered container {container.name} in tracking storage")
                except StorageError as e:
                    logger.warning(
                        f"Failed to register container {container.name} in tracking storage: {e}",
                        exc_info=True,
                    )
                    # Continue anyway - container is still running

                # For reconnect, container is already running
                # It will be picked up by monitoring system
                return True

            if assessment.action == "kill":
                logger.info(f"Killing container {assessment.container_id} (reason: {assessment.reason})")

                # Extract metadata BEFORE killing container
                agent = container.labels.get(CONTAINER_LABEL_AGENT)
                project = container.labels.get(CONTAINER_LABEL_PROJECT)
                work_item_id = container.labels.get(CONTAINER_LABEL_WORK_ITEM_ID)

                def _kill_container():
                    """Kill and remove container synchronously."""
                    try:
                        # Kill the container with SIGKILL
                        container.kill()
                    except DockerNotFound as kill_error:
                        logger.warning(
                            f"Container {assessment.container_id} not found or already killed: {kill_error}",
                            exc_info=True,
                            extra={
                                "error_id": ErrorRegistry.ERR_CONTAINER_NOT_FOUND,
                                "error_type": "expected",
                            },
                        )
                    except Exception as kill_error:
                        logger.error(
                            f"UNEXPECTED error killing container {assessment.container_id}: {kill_error}",
                            exc_info=True,
                            extra={
                                "error_id": ErrorRegistry.ERR_CONTAINER_ERROR,
                                "error_type": "unexpected",
                            },
                        )

                    # Remove the container
                    try:
                        container.remove(force=True)
                        logger.info(f"Removed container {assessment.container_id}")
                    except DockerNotFound as remove_error:
                        logger.warning(
                            f"Container {assessment.container_id} not found or already removed: {remove_error}",
                            exc_info=True,
                            extra={
                                "error_id": ErrorRegistry.ERR_CONTAINER_NOT_FOUND,
                                "error_type": "expected",
                            },
                        )
                    except Exception as remove_error:
                        logger.error(
                            f"UNEXPECTED error removing container {assessment.container_id}: {remove_error}",
                            exc_info=True,
                            extra={
                                "error_id": ErrorRegistry.ERR_CONTAINER_ERROR,
                                "error_type": "unexpected",
                            },
                        )

                # Kill container in executor
                await loop.run_in_executor(None, _kill_container)

                # Mark execution failed if we have execution info
                if assessment.execution_id and self.execution_tracker:
                    try:
                        if project and work_item_id and agent:
                            # Try to mark execution failed if tracker supports it
                            if hasattr(self.execution_tracker, "mark_execution_failed"):
                                await self.execution_tracker.mark_execution_failed(
                                    project=project,
                                    work_item_id=work_item_id,
                                    agent=agent,
                                    reason=assessment.reason,
                                )
                                logger.debug(
                                    f"Marked execution failed for {work_item_id} with reason {assessment.reason}"
                                )
                    except (KeyError, AttributeError, ValueError) as mark_error:
                        logger.warning(
                            f"Failed to mark execution failed for {assessment.execution_id} (expected error): {mark_error}",
                            exc_info=True,
                            extra={
                                "error_id": ErrorRegistry.ERR_CONTAINER_EXECUTION_ERROR,
                                "error_type": "expected",
                            },
                        )
                    except Exception as mark_error:
                        logger.error(
                            f"UNEXPECTED error marking execution failed for {assessment.execution_id}: {mark_error}",
                            exc_info=True,
                            extra={
                                "error_id": ErrorRegistry.ERR_CONTAINER_EXECUTION_ERROR,
                                "error_type": "unexpected",
                            },
                        )
                return True

        except (KeyError, AttributeError) as e:
            logger.error(
                f"UNEXPECTED error with container or metadata during recovery for {assessment.container_id}: {e}",
                exc_info=True,
                extra={"error_id": ErrorRegistry.ERR_INTERNAL_ERROR, "error_type": "unexpected"},
            )
            return False
        except Exception as e:
            logger.error(
                f"UNEXPECTED error executing recovery action for {assessment.container_id}: {e}",
                exc_info=True,
                extra={"error_id": ErrorRegistry.ERR_CONTAINER_ERROR, "error_type": "unexpected"},
            )
            return False

    @instrument_async_function(
        name="container_recovery.process_orphaned_repair_results",
        attributes={
            "service": "docker_container_recovery_adapter",
            "operation": "process_orphaned_repair_results",
        },
        capture_result=False,
    )
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
                        logger.debug(f"Repair cycle result not yet complete: {key}")
                        continue

                    # Parse key to extract metadata
                    # Example: repair_cycle:result:myproject:100:abc12345
                    parts = key.split(":")
                    if len(parts) < 5:
                        logger.warning(f"Invalid result key format: {key}")
                        continue

                    project_id = parts[2]
                    work_item_id = parts[3]
                    run_id = ":".join(parts[4:])  # Handle run_ids that may contain colons

                    logger.info(f"Processing completed repair cycle result: {project_id}/{work_item_id}/{run_id}")

                    # Mark as processed before processing to avoid reprocessing on failures
                    result["processed"] = True
                    await self.tracking_storage.set(key, result, ttl=86400)  # 24 hour retention

                    # NOTE: This adapter marks results as processed in storage for deduplication.
                    # The actual completion flow (work item advancement, auto-commit, cleanup, etc.)
                    # should be handled by the ContainerRecoveryService or a delegated
                    # repair cycle completion service. This adapter's responsibility is limited
                    # to identifying completed results and preventing duplicate processing.

                    processed += 1

                except (KeyError, ValueError, IndexError) as e:
                    logger.warning(
                        f"Invalid repair cycle result format {key}: {e}",
                        exc_info=True,
                        extra={
                            "error_id": ErrorRegistry.ERR_REPAIR_CYCLE_ERROR,
                            "error_type": "expected",
                        },
                    )
                except StorageError as e:
                    logger.warning(
                        f"Storage error processing repair cycle result {key}: {e}",
                        exc_info=True,
                        extra={
                            "error_id": ErrorRegistry.ERR_STORAGE_ERROR,
                            "error_type": "expected",
                        },
                    )
                except Exception as e:
                    logger.error(
                        f"UNEXPECTED error processing repair cycle result {key}: {e}",
                        exc_info=True,
                        extra={
                            "error_id": ErrorRegistry.ERR_REPAIR_CYCLE_ERROR,
                            "error_type": "unexpected",
                        },
                    )
            logger.info(f"Processed {processed} orphaned repair cycle results")

        except StorageError as e:
            logger.error(
                f"Storage error during orphaned repair result processing: {e}",
                exc_info=True,
                extra={"error_id": ErrorRegistry.ERR_STORAGE_ERROR, "error_type": "expected"},
            )
            raise
        except (KeyError, ValueError) as e:
            logger.warning(
                f"Invalid data during orphaned repair result processing: {e}",
                exc_info=True,
                extra={"error_id": ErrorRegistry.ERR_REPAIR_CYCLE_ERROR, "error_type": "expected"},
            )
        except Exception as e:
            logger.error(
                f"UNEXPECTED error processing orphaned repair results: {e}",
                exc_info=True,
                extra={"error_id": ErrorRegistry.ERR_INTERNAL_ERROR, "error_type": "unexpected"},
            )
        return processed

    def close(self) -> None:
        """Close Docker client and clean up all resources."""
        if self._docker_client is not None:
            try:
                # Close the API client's session and adapter connection pools
                if hasattr(self._docker_client, "api"):
                    api = self._docker_client.api
                    # Close HTTP session
                    if hasattr(api, "_session") and api._session:
                        try:
                            api._session.close()
                        except Exception:
                            logger.debug("Error closing Docker API session", exc_info=True)
                    # Close adapters (which hold socket connections)
                    if hasattr(api, "_adapters") and api._adapters:
                        try:
                            for adapter in api._adapters.values():
                                if hasattr(adapter, "close"):
                                    adapter.close()
                        except Exception:
                            logger.debug("Error closing Docker API adapters", exc_info=True)
                    if hasattr(api, "close"):
                        try:
                            api.close()
                        except Exception:
                            logger.debug("Error closing Docker API", exc_info=True)
            except Exception:
                logger.debug("Error cleaning up Docker API client", exc_info=True)

            try:
                self._docker_client.close()
            except Exception:
                logger.debug("Error closing Docker client", exc_info=True)
            finally:
                self._docker_client = None

    async def recover_or_cleanup_containers(self) -> "RecoveryResult":
        """Execute full recovery/cleanup cycle - DEPRECATED.

        This method is kept for interface compatibility but should not be called directly.
        The recovery orchestration logic has been moved to ContainerRecoveryService.

        Use ContainerRecoveryService which coordinates:
        1. Container discovery via get_running_agent_containers()
        2. Container assessment via assess_container()
        3. Recovery action execution via execute_recovery_action()
        4. Result collection and event emission

        Returns:
            RecoveryResult: Placeholder result (not used)

        Raises:
            NotImplementedError: This method should be called through ContainerRecoveryService
        """
        msg = (
            "recover_or_cleanup_containers is orchestrated by ContainerRecoveryService. "
            "Call the service instead of invoking this method directly."
        )
        raise NotImplementedError(msg)
