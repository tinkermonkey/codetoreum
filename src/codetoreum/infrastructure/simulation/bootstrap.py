"""
Simulation Application Bootstrap

Wires up the entire application stack in simulation mode through 6 phases:

**Phase 0**: Create simulation engine (encapsulates clock and timing)
**Phase 1**: Create infrastructure (event bus, logger, error registry) - EARLY for event subscriptions
**Phase 2**: Create adapters (24 mock adapters: ticket system, LLM, container, repository,
           event store, metrics, storage, config, notifier, encryption, board, repair cycle,
           project manager, lock service, workflow config, agent executor, version control,
           message broker, discussion, review cycle, identity service, checkpoint store, queue service, event emitter)
**Phase 3**: Create services (11 application services with their dependencies: workflow orchestrator,
           execution service, agent scheduler, pipeline manager, review service, feedback processor,
           workspace router, configuration service, work item service, multi-project orchestrator,
           container recovery service)
**Phase 4**: Create ports (16 input port implementations)
**Phase 5**: Create FastAPI app (wire all ports to API endpoints, register event handlers)

Note: Infrastructure (event bus) is created before adapters to enable causal linking via
event subscriptions. Adapters can subscribe to domain events during initialization.

This is the foundational component that enables simulation testing. It provides a complete
application bootstrap that wires together all components in the correct order with proper
dependency injection.
"""

import asyncio
import logging
from dataclasses import dataclass
from typing import Any

from fastapi import FastAPI

# FastAPI app factory
from codetoreum.adapters.primary.fastapi_app import create_app

# Mock Port Adapters (these wrap application services to implement port interfaces)
from codetoreum.adapters.primary.input_port_adapters.mock import (
    MockAgentCommandAdapter,
    MockAgentQueryAdapter,
    MockConfigCommandAdapter,
    MockConfigQueryAdapter,
    MockConfigServiceAdapter,
    MockExecutionCommandAdapter,
    MockExecutionQueryAdapter,
    MockLoggerAdapter,
    MockOrchestrationCommandAdapter,
    MockTaskQueryAdapter,
    MockWorkflowCommandAdapter,
    MockWorkflowDefinitionCommandAdapter,
    MockWorkflowQueryAdapter,
    MockWorkItemCommandAdapter,
    MockWorkItemQueryAdapter,
    MockWorkspaceQueryAdapter,
)

# Import simulation ticketing router
from codetoreum.adapters.primary.routers.simulation_ticketing import (
    create_simulation_ticketing_router,
)
from codetoreum.adapters.secondary.in_memory_queue_lock_service import (
    InMemoryLockService,
)
from codetoreum.adapters.secondary.mock_event_emitter import MockEventEmitter

# Adapters
from codetoreum.adapters.testing import (
    CapturingMockEventEmitter,
    ConfigurableIdentityService,
    FakeContainerAdapter,
    InMemoryActiveWorkflowRunRegistry,
    InMemoryAgentRepository,
    InMemoryCheckpointStore,
    InMemoryConfigStore,
    InMemoryEventStore,
    InMemoryMessageBroker,
    InMemoryMetricsAdapter,
    InMemoryQueueService,
    InMemoryRepositoryAdapter,
    InMemoryTicketAdapter,
    InMemoryVersionControlService,
    InMemoryWorkflowConfigService,
    InMemoryWorkItemBranchTracker,
    MockAgentExecutor,
    MockBoardAdapter,
    MockDiscussionAdapter,
    MockLLMAdapter,
    MockNotifierAdapter,
    MockProjectManagerAdapter,
    MockReviewCycleAdapter,
    SimpleEncryptionAdapter,
)
from codetoreum.adapters.testing.execution_service_agent_executor import (
    ExecutionServiceAgentExecutor,
)
from codetoreum.adapters.testing.in_memory_storage_adapter import InMemoryStorageAdapter
from codetoreum.adapters.testing.mock_container_recovery_adapter import (
    MockContainerRecoveryAdapter,
)
from codetoreum.adapters.testing.mock_work_item_service import MockWorkItemService
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
from codetoreum.application.event_handlers.board_event_handler import (
    BoardColumnEventHandler,
)
from codetoreum.application.execution_service import ExecutionService
from codetoreum.application.feedback_processor import FeedbackProcessor
from codetoreum.application.multi_project_orchestrator import MultiProjectOrchestrator
from codetoreum.application.pipeline_manager import PipelineManager
from codetoreum.application.review_service import ReviewService
from codetoreum.application.work_item_service import WorkItemService

# Application Services
from codetoreum.application.workflow_orchestrator import WorkflowOrchestrator, WorkflowState
from codetoreum.application.workflow_run_query_service import WorkflowRunQueryService
from codetoreum.application.workspace_router import WorkspaceRouter

# Domain
from codetoreum.domain.events import BoardReconciled, WorkItemColumnChanged
from codetoreum.domain.value_objects import ProjectConfig
from codetoreum.domain.work_item import WorkItemStatus
from codetoreum.infrastructure.adapters.factory import (
    AdapterFactory,
    AdapterFactoryConfig,
)
from codetoreum.infrastructure.error_ids import ErrorRegistry

# Infrastructure
from codetoreum.infrastructure.event_bus import EventBus
from codetoreum.infrastructure.resilience import OperationMode
from codetoreum.infrastructure.simulation.causal_link_registry import (
    CausalLinkRegistry,
    LinkType,
)

# Mock tracer for trace propagation testing
from codetoreum.infrastructure.simulation.mock_tracer import MockTracer
from codetoreum.infrastructure.simulation.simulation_config import SimulationConfig
from codetoreum.infrastructure.simulation.simulation_engine import SimulationEngine
from codetoreum.ports.input.agent_command import IAgentCommandPort
from codetoreum.ports.input.agent_query import IAgentQueryPort
from codetoreum.ports.input.config_command import IConfigurationCommandPort
from codetoreum.ports.input.config_query import IConfigurationQueryPort
from codetoreum.ports.input.execution_command import IExecutionCommandPort
from codetoreum.ports.input.execution_query import IExecutionQueryPort
from codetoreum.ports.input.metrics_query import IMetricsQueryPort
from codetoreum.ports.input.orchestration_command import IOrchestrationCommandPort
from codetoreum.ports.input.task_query import ITaskQueryPort
from codetoreum.ports.input.work_item_command import IWorkItemCommandPort
from codetoreum.ports.input.work_item_query import IWorkItemQueryPort

# Ports
from codetoreum.ports.input.workflow_command import IWorkflowCommandPort
from codetoreum.ports.input.workflow_definition_command import (
    IWorkflowDefinitionCommandPort,
)
from codetoreum.ports.input.workflow_query import IWorkflowQueryPort
from codetoreum.ports.input.workflow_run_query import IWorkflowRunQueryPort
from codetoreum.ports.input.workspace_query import IWorkspaceQueryPort

logger = logging.getLogger(__name__)


@dataclass
class SimulationAdapters:
    """Container for all simulation adapters."""

    # Output port adapters
    ticket_system: InMemoryTicketAdapter
    llm_provider: MockLLMAdapter
    container: FakeContainerAdapter
    repository: InMemoryRepositoryAdapter
    event_store: InMemoryEventStore
    metrics: InMemoryMetricsAdapter
    storage: InMemoryStorageAdapter
    config_store: InMemoryConfigStore
    notifier: MockNotifierAdapter
    encryption: SimpleEncryptionAdapter
    board: MockBoardAdapter
    repair_cycle: Any  # MockRepairCycleAdapter - lazy imported to avoid circular dependency
    project_manager: MockProjectManagerAdapter  # Multi-project management
    lock_service: InMemoryLockService
    workflow_config: InMemoryWorkflowConfigService
    agent_executor: MockAgentExecutor
    queue_service: InMemoryQueueService  # Pipeline queue service for board automation
    event_emitter: CapturingMockEventEmitter  # For domain event capture

    # Additional adapters (wired in simulation mode)
    version_control: InMemoryVersionControlService  # Version control operations
    message_broker: InMemoryMessageBroker  # Pub/sub message distribution
    discussion_adapter: MockDiscussionAdapter  # Discussion/comment thread management
    review_cycle: MockReviewCycleAdapter  # Code review workflow
    identity_service: ConfigurableIdentityService  # Bot/user identification
    checkpoint_store: InMemoryCheckpointStore  # Repair cycle state persistence

    # Phase 3 adapters (ExecutionService chain)
    agent_repository: InMemoryAgentRepository  # Domain Agent objects for execution chain
    run_registry: InMemoryActiveWorkflowRunRegistry  # Active workflow run tracking
    branch_tracker: InMemoryWorkItemBranchTracker  # Work item → VCS branch tracking
    execution_service_executor: ExecutionServiceAgentExecutor  # Full execution chain
    work_item_service: MockWorkItemService  # Work item lookups for execution chain


@dataclass
class SimulationServices:
    """Container for all application services."""

    workflow_orchestrator: WorkflowOrchestrator
    execution_service: ExecutionService
    agent_scheduler: AgentScheduler
    pipeline_manager: PipelineManager
    review_service: ReviewService
    feedback_processor: FeedbackProcessor
    workspace_router: WorkspaceRouter
    configuration_service: ConfigurationService
    work_item_service: WorkItemService
    multi_project_orchestrator: Any | None = None  # MultiProjectOrchestrator
    container_recovery_service: Any | None = None


@dataclass
class SimulationPorts:
    """Container for all input/output port implementations."""

    # Input ports (command)
    workflow_command: IWorkflowCommandPort
    work_item_command: IWorkItemCommandPort
    workflow_definition_command: IWorkflowDefinitionCommandPort
    orchestration_command: IOrchestrationCommandPort
    agent_command: IAgentCommandPort
    execution_command: IExecutionCommandPort
    config_command: IConfigurationCommandPort

    # Input ports (query)
    task_query: ITaskQueryPort
    work_item_query: IWorkItemQueryPort
    workflow_query: IWorkflowQueryPort
    workflow_run_query: IWorkflowRunQueryPort
    agent_query: IAgentQueryPort
    execution_query: IExecutionQueryPort
    config_query: IConfigurationQueryPort
    metrics_query: IMetricsQueryPort
    workspace_query: IWorkspaceQueryPort


@dataclass
class SimulationInfrastructure:
    """
    Container for infrastructure components.

    Note: Clock is managed by SimulationEngine, not exposed here.
    """

    event_bus: EventBus
    logger: logging.Logger
    mock_tracer: MockTracer
    causal_link_registry: CausalLinkRegistry


class SimulationApplicationBootstrap:
    """
    Bootstrap the entire application stack in simulation mode.

    This class wires up:
    1. All 24 testing and simulation adapters
    2. Infrastructure (event bus, clock, logger)
    3. All application services
    4. All input/output ports
    5. FastAPI application

    Usage:
        bootstrap = SimulationApplicationBootstrap(config)
        await bootstrap.setup()
        app = bootstrap.app
        # ... use app for testing
        await bootstrap.teardown()
    """

    def __init__(self, config: SimulationConfig | None = None):
        """
        Initialize bootstrap with simulation configuration.

        This creates an internal SimulationEngine that manages all timing
        and time-aware components in simulation mode.

        Args:
            config: Simulation configuration (creates default if None)
        """
        self.config = config or SimulationConfig.create_fast_config("default")

        # Components (initialized by setup())
        self.adapters: SimulationAdapters | None = None
        self.infrastructure: SimulationInfrastructure | None = None
        self.services: SimulationServices | None = None
        self.ports: SimulationPorts | None = None
        self.app: FastAPI | None = None

        # Internal state
        self._is_setup = False
        self._adapter_factory: AdapterFactory | None = None
        self._engine: SimulationEngine | None = None
        self._board_event_handler: BoardColumnEventHandler | None = None

    async def setup(self) -> FastAPI:
        """
        Set up the entire application stack.

        This method executes bootstrap phases in order:
        - Phase 0: Create simulation engine (encapsulates clock and timing)
        - Phase 1: Create infrastructure (event bus, logger, error registry) - EARLY for subscriptions
        - Phase 2: Create adapters (24 mock adapters for all output ports)
        - Phase 3: Create services (11 application services with dependencies)
        - Phase 4: Create ports (16 input port implementations)
        - Phase 5: Create FastAPI app (wire all ports to API endpoints, register handlers)

        Infrastructure is created before adapters to enable causal linking via event bus subscriptions.

        Returns:
            Fully configured FastAPI application

        Raises:
            RuntimeError: If already set up or if setup fails
        """
        if self._is_setup:
            message = "Bootstrap already set up"
            raise RuntimeError(message)

        try:
            logger.info("Starting simulation bootstrap...")

            # Phase 0: Create simulation engine (encapsulates clock and timing)
            logger.info("Phase 0: Creating simulation engine...")
            self._engine = SimulationEngine.create(self.config)

            # Phase 1 (early): Create infrastructure including event bus
            # Created before adapters so they can subscribe to domain events
            logger.info("Phase 1: Creating infrastructure...")
            self.infrastructure = self._create_infrastructure()

            # Phase 2: Create adapters (24 total) with event bus subscriptions
            logger.info("Phase 2: Creating 24 adapters...")
            self.adapters = await self._create_adapters()

            # Register causal links between adapters and domain events
            logger.info("Phase 2b: Registering causal links...")
            self._register_causal_links()

            # Phase 3: Create services
            logger.info("Phase 3: Creating services...")
            self.services = await self._create_services()

            # Phase 4: Create ports
            logger.info("Phase 4: Creating ports...")
            self.ports = self._create_ports()

            # Phase 5: Create FastAPI app
            logger.info("Phase 5: Creating FastAPI app...")
            self.app = self._create_fastapi_app()

            # Validate causal link consistency (Phase 5b)
            logger.info("Phase 5b: Validating causal link consistency...")
            self._validate_causal_links()

            self._is_setup = True
            logger.info("Simulation bootstrap completed successfully")

            return self.app

        except Exception as e:
            logger.error(
                f"Bootstrap setup failed: {e}",
                exc_info=True,
                extra={"error_id": ErrorRegistry.ERR_INTERNAL_ERROR},
            )
            raise

    async def teardown(self) -> None:
        """
        Clean up all resources.

        Performs cleanup in reverse order:
        - Stop clock auto-advance (if running)
        - Stop event bus
        - Clear adapters
        - Reset state
        """
        if not self._is_setup:
            return

        try:
            logger.info("Tearing down simulation bootstrap...")

            # Stop simulation engine
            if self._engine:
                await self._engine.stop()

            # Clean up resources
            if self.infrastructure and self.infrastructure.event_bus:
                # Event bus cleanup (no async stop needed for in-memory implementation)
                self.infrastructure.event_bus.reset_statistics()

            # Clear causal link registry
            if self.infrastructure and self.infrastructure.causal_link_registry:
                self.infrastructure.causal_link_registry.clear()

            # Clear references
            self.app = None
            self.ports = None
            self.services = None
            self.infrastructure = None
            self.adapters = None
            self._adapter_factory = None
            self._engine = None

            self._is_setup = False
            logger.info("Simulation bootstrap teardown complete")

        except Exception as e:
            logger.error(
                f"Error during teardown: {e}",
                extra={"error_id": ErrorRegistry.ERR_INTERNAL_ERROR},
                exc_info=True,
            )

    # =========================================================================
    # Phase 2: Create Adapters
    # =========================================================================

    async def _create_adapters(self) -> SimulationAdapters:
        """
        Create all 24 mock adapters in simulation mode.

        5 adapters created via AdapterFactory:
        - ticket_system (in_memory)
        - llm_provider (mock)
        - container (fake)
        - repository (in_memory)
        - event_store (in_memory)

        19 additional adapters created directly:
        - metrics, storage, config_store, notifier, encryption, board, repair_cycle, project_manager
        - lock_service, workflow_config, agent_executor
        - version_control, message_broker, discussion_adapter, review_cycle, identity_service, checkpoint_store
        - queue_service, event_emitter

        The SimulationEngine automatically injects the clock into time-aware
        adapters (repair_cycle), hiding simulation implementation details from
        the adapter constructors.

        Returns:
            SimulationAdapters with all 24 adapters configured in SimulationAdapters dataclass
        """
        if not self._engine:
            message = "SimulationEngine must be created before adapters"
            raise RuntimeError(message)
        if not self.infrastructure:
            message = "Infrastructure (event bus) must be created before adapters"
            raise RuntimeError(message)

        # Create adapter factory in simulation mode with resilience disabled
        factory_config = AdapterFactoryConfig(
            operation_mode=OperationMode.SIMULATION,
            enable_resilience=False,  # ADR-005: No resilience in simulation
        )
        self._adapter_factory = AdapterFactory(factory_config)

        # Create event emitter for domain event capture
        event_emitter = CapturingMockEventEmitter()

        # Get event bus from infrastructure for event subscriptions
        event_bus = self.infrastructure.event_bus

        # Create adapters using factory
        ticket_system = self._adapter_factory.create_ticket_system(adapter_name="in_memory")

        # Pass config and clock to LLM adapter for fidelity-aware timing
        llm_provider = self._adapter_factory.create_llm_provider(
            adapter_name="mock",
            config=self.config,
            clock=self._engine.get_clock_for_testing() if self._engine else None,
        )

        # Pass event_emitter, event_bus, config, and clock to container for event subscription
        # and fidelity-aware timing
        container = self._adapter_factory.create_container(
            adapter_name="fake",
            event_emitter=event_emitter,
            event_bus=event_bus,
            config=self.config,
            clock=self._engine.get_clock_for_testing() if self._engine else None,
        )

        repository = InMemoryRepositoryAdapter(event_emitter=event_emitter)
        event_store = self._adapter_factory.create_event_store(adapter_name="in_memory")

        # Adapters not in factory yet - create directly with event bus for causal linking
        metrics = InMemoryMetricsAdapter()
        storage = InMemoryStorageAdapter(
            event_emitter=event_emitter,
            event_bus=event_bus,  # Subscribe to container execution completion events
            container=container,  # Enable retrieval of actual file content from container
        )
        config_store = InMemoryConfigStore()
        notifier = MockNotifierAdapter()

        # Create queue service with event emitter and event bus for causal linking
        queue_service = InMemoryQueueService(
            event_emitter=event_emitter,
            event_bus=event_bus,  # Subscribe to board position changes
        )

        # Note: SimpleEncryptionAdapter is created directly (not via AdapterFactory)
        # because it's a simple utility service, not a main output port adapter.
        # AdapterFactory is specifically for the 5 main output ports:
        # ticket_system, llm_provider, container, repository, and event_store.
        encryption = SimpleEncryptionAdapter()

        # Create time-aware adapters via engine (clock is injected internally)
        repair_cycle = self._engine.create_repair_cycle_adapter()

        # Create board adapter with event emitter for domain events
        board = MockBoardAdapter(event_emitter=event_emitter)

        # Create project manager adapter
        project_manager = MockProjectManagerAdapter()

        # Create pipeline lock, workflow config, and agent executor for board automation
        lock_service = InMemoryLockService()
        workflow_config = InMemoryWorkflowConfigService()
        agent_executor = MockAgentExecutor(execution_delay_seconds=3.0)

        # Pre-configure default test project for simulation testing
        project_manager.add_project(
            "default_project",
            ProjectConfig(
                repo_url="https://vcs.example.com/org/default.git",
                branch="main",
                enabled=True,
                org="test-org",
            ),
        )

        # Create additional adapters (version control, messaging, discussion, etc.)
        version_control = InMemoryVersionControlService(event_emitter=event_emitter)
        message_broker = InMemoryMessageBroker()
        await message_broker.initialize()  # Initialize message broker
        identity_service = ConfigurableIdentityService()
        identity_service.set_bot_username("codetoreum-bot")
        discussion_adapter = MockDiscussionAdapter(identity_service=identity_service)
        review_cycle = MockReviewCycleAdapter(clock=self._engine.get_clock_for_testing() if self._engine else None)
        checkpoint_store = InMemoryCheckpointStore()

        # Phase 3: Create new adapters for ExecutionService chain
        agent_repository = InMemoryAgentRepository()
        run_registry = InMemoryActiveWorkflowRunRegistry()
        branch_tracker = InMemoryWorkItemBranchTracker()
        work_item_service = MockWorkItemService()

        # ExecutionServiceAgentExecutor is created later in _create_services
        # (needs execution_service and workspace_router which don't exist yet)
        # We use a placeholder here; it's replaced in _create_services.
        execution_service_executor_placeholder = None  # type: ignore[assignment]

        logger.info("Created 24+ simulation adapters with domain event emission")

        return SimulationAdapters(
            ticket_system=ticket_system,
            llm_provider=llm_provider,
            container=container,
            repository=repository,
            event_store=event_store,
            metrics=metrics,
            storage=storage,
            config_store=config_store,
            notifier=notifier,
            encryption=encryption,
            board=board,
            repair_cycle=repair_cycle,
            project_manager=project_manager,
            lock_service=lock_service,
            workflow_config=workflow_config,
            agent_executor=agent_executor,
            queue_service=queue_service,
            event_emitter=event_emitter,
            version_control=version_control,
            message_broker=message_broker,
            discussion_adapter=discussion_adapter,
            review_cycle=review_cycle,
            identity_service=identity_service,
            checkpoint_store=checkpoint_store,
            agent_repository=agent_repository,
            run_registry=run_registry,
            branch_tracker=branch_tracker,
            execution_service_executor=execution_service_executor_placeholder,  # type: ignore[arg-type]
            work_item_service=work_item_service,
        )

    # =========================================================================
    # Phase 2b: Register Causal Links
    # =========================================================================

    def _register_causal_links(self) -> None:
        """
        Register causal dependencies between adapters and domain events.

        This enables runtime enforcement and discoverability of causal links,
        providing visibility into which adapters depend on which domain events.

        Causal links are registered in the CausalLinkRegistry, enabling:
        - Discovery of adapter dependencies (e.g., which adapters depend on container output)
        - Cycle detection to ensure no circular dependencies
        - Audit trail of system integration points
        - Potential future enforcement of causal link consistency

        Key dependencies documented here:
        - InMemoryQueueService subscribes to WorkItemColumnChangedEvent
        - InMemoryStorageAdapter subscribes to ContainerExecutionCompletedEvent
        - RepairCycleAdapter subscribes to WorkItemColumnChangedEvent
        - ReviewCycleAdapter receives events via event emitter (event-driven)
        """
        if not self.infrastructure or not self.adapters:
            logger.warning("Cannot register causal links: infrastructure or adapters not ready")
            return

        registry = self.infrastructure.causal_link_registry

        # Container adapter → Storage adapter (test results flow)
        registry.register_dependency(
            source="FakeContainerAdapter",
            target="InMemoryStorageAdapter",
            link_type=LinkType.TEST_RESULTS,
            metadata={"event_type": "ContainerExecutionCompletedEvent", "purpose": "Store execution artifacts"},
        )

        # Container adapter → Repair cycle adapter (test output feeds repair decisions)
        registry.register_dependency(
            source="FakeContainerAdapter",
            target="MockRepairCycleAdapter",
            link_type=LinkType.TEST_RESULTS,
            metadata={"event_type": "ContainerExecutionCompletedEvent", "purpose": "Drive repair cycle"},
        )

        # LLM adapter → Review cycle adapter (code quality metrics inform review)
        registry.register_dependency(
            source="MockLLMAdapter",
            target="MockReviewCycleAdapter",
            link_type=LinkType.CODE_QUALITY,
            metadata={"purpose": "Code quality assessment drives review cycle"},
        )

        # Event bus → Queue service (board position changes trigger queue updates)
        registry.register_event_subscription(
            publisher="EventBus",
            subscriber="InMemoryQueueService",
            event_type="WorkItemColumnChangedEvent",
            metadata={"purpose": "Track work item position in queue"},
        )

        # Event bus → Repair cycle adapter (column changes trigger repair checks)
        registry.register_event_subscription(
            publisher="EventBus",
            subscriber="MockRepairCycleAdapter",
            event_type="WorkItemColumnChangedEvent",
            metadata={"purpose": "Trigger repair cycle when item moves to repair stage"},
        )

        # Event bus → Storage adapter (container completion stores artifacts)
        registry.register_event_subscription(
            publisher="EventBus",
            subscriber="InMemoryStorageAdapter",
            event_type="ContainerExecutionCompletedEvent",
            metadata={"purpose": "Store container execution artifacts"},
        )

        logger.info(
            f"Registered {len(registry.get_all_links())} causal links and "
            f"{len(registry.get_all_subscriptions())} event subscriptions"
        )

    # =========================================================================
    # Phase 5b: Validate Causal Links
    # =========================================================================

    def _validate_causal_links(self) -> None:
        """
        Validate causal link consistency and log dependency summary.

        Ensures:
        - No cycles in the dependency graph
        - All registered links are acyclic

        Provides visibility into the adapter dependency graph for debugging
        and understanding system integration points.
        """
        if not self.infrastructure:
            logger.warning("Cannot validate causal links: infrastructure not ready")
            return

        registry = self.infrastructure.causal_link_registry

        try:
            registry.validate_consistency()
            logger.info("Causal link validation passed - no cycles detected")

            # Log summary of causal links for debugging
            all_links = registry.get_all_links()
            all_subs = registry.get_all_subscriptions()

            if all_links or all_subs:
                logger.info(
                    f"Causal link summary: {len(all_links)} direct dependencies, {len(all_subs)} event subscriptions"
                )

                # Log direct dependencies
                for link in all_links:
                    logger.debug(f"  {link.source} → {link.target} ({link.link_type.value})")

                # Log event subscriptions
                for sub in all_subs:
                    logger.debug(f"  {sub.publisher} ⟹ {sub.subscriber} ({sub.event_type})")
            else:
                logger.info("No causal links registered (adapters may not use event subscriptions)")

        except Exception as e:
            logger.error(
                f"Causal link validation failed: {e}",
                exc_info=True,
                extra={"error_id": ErrorRegistry.ERR_INTERNAL_ERROR},
            )
            raise

    # =========================================================================
    # Phase 1: Create Infrastructure (Early for Event Bus Subscriptions)
    # =========================================================================

    def _create_infrastructure(self) -> SimulationInfrastructure:
        """
        Create infrastructure components (event bus, logger, causal link registry).

        The SimulationEngine manages the clock internally. The engine is used
        directly to access clock functionality, not through infrastructure.

        The CausalLinkRegistry enables runtime enforcement and discoverability of
        causal dependencies between adapters and domain events.

        Returns:
            SimulationInfrastructure with configured components
        """
        if not self._engine:
            message = "SimulationEngine must be created before infrastructure"
            raise RuntimeError(message)

        # Create event bus
        event_bus = EventBus()

        # Get logger
        app_logger = logging.getLogger("codetoreum")

        # Create mock tracer for trace propagation testing in simulation mode
        mock_tracer = MockTracer(service_name="simulation")

        # Create causal link registry for managing adapter dependencies
        causal_link_registry = CausalLinkRegistry()

        logger.info("Created infrastructure components (including CausalLinkRegistry)")

        # Note: Clock is no longer exposed here - it's managed by SimulationEngine
        # The engine is the single point of control for all timing operations
        return SimulationInfrastructure(
            event_bus=event_bus,
            logger=app_logger,
            mock_tracer=mock_tracer,
            causal_link_registry=causal_link_registry,
        )

    # =========================================================================
    # Phase 3: Create Services
    # =========================================================================

    async def _create_services(self) -> SimulationServices:
        """
        Create all 11 application services with proper dependencies.

        Returns:
            SimulationServices with all services configured
        """
        if not self.adapters or not self.infrastructure:
            message = "Adapters and infrastructure must be created first"
            raise RuntimeError(message)

        # Configuration Service
        configuration_service = ConfigurationService(
            config_store=self.adapters.config_store,
            event_bus=self.infrastructure.event_bus,
            encryption_service=self.adapters.encryption,
        )

        # NOTE: For simulation mode, the mock port adapters (created in Phase 4)
        # provide all functionality needed by FastAPI. Application services are
        # only needed for production mode where they orchestrate between adapters.
        # We create stubs here to satisfy the SimulationServices container structure.

        # Execution Service
        execution_service = ExecutionService(
            llm_provider=self.adapters.llm_provider,
            container=self.adapters.container,
            event_store=self.adapters.event_store,
            storage=self.adapters.storage,
        )

        # Workspace Router
        workspace_router = WorkspaceRouter(
            vcs=self.adapters.version_control,
            container=self.adapters.container,
            event_store=self.adapters.event_store,
        )

        # Phase 3: Create ExecutionServiceAgentExecutor and wire into adapters
        # This requires execution_service + workspace_router which are now available
        execution_service_executor = ExecutionServiceAgentExecutor(
            execution_service=execution_service,
            workspace_router=workspace_router,
            config_store=self.adapters.config_store,
            agent_repository=self.adapters.agent_repository,
            work_item_service=self.adapters.work_item_service,
            run_registry=self.adapters.run_registry,
            branch_tracker=self.adapters.branch_tracker,
            vcs=self.adapters.version_control,
        )
        # Store on adapters so it can be accessed by tests
        self.adapters.execution_service_executor = execution_service_executor

        # Review Service
        review_service = ReviewService(
            event_store=self.adapters.event_store,
        )

        # Feedback Processor
        feedback_processor = FeedbackProcessor()

        # Pipeline Manager
        pipeline_manager = PipelineManager(
            event_store=self.adapters.event_store,
        )

        # Agent Scheduler - create with simulation dependencies
        # Import mock implementations from agent_scheduler module
        task_queue = InMemoryTaskQueue()
        resource_monitor = MockResourceMonitor()
        rate_limiter = MockRateLimiter()
        project_config = MockProjectConfiguration()
        scheduling_events = MockSchedulingEvents()

        agent_scheduler = AgentScheduler(
            task_queue=task_queue,
            resource_monitor=resource_monitor,
            rate_limiter=rate_limiter,
            config=project_config,
            scheduling_events=scheduling_events,
            event_store=self.adapters.event_store,
        )

        # Workflow Orchestrator - create with simulation dependencies
        # Create mock implementations for workflow orchestrator dependencies
        class SimulationWorkflowStateManager:
            """Mock workflow state manager for simulation."""

            def __init__(self):
                self._states = {}

            async def get_workflow_state(self, issue_id: str) -> "WorkflowState":
                if issue_id not in self._states:
                    self._states[issue_id] = WorkflowState(
                        in_progress_tasks={}, current_column=None, current_agent=None
                    )
                return self._states[issue_id]

            async def update_workflow_state(self, issue_id: str, state) -> None:
                self._states[issue_id] = state

        class SimulationDecisionEvents:
            """Mock decision events for simulation."""

            def __init__(self):
                self.routing_decisions = []
                self.progression_decisions = []

            async def emit_routing_decision(self, decision) -> None:
                self.routing_decisions.append(decision)

            async def emit_progression_decision(self, decision) -> None:
                self.progression_decisions.append(decision)

        class SimulationProjectsAPI:
            """Mock projects API for simulation."""

            def __init__(self):
                self.card_movements = []
                self.labels_added = []

            async def move_card_to_column(self, project: str, issue_number: int, column_name: str) -> None:
                self.card_movements.append(
                    {
                        "project": project,
                        "issue_number": issue_number,
                        "column_name": column_name,
                    }
                )

            async def add_label(self, project: str, issue_number: int, label: str) -> None:
                self.labels_added.append({"project": project, "issue_number": issue_number, "label": label})

        workflow_state_manager = SimulationWorkflowStateManager()
        decision_events = SimulationDecisionEvents()
        projects_api = SimulationProjectsAPI()

        workflow_orchestrator = WorkflowOrchestrator(
            task_queue=task_queue,  # Reuse same task queue
            config=project_config,  # Reuse same config
            workflow_state=workflow_state_manager,
            decision_events=decision_events,
            event_store=self.adapters.event_store,
            ticket_system=self.adapters.ticket_system,
            projects_api=projects_api,
        )

        # Work Item Service
        work_item_service = WorkItemService(
            event_store=self.adapters.event_store,
        )

        # Container Recovery Service
        mock_recovery_adapter = MockContainerRecoveryAdapter()
        mock_event_emitter = MockEventEmitter()
        container_recovery_service = ContainerRecoveryService(
            recovery_adapter=mock_recovery_adapter,
            event_emitter=mock_event_emitter,
            container_timeout_hours=2,
        )

        # Multi-Project Orchestrator
        multi_project_orchestrator = MultiProjectOrchestrator(
            project_manager=self.adapters.project_manager,
            workflow_orchestrator=workflow_orchestrator,
            board_service=self.adapters.board,
            event_emitter=mock_event_emitter,
            poll_interval_seconds=30,
        )

        logger.info(
            "Created all application services with simulation dependencies (including container recovery and multi-project orchestrator)"
        )

        return SimulationServices(
            workflow_orchestrator=workflow_orchestrator,
            execution_service=execution_service,
            agent_scheduler=agent_scheduler,
            pipeline_manager=pipeline_manager,
            review_service=review_service,
            feedback_processor=feedback_processor,
            workspace_router=workspace_router,
            configuration_service=configuration_service,
            work_item_service=work_item_service,
            multi_project_orchestrator=multi_project_orchestrator,
            container_recovery_service=container_recovery_service,
        )

    # =========================================================================
    # Phase 4: Create Ports
    # =========================================================================

    def _create_ports(self) -> SimulationPorts:
        """
        Wire services to input/output ports following hexagonal architecture.

        Returns:
            SimulationPorts with all port implementations
        """
        if not self.adapters or not self.services:
            message = "Adapters and services must be created first"
            raise RuntimeError(message)

        # Create mock port adapters, injecting Phase 1 backing stores where available
        # so query adapters read directly from the canonical data source.
        work_item_command = MockWorkItemCommandAdapter()
        work_item_query = MockWorkItemQueryAdapter(
            ticket_adapter=self.adapters.ticket_system,
        )
        agent_command = MockAgentCommandAdapter()
        agent_query = MockAgentQueryAdapter()
        execution_command = MockExecutionCommandAdapter()
        execution_query = MockExecutionQueryAdapter()
        config_query = MockConfigQueryAdapter(
            config_store=self.adapters.config_store,
        )
        # Create metrics query adapter via engine (clock is injected internally)
        if not self._engine:
            message = "SimulationEngine must be created before ports"
            raise RuntimeError(message)
        metrics_query = self._engine.create_metrics_query_adapter(
            metrics_adapter=self.adapters.metrics,
            event_store=self.adapters.event_store,
        )
        workspace_query = MockWorkspaceQueryAdapter()
        workflow_command = MockWorkflowCommandAdapter()
        workflow_query = MockWorkflowQueryAdapter()
        workflow_run_query = WorkflowRunQueryService(
            event_store=self.adapters.event_store,
            ticket_system=self.adapters.ticket_system,
        )
        orchestration_command = MockOrchestrationCommandAdapter()
        workflow_definition_command = MockWorkflowDefinitionCommandAdapter()
        config_command = MockConfigCommandAdapter()
        task_query = MockTaskQueryAdapter()

        logger.info("Created all port implementations")

        return SimulationPorts(
            workflow_command=workflow_command,
            work_item_command=work_item_command,
            workflow_definition_command=workflow_definition_command,
            orchestration_command=orchestration_command,
            agent_command=agent_command,
            execution_command=execution_command,
            config_command=config_command,
            task_query=task_query,
            work_item_query=work_item_query,
            workflow_query=workflow_query,
            workflow_run_query=workflow_run_query,
            agent_query=agent_query,
            execution_query=execution_query,
            config_query=config_query,
            metrics_query=metrics_query,
            workspace_query=workspace_query,
        )

    # =========================================================================
    # Phase 5: Create FastAPI App and Register Event Handlers
    # =========================================================================

    def _create_fastapi_app(self) -> FastAPI:
        """
        Create FastAPI application with all routers wired to ports.

        This is the final step in Phase 5, which:
        1. Creates FastAPI app instance using create_app() factory
        2. Wires all 16 input ports (7 command + 9 query) to API endpoints
        3. Wires infrastructure components (event store, event bus)
        4. Wires application services (configuration service, logger, recovery service)
        5. Configures CORS for localhost development
        6. Disables authentication (ADR-003: simulation mode requirement)
        7. Registers event handlers for cross-cutting concerns

        Returns:
            Configured FastAPI application ready for testing

        Raises:
            RuntimeError: If ports, infrastructure, or services not created first
        """
        if not self.adapters or not self.ports or not self.infrastructure or not self.services:
            message = "Adapters, ports, infrastructure, and services must be created first"
            raise RuntimeError(message)

        # Create adapter for config service (wraps application service for FastAPI interface)
        config_service_interface = MockConfigServiceAdapter(self.services.configuration_service)

        # Create logger adapter for FastAPI
        logger_interface = MockLoggerAdapter()

        # Create FastAPI app using factory (ADR-003: disable auth, allow localhost CORS in simulation)
        # Note: Cannot use ["*"] with credentials, so we explicitly allow common localhost ports
        app = create_app(
            workflow_command_port=self.ports.workflow_command,
            task_query_port=self.ports.task_query,
            config_command_port=self.ports.config_command,
            config_query_port=self.ports.config_query,
            metrics_query_port=self.ports.metrics_query,
            workspace_query_port=self.ports.workspace_query,
            work_item_command_port=self.ports.work_item_command,
            work_item_query_port=self.ports.work_item_query,
            workflow_query_port=self.ports.workflow_query,
            workflow_run_query_port=self.ports.workflow_run_query,
            workflow_definition_command_port=self.ports.workflow_definition_command,
            orchestration_command_port=self.ports.orchestration_command,
            agent_command_port=self.ports.agent_command,
            agent_query_port=self.ports.agent_query,
            execution_command_port=self.ports.execution_command,
            execution_query_port=self.ports.execution_query,
            event_store=self.adapters.event_store,
            event_bus=self.infrastructure.event_bus,
            config_service=config_service_interface,
            logger=logger_interface,
            disable_auth=True,  # ADR-003: Disable authentication in simulation
            cors_origins=["*"],  # Allow all origins in simulation mode (auth is disabled)
            container_recovery_service=self.services.container_recovery_service,
        )

        # Mount simulation-only ticketing router (never in production create_app)
        sim_router = create_simulation_ticketing_router(self.adapters.ticket_system, self.adapters.board)
        app.include_router(sim_router)

        logger.info("Created FastAPI application with all ports wired")

        # Bridge board adapter events to central EventBus
        self._register_board_event_bridge()

        # Register board column event handler for automation (agent execution + auto-progression)
        self._register_board_column_handler()

        # Register repair cycle event handler with event bus
        # This allows the handler to listen for WorkItemColumnChanged events
        # and invoke the repair cycle when items enter the configured repair cycle stage
        self._register_repair_cycle_handler()

        # Wire execution query adapter to agent executor for UX visibility
        # (ports.execution_query is the MockExecutionQueryAdapter created in Phase 4)
        self.adapters.agent_executor.set_execution_query(self.ports.execution_query)

        return app

    def _register_repair_cycle_handler(self) -> None:
        """
        Register repair cycle event handler with the event bus.

        Part of Phase 5: Event handler registration for cross-cutting concerns.

        This handler listens for WorkItemColumnChanged events and invokes
        the repair cycle when items enter the configured repair cycle stage.

        The SimulationEngine injects the clock into the handler, keeping
        simulation details encapsulated and allowing deterministic test
        execution with controlled timing.

        Logs a warning if components are not yet initialized, allowing
        graceful degradation if called before full setup completion.
        """
        if not self.adapters or not self.infrastructure or not self._engine:
            logger.warning("Cannot register repair cycle handler: components not ready")
            return

        handler = self._engine.create_repair_cycle_event_handler(
            repair_cycle=self.adapters.repair_cycle,
            event_bus=self.infrastructure.event_bus,
        )

        self.infrastructure.event_bus.register_handler(handler)
        logger.info("Registered RepairCycleEventHandler with event bus")

    def _register_board_event_bridge(self) -> None:
        """
        Bridge board adapter events to the central EventBus.

        The MockBoardAdapter emits CodetoreumEvent objects (which have `.type`),
        but the EventBus expects DomainEvent objects (which have `.event_type`).
        This bridge translates between the two event hierarchies before publishing.
        """
        if not self.adapters or not self.infrastructure:
            logger.warning("Cannot register board event bridge: components not ready")
            return

        event_bus = self.infrastructure.event_bus
        ticket_adapter = self.adapters.ticket_system

        # Map board columns to work item statuses
        _column_to_status = {
            "Backlog": WorkItemStatus.NEW,
            "Ready": WorkItemStatus.ASSIGNED,
            "In Progress": WorkItemStatus.IN_PROGRESS,
            "Review": WorkItemStatus.UNDER_REVIEW,
            "Done": WorkItemStatus.COMPLETED,
        }

        def _handle_publish_task_error(task: asyncio.Task) -> None:
            """Handle errors from event publish tasks."""
            try:
                task.result()
            except asyncio.CancelledError:
                # Task was cancelled, this is normal during shutdown
                pass
            except Exception as e:
                logger.error(
                    f"Event publish task failed: {e}",
                    exc_info=True,
                    extra={"error_id": ErrorRegistry.ERR_INTERNAL_ERROR},
                )

        def _handle_sync_task_error(task: asyncio.Task) -> None:
            """Handle errors from work item status sync tasks."""
            try:
                task.result()
            except asyncio.CancelledError:
                # Task was cancelled, this is normal during shutdown
                pass
            except Exception as e:
                logger.error(
                    f"Work item status sync task failed: {e}",
                    exc_info=True,
                    extra={"error_id": ErrorRegistry.ERR_INTERNAL_ERROR},
                )

        def board_column_changed_bridge(event):
            """Translate WorkItemColumnChangedEvent (CodetoreumEvent) to WorkItemColumnChanged (DomainEvent).

            Also syncs work item status in the ticket adapter so the UX
            reflects the current column position.
            """
            try:
                loop = asyncio.get_running_loop()
                domain_event = WorkItemColumnChanged(
                    aggregate_id=event.work_item_id,
                    payload={
                        "work_item_id": event.work_item_id,
                        "board_id": event.board_id,
                        "project_id": event.project_id,
                        "from_column": event.from_column,
                        "to_column": event.to_column,
                        "moved_by": event.moved_by,
                    },
                )
                # Create task with error callback to catch publish failures
                task = loop.create_task(event_bus.publish(domain_event))
                task.add_done_callback(_handle_publish_task_error)

                # Sync work item status based on target column (best-effort)
                target_status = _column_to_status.get(event.to_column)
                if target_status is not None:
                    sync_task = loop.create_task(_sync_work_item_status(event.work_item_id, target_status))
                    sync_task.add_done_callback(_handle_sync_task_error)
            except RuntimeError as e:
                logger.error(
                    f"Failed to schedule board column event bridge tasks: {e}",
                    exc_info=True,
                    extra={"error_id": ErrorRegistry.ERR_INTERNAL_ERROR},
                )

        async def _sync_work_item_status(work_item_id: str, target_status: WorkItemStatus) -> None:
            """Best-effort sync of work item status in ticket adapter.

            The domain model validates transitions strictly, so some jumps
            (e.g. NEW -> IN_PROGRESS) will be rejected. We apply intermediate
            steps where needed and silently ignore validation failures.
            """
            try:
                work_item = await ticket_adapter.get_work_item(work_item_id)
                if work_item.status == target_status:
                    return

                # For ASSIGNED: use assign_agent directly since update_status
                # doesn't handle NEW -> ASSIGNED
                if target_status == WorkItemStatus.ASSIGNED:
                    if work_item.status == WorkItemStatus.NEW:
                        work_item.assign_agent("simulation-agent", "Board column sync")
                        work_item.clear_events()
                    return

                # For IN_PROGRESS: must go through ASSIGNED first
                if target_status == WorkItemStatus.IN_PROGRESS:
                    if work_item.status == WorkItemStatus.NEW:
                        work_item.assign_agent("simulation-agent", "Board column sync")
                        work_item.clear_events()
                    if work_item.status == WorkItemStatus.ASSIGNED:
                        await ticket_adapter.update_status(work_item_id, WorkItemStatus.IN_PROGRESS)
                    return

                # For UNDER_REVIEW: must go through ASSIGNED -> IN_PROGRESS first
                if target_status == WorkItemStatus.UNDER_REVIEW:
                    if work_item.status == WorkItemStatus.NEW:
                        work_item.assign_agent("simulation-agent", "Board column sync")
                        work_item.clear_events()
                    if work_item.status == WorkItemStatus.ASSIGNED:
                        await ticket_adapter.update_status(work_item_id, WorkItemStatus.IN_PROGRESS)
                    # Re-read after intermediate transition
                    work_item = await ticket_adapter.get_work_item(work_item_id)
                    if work_item.status == WorkItemStatus.IN_PROGRESS:
                        await ticket_adapter.update_status(work_item_id, WorkItemStatus.UNDER_REVIEW)
                    return

                # For COMPLETED: must go through the full chain
                if target_status == WorkItemStatus.COMPLETED:
                    if work_item.status == WorkItemStatus.NEW:
                        work_item.assign_agent("simulation-agent", "Board column sync")
                        work_item.clear_events()
                    if work_item.status == WorkItemStatus.ASSIGNED:
                        await ticket_adapter.update_status(work_item_id, WorkItemStatus.IN_PROGRESS)
                    work_item = await ticket_adapter.get_work_item(work_item_id)
                    if work_item.status == WorkItemStatus.IN_PROGRESS:
                        await ticket_adapter.update_status(work_item_id, WorkItemStatus.UNDER_REVIEW)
                    work_item = await ticket_adapter.get_work_item(work_item_id)
                    if work_item.status == WorkItemStatus.UNDER_REVIEW:
                        await ticket_adapter.update_status(work_item_id, WorkItemStatus.COMPLETED)
                    return

                # Fallback: try direct update
                await ticket_adapter.update_status(work_item_id, target_status)

            except Exception as e:
                logger.warning(
                    f"Best-effort status sync failed for {work_item_id} -> {target_status.value}: {e}",
                    exc_info=True,
                    extra={"error_id": ErrorRegistry.ERR_INTERNAL_ERROR},
                )

        def board_reconciled_bridge(event):
            """Translate BoardReconciledEvent (CodetoreumEvent) to BoardReconciled (DomainEvent)."""
            try:
                loop = asyncio.get_running_loop()
                domain_event = BoardReconciled(
                    aggregate_id=event.board_id,
                    payload={
                        "board_id": event.board_id,
                        "project_id": event.project_id,
                        "columns_added": list(event.columns_added) if hasattr(event, "columns_added") else [],
                        "columns_removed": list(event.columns_removed) if hasattr(event, "columns_removed") else [],
                        "orphaned_items": [],
                    },
                )
                # Create task with error callback to catch publish failures
                task = loop.create_task(event_bus.publish(domain_event))
                task.add_done_callback(_handle_publish_task_error)
            except RuntimeError as e:
                logger.error(
                    f"Failed to schedule board reconciliation event bridge task: {e}",
                    exc_info=True,
                    extra={"error_id": ErrorRegistry.ERR_INTERNAL_ERROR},
                )

        self.adapters.board.on("workitem.column_changed", board_column_changed_bridge)
        self.adapters.board.on("board.reconciled", board_reconciled_bridge)
        logger.info("Registered board event bridge to central EventBus")

    def _register_board_column_handler(self) -> None:
        """Register BoardColumnEventHandler for automated column processing.

        Creates the handler with its 5 dependencies and wires the agent
        executor's completion callback to the handler's handle_agent_completion
        method. This closes the loop: column change -> agent execution ->
        completion callback -> auto-progress to next column.
        """
        if not self.adapters or not self.infrastructure:
            logger.warning("Cannot register board column handler: components not ready")
            return

        handler = BoardColumnEventHandler(
            board_service=self.adapters.board,
            lock_service=self.adapters.lock_service,
            workflow_config=self.adapters.workflow_config,
            event_store=self.adapters.event_store,
            agent_executor=self.adapters.agent_executor,
            event_bus=self.infrastructure.event_bus,
            run_registry=self.adapters.run_registry,
            event_emitter=self.adapters.event_emitter,
        )

        # Wire completion callback: executor -> handler.handle_agent_completion
        self.adapters.agent_executor.set_completion_handler(handler.handle_agent_completion, "board-1")

        # Store reference to handler for executor swapping
        self._board_event_handler = handler

        self.infrastructure.event_bus.register_handler(handler)
        logger.info("Registered BoardColumnEventHandler with event bus")

    # =========================================================================
    # Public API
    # =========================================================================

    @property
    def engine(self) -> SimulationEngine | None:
        """
        Get the SimulationEngine instance.

        The engine manages all simulation timing and coordinates time-aware
        components. Use this to advance time or access clock operations.

        Returns:
            SimulationEngine instance (None if not yet set up)
        """
        return self._engine

    @property
    def causal_link_registry(self) -> CausalLinkRegistry | None:
        """
        Get the CausalLinkRegistry instance.

        The registry manages causal dependencies between adapters and domain events,
        providing:
        - Discovery of adapter integration points
        - Cycle detection for dependency consistency
        - Audit trail of system wiring
        - Runtime enforcement of causal constraints

        Returns:
            CausalLinkRegistry instance (None if not yet set up)
        """
        return self.infrastructure.causal_link_registry if self.infrastructure else None

    def enable_execution_service_executor(self) -> "ExecutionServiceAgentExecutor":
        """Swap the board handler's agent executor to use ExecutionServiceAgentExecutor.

        This enables the full LLM → Container → VCS execution chain for Phase 3
        testing. The MockAgentExecutor is replaced with ExecutionServiceAgentExecutor
        on the BoardColumnEventHandler, and the completion callback is wired so
        agent completions auto-progress items to the next column.

        Returns:
            The ExecutionServiceAgentExecutor for further configuration.

        Raises:
            RuntimeError: If bootstrap is not set up or handler not registered.
        """
        if not self._is_setup or self.adapters is None:
            msg = "Bootstrap must be set up before enabling execution service executor"
            raise RuntimeError(msg)
        if self._board_event_handler is None:
            msg = "BoardColumnEventHandler not registered yet"
            raise RuntimeError(msg)

        executor = self.adapters.execution_service_executor
        # Wire completion callback so auto-progression works with the new executor
        executor.set_completion_handler(self._board_event_handler.handle_agent_completion, "board-1")
        self._swap_executor(executor)
        return executor

    def _swap_executor(self, executor: Any) -> None:
        """Replace the agent executor on the BoardColumnEventHandler.

        Args:
            executor: New agent executor to use
        """
        if self._board_event_handler is not None:
            self._board_event_handler.agent_executor = executor
