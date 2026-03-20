"""
Adapter Resolver - Configuration-driven adapter instantiation with credential validation.

This module provides:
- AdapterDependencies: Dataclass holding infrastructure dependencies
- AdapterConfigurationError: Aggregated error for missing credentials/invalid config
- AdapterResolver: Per-adapter config entries to concrete adapter instances with validation
"""

import logging
import os
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from codetoreum.infrastructure.adapters.registry_base import (
    AdapterCredentialRequirement,
)
from codetoreum.infrastructure.event_bus import EventBus
from codetoreum.infrastructure.simulation.simulation_config import AdapterSelectionConfig
from codetoreum.ports.output.active_workflow_run_registry import IActiveWorkflowRunRegistry
from codetoreum.ports.output.agent_repository import IAgentRepository
from codetoreum.ports.output.board_service import IBoardService
from codetoreum.ports.output.code_review_service import ICodeReviewService
from codetoreum.ports.output.config_store import IConfigStore
from codetoreum.ports.output.container import IContainer
from codetoreum.ports.output.container_recovery import IAgentContainerRecoveryService
from codetoreum.ports.output.discussion_adapter import IDiscussionAdapter
from codetoreum.ports.output.encryption_service import IEncryptionService
from codetoreum.ports.output.event_emitter import IEventEmitter
from codetoreum.ports.output.event_store import IEventStore
from codetoreum.ports.output.identity_service import IIdentityService
from codetoreum.ports.output.llm_provider import ILLMProvider
from codetoreum.ports.output.message_broker import IMessageBroker
from codetoreum.ports.output.metrics import IMetrics
from codetoreum.ports.output.notifier import INotifier
from codetoreum.ports.output.pipeline_lock_service import IPipelineLockService
from codetoreum.ports.output.pipeline_queue_service import IPipelineQueueService
from codetoreum.ports.output.project_manager_service import IProjectManagerService
from codetoreum.ports.output.repair_cycle_checkpoint_store import IRepairCycleCheckpointStore
from codetoreum.ports.output.repair_cycle_service import IRepairCycle
from codetoreum.ports.output.repository import IRepository
from codetoreum.ports.output.review_cycle_service import IReviewCycle
from codetoreum.ports.output.storage import IStorage
from codetoreum.ports.output.ticket_system import ITicketSystem
from codetoreum.ports.output.version_control_service import IVersionControlService
from codetoreum.ports.output.work_item_branch_tracker import IWorkItemBranchTracker
from codetoreum.ports.output.work_item_service import IWorkItemService
from codetoreum.ports.output.workflow_config_service import IWorkflowConfigService

if TYPE_CHECKING:
    from codetoreum.infrastructure.adapters.factory import AdapterFactory
    from codetoreum.infrastructure.simulation.bootstrap import SimulationAdapters
    from codetoreum.infrastructure.simulation.simulation_config import SimulationConfig
    from codetoreum.infrastructure.simulation.simulation_engine import SimulationEngine

logger = logging.getLogger(__name__)


@dataclass
class AdapterDependencies:
    """Infrastructure dependencies injected into adapters during bootstrap Phase 2.

    These dependencies are available after Phase 1 bootstrap and are passed to adapters
    that require them for cross-adapter communication or infrastructure access.

    Note: Currently only `engine` and `config` are actively used in `resolve_review_cycle()`
    and `resolve_repair_cycle()`. The `event_bus`, `event_emitter`, and `logger` fields
    are available for adapters to use in future versions when their constructors are updated
    to accept these parameters. They provide infrastructure access for cross-cutting concerns
    like event emission and structured logging.
    """

    event_bus: EventBus  # No IEventBus ABC exists yet; using concrete EventBus
    event_emitter: IEventEmitter  # CapturingMockEventEmitter in simulation - Fallback default for resolved adapters
    logger: logging.Logger  # No ILogger ABC implemented yet; using stdlib Logger
    engine: "SimulationEngine"  # For clock injection in time-aware adapters (actively used)
    config: "SimulationConfig"  # Actively used for metadata/config lookups


class AdapterConfigurationError(Exception):
    """
    Raised at startup when real adapter configuration is missing or invalid.

    Aggregates all credential/configuration errors into a single exception
    with a readable message listing each issue.
    """

    def __init__(self, errors: list[str]):
        """
        Initialize the configuration error with aggregated errors.

        Args:
            errors: List of error messages to report
        """
        self.errors = errors
        message = "Adapter configuration errors:\n" + "\n".join(f"  - {e}" for e in errors)
        super().__init__(message)


class AdapterResolver:
    """
    Resolves per-adapter config entries to concrete adapter instances.

    Reads AdapterSelectionConfig, uses AdapterFactory registries, injects
    infrastructure dependencies, validates credentials for real adapters
    before construction, and raises aggregated errors for missing credentials.

    Ensures adapters are constructed in proper dependency order to avoid
    issues with missing dependencies.
    """

    def __init__(
        self,
        adapter_config: AdapterSelectionConfig,
        factory: "AdapterFactory",
        dependencies: AdapterDependencies,
    ) -> None:
        """
        Initialize the adapter resolver.

        Args:
            adapter_config: Per-adapter implementation selector
            factory: Adapter factory with registries
            dependencies: Infrastructure dependencies to inject
        """
        self._config = adapter_config
        self._factory = factory
        self._deps = dependencies
        self._resolved: dict[str, Any] = {}

    def validate_credentials(self) -> None:
        """
        Pre-flight check: aggregate all missing credential errors.

        Validates all 29 adapter slots before constructing any adapter.
        Checks that:
        - Implementation names are registered in factories
        - All required environment variables exist
        - All required config keys exist (accepting falsy values like 0, "", False)

        Raises:
            AdapterConfigurationError: If any validation errors are found
        """
        errors: list[str] = []

        # Get all adapter slot names from AdapterSelectionConfig
        for field_name in AdapterSelectionConfig.__dataclass_fields__:
            impl_name = getattr(self._config, field_name)

            # Get the registry for this adapter slot
            try:
                registry = self._factory.get_registry(field_name)
            except KeyError:
                errors.append(f"{field_name}: no registry found (internal error)")
                continue

            # Check if implementation exists
            if not registry.has_adapter(impl_name):
                errors.append(f"{field_name}: unknown implementation '{impl_name}'")
                continue

            # Get metadata for validation
            try:
                metadata = registry.get_metadata(impl_name)
            except KeyError:
                errors.append(f"{field_name}: no metadata for '{impl_name}'")
                continue

            req = metadata.config_schema
            if not req or not isinstance(req, AdapterCredentialRequirement):
                continue

            # Skip credential validation for simulation-only adapters
            if req.simulation_only:
                continue

            # Check required environment variables
            # Use membership test (not in) instead of truthiness check to accept falsy values
            for env_var in req.env_vars:
                if env_var not in os.environ:
                    errors.append(f"{field_name}/{impl_name}: missing env var '{env_var}'")

            # Check required config keys (accept falsy values like 0, "", False)
            for config_key in req.config_keys:
                if config_key not in self._deps.config.metadata:
                    errors.append(f"{field_name}/{impl_name}: missing config key '{config_key}'")

        if errors:
            raise AdapterConfigurationError(errors)

    # =========================================================================
    # Resolve methods for all 29 adapter slots
    # =========================================================================

    def resolve_event_store(self) -> IEventStore:
        """Resolve event store adapter."""
        return self._factory.create_event_store(adapter_name=self._config.event_store)

    def resolve_config_store(self) -> IConfigStore:
        """Resolve config store adapter."""
        return self._factory.create_config_store(adapter_name=self._config.config_store)

    def resolve_metrics(self) -> IMetrics:
        """Resolve metrics adapter."""
        return self._factory.create_metrics(adapter_name=self._config.metrics)

    def resolve_storage(self) -> IStorage:
        """Resolve storage adapter."""
        return self._factory.create_storage(
            adapter_name=self._config.storage,
            event_emitter=self._resolved["event_emitter"],
            event_bus=self._deps.event_bus,
        )

    def resolve_encryption(self) -> IEncryptionService:
        """Resolve encryption service adapter."""
        return self._factory.create_encryption_service(adapter_name=self._config.encryption)

    def resolve_identity_service(self) -> IIdentityService:
        """Resolve identity service adapter."""
        return self._factory.create_identity_service(adapter_name=self._config.identity_service)

    def resolve_event_emitter(self) -> IEventEmitter:
        """Resolve event emitter adapter."""
        return self._factory.create_event_emitter(adapter_name=self._config.event_emitter)

    def resolve_message_broker(self) -> IMessageBroker:
        """Resolve message broker adapter."""
        return self._factory.create_message_broker(adapter_name=self._config.message_broker)

    def resolve_ticket(self) -> ITicketSystem:
        """Resolve ticket system adapter."""
        return self._factory.create_ticket_system(adapter_name=self._config.ticket)

    def resolve_llm(self) -> ILLMProvider:
        """Resolve LLM provider adapter."""
        return self._factory.create_llm_provider(adapter_name=self._config.llm)

    def resolve_container(self) -> IContainer:
        """Resolve container adapter."""
        return self._factory.create_container(
            adapter_name=self._config.container,
            event_emitter=self._resolved["event_emitter"],
            event_bus=self._deps.event_bus,
        )

    def resolve_board(self) -> IBoardService:
        """Resolve board service adapter."""
        return self._factory.create_board_service(
            adapter_name=self._config.board,
            event_emitter=self._resolved["event_emitter"],
        )

    def resolve_discussion_adapter(self) -> IDiscussionAdapter:
        """Resolve discussion adapter."""
        # MockDiscussionAdapter requires identity_service dependency
        identity_service = self._resolved.get("identity_service")
        return self._factory.create_discussion_adapter(
            adapter_name=self._config.discussion_adapter,
            identity_service=identity_service,
        )

    def resolve_lock_service(self) -> IPipelineLockService:
        """Resolve pipeline lock service adapter."""
        return self._factory.create_pipeline_lock_service(adapter_name=self._config.lock_service)

    def resolve_queue_service(self) -> IPipelineQueueService:
        """Resolve pipeline queue service adapter."""
        return self._factory.create_pipeline_queue_service(
            adapter_name=self._config.queue_service,
            event_emitter=self._resolved["event_emitter"],
            event_bus=self._deps.event_bus,
        )

    def resolve_checkpoint_store(self) -> IRepairCycleCheckpointStore:
        """Resolve repair cycle checkpoint store adapter."""
        return self._factory.create_repair_cycle_checkpoint_store(adapter_name=self._config.checkpoint_store)

    def resolve_agent_repository(self) -> IAgentRepository:
        """Resolve agent repository adapter."""
        return self._factory.create_agent_repository(adapter_name=self._config.agent_repository)

    def resolve_run_registry(self) -> IActiveWorkflowRunRegistry:
        """Resolve active workflow run registry adapter."""
        return self._factory.create_active_workflow_run_registry(adapter_name=self._config.run_registry)

    def resolve_branch_tracker(self) -> IWorkItemBranchTracker:
        """Resolve work item branch tracker adapter."""
        return self._factory.create_work_item_branch_tracker(adapter_name=self._config.branch_tracker)

    def resolve_work_item_service(self) -> IWorkItemService:
        """Resolve work item service adapter."""
        return self._factory.create_work_item_service(adapter_name=self._config.work_item_service)

    def resolve_workflow_config(self) -> IWorkflowConfigService:
        """Resolve workflow config service adapter."""
        return self._factory.create_workflow_config_service(adapter_name=self._config.workflow_config)

    def resolve_notifier(self) -> INotifier:
        """Resolve notifier adapter."""
        return self._factory.create_notifier(adapter_name=self._config.notifier)

    def resolve_version_control(self) -> IVersionControlService:
        """Resolve version control service adapter."""
        return self._factory.create_version_control_service(
            adapter_name=self._config.version_control,
            event_emitter=self._resolved["event_emitter"],
        )

    def resolve_project_manager(self) -> IProjectManagerService:
        """Resolve project manager service adapter."""
        return self._factory.create_project_manager_service(adapter_name=self._config.project_manager)

    def resolve_review_cycle(self) -> IReviewCycle:
        """
        Resolve review cycle adapter.

        Special handling for SimulationEngine-coupled adapters:
        - If mock variant selected: use engine to create time-aware mock
        - If real variant: create directly without engine
        """
        if self._config.review_cycle == "mock":
            # Engine creates time-aware mock with optional LLM adapter
            llm_adapter = self._resolved.get("llm")
            return self._deps.engine.create_review_cycle_adapter(llm_adapter=llm_adapter)
        # Real adapter: bypass engine, use factory directly
        return self._factory.create_review_cycle_service(adapter_name=self._config.review_cycle)

    def resolve_repair_cycle(self) -> IRepairCycle:
        """
        Resolve repair cycle adapter.

        Special handling for SimulationEngine-coupled adapters:
        - If mock variant selected: use engine to create time-aware mock
        - If real variant: create directly without engine
        """
        if self._config.repair_cycle == "mock":
            # Engine creates time-aware mock with optional dependencies
            checkpoint_store = self._resolved.get("checkpoint_store")
            container_adapter = self._resolved.get("container")
            return self._deps.engine.create_repair_cycle_adapter(
                checkpoint_store=checkpoint_store,
                container_adapter=container_adapter,
            )
        # Real adapter: bypass engine, use factory directly
        return self._factory.create_repair_cycle(adapter_name=self._config.repair_cycle)

    def resolve_code_review(self) -> ICodeReviewService:
        """Resolve code review service adapter."""
        return self._factory.create_code_review_service(adapter_name=self._config.code_review)

    def resolve_container_recovery(self) -> IAgentContainerRecoveryService:
        """Resolve container recovery adapter."""
        return self._factory.create_container_recovery(adapter_name=self._config.container_recovery)

    def resolve_repository(self) -> IRepository:
        """Resolve repository adapter.

        Uses the resolved event_emitter (from step 2) instead of the placeholder
        to ensure consistency with SimulationAdapters.event_emitter.
        """
        return self._factory.create_repository(
            adapter_name=self._config.repository,
            event_emitter=self._resolved["event_emitter"],
        )

    def resolve_all(self) -> "SimulationAdapters":
        """
        Resolve all adapters in dependency order.

        Constructs adapters following a partial ordering that respects
        adapter dependencies. Ensures adapters that depend on others
        are constructed after their dependencies.

        Returns:
            SimulationAdapters instance with all 29 adapters fully typed

        Raises:
            AdapterConfigurationError: If credentials are missing/invalid
        """
        # Pre-flight validation before constructing any adapter
        self.validate_credentials()

        # Dependency order (leaf adapters first, composite last):
        # 1. Leaf adapters (no adapter dependencies, excluding those that need event_emitter)
        self._resolved["event_store"] = self.resolve_event_store()
        self._resolved["config_store"] = self.resolve_config_store()
        self._resolved["metrics"] = self.resolve_metrics()
        self._resolved["encryption"] = self.resolve_encryption()
        self._resolved["identity_service"] = self.resolve_identity_service()

        # 2. Event infrastructure (must come before adapters that use event_emitter)
        self._resolved["event_emitter"] = self.resolve_event_emitter()
        self._resolved["message_broker"] = self.resolve_message_broker()

        # 3. Adapters that depend on event_emitter (resolved in step 2)
        self._resolved["storage"] = self.resolve_storage()
        self._resolved["container"] = self.resolve_container()
        self._resolved["version_control"] = self.resolve_version_control()
        self._resolved["board"] = self.resolve_board()
        self._resolved["queue_service"] = self.resolve_queue_service()

        # 4. External system adapters
        self._resolved["ticket"] = self.resolve_ticket()
        self._resolved["llm"] = self.resolve_llm()

        # 5. Coordination adapters
        self._resolved["discussion_adapter"] = self.resolve_discussion_adapter()
        self._resolved["lock_service"] = self.resolve_lock_service()

        # 6. State adapters
        self._resolved["checkpoint_store"] = self.resolve_checkpoint_store()
        self._resolved["agent_repository"] = self.resolve_agent_repository()
        self._resolved["run_registry"] = self.resolve_run_registry()
        self._resolved["branch_tracker"] = self.resolve_branch_tracker()
        self._resolved["work_item_service"] = self.resolve_work_item_service()
        self._resolved["workflow_config"] = self.resolve_workflow_config()
        self._resolved["notifier"] = self.resolve_notifier()

        # 7. Composite adapters (depend on others)
        self._resolved["project_manager"] = self.resolve_project_manager()

        # 8. Repository adapter (depends on event_emitter)
        self._resolved["repository"] = self.resolve_repository()

        # 9. Review and repair cycles depend on previously resolved adapters
        # (review_cycle depends on llm, repair_cycle depends on checkpoint_store and container)
        self._resolved["review_cycle"] = self.resolve_review_cycle()
        self._resolved["repair_cycle"] = self.resolve_repair_cycle()

        # 10. Code review and container recovery adapters
        self._resolved["code_review"] = self.resolve_code_review()
        self._resolved["container_recovery"] = self.resolve_container_recovery()

        logger.info(
            f"Successfully resolved all {len(self._resolved)} adapters",
            extra={"adapter_count": len(self._resolved)},
        )

        # Import here to avoid circular import
        from codetoreum.infrastructure.simulation.bootstrap import SimulationAdapters

        # Construct SimulationAdapters with resolved adapters
        return SimulationAdapters(
            # Output port adapters
            ticket_system=self._resolved["ticket"],
            llm_provider=self._resolved["llm"],
            container=self._resolved["container"],
            repository=self._resolved["repository"],
            event_store=self._resolved["event_store"],
            metrics=self._resolved["metrics"],
            storage=self._resolved["storage"],
            config_store=self._resolved["config_store"],
            notifier=self._resolved["notifier"],
            encryption=self._resolved["encryption"],
            board=self._resolved["board"],
            repair_cycle=self._resolved["repair_cycle"],
            project_manager=self._resolved["project_manager"],
            lock_service=self._resolved["lock_service"],
            workflow_config=self._resolved["workflow_config"],
            queue_service=self._resolved["queue_service"],
            event_emitter=self._resolved["event_emitter"],
            audit_store=self._resolved.get("audit_store"),
            # Additional adapters
            version_control=self._resolved["version_control"],
            message_broker=self._resolved["message_broker"],
            discussion_adapter=self._resolved["discussion_adapter"],
            review_cycle=self._resolved["review_cycle"],
            code_review=self._resolved["code_review"],
            identity_service=self._resolved["identity_service"],
            checkpoint_store=self._resolved["checkpoint_store"],
            # Phase 3 adapters
            agent_repository=self._resolved["agent_repository"],
            run_registry=self._resolved["run_registry"],
            branch_tracker=self._resolved["branch_tracker"],
            work_item_service=self._resolved["work_item_service"],
            # Container recovery
            container_recovery=self._resolved["container_recovery"],
        )
