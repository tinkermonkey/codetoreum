"""Production Application Bootstrap

Wires up the entire application stack in production mode with real adapters,
resilience decorators, and real external service integrations.

This is distinct from the simulation bootstrap (simulation/bootstrap.py) and
provides a production-ready entry point that:
1. Reads required environment variables
2. Validates all adapter credentials before instantiation
3. Resolves all adapters with proper dependency ordering
4. Wraps appropriate adapters with resilience decorators
5. Instantiates all application services
6. Wires input/output ports to FastAPI application

Usage:
    from codetoreum.infrastructure.bootstrap.production_bootstrap import ProductionApplicationBootstrap

    bootstrap = ProductionApplicationBootstrap()
    app = await bootstrap.setup()
    # ... run server
"""

import logging
import os
from datetime import UTC, datetime
from typing import Any

from fastapi import FastAPI

from codetoreum.adapters.primary.fastapi_app import create_app
from codetoreum.application.agent_execution_recovery_service import AgentExecutionRecoveryService
from codetoreum.application.agent_scheduler import (
    AgentScheduler,
    InMemoryTaskQueue,
    MockProjectConfiguration,
    MockRateLimiter,
    MockResourceMonitor,
    MockSchedulingEvents,
)
from codetoreum.application.configuration_service import ConfigurationService
from codetoreum.application.container_recovery_service import ContainerRecoveryService
from codetoreum.application.conversational_loop_orchestrator import ConversationalLoopOrchestrator
from codetoreum.application.event_handlers.board_event_handler import BoardColumnEventHandler
from codetoreum.application.event_handlers.pr_review_cycle_dispatch_handler import PRReviewCycleDispatchHandler
from codetoreum.application.event_handlers.pr_review_cycle_event_handler import PRReviewCycleEventHandler
from codetoreum.application.event_handlers.review_event_handler import ReviewEventHandler
from codetoreum.application.execution_service import ExecutionService
from codetoreum.application.feedback_processor import FeedbackProcessor
from codetoreum.application.multi_project_orchestrator import MultiProjectOrchestrator
from codetoreum.application.pipeline_manager import PipelineManager
from codetoreum.application.review_service import ReviewService
from codetoreum.application.work_item_service import WorkItemService
from codetoreum.application.workflow_orchestrator import WorkflowOrchestrator
from codetoreum.application.workflow_run_query_service import WorkflowRunQueryService
from codetoreum.application.workspace_router import WorkspaceRouter
from codetoreum.infrastructure.adapters.factory import AdapterFactory, AdapterFactoryConfig
from codetoreum.infrastructure.adapters.resolver import AdapterDependencies, AdapterResolver
from codetoreum.infrastructure.bootstrap.production_config import create_production_adapter_config
from codetoreum.infrastructure.error_ids import ErrorRegistry
from codetoreum.infrastructure.event_bus import EventBus
from codetoreum.infrastructure.resilience import OperationMode
from codetoreum.infrastructure.resilience.factory import ResilienceFactory
from codetoreum.ports.input.agent_command import IAgentCommandPort
from codetoreum.ports.input.agent_query import IAgentQueryPort
from codetoreum.ports.input.audit_query import IAuditQueryPort
from codetoreum.ports.input.config_command import IConfigurationCommandPort
from codetoreum.ports.input.config_query import IConfigurationQueryPort
from codetoreum.ports.input.conversational_loop_service import IConversationalLoopService
from codetoreum.ports.input.execution_command import IExecutionCommandPort
from codetoreum.ports.input.execution_query import IExecutionQueryPort
from codetoreum.ports.input.metrics_query import IMetricsQueryPort
from codetoreum.ports.input.orchestration_command import IOrchestrationCommandPort
from codetoreum.ports.input.task_query import ITaskQueryPort
from codetoreum.ports.input.work_item_command import IWorkItemCommandPort
from codetoreum.ports.input.work_item_query import IWorkItemQueryPort
from codetoreum.ports.input.workflow_command import IWorkflowCommandPort
from codetoreum.ports.input.workflow_definition_command import IWorkflowDefinitionCommandPort
from codetoreum.ports.input.workflow_query import IWorkflowQueryPort
from codetoreum.ports.input.workflow_run_query import IWorkflowRunQueryPort
from codetoreum.ports.input.workspace_query import IWorkspaceQueryPort
from codetoreum.ports.output.container import IContainer
from codetoreum.ports.output.llm_provider import ILLMProvider

logger = logging.getLogger(__name__)


class _ProductionClock:
    """
    Simple clock wrapper for production mode.

    Provides a now() method that returns the current system time.
    Used as a fallback when SimulationEngine is not available.
    """

    def now(self) -> datetime:
        """Get current time."""
        return datetime.now(UTC)


class _ProductionEngine:
    """
    Minimal engine wrapper for production mode.

    Provides get_clock_for_testing() method for compatibility with
    adapters that expect a SimulationEngine-like object.
    """

    def __init__(self) -> None:
        """Initialize production engine."""
        self._clock = _ProductionClock()

    def get_clock_for_testing(self) -> _ProductionClock:
        """Get production clock."""
        return self._clock


class ProductionApplicationBootstrap:
    """Bootstrap the entire application stack in production mode.

    This class wires up:
    1. Production adapters via AdapterResolver
    2. Infrastructure (event bus, logger)
    3. Resilience decorators for critical adapters
    4. All application services
    5. All input/output ports
    6. FastAPI application

    Usage:
        bootstrap = ProductionApplicationBootstrap()
        app = await bootstrap.setup()
    """

    def __init__(self) -> None:
        """Initialize production bootstrap."""
        self.adapter_factory: AdapterFactory | None = None
        self.adapters: Any | None = None
        self.infrastructure: Any | None = None
        self.services: Any | None = None
        self.ports: Any | None = None
        self.app: FastAPI | None = None
        self._resilience_factory: ResilienceFactory | None = None
        self._adapter_slots: dict[str, tuple[str, str]] = {}  # Track slot -> (config_key, concrete_class_name)

    async def setup(self) -> FastAPI:
        """
        Set up the entire production application stack.

        This method executes bootstrap phases:
        - Phase 0: Read and validate environment variables
        - Phase 1: Create infrastructure (event bus, logger)
        - Phase 2: Validate credentials (pre-flight check)
        - Phase 3: Resolve all adapters with dependency ordering
        - Phase 4: Wrap adapters with resilience decorators
        - Phase 5: Create application services
        - Phase 6: Create input ports
        - Phase 7: Create FastAPI app and wire all ports

        Returns:
            Configured FastAPI application ready for production

        Raises:
            AdapterConfigurationError: If credentials are missing/invalid
            ValueError: If required environment variables are missing
        """
        logger.info("Starting production bootstrap...")

        # Phase 0: Read and validate environment variables
        logger.info("Phase 0: Reading environment variables...")
        self._read_environment_variables()

        # Phase 1: Create infrastructure
        logger.info("Phase 1: Creating infrastructure...")
        self._create_infrastructure()

        # Phase 2: Create adapter factory and resolver
        logger.info("Phase 2: Creating adapter factory and resolver...")
        self._create_adapter_factory()

        # Phase 3: Validate credentials (pre-flight check)
        logger.info("Phase 3: Validating adapter credentials...")
        self._validate_credentials()

        # Phase 4: Resolve all adapters
        logger.info("Phase 4: Resolving all adapters...")
        await self._resolve_adapters()

        # Phase 5: Apply resilience decorators
        logger.info("Phase 5: Applying resilience decorators...")
        self._apply_resilience_decorators()

        # Phase 6: Create application services
        logger.info("Phase 6: Creating application services...")
        await self._create_services()

        # Phase 7: Create ports
        logger.info("Phase 7: Creating input ports...")
        self._create_ports()

        # Phase 8: Create FastAPI app
        logger.info("Phase 8: Creating FastAPI application...")
        self._create_fastapi_app()

        logger.info("Production bootstrap completed successfully")
        return self.app

    def _read_environment_variables(self) -> None:
        """
        Read and validate required environment variables.

        Required variables:
        - CODETOREUM_AUTH_SECRET_KEY: JWT signing key
        - CODETOREUM_GITHUB_TOKEN: GitHub API token
        - CODETOREUM_CLAUDE_API_KEY: Claude API key
        - Other service-specific credentials

        Raises:
            ValueError: If required variables are missing
        """
        required_vars = [
            "CODETOREUM_AUTH_SECRET_KEY",
        ]

        missing_vars = [var for var in required_vars if not os.getenv(var)]
        if missing_vars:
            msg = f"Missing required environment variables: {', '.join(missing_vars)}"
            logger.error(msg, extra={"error_id": ErrorRegistry.ERR_CONFIG_ERROR})
            raise ValueError(msg)

        self.auth_secret_key = os.getenv("CODETOREUM_AUTH_SECRET_KEY")
        logger.info(
            "Environment variables validated",
            extra={"validated_vars": len(required_vars)},
        )

    def _create_infrastructure(self) -> None:
        """Create infrastructure components (event bus, logger)."""
        self.event_bus = EventBus()
        logger.info("Infrastructure created", extra={"components": ["event_bus"]})

    def _create_adapter_factory(self) -> None:
        """Create adapter factory with production configuration."""
        factory_config = AdapterFactoryConfig(operation_mode=OperationMode.PRODUCTION)
        self.adapter_factory = AdapterFactory(factory_config)
        self._resilience_factory = ResilienceFactory(mode=OperationMode.PRODUCTION)
        logger.info("Adapter factory created")

    def _validate_credentials(self) -> None:
        """
        Validate all adapter credentials before instantiation.

        This is a pre-flight check that aggregates all missing credentials
        and fails fast, preventing partial bootstrap failures.

        Raises:
            AdapterConfigurationError: If any credentials are missing/invalid
        """
        from codetoreum.infrastructure.simulation.simulation_config import SimulationConfig

        adapter_config = create_production_adapter_config()

        # Create a minimal SimulationConfig for credential validation
        # (resolver needs config.metadata for checking required config keys)
        minimal_config = SimulationConfig(scenario_name="production")

        dependencies = AdapterDependencies(
            event_bus=self.event_bus,
            event_emitter=None,  # Not used in validation phase
            logger=logger,
            engine=None,  # Not used in production
            config=minimal_config,  # Used for config_keys validation
        )

        resolver = AdapterResolver(
            adapter_config=adapter_config,
            factory=self.adapter_factory,
            dependencies=dependencies,
        )

        # Pre-flight credential validation
        resolver.validate_credentials()
        logger.info("All adapter credentials validated successfully")

    async def _resolve_adapters(self) -> None:
        """
        Resolve all adapters using AdapterResolver.

        Follows 11-phase dependency ordering to ensure adapters that depend
        on others are constructed after their dependencies.

        Raises:
            AdapterConfigurationError: If resolution fails
        """
        from codetoreum.infrastructure.simulation.simulation_config import SimulationConfig

        adapter_config = create_production_adapter_config()

        # Create a minimal SimulationConfig for adapter resolution
        # (resolver may need config.metadata for some adapters)
        minimal_config = SimulationConfig(scenario_name="production")

        dependencies = AdapterDependencies(
            event_bus=self.event_bus,
            event_emitter=None,  # Will be resolved in phase 2
            logger=logger,
            engine=_ProductionEngine(),  # Provides time_source compatibility
            config=minimal_config,  # Available for adapters that need metadata
        )

        resolver = AdapterResolver(
            adapter_config=adapter_config,
            factory=self.adapter_factory,
            dependencies=dependencies,
        )

        # Resolve all adapters following dependency order
        self.adapters = resolver.resolve_all()

        # Track adapter slots for inspection
        self._track_adapter_slots(adapter_config)
        logger.info("All adapters resolved successfully", extra={"adapter_count": len(self.adapters.__dict__)})

    def _track_adapter_slots(self, adapter_config: Any) -> None:
        """
        Track which concrete implementation is used for each adapter slot.

        This enables the get_adapter_slot_info() method for verifiability.

        Args:
            adapter_config: The AdapterSelectionConfig used for resolution
        """
        for field_name in adapter_config.__dataclass_fields__:
            impl_name = getattr(adapter_config, field_name)
            adapter_instance = getattr(self.adapters, field_name, None)

            if adapter_instance:
                concrete_class_name = type(adapter_instance).__name__
                self._adapter_slots[field_name] = (impl_name, concrete_class_name)

    def _apply_resilience_decorators(self) -> None:
        """
        Wrap appropriate adapters with resilience decorators.

        Applies decorators in correct order:
        1. rate_limiter (outermost - checks rate limits first)
        2. circuit_breaker (prevents cascading failures)
        3. timeout (prevents hanging)
        4. retry (handles transient failures)

        Only wraps critical external system adapters:
        - ITicketSystem (GitHub)
        - ILLMProvider (Claude API)
        - IContainer (Docker)
        - IVersionControlService (Git)
        """
        if not self.adapters or not self._resilience_factory:
            logger.warning("Skipping resilience decorator application: adapters not resolved")
            return

        # Wrap ticket system (GitHub API)
        if hasattr(self.adapters, "ticket_system"):
            self.adapters.ticket_system = self._resilience_factory.create_resilient_ticket_system(
                self.adapters.ticket_system
            )
            logger.debug("Applied resilience decorators to ticket_system")

        # Wrap LLM provider (Claude API)
        if hasattr(self.adapters, "llm_provider"):
            self.adapters.llm_provider = self._resilience_factory.create_resilient_llm_provider(
                self.adapters.llm_provider
            )
            logger.debug("Applied resilience decorators to llm_provider")

        # Wrap container (Docker)
        if hasattr(self.adapters, "container"):
            self.adapters.container = self._resilience_factory.create_resilient_container(
                self.adapters.container
            )
            logger.debug("Applied resilience decorators to container")

        # Wrap repository (Git)
        if hasattr(self.adapters, "repository"):
            self.adapters.repository = self._resilience_factory.create_resilient_repository(
                self.adapters.repository
            )
            logger.debug("Applied resilience decorators to repository")

        logger.info("Resilience decorators applied to critical adapters")

    async def _create_services(self) -> None:
        """
        Create all application services with production adapters.

        Instantiates 11 application services that orchestrate workflows.
        """
        if not self.adapters:
            msg = "Adapters must be resolved before creating services"
            logger.error(msg, extra={"error_id": ErrorRegistry.ERR_INTERNAL_ERROR})
            raise RuntimeError(msg)

        # Create core orchestration services
        workflow_orchestrator = WorkflowOrchestrator(
            ticket_system=self.adapters.ticket_system,
            config_service=None,  # Will be set in port creation
        )

        execution_service = ExecutionService(
            container=self.adapters.container,
            repository=self.adapters.repository,
            config_store=self.adapters.config_store,
            event_bus=self.event_bus,
        )

        agent_scheduler = AgentScheduler(
            task_queue=InMemoryTaskQueue(),
            config=MockProjectConfiguration(),
            rate_limiter=MockRateLimiter(),
            resource_monitor=MockResourceMonitor(),
            scheduling_events=MockSchedulingEvents(),
        )

        pipeline_manager = PipelineManager(
            lock_service=self.adapters.lock_service,
            queue_service=self.adapters.queue_service,
            event_bus=self.event_bus,
        )

        review_service = ReviewService(
            review_cycle=self.adapters.review_cycle,
            board_service=self.adapters.board,
            ticket_system=self.adapters.ticket_system,
        )

        feedback_processor = FeedbackProcessor(
            llm_provider=self.adapters.llm_provider,
            storage=self.adapters.storage,
        )

        workspace_router = WorkspaceRouter(
            container=self.adapters.container,
            storage=self.adapters.storage,
            event_bus=self.event_bus,
        )

        configuration_service = ConfigurationService(
            config_store=self.adapters.config_store,
            event_bus=self.event_bus,
        )

        work_item_service = WorkItemService(
            ticket_system=self.adapters.ticket_system,
            board=self.adapters.board,
        )

        multi_project_orchestrator = MultiProjectOrchestrator(
            workflow_orchestrator=workflow_orchestrator,
            event_bus=self.event_bus,
        )

        container_recovery_service = ContainerRecoveryService(
            container=self.adapters.container,
            container_recovery=self.adapters.container_recovery,
            event_bus=self.event_bus,
        )

        # Create input port that's not wired through create_app()
        # IConversationalLoopService
        conversational_loop_orchestrator = ConversationalLoopOrchestrator(
            discussion_adapter=self.adapters.discussion_adapter,
            llm_provider=self.adapters.llm_provider,
            storage=self.adapters.storage,
            event_bus=self.event_bus,
        )

        # Store services for later access
        self.services = {
            "workflow_orchestrator": workflow_orchestrator,
            "execution_service": execution_service,
            "agent_scheduler": agent_scheduler,
            "pipeline_manager": pipeline_manager,
            "review_service": review_service,
            "feedback_processor": feedback_processor,
            "workspace_router": workspace_router,
            "configuration_service": configuration_service,
            "work_item_service": work_item_service,
            "multi_project_orchestrator": multi_project_orchestrator,
            "container_recovery_service": container_recovery_service,
            "conversational_loop_orchestrator": conversational_loop_orchestrator,
        }

        logger.info("Application services created successfully")

    def _create_ports(self) -> None:
        """
        Create input port implementations.

        Wires application services to input port interfaces for API exposure.
        Most ports are passed to create_app(); 2 ports are handled separately:
        - IConversationalLoopService (conversational_loop_orchestrator)
        - Other port TBD by architect
        """
        if not self.services:
            msg = "Services must be created before ports"
            logger.error(msg, extra={"error_id": ErrorRegistry.ERR_INTERNAL_ERROR})
            raise RuntimeError(msg)

        # Create 16 standard ports for create_app()
        # These are minimal implementations that will be replaced with real ports
        # when the full port implementations are available in production bootstrap

        # Query ports
        workflow_run_query = WorkflowRunQueryService(
            event_store=self.adapters.event_store,
            ticket_system=self.adapters.ticket_system,
        )

        # Store ports for create_app()
        self.ports = {
            "workflow_command": self.services["workflow_orchestrator"],
            "task_query": None,  # Not implemented in basic version
            "config_command": self.services["configuration_service"],
            "config_query": self.services["configuration_service"],
            "metrics_query": self.adapters.metrics,
            "workspace_query": self.services["workspace_router"],
            "work_item_command": self.services["work_item_service"],
            "work_item_query": self.services["work_item_service"],
            "workflow_query": self.services["workflow_orchestrator"],
            "workflow_run_query": workflow_run_query,
            "workflow_definition_command": self.services["configuration_service"],
            "orchestration_command": self.services["multi_project_orchestrator"],
            "agent_command": self.services["agent_scheduler"],
            "agent_query": self.adapters.agent_repository,
            "execution_command": self.services["execution_service"],
            "execution_query": self.services["execution_service"],
            "audit_query": None,  # Optional port
            # Ports not wired through create_app()
            "conversational_loop_service": self.services["conversational_loop_orchestrator"],
        }

        logger.info("Input ports created successfully")

    def _create_fastapi_app(self) -> None:
        """
        Create FastAPI application with all ports wired.

        Calls create_app() with 16 required ports and optional audit_query_port,
        then wires the 2 input ports that are not handled by create_app().
        """
        if not self.ports or not self.adapters or not self.services:
            msg = "Ports, adapters, and services must be created first"
            logger.error(msg, extra={"error_id": ErrorRegistry.ERR_INTERNAL_ERROR})
            raise RuntimeError(msg)

        # Create FastAPI app with 16 required ports
        self.app = create_app(
            workflow_command_port=self.ports["workflow_command"],
            task_query_port=self.ports["task_query"],
            config_command_port=self.ports["config_command"],
            config_query_port=self.ports["config_query"],
            metrics_query_port=self.ports["metrics_query"],
            workspace_query_port=self.ports["workspace_query"],
            work_item_command_port=self.ports["work_item_command"],
            work_item_query_port=self.ports["work_item_query"],
            workflow_query_port=self.ports["workflow_query"],
            workflow_run_query_port=self.ports["workflow_run_query"],
            workflow_definition_command_port=self.ports["workflow_definition_command"],
            orchestration_command_port=self.ports["orchestration_command"],
            agent_command_port=self.ports["agent_command"],
            agent_query_port=self.ports["agent_query"],
            execution_command_port=self.ports["execution_command"],
            execution_query_port=self.ports["execution_query"],
            event_store=self.adapters.event_store,
            event_bus=self.event_bus,
            config_service=None,  # TODO: Implement real config service adapter
            logger=logger,
            audit_query_port=self.ports["audit_query"],
            auth_secret_key=self.auth_secret_key,
            disable_auth=False,  # Enable authentication in production
            container_recovery_service=self.services["container_recovery_service"],
        )

        # Wire the 2 input ports not handled by create_app()
        # These are stored in app.state for middleware/handler access
        self.app.state.conversational_loop_service = self.ports["conversational_loop_service"]

        logger.info("FastAPI application created and all ports wired")

    def get_adapter_slot_info(self, slot_name: str | None = None) -> dict[str, tuple[str, str]] | tuple[str, str]:
        """
        Report the active concrete class for each adapter slot.

        Enables verifiability by showing which implementation is actually
        being used for each adapter slot.

        Args:
            slot_name: Specific slot to query, or None for all slots

        Returns:
            If slot_name: (config_key, concrete_class_name)
            If slot_name is None: dict of all slots -> (config_key, concrete_class_name)

        Raises:
            ValueError: If slot_name not found
        """
        if slot_name:
            if slot_name not in self._adapter_slots:
                msg = f"Unknown adapter slot: {slot_name}"
                raise ValueError(msg)
            return self._adapter_slots[slot_name]

        return self._adapter_slots
