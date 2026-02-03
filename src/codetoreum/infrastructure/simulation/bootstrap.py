"""
Simulation Application Bootstrap

Wires up the entire application stack in simulation mode including:
- All 9 mock adapters
- All 8 application services
- All input/output ports
- FastAPI application

This is the foundational component that enables simulation testing.
"""

import logging
from dataclasses import dataclass
from typing import Any, Dict, Optional

from fastapi import FastAPI

# Adapters
from codetoreum.adapters.testing import (
    InMemoryEventStore,
    InMemoryRepositoryAdapter,
    InMemoryTicketAdapter,
    FakeContainerAdapter,
    MockLLMAdapter,
    InMemoryMetricsAdapter,
    MockNotifierAdapter,
    SimpleEncryptionAdapter,
)
# Lazy import to avoid circular dependency
from codetoreum.adapters.testing.mock_container_recovery_adapter import (
    MockContainerRecoveryAdapter,
)
from codetoreum.adapters.testing.in_memory_config_store import InMemoryConfigStore
from codetoreum.adapters.testing.in_memory_storage_adapter import InMemoryStorageAdapter
from codetoreum.adapters.secondary.mock_event_emitter import MockEventEmitter

# Application Services
from codetoreum.application.workflow_orchestrator import WorkflowOrchestrator
from codetoreum.application.execution_service import ExecutionService
from codetoreum.application.agent_scheduler import AgentScheduler
from codetoreum.application.pipeline_manager import PipelineManager
from codetoreum.application.review_service import ReviewService
from codetoreum.application.feedback_processor import FeedbackProcessor
from codetoreum.application.workspace_router import WorkspaceRouter
from codetoreum.application.configuration_service import ConfigurationService
from codetoreum.application.work_item_service import WorkItemService
from codetoreum.application.container_recovery_service import ContainerRecoveryService

# Infrastructure
from codetoreum.infrastructure.event_bus import EventBus
from codetoreum.infrastructure.simulation.simulation_clock import SimulationClock
from codetoreum.infrastructure.simulation.simulation_config import SimulationConfig
from codetoreum.infrastructure.adapters.factory import (
    AdapterFactory,
    AdapterFactoryConfig,
)
from codetoreum.infrastructure.resilience import OperationMode

# Ports
from codetoreum.ports.input.workflow_command import IWorkflowCommandPort
from codetoreum.ports.input.task_query import ITaskQueryPort
from codetoreum.ports.input.config_command import IConfigurationCommandPort
from codetoreum.ports.input.config_query import IConfigurationQueryPort
from codetoreum.ports.input.metrics_query import IMetricsQueryPort
from codetoreum.ports.input.workspace_query import IWorkspaceQueryPort
from codetoreum.ports.input.work_item_command import IWorkItemCommandPort
from codetoreum.ports.input.work_item_query import IWorkItemQueryPort
from codetoreum.ports.input.workflow_query import IWorkflowQueryPort
from codetoreum.ports.input.workflow_run_query import IWorkflowRunQueryPort
from codetoreum.ports.input.workflow_definition_command import IWorkflowDefinitionCommandPort
from codetoreum.ports.input.orchestration_command import IOrchestrationCommandPort
from codetoreum.ports.input.agent_command import IAgentCommandPort
from codetoreum.ports.input.agent_query import IAgentQueryPort
from codetoreum.ports.input.execution_command import IExecutionCommandPort
from codetoreum.ports.input.execution_query import IExecutionQueryPort

# FastAPI app factory
from codetoreum.adapters.primary.fastapi_app import create_app

# Mock Port Adapters (these wrap application services to implement port interfaces)
from codetoreum.adapters.primary.input_port_adapters.mock import (
    MockWorkItemCommandAdapter,
    MockWorkItemQueryAdapter,
    MockAgentCommandAdapter,
    MockAgentQueryAdapter,
    MockExecutionCommandAdapter,
    MockExecutionQueryAdapter,
    MockConfigQueryAdapter,
    MockMetricsQueryAdapter,
    MockWorkspaceQueryAdapter,
    MockWorkflowCommandAdapter,
    MockWorkflowQueryAdapter,
    MockWorkflowRunQueryAdapter,
    MockOrchestrationCommandAdapter,
    MockWorkflowDefinitionCommandAdapter,
    MockConfigCommandAdapter,
    MockTaskQueryAdapter,
    MockConfigServiceAdapter,
    MockLoggerAdapter,
)

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
    repair_cycle: Any  # MockRepairCycleAdapter - lazy imported to avoid circular dependency


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
    container_recovery_service: Optional[Any] = None


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
    """Container for infrastructure components."""

    event_bus: EventBus
    clock: SimulationClock
    logger: logging.Logger


class SimulationApplicationBootstrap:
    """
    Bootstrap the entire application stack in simulation mode.

    This class wires up:
    1. All 9 mock adapters (via AdapterFactory)
    2. Infrastructure (event bus, clock, logger)
    3. All 8 application services
    4. All input/output ports
    5. FastAPI application

    Usage:
        bootstrap = SimulationApplicationBootstrap(config)
        await bootstrap.setup()
        app = bootstrap.app
        # ... use app for testing
        await bootstrap.teardown()
    """

    def __init__(self, config: Optional[SimulationConfig] = None):
        """
        Initialize bootstrap with simulation configuration.

        Args:
            config: Simulation configuration (creates default if None)
        """
        self.config = config or SimulationConfig.create_fast_config("default")

        # Components (initialized by setup())
        self.adapters: Optional[SimulationAdapters] = None
        self.infrastructure: Optional[SimulationInfrastructure] = None
        self.services: Optional[SimulationServices] = None
        self.ports: Optional[SimulationPorts] = None
        self.app: Optional[FastAPI] = None

        # Internal state
        self._is_setup = False
        self._adapter_factory: Optional[AdapterFactory] = None
        self._clock: Optional[SimulationClock] = None

    async def setup(self) -> FastAPI:
        """
        Set up the entire application stack.

        This method executes all 5 bootstrap phases in order:
        1. Create clock (early, shared by adapters and infrastructure)
        2. Create adapters
        3. Create infrastructure
        4. Create services
        5. Create ports
        6. Create FastAPI app

        Returns:
            Fully configured FastAPI application

        Raises:
            RuntimeError: If already set up or if setup fails
        """
        if self._is_setup:
            raise RuntimeError("Bootstrap already set up")

        try:
            logger.info("Starting simulation bootstrap...")

            # Phase 0: Create clock (early, shared by adapters and infrastructure)
            logger.info("Phase 0: Creating simulation clock...")
            self._clock = self._create_clock()

            # Phase 1: Create adapters
            logger.info("Phase 1: Creating adapters...")
            self.adapters = await self._create_adapters()

            # Phase 2: Create infrastructure
            logger.info("Phase 2: Creating infrastructure...")
            self.infrastructure = self._create_infrastructure()

            # Phase 3: Create services
            logger.info("Phase 3: Creating services...")
            self.services = await self._create_services()

            # Phase 4: Create ports
            logger.info("Phase 4: Creating ports...")
            self.ports = self._create_ports()

            # Phase 5: Create FastAPI app
            logger.info("Phase 5: Creating FastAPI app...")
            self.app = self._create_fastapi_app()

            self._is_setup = True
            logger.info("Simulation bootstrap completed successfully")

            return self.app

        except Exception as e:
            logger.error(f"Bootstrap setup failed: {e}",
                extra={"error_id": ErrorRegistry.ERR_INTERNAL_ERROR}
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

            # Stop clock auto-advance if it's running
            if self.infrastructure and self.infrastructure.clock:
                await self.infrastructure.clock.stop_auto_advance()

            # Clean up resources
            if self.infrastructure and self.infrastructure.event_bus:
                # Event bus cleanup (no async stop needed for in-memory implementation)
                self.infrastructure.event_bus.reset_statistics()

            # Clear references
            self.app = None
            self.ports = None
            self.services = None
            self.infrastructure = None
            self.adapters = None
            self._adapter_factory = None
            self._clock = None

            self._is_setup = False
            logger.info("Simulation bootstrap teardown complete")

        except Exception as e:
            logger.error(f"Error during teardown: {e}",
                extra={"error_id": ErrorRegistry.ERR_INTERNAL_ERROR}
            )

    # =========================================================================
    # Phase 0: Create Clock (early, shared by adapters and infrastructure)
    # =========================================================================

    def _create_clock(self) -> SimulationClock:
        """
        Create simulation clock early so it can be shared by adapters and infrastructure.

        Returns:
            SimulationClock with configured speed and start time
        """
        clock = SimulationClock(
            speed_multiplier=self.config.time.speed_multiplier,
            auto_advance=self.config.time.auto_advance,
        )

        # Set start time if configured
        if self.config.time.start_time:
            clock.start_at(self.config.time.start_time)

        return clock

    # =========================================================================
    # Phase 1: Create Adapters
    # =========================================================================

    async def _create_adapters(self) -> SimulationAdapters:
        """
        Create all 10 mock adapters using AdapterFactory in simulation mode.

        Returns:
            SimulationAdapters with all adapters configured
        """
        # Lazy import to avoid circular dependency with SimulationClock
        from codetoreum.adapters.testing.mock_repair_cycle_adapter import MockRepairCycleAdapter

        # Create adapter factory in simulation mode with resilience disabled
        factory_config = AdapterFactoryConfig(
            operation_mode=OperationMode.SIMULATION,
            enable_resilience=False,  # ADR-005: No resilience in simulation
        )
        self._adapter_factory = AdapterFactory(factory_config)

        # Create adapters using factory
        ticket_system = self._adapter_factory.create_ticket_system(adapter_name="in_memory")
        llm_provider = self._adapter_factory.create_llm_provider(adapter_name="mock")
        container = self._adapter_factory.create_container(adapter_name="fake")
        repository = self._adapter_factory.create_repository(adapter_name="in_memory")
        event_store = self._adapter_factory.create_event_store(adapter_name="in_memory")

        # Adapters not in factory yet - create directly
        metrics = InMemoryMetricsAdapter()
        storage = InMemoryStorageAdapter()
        config_store = InMemoryConfigStore()
        notifier = MockNotifierAdapter()

        # Note: SimpleEncryptionAdapter is created directly (not via AdapterFactory)
        # because it's a simple utility service, not a main output port adapter.
        # AdapterFactory is specifically for the 5 main output ports:
        # ticket_system, llm_provider, container, repository, and event_store.
        encryption = SimpleEncryptionAdapter()

        # Create repair cycle adapter with the shared simulation clock
        if not self._clock:
            raise RuntimeError("Clock must be created before adapters")
        repair_cycle = MockRepairCycleAdapter(clock=self._clock)

        logger.info("Created 10 simulation adapters")

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
            repair_cycle=repair_cycle,
        )

    # =========================================================================
    # Phase 2: Create Infrastructure
    # =========================================================================

    def _create_infrastructure(self) -> SimulationInfrastructure:
        """
        Create infrastructure components (event bus, clock, logger).

        Uses the clock created early in Phase 0 to ensure it's shared with adapters.

        Returns:
            SimulationInfrastructure with configured components
        """
        if not self._clock:
            raise RuntimeError("Clock must be created before infrastructure")

        # Create event bus
        event_bus = EventBus()

        # Get logger
        app_logger = logging.getLogger("codetoreum")

        logger.info("Created infrastructure components")

        return SimulationInfrastructure(
            event_bus=event_bus,
            clock=self._clock,
            logger=app_logger,
        )

    # =========================================================================
    # Phase 3: Create Services
    # =========================================================================

    async def _create_services(self) -> SimulationServices:
        """
        Create all 8 application services with proper dependencies.

        Returns:
            SimulationServices with all services configured
        """
        if not self.adapters or not self.infrastructure:
            raise RuntimeError("Adapters and infrastructure must be created first")

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
            repository=self.adapters.repository,
            container=self.adapters.container,
            event_store=self.adapters.event_store,
        )

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
        from codetoreum.application.agent_scheduler import (
            InMemoryTaskQueue,
            MockResourceMonitor,
            MockRateLimiter,
            MockProjectConfiguration,
            MockSchedulingEvents,
        )

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

            async def get_workflow_state(self, issue_id: str):
                from codetoreum.application.workflow_orchestrator import WorkflowState
                from codetoreum.infrastructure.error_ids import ErrorRegistry

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

            async def move_card_to_column(
                self, project: str, issue_number: int, column_name: str
            ) -> None:
                self.card_movements.append(
                    {
                        "project": project,
                        "issue_number": issue_number,
                        "column_name": column_name,
                    }
                )

            async def add_label(
                self, project: str, issue_number: int, label: str
            ) -> None:
                self.labels_added.append(
                    {"project": project, "issue_number": issue_number, "label": label}
                )

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

        logger.info("Created all application services with simulation dependencies (including container recovery)")

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
        if not self.services:
            raise RuntimeError("Services must be created first")

        # Create all mock port adapters (standalone implementations for simulation)
        work_item_command = MockWorkItemCommandAdapter()
        work_item_query = MockWorkItemQueryAdapter()
        agent_command = MockAgentCommandAdapter()
        agent_query = MockAgentQueryAdapter()
        execution_command = MockExecutionCommandAdapter()
        execution_query = MockExecutionQueryAdapter()
        config_query = MockConfigQueryAdapter()
        metrics_query = MockMetricsQueryAdapter(
            metrics_adapter=self.adapters.metrics,
            event_store=self.adapters.event_store,
            clock=self.infrastructure.clock,
        )
        workspace_query = MockWorkspaceQueryAdapter()
        workflow_command = MockWorkflowCommandAdapter()
        workflow_query = MockWorkflowQueryAdapter()
        workflow_run_query = MockWorkflowRunQueryAdapter()
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
    # Phase 5: Create FastAPI App
    # =========================================================================

    # =========================================================================
    # Helper Methods
    # =========================================================================

    def _register_repair_cycle_handler(self) -> None:
        """
        Register repair cycle event handler with the event bus.

        This handler listens for WorkItemColumnChanged events and invokes
        the repair cycle when items enter the Testing column.
        """
        if not self.adapters or not self.infrastructure:
            logger.warning("Cannot register repair cycle handler: adapters or infrastructure not ready")
            return

        from codetoreum.application.event_handlers import RepairCycleEventHandler

        handler = RepairCycleEventHandler(
            repair_cycle=self.adapters.repair_cycle,
            clock=self._clock,
            event_bus=self.infrastructure.event_bus,
        )

        self.infrastructure.event_bus.register_handler(handler)
        logger.info("Registered RepairCycleEventHandler with event bus")

    def _create_fastapi_app(self) -> FastAPI:
        """
        Create FastAPI application with all routers wired to ports.

        Returns:
            Configured FastAPI application ready for testing
        """
        if not self.ports or not self.infrastructure or not self.services:
            raise RuntimeError("Ports and infrastructure must be created first")

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
            cors_origins=[
                "http://localhost:3000",  # Vite default dev server
                "http://localhost:3001",  # Vite when 3000 is in use
                "http://localhost:3010",  # Configured Vite port
                "http://localhost:5173",  # Vite alternative port
                "http://localhost:8080",  # Common alternative
                "http://127.0.0.1:3000",
                "http://127.0.0.1:3001",
                "http://127.0.0.1:3010",
                "http://127.0.0.1:5173",
                "http://127.0.0.1:8080",
            ],
            container_recovery_service=self.services.container_recovery_service,
        )

        logger.info("Created FastAPI application")

        # Register repair cycle event handler with event bus
        # This allows the handler to listen for WorkItemColumnChanged events
        # and invoke the repair cycle when items enter the Testing column
        self._register_repair_cycle_handler()

        return app
