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
from dataclasses import dataclass, field
from datetime import timedelta
from enum import Enum
from typing import Any, cast

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
from codetoreum.adapters.primary.routers.simulation_clock import (
    create_simulation_clock_router,
)

# Import simulation routers
from codetoreum.adapters.primary.routers.simulation_ticketing import (
    create_simulation_ticketing_router,
)
from codetoreum.adapters.secondary.failed_event_store_adapter import (
    DeadLetterQueueFailedEventStoreAdapter,
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

# Application Services
from codetoreum.application.agent_execution_recovery_service import (
    AgentExecutionRecoveryService,
)
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
from codetoreum.infrastructure.adapters.resolver import (
    AdapterDependencies,
    AdapterResolver,
)
from codetoreum.infrastructure.audit.stores import InMemoryAuditStore
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
from codetoreum.infrastructure.simulation.watchdogs import (
    ColumnProgressionWatchdog,
    ExecutionTimeoutWatchdog,
    SLAExpiryWatchdog,
    StaleLockWatchdog,
)
from codetoreum.ports.input.agent_command import IAgentCommandPort
from codetoreum.ports.input.agent_query import IAgentQueryPort

# Ports
from codetoreum.ports.input.audit_query import IAuditQueryPort
from codetoreum.ports.input.config_command import IConfigurationCommandPort
from codetoreum.ports.input.config_query import IConfigurationQueryPort
from codetoreum.ports.input.execution_command import IExecutionCommandPort
from codetoreum.ports.input.execution_query import IExecutionQueryPort
from codetoreum.ports.input.metrics_query import IMetricsQueryPort
from codetoreum.ports.input.orchestration_command import IOrchestrationCommandPort
from codetoreum.ports.input.task_query import ITaskQueryPort
from codetoreum.ports.input.work_item_command import IWorkItemCommandPort
from codetoreum.ports.input.work_item_query import IWorkItemQueryPort
from codetoreum.ports.input.workflow_command import IWorkflowCommandPort
from codetoreum.ports.input.workflow_definition_command import (
    IWorkflowDefinitionCommandPort,
)
from codetoreum.ports.input.workflow_query import IWorkflowQueryPort
from codetoreum.ports.input.workflow_run_query import IWorkflowRunQueryPort
from codetoreum.ports.input.workspace_query import IWorkspaceQueryPort
from codetoreum.ports.output.active_workflow_run_registry import (
    IActiveWorkflowRunRegistry,
)
from codetoreum.ports.output.agent_executor import IAgentExecutor
from codetoreum.ports.output.agent_repository import IAgentRepository
from codetoreum.ports.output.board_service import IBoardService
from codetoreum.ports.output.config_store import IConfigStore
from codetoreum.ports.output.container import IContainer
from codetoreum.ports.output.discussion_adapter import IDiscussionAdapter
from codetoreum.ports.output.encryption_service import IEncryptionService
from codetoreum.ports.output.event_emitter import IEventEmitter
from codetoreum.ports.output.event_store import IEventStore
from codetoreum.ports.output.failed_event_store import IFailedEventStore
from codetoreum.ports.output.identity_service import IIdentityService
from codetoreum.ports.output.llm_provider import ILLMProvider
from codetoreum.ports.output.message_broker import IMessageBroker
from codetoreum.ports.output.metrics import IMetrics
from codetoreum.ports.output.notifier import INotifier
from codetoreum.ports.output.pipeline_lock_service import IPipelineLockService
from codetoreum.ports.output.pipeline_queue_service import IPipelineQueueService
from codetoreum.ports.output.project_manager_service import IProjectManagerService
from codetoreum.ports.output.repair_cycle_checkpoint_store import (
    IRepairCycleCheckpointStore,
)
from codetoreum.ports.output.repair_cycle_service import IRepairCycle
from codetoreum.ports.output.review_cycle_service import IReviewCycle
from codetoreum.ports.output.storage import IStorage
from codetoreum.ports.output.ticket_system import ITicketSystem
from codetoreum.ports.output.version_control_service import IVersionControlService
from codetoreum.ports.output.work_item_branch_tracker import IWorkItemBranchTracker
from codetoreum.ports.output.work_item_service import IWorkItemService
from codetoreum.ports.output.workflow_config_service import IWorkflowConfigService

logger = logging.getLogger(__name__)


class BootstrapPhase(Enum):
    """Bootstrap phases that can fail in degraded mode."""

    AUTO_ADVANCE = "auto_advance"
    STALE_LOCK_WATCHDOG = "stale_lock_watchdog"
    EXECUTION_TIMEOUT_WATCHDOG = "execution_timeout_watchdog"
    SLA_EXPIRY_WATCHDOG = "sla_expiry_watchdog"
    COLUMN_PROGRESSION_WATCHDOG = "column_progression_watchdog"


@dataclass
class BootstrapDegradedModeState:
    """Tracks which bootstrap phases failed and why.

    When critical phases fail (e.g., watchdogs), the bootstrap continues but
    marks these failures so callers can detect degraded mode and decide whether
    to proceed or fail.
    """

    failed_phases: dict[BootstrapPhase, str] = field(default_factory=dict)

    def mark_failed(self, phase: BootstrapPhase, error: str) -> None:
        """Mark a phase as failed with the error message."""
        self.failed_phases[phase] = error

    @property
    def is_degraded(self) -> bool:
        """True if any phases failed."""
        return bool(self.failed_phases)

    @property
    def failed_phase_names(self) -> list[str]:
        """List of failed phase names."""
        return [phase.value for phase in self.failed_phases.keys()]

    def get_summary(self) -> str:
        """Get human-readable summary of failures."""
        if not self.is_degraded:
            return "Bootstrap completed successfully"

        lines = ["Bootstrap running in degraded mode:"]
        for phase, error in self.failed_phases.items():
            lines.append(f"  - {phase.value}: {error}")
        return "\n".join(lines)


@dataclass
class SimulationAdapters:
    """Container for all simulation adapters.

    All fields are typed as port interfaces, not concrete adapter classes.
    This allows test code to inject different implementations (mock vs. real)
    while maintaining type safety.

    Note: agent_executor is assigned in Phase 3 (ExecutionService creation) and is
    always ExecutionServiceAgentExecutor. It implements IAgentExecutor and provides
    set_completion_handler() for BoardColumnEventHandler wiring.

    For test code that needs simulation-specific methods (e.g., add_response(),
    movements, executions), use the accessor helpers:
    - ticket_as_mock() -> InMemoryTicketAdapter
    - llm_as_mock() -> MockLLMAdapter
    - container_as_fake() -> FakeContainerAdapter
    - board_as_mock() -> MockBoardAdapter
    - etc.
    """

    # Output port adapters (typed as interfaces)
    ticket_system: ITicketSystem
    llm_provider: ILLMProvider
    container: IContainer
    repository: Any  # IRepository (not yet in resolver, keeping concrete type)
    event_store: IEventStore
    metrics: IMetrics
    storage: IStorage
    config_store: IConfigStore
    notifier: INotifier
    encryption: IEncryptionService
    board: IBoardService
    repair_cycle: IRepairCycle
    project_manager: IProjectManagerService
    lock_service: IPipelineLockService
    workflow_config: IWorkflowConfigService
    queue_service: IPipelineQueueService
    event_emitter: IEventEmitter  # CapturingMockEventEmitter in simulation
    audit_store: Any  # InMemoryAuditStore (not a port interface yet)

    # Additional adapters (typed as interfaces where available)
    version_control: IVersionControlService
    message_broker: IMessageBroker
    discussion_adapter: IDiscussionAdapter
    review_cycle: IReviewCycle
    identity_service: IIdentityService
    checkpoint_store: IRepairCycleCheckpointStore

    # Phase 3 adapters (ExecutionService chain)
    agent_repository: IAgentRepository
    run_registry: IActiveWorkflowRunRegistry
    branch_tracker: IWorkItemBranchTracker
    work_item_service: IWorkItemService

    # Fields with defaults (must come after fields without defaults)
    agent_executor: IAgentExecutor | None = None

    # =========================================================================
    # Accessor helpers for test code needing simulation-specific methods
    # =========================================================================

    def ticket_as_mock(self) -> InMemoryTicketAdapter:
        """Get ticket system as InMemoryTicketAdapter.

        Raises TypeError if ticket_system is not InMemoryTicketAdapter.
        """
        if not isinstance(self.ticket_system, InMemoryTicketAdapter):
            msg = f"ticket_system is {type(self.ticket_system).__name__}, not InMemoryTicketAdapter"
            raise TypeError(msg)
        return cast(InMemoryTicketAdapter, self.ticket_system)

    def llm_as_mock(self) -> MockLLMAdapter:
        """Get LLM provider as MockLLMAdapter.

        Raises TypeError if llm_provider is not MockLLMAdapter.
        """
        if not isinstance(self.llm_provider, MockLLMAdapter):
            msg = f"llm_provider is {type(self.llm_provider).__name__}, not MockLLMAdapter"
            raise TypeError(msg)
        return cast(MockLLMAdapter, self.llm_provider)

    def container_as_fake(self) -> FakeContainerAdapter:
        """Get container as FakeContainerAdapter.

        Raises TypeError if container is not FakeContainerAdapter.
        """
        if not isinstance(self.container, FakeContainerAdapter):
            msg = f"container is {type(self.container).__name__}, not FakeContainerAdapter"
            raise TypeError(msg)
        return cast(FakeContainerAdapter, self.container)

    def repository_as_memory(self) -> InMemoryRepositoryAdapter:
        """Get repository as InMemoryRepositoryAdapter.

        Raises TypeError if repository is not InMemoryRepositoryAdapter.
        """
        if not isinstance(self.repository, InMemoryRepositoryAdapter):
            msg = f"repository is {type(self.repository).__name__}, not InMemoryRepositoryAdapter"
            raise TypeError(msg)
        return cast(InMemoryRepositoryAdapter, self.repository)

    def board_as_mock(self) -> MockBoardAdapter:
        """Get board as MockBoardAdapter.

        Raises TypeError if board is not MockBoardAdapter.
        """
        if not isinstance(self.board, MockBoardAdapter):
            msg = f"board is {type(self.board).__name__}, not MockBoardAdapter"
            raise TypeError(msg)
        return cast(MockBoardAdapter, self.board)

    def repair_cycle_as_mock(self) -> Any:
        """Get repair cycle as MockRepairCycleAdapter.

        Raises TypeError if repair_cycle is not MockRepairCycleAdapter.
        """
        try:
            from codetoreum.adapters.testing.mock_repair_cycle_adapter import (
                MockRepairCycleAdapter,
            )
            if not isinstance(self.repair_cycle, MockRepairCycleAdapter):
                msg = f"repair_cycle is {type(self.repair_cycle).__name__}, not MockRepairCycleAdapter"
                raise TypeError(msg)
            return cast(Any, self.repair_cycle)
        except ImportError as e:
            msg = f"Failed to import MockRepairCycleAdapter: {e}"
            raise TypeError(msg) from e

    def project_manager_as_mock(self) -> MockProjectManagerAdapter:
        """Get project manager as MockProjectManagerAdapter.

        Raises TypeError if project_manager is not MockProjectManagerAdapter.
        """
        if not isinstance(self.project_manager, MockProjectManagerAdapter):
            msg = f"project_manager is {type(self.project_manager).__name__}, not MockProjectManagerAdapter"
            raise TypeError(msg)
        return cast(MockProjectManagerAdapter, self.project_manager)

    def lock_service_as_memory(self) -> InMemoryLockService:
        """Get lock service as InMemoryLockService.

        Raises TypeError if lock_service is not InMemoryLockService.
        """
        if not isinstance(self.lock_service, InMemoryLockService):
            msg = f"lock_service is {type(self.lock_service).__name__}, not InMemoryLockService"
            raise TypeError(msg)
        return cast(InMemoryLockService, self.lock_service)

    def workflow_config_as_memory(self) -> InMemoryWorkflowConfigService:
        """Get workflow config as InMemoryWorkflowConfigService.

        Raises TypeError if workflow_config is not InMemoryWorkflowConfigService.
        """
        if not isinstance(self.workflow_config, InMemoryWorkflowConfigService):
            msg = f"workflow_config is {type(self.workflow_config).__name__}, not InMemoryWorkflowConfigService"
            raise TypeError(msg)
        return cast(InMemoryWorkflowConfigService, self.workflow_config)

    def queue_service_as_memory(self) -> InMemoryQueueService:
        """Get queue service as InMemoryQueueService.

        Raises TypeError if queue_service is not InMemoryQueueService.
        """
        if not isinstance(self.queue_service, InMemoryQueueService):
            msg = f"queue_service is {type(self.queue_service).__name__}, not InMemoryQueueService"
            raise TypeError(msg)
        return cast(InMemoryQueueService, self.queue_service)

    def event_emitter_as_capturing(self) -> CapturingMockEventEmitter:
        """Get event emitter as CapturingMockEventEmitter.

        Raises TypeError if event_emitter is not CapturingMockEventEmitter.
        """
        if not isinstance(self.event_emitter, CapturingMockEventEmitter):
            msg = f"event_emitter is {type(self.event_emitter).__name__}, not CapturingMockEventEmitter"
            raise TypeError(msg)
        return cast(CapturingMockEventEmitter, self.event_emitter)

    def version_control_as_memory(self) -> InMemoryVersionControlService:
        """Get version control as InMemoryVersionControlService.

        Raises TypeError if version_control is not InMemoryVersionControlService.
        """
        if not isinstance(self.version_control, InMemoryVersionControlService):
            msg = f"version_control is {type(self.version_control).__name__}, not InMemoryVersionControlService"
            raise TypeError(msg)
        return cast(InMemoryVersionControlService, self.version_control)

    def message_broker_as_memory(self) -> InMemoryMessageBroker:
        """Get message broker as InMemoryMessageBroker.

        Raises TypeError if message_broker is not InMemoryMessageBroker.
        """
        if not isinstance(self.message_broker, InMemoryMessageBroker):
            msg = f"message_broker is {type(self.message_broker).__name__}, not InMemoryMessageBroker"
            raise TypeError(msg)
        return cast(InMemoryMessageBroker, self.message_broker)

    def discussion_adapter_as_mock(self) -> MockDiscussionAdapter:
        """Get discussion adapter as MockDiscussionAdapter.

        Raises TypeError if discussion_adapter is not MockDiscussionAdapter.
        """
        if not isinstance(self.discussion_adapter, MockDiscussionAdapter):
            msg = f"discussion_adapter is {type(self.discussion_adapter).__name__}, not MockDiscussionAdapter"
            raise TypeError(msg)
        return cast(MockDiscussionAdapter, self.discussion_adapter)

    def review_cycle_as_mock(self) -> MockReviewCycleAdapter:
        """Get review cycle as MockReviewCycleAdapter.

        Raises TypeError if review_cycle is not MockReviewCycleAdapter.
        """
        if not isinstance(self.review_cycle, MockReviewCycleAdapter):
            msg = f"review_cycle is {type(self.review_cycle).__name__}, not MockReviewCycleAdapter"
            raise TypeError(msg)
        return cast(MockReviewCycleAdapter, self.review_cycle)

    def identity_service_as_configurable(self) -> ConfigurableIdentityService:
        """Get identity service as ConfigurableIdentityService.

        Raises TypeError if identity_service is not ConfigurableIdentityService.
        """
        if not isinstance(self.identity_service, ConfigurableIdentityService):
            msg = f"identity_service is {type(self.identity_service).__name__}, not ConfigurableIdentityService"
            raise TypeError(msg)
        return cast(ConfigurableIdentityService, self.identity_service)

    def checkpoint_store_as_memory(self) -> InMemoryCheckpointStore:
        """Get checkpoint store as InMemoryCheckpointStore.

        Raises TypeError if checkpoint_store is not InMemoryCheckpointStore.
        """
        if not isinstance(self.checkpoint_store, InMemoryCheckpointStore):
            msg = f"checkpoint_store is {type(self.checkpoint_store).__name__}, not InMemoryCheckpointStore"
            raise TypeError(msg)
        return cast(InMemoryCheckpointStore, self.checkpoint_store)

    def agent_repository_as_memory(self) -> InMemoryAgentRepository:
        """Get agent repository as InMemoryAgentRepository.

        Raises TypeError if agent_repository is not InMemoryAgentRepository.
        """
        if not isinstance(self.agent_repository, InMemoryAgentRepository):
            msg = f"agent_repository is {type(self.agent_repository).__name__}, not InMemoryAgentRepository"
            raise TypeError(msg)
        return cast(InMemoryAgentRepository, self.agent_repository)

    def run_registry_as_memory(self) -> InMemoryActiveWorkflowRunRegistry:
        """Get run registry as InMemoryActiveWorkflowRunRegistry.

        Raises TypeError if run_registry is not InMemoryActiveWorkflowRunRegistry.
        """
        if not isinstance(self.run_registry, InMemoryActiveWorkflowRunRegistry):
            msg = f"run_registry is {type(self.run_registry).__name__}, not InMemoryActiveWorkflowRunRegistry"
            raise TypeError(msg)
        return cast(InMemoryActiveWorkflowRunRegistry, self.run_registry)

    def branch_tracker_as_memory(self) -> InMemoryWorkItemBranchTracker:
        """Get branch tracker as InMemoryWorkItemBranchTracker.

        Raises TypeError if branch_tracker is not InMemoryWorkItemBranchTracker.
        """
        if not isinstance(self.branch_tracker, InMemoryWorkItemBranchTracker):
            msg = f"branch_tracker is {type(self.branch_tracker).__name__}, not InMemoryWorkItemBranchTracker"
            raise TypeError(msg)
        return cast(InMemoryWorkItemBranchTracker, self.branch_tracker)

    def work_item_service_as_mock(self) -> MockWorkItemService:
        """Get work item service as MockWorkItemService.

        Raises TypeError if work_item_service is not MockWorkItemService.
        """
        if not isinstance(self.work_item_service, MockWorkItemService):
            msg = f"work_item_service is {type(self.work_item_service).__name__}, not MockWorkItemService"
            raise TypeError(msg)
        return cast(MockWorkItemService, self.work_item_service)


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
    agent_execution_recovery_service: AgentExecutionRecoveryService | None = None
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
    audit_query: IAuditQueryPort


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
    failed_event_store: IFailedEventStore


class SimulationApplicationBootstrap:
    """
    Bootstrap the entire application stack in simulation mode.

    This class wires up:
    1. All 24 testing and simulation adapters
    2. Infrastructure (event bus, clock, logger)
    3. All application services
    4. All input/output ports
    5. FastAPI application
    6. Conditionally auto-advance simulation clock (if configured via TimeConfig.auto_advance)

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
        self._degraded_mode = BootstrapDegradedModeState()
        self._adapter_factory: AdapterFactory | None = None
        self._engine: SimulationEngine | None = None
        self._board_event_handler: BoardColumnEventHandler | None = None
        self._stale_lock_watchdog: StaleLockWatchdog | None = None
        self._execution_timeout_watchdog: ExecutionTimeoutWatchdog | None = None
        self._sla_expiry_watchdog: SLAExpiryWatchdog | None = None
        self._column_progression_watchdog: ColumnProgressionWatchdog | None = None

    @property
    def is_degraded(self) -> bool:
        """
        Check if bootstrap is running in degraded mode.

        Degraded mode occurs when critical phases fail (watchdogs, auto-advance, etc.)
        but the bootstrap continues to allow testing/debugging.

        Callers MUST check this property after setup() completes successfully
        to determine if the system is operating with reduced functionality.

        Returns:
            True if any critical phase failed; False if setup is fully healthy.
        """
        return self._degraded_mode.is_degraded

    @property
    def degraded_mode_state(self) -> BootstrapDegradedModeState:
        """
        Get detailed degraded mode state.

        Returns the full state including which phases failed and why.
        Only relevant if is_degraded is True.
        """
        return self._degraded_mode

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
        - Phase 6: Conditionally start auto-advance clock (if configured)
        - Phase 6b: Register stale lock watchdog (deadlock prevention)
        - Phase 6c: Register execution timeout watchdog (runaway agent prevention)
        - Phase 6d: Register SLA expiry watchdog (compliance enforcement)

        Infrastructure is created before adapters to enable causal linking via event bus subscriptions.
        Auto-advance and watchdogs are started after all event handlers are registered to ensure
        tick-driven events have handlers.

        **DEGRADED MODE**: If phases 6/6b/6c/6d fail, the bootstrap continues to allow testing
        and debugging, but logs errors and marks components as degraded. Callers MUST check the
        `is_degraded` property after setup() returns successfully to determine if critical
        functionality is missing.

        Returns:
            Fully configured FastAPI application (check `is_degraded` property for health status)

        Raises:
            RuntimeError: If already set up or if core phases 0-5 fail (degraded mode is only
                        for phases 6+)
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

            # Start dead letter queue retry processor
            # This enables automatic retry of failed event publishing (issue #371)
            if self.infrastructure and self.infrastructure.failed_event_store:
                logger.info("Starting failed event store retry processor...")
                # Cast to adapter to access infrastructure-specific lifecycle methods
                dlq_adapter = self.infrastructure.failed_event_store
                if isinstance(dlq_adapter, DeadLetterQueueFailedEventStoreAdapter):
                    await dlq_adapter.start_retry_processor(self._create_dlq_retry_handler())

            # Phase 6: Start auto-advance if configured
            # This must come after all event handlers are registered so tick-driven events have handlers
            if self.config.time.auto_advance and self._engine:
                try:
                    logger.info(
                        "Phase 6: Starting auto-advance at %sx speed",
                        self.config.time.speed_multiplier,
                    )
                    await self._engine.start_auto_advance()
                except RuntimeError as e:
                    # If auto-advance is already running, log warning and continue in degraded mode
                    error_msg = f"Auto-advance already running or failed to start: {e}"
                    logger.warning(
                        error_msg,
                        extra={"error_id": ErrorRegistry.ERR_INTERNAL_ERROR},
                    )
                    self._degraded_mode.mark_failed(BootstrapPhase.AUTO_ADVANCE, str(e))
                except Exception as e:
                    # Mark as degraded and log with full context
                    error_msg = f"Unexpected error starting auto-advance: {e}"
                    logger.error(
                        error_msg,
                        exc_info=True,
                        extra={"error_id": ErrorRegistry.ERR_INTERNAL_ERROR},
                    )
                    self._degraded_mode.mark_failed(BootstrapPhase.AUTO_ADVANCE, str(e))
                    # Continue without auto-advance rather than crashing the server
                    logger.info("Continuing server startup in degraded mode without auto-advance")

            # Phase 6b: Register stale lock watchdog
            # Must come after auto-advance starts so it can schedule callbacks with the clock
            if self.adapters and self._engine:
                try:
                    logger.info("Phase 6b: Registering stale lock watchdog...")
                    self._stale_lock_watchdog = StaleLockWatchdog(
                        lock_service=self.adapters.lock_service,
                        event_emitter=self.adapters.event_emitter,
                        clock=self._engine.get_clock_for_testing(),
                        stale_threshold_seconds=7200,  # 2 hours default
                    )
                    self._stale_lock_watchdog.start()

                    # Wire the on_lock_acquired event handler to clear deduplication tracking
                    # when locks are newly acquired after being recovered
                    if self.infrastructure and self.infrastructure.event_bus:
                        self.infrastructure.event_bus.subscribe(
                            "lock.acquired",
                            self._stale_lock_watchdog.on_lock_acquired,
                        )

                    logger.info("Stale lock watchdog registered and started")
                except Exception as e:
                    # Mark as degraded - stale lock detection is critical for deadlock prevention
                    error_msg = f"Failed to register stale lock watchdog: {e}"
                    logger.error(
                        error_msg,
                        exc_info=True,
                        extra={"error_id": ErrorRegistry.ERR_INTERNAL_ERROR},
                    )
                    self._degraded_mode.mark_failed(BootstrapPhase.STALE_LOCK_WATCHDOG, str(e))
                    # Continue without watchdog rather than crashing the server
                    logger.warning(
                        "Continuing server startup in degraded mode without stale lock watchdog. "
                        "Pipeline may deadlock if locks become stale."
                    )

            # Phase 6c: Register execution timeout watchdog
            # Must come after auto-advance starts and ExecutionServiceAgentExecutor is initialized
            if self.adapters and self._engine:
                try:
                    logger.info("Phase 6c: Registering execution timeout watchdog...")
                    # Type guard: agent_executor must be ExecutionServiceAgentExecutor, not None
                    if self.adapters.agent_executor is None:
                        raise RuntimeError("ExecutionServiceAgentExecutor not initialized in Phase 3")
                    from codetoreum.adapters.testing.execution_service_agent_executor import (
                        ExecutionServiceAgentExecutor,
                    )

                    if not isinstance(self.adapters.agent_executor, ExecutionServiceAgentExecutor):
                        raise TypeError(
                            f"agent_executor must be ExecutionServiceAgentExecutor, "
                            f"got {type(self.adapters.agent_executor).__name__}"
                        )
                    self._execution_timeout_watchdog = ExecutionTimeoutWatchdog(
                        executor=self.adapters.agent_executor,
                        event_emitter=self.adapters.event_emitter,
                        clock=self._engine.get_clock_for_testing(),
                        check_interval=timedelta(seconds=30),  # Check every 30 simulated seconds
                    )
                    self._execution_timeout_watchdog.start()
                    logger.info("Execution timeout watchdog registered and started")
                except Exception as e:
                    # Mark as degraded - execution timeout detection is critical for runaway prevention
                    error_msg = f"Failed to register execution timeout watchdog: {e}"
                    logger.error(
                        error_msg,
                        exc_info=True,
                        extra={"error_id": ErrorRegistry.ERR_INTERNAL_ERROR},
                    )
                    self._degraded_mode.mark_failed(BootstrapPhase.EXECUTION_TIMEOUT_WATCHDOG, str(e))
                    # Continue without watchdog rather than crashing the server
                    logger.warning(
                        "Continuing server startup in degraded mode without execution timeout watchdog. "
                        "Agents may run indefinitely if they hang."
                    )

            # Phase 6d: Register SLA expiry watchdog
            # Must come after auto-advance starts and all adapters are initialized
            if self.adapters and self._engine:
                try:
                    logger.info("Phase 6d: Registering SLA expiry watchdog...")
                    self._sla_expiry_watchdog = SLAExpiryWatchdog(
                        board_service=self.adapters.board,
                        workflow_config_service=self.adapters.workflow_config,
                        event_emitter=self.adapters.event_emitter,
                        clock=self._engine.get_clock_for_testing(),
                        check_interval=timedelta(seconds=60),  # Check every 60 simulated seconds
                    )
                    self._sla_expiry_watchdog.start()
                    logger.info("SLA expiry watchdog registered and started")
                except Exception as e:
                    # Mark as degraded - SLA enforcement is critical for compliance
                    error_msg = f"Failed to register SLA expiry watchdog: {e}"
                    logger.error(
                        error_msg,
                        exc_info=True,
                        extra={"error_id": ErrorRegistry.ERR_INTERNAL_ERROR},
                    )
                    self._degraded_mode.mark_failed(BootstrapPhase.SLA_EXPIRY_WATCHDOG, str(e))
                    # Continue without watchdog rather than crashing the server
                    logger.warning(
                        "Continuing server startup in degraded mode without SLA expiry watchdog. "
                        "SLA violations will not be detected."
                    )

            # Phase 6e: Register column progression watchdog
            # Must come after auto-advance starts and all adapters are initialized
            # Provides clock-driven autonomous progression as alternative to HTTP-triggered moves
            if self.adapters and self._engine:
                try:
                    logger.info("Phase 6e: Registering column progression watchdog...")
                    self._column_progression_watchdog = ColumnProgressionWatchdog(
                        board_service=self.adapters.board,
                        workflow_config_service=self.adapters.workflow_config,
                        clock=self._engine.get_clock_for_testing(),
                        check_interval=timedelta(seconds=30),  # Check every 30 simulated seconds
                        dedup_window=timedelta(seconds=5),  # Dedup window for recent progressions
                    )
                    self._column_progression_watchdog.start()
                    logger.info("Column progression watchdog registered and started")
                except Exception as e:
                    # Mark as degraded - column progression is essential for autonomous workflows
                    error_msg = f"Failed to register column progression watchdog: {e}"
                    logger.error(
                        error_msg,
                        exc_info=True,
                        extra={"error_id": ErrorRegistry.ERR_INTERNAL_ERROR},
                    )
                    self._degraded_mode.mark_failed(BootstrapPhase.COLUMN_PROGRESSION_WATCHDOG, str(e))
                    # Continue without watchdog - progression will work via HTTP calls only
                    logger.warning(
                        "Continuing server startup in degraded mode without column progression watchdog. "
                        "Clock-driven progression will not work, but HTTP-triggered progression should work."
                    )

            self._is_setup = True

            # Log degraded mode status before returning
            if self.is_degraded:
                logger.warning(self._degraded_mode.get_summary())
                logger.warning(
                    "Bootstrap completed in DEGRADED MODE with %d critical failures. "
                    "Check is_degraded property and degraded_mode_state for details.",
                    len(self._degraded_mode.failed_phases),
                )
            else:
                logger.info("Simulation bootstrap completed successfully (fully healthy)")

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
        - Stop all three watchdogs (prevent accessing cleaned-up resources)
        - Stop dead letter queue retry processor
        - Stop clock auto-advance (if running)
        - Stop event bus
        - Clear adapters
        - Reset state

        Raises:
            Exception: Re-raises any exception encountered during cleanup with full context.
                     The _is_setup flag is only cleared if all cleanup steps succeed,
                     ensuring reliable state tracking even on failure.
        """
        if not self._is_setup:
            return

        try:
            logger.info("Tearing down simulation bootstrap...")

            # Stop all watchdogs before cleaning up adapters/infrastructure
            # This prevents scheduled callbacks from firing during teardown and
            # attempting to access None references (adapters, lock_service, etc.)
            if self._stale_lock_watchdog:
                self._stale_lock_watchdog.stop()
                logger.debug("Stale lock watchdog stopped")

            if self._execution_timeout_watchdog:
                self._execution_timeout_watchdog.stop()
                logger.debug("Execution timeout watchdog stopped")

            if self._sla_expiry_watchdog:
                self._sla_expiry_watchdog.stop()
                logger.debug("SLA expiry watchdog stopped")

            if self._column_progression_watchdog:
                self._column_progression_watchdog.stop()
                logger.debug("Column progression watchdog stopped")

            # Stop dead letter queue retry processor
            if self.infrastructure and self.infrastructure.failed_event_store:
                dlq_adapter = self.infrastructure.failed_event_store
                if isinstance(dlq_adapter, DeadLetterQueueFailedEventStoreAdapter):
                    await dlq_adapter.stop_retry_processor()

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
            self._stale_lock_watchdog = None
            self._execution_timeout_watchdog = None
            self._sla_expiry_watchdog = None

            self._is_setup = False
            logger.info("Simulation bootstrap teardown complete")

        except Exception as e:
            logger.error(
                f"Error during teardown: {e}",
                extra={"error_id": ErrorRegistry.ERR_INTERNAL_ERROR},
                exc_info=True,
            )
            # Re-raise to ensure caller (typically test fixture) knows teardown failed
            raise

    # =========================================================================
    # Phase 2: Create Adapters
    # =========================================================================

    async def _create_adapters(self) -> SimulationAdapters:
        """
        Create all 28 adapters using AdapterResolver in dependency order.

        Phase 2 bootstrap creates adapters following a partial dependency ordering:
        1. Leaf adapters (no dependencies): event_store, config_store, metrics, storage, encryption
        2. Event infrastructure: event_emitter, message_broker
        3. External systems: ticket_system, llm_provider, container, version_control
        4. Coordination: board, discussion_adapter, lock_service, queue_service
        5. State: checkpoint_store, agent_repository, run_registry, branch_tracker, work_item_service,
                   workflow_config, notifier
        6. Composite: project_manager
        7. Engine-coupled: review_cycle, repair_cycle (use SimulationEngine for clock injection)

        AdapterResolver validates credentials before construction and raises aggregated
        configuration errors if any adapter is misconfigured.

        All adapters are typed as port interfaces, allowing test code to use accessor
        helpers (e.g., adapters.board_as_mock(), adapters.llm_as_mock()) to access
        simulation-specific methods.

        Returns:
            SimulationAdapters with all 28 adapters typed as port interfaces
        """
        if not self._engine:
            message = "SimulationEngine must be created before adapters"
            raise RuntimeError(message)
        if not self.infrastructure:
            message = "Infrastructure (event bus) must be created before adapters"
            raise RuntimeError(message)

        # Phase 2: Create adapter factory and resolver
        factory_config = AdapterFactoryConfig(
            operation_mode=OperationMode.SIMULATION,
            enable_resilience=False,  # ADR-005: No resilience in simulation
        )
        self._adapter_factory = AdapterFactory(factory_config)

        # Create adapter dependencies for injection
        deps = AdapterDependencies(
            event_bus=self.infrastructure.event_bus,
            event_emitter=CapturingMockEventEmitter(),  # For domain event capture
            logger=self.infrastructure.logger,
            engine=self._engine,
            config=self.config,
        )

        # Create resolver with dependency order management
        resolver = AdapterResolver(
            adapter_config=self.config.adapters,
            factory=self._adapter_factory,
            dependencies=deps,
        )

        # Resolve all adapters in dependency order with credential validation
        resolved = resolver.resolve_all()

        # Extract resolved adapters and apply simulation-specific post-processing
        # where needed (e.g., pre-configuring default project for tests)

        # Post-process project manager: pre-configure default test project
        project_manager = cast(IProjectManagerService, resolved["project_manager"])
        if isinstance(project_manager, MockProjectManagerAdapter):
            project_manager.add_project(
                "default_project",
                ProjectConfig(
                    repo_url="https://vcs.example.com/org/default.git",
                    branch="main",
                    enabled=True,
                    org="test-org",
                ),
            )

        # Post-process message broker: initialize async
        message_broker = cast(IMessageBroker, resolved["message_broker"])
        if isinstance(message_broker, InMemoryMessageBroker):
            await message_broker.initialize()

        # Post-process identity service: set bot username
        identity_service = cast(IIdentityService, resolved["identity_service"])
        if isinstance(identity_service, ConfigurableIdentityService):
            identity_service.set_bot_username("codetoreum-bot")

        # Post-process storage adapter: inject container for file retrieval
        # (storage depends on container, so we inject it after resolution)
        storage = cast(IStorage, resolved["storage"])
        container = cast(IContainer, resolved["container"])
        if isinstance(storage, InMemoryStorageAdapter):
            storage.container = container

        logger.info("Created 28 simulation adapters via AdapterResolver")

        return SimulationAdapters(
            ticket_system=cast(ITicketSystem, resolved["ticket"]),
            llm_provider=cast(ILLMProvider, resolved["llm"]),
            container=container,
            repository=cast(Any, resolved["version_control"]),  # Using version_control as repository placeholder
            event_store=cast(IEventStore, resolved["event_store"]),
            metrics=cast(IMetrics, resolved["metrics"]),
            storage=storage,
            config_store=cast(IConfigStore, resolved["config_store"]),
            notifier=cast(INotifier, resolved["notifier"]),
            encryption=cast(IEncryptionService, resolved["encryption"]),
            board=cast(IBoardService, resolved["board"]),
            repair_cycle=cast(IRepairCycle, resolved["repair_cycle"]),
            project_manager=project_manager,
            lock_service=cast(IPipelineLockService, resolved["lock_service"]),
            workflow_config=cast(IWorkflowConfigService, resolved["workflow_config"]),
            queue_service=cast(IPipelineQueueService, resolved["queue_service"]),
            event_emitter=cast(IEventEmitter, deps.event_emitter),
            audit_store=cast(Any, resolved.get("audit_store")),
            version_control=cast(IVersionControlService, resolved["version_control"]),
            message_broker=message_broker,
            discussion_adapter=cast(IDiscussionAdapter, resolved["discussion_adapter"]),
            review_cycle=cast(IReviewCycle, resolved["review_cycle"]),
            identity_service=identity_service,
            checkpoint_store=cast(IRepairCycleCheckpointStore, resolved["checkpoint_store"]),
            agent_repository=cast(IAgentRepository, resolved["agent_repository"]),
            run_registry=cast(IActiveWorkflowRunRegistry, resolved["run_registry"]),
            branch_tracker=cast(IWorkItemBranchTracker, resolved["branch_tracker"]),
            work_item_service=cast(IWorkItemService, resolved["work_item_service"]),
            agent_executor=None,  # Assigned in Phase 3
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

    def _create_dlq_retry_handler(self) -> Any:
        """
        Create a retry handler function for the dead letter queue.

        The handler is called by the DLQ retry processor to retry failed events.
        It simply re-publishes the event to the event bus.

        Returns:
            Async function that retries an event
        """
        event_bus = self.infrastructure.event_bus if self.infrastructure else None

        async def retry_event(event_type: str, event_data: dict[str, Any]) -> None:
            """Retry publishing a failed event."""
            if not event_bus:
                message = "Event bus not available for retry"
                raise RuntimeError(message)

            # Reconstruct the domain event from the stored data
            # Map event type to actual event class for proper reconstruction
            retry_event_obj = None

            if event_type == "WorkItemColumnChanged":
                retry_event_obj = WorkItemColumnChanged(
                    aggregate_id=event_data.get("work_item_id", ""),
                    payload=event_data,
                )
            elif event_type == "BoardReconciled":
                retry_event_obj = BoardReconciled(
                    aggregate_id=event_data.get("board_id", ""),
                    payload=event_data,
                )
            else:
                # For unknown event types, raise exception to prevent silent deletion
                # This ensures the DLQ doesn't remove events of unmapped types on first retry.
                # The retry processor will treat this as a processing failure and retry with backoff.
                message = f"Unknown event type '{event_type}' in dead letter queue - handler mapping not updated"
                logger.error(
                    message,
                    extra={
                        "event_type": event_type,
                        "error_id": ErrorRegistry.ERR_INTERNAL_ERROR,
                    },
                )
                raise ValueError(message)

            await event_bus.publish(retry_event_obj)

        return retry_event

    # =========================================================================
    # Phase 1: Create Infrastructure (Early for Event Bus Subscriptions)
    # =========================================================================

    def _create_infrastructure(self) -> SimulationInfrastructure:
        """
        Create infrastructure components (event bus, logger, causal link registry, dead letter queue).

        The SimulationEngine manages the clock internally. The engine is used
        directly to access clock functionality, not through infrastructure.

        The CausalLinkRegistry enables runtime enforcement and discoverability of
        causal dependencies between adapters and domain events.

        The DeadLetterQueue captures failed event publishing attempts, enabling
        event bridge reliability (see issue #371).

        Returns:
            SimulationInfrastructure with configured components
        """
        if not self._engine:
            message = "SimulationEngine must be created before infrastructure"
            raise RuntimeError(message)

        from codetoreum.infrastructure.dead_letter_queue import DeadLetterQueue

        # Create event bus
        event_bus = EventBus()

        # Get logger
        app_logger = logging.getLogger("codetoreum")

        # Create mock tracer for trace propagation testing in simulation mode
        mock_tracer = MockTracer(service_name="simulation")

        # Create causal link registry for managing adapter dependencies
        causal_link_registry = CausalLinkRegistry()

        # Create dead letter queue for capturing failed event publishing
        # Wrap it with the port adapter to decouple infrastructure from application
        # This is critical for event bridge reliability (issue #371)
        dead_letter_queue = DeadLetterQueue()
        failed_event_store = DeadLetterQueueFailedEventStoreAdapter(dead_letter_queue)

        logger.info("Created infrastructure components (including CausalLinkRegistry and IFailedEventStore)")

        # Note: Clock is no longer exposed here - it's managed by SimulationEngine
        # The engine is the single point of control for all timing operations
        return SimulationInfrastructure(
            event_bus=event_bus,
            logger=app_logger,
            mock_tracer=mock_tracer,
            causal_link_registry=causal_link_registry,
            failed_event_store=failed_event_store,
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

        # Phase 3a: Create AgentExecutionRecoveryService
        # This service handles recovery from agent execution failures (completion callback failures,
        # lock stuck detection, etc.). It's injected into both ExecutionServiceAgentExecutor
        # (for completion callback failures) and BoardColumnEventHandler (for execution failures).
        recovery_service = AgentExecutionRecoveryService(
            board_service=self.adapters.board,
            event_store=self.adapters.event_store,
            run_registry=self.adapters.run_registry,
            failed_event_store=self.infrastructure.failed_event_store,
        )

        # Phase 3b: Create ExecutionServiceAgentExecutor and wire into adapters
        # This requires execution_service + workspace_router which are now available
        # ExecutionServiceAgentExecutor is now the sole agent executor
        execution_service_executor = ExecutionServiceAgentExecutor(
            execution_service=execution_service,
            workspace_router=workspace_router,
            config_store=self.adapters.config_store,
            agent_repository=self.adapters.agent_repository,
            work_item_service=self.adapters.work_item_service,
            run_registry=self.adapters.run_registry,
            branch_tracker=self.adapters.branch_tracker,
            vcs=self.adapters.version_control,
            clock=self._engine.get_clock_for_testing(),
            recovery_service=recovery_service,
        )
        # Assign to agent_executor (the primary executor for the board handler)
        self.adapters.agent_executor = execution_service_executor

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
            "Created all application services with simulation dependencies "
            "(including container recovery and multi-project orchestrator)"
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
            agent_execution_recovery_service=recovery_service,
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
        execution_query = MockExecutionQueryAdapter(
            agent_executor=self.adapters.agent_executor,
        )
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

        # Create audit query adapter using the audit store
        from codetoreum.adapters.primary.audit_query_adapter import AuditQueryAdapter

        audit_query = AuditQueryAdapter(audit_store=self.adapters.audit_store)

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
            audit_query=audit_query,
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
            audit_query_port=self.ports.audit_query,
            disable_auth=True,  # ADR-003: Disable authentication in simulation
            cors_origins=["*"],  # Allow all origins in simulation mode (auth is disabled)
            container_recovery_service=self.services.container_recovery_service,
        )

        # Mount simulation-only ticketing router (never in production create_app)
        # Pass workflow_config_service to enable proper staging column detection (issue #442)
        sim_router = create_simulation_ticketing_router(
            self.adapters.ticket_system, self.adapters.board, self.adapters.workflow_config
        )
        app.include_router(sim_router)

        # Mount simulation-only clock control router (never in production create_app)
        clock_router = create_simulation_clock_router(self._engine)
        app.include_router(clock_router)

        logger.info("Created FastAPI application with all ports wired")

        # Bridge board adapter events to central EventBus
        self._register_board_event_bridge()

        # Register board column event handler for automation (agent execution + auto-progression)
        self._register_board_column_handler()

        # Register repair cycle event handler with event bus
        # This allows the handler to listen for WorkItemColumnChanged events
        # and invoke the repair cycle when items enter the configured repair cycle stage
        self._register_repair_cycle_handler()

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

        CRITICAL: Event publishing is awaited (not fire-and-forget) to ensure failures
        are captured by the dead letter queue. Silent failures would disable automation
        for affected work items. See issue #371.
        """
        if not self.adapters or not self.infrastructure:
            logger.warning("Cannot register board event bridge: components not ready")
            return

        event_bus = self.infrastructure.event_bus
        ticket_adapter = self.adapters.ticket_system
        failed_event_store = self.infrastructure.failed_event_store

        # Map board columns to work item statuses
        _column_to_status = {
            "Backlog": WorkItemStatus.NEW,
            "Ready": WorkItemStatus.ASSIGNED,
            "In Progress": WorkItemStatus.IN_PROGRESS,
            "Review": WorkItemStatus.UNDER_REVIEW,
            "Done": WorkItemStatus.COMPLETED,
        }

        def board_column_changed_bridge(event):
            """Translate WorkItemColumnChangedEvent (CodetoreumEvent) to WorkItemColumnChanged (DomainEvent).

            Also syncs work item status in the ticket adapter so the UX reflects the current column position.

            CRITICAL: This bridge runs as a fire-and-forget async task created via loop.create_task().
            However, failures within the task are NOT silent:
            1. Event publishing failures are caught and sent to the dead letter queue for automatic retry
            2. Task exceptions are logged via a done callback, preventing silent swallowing of errors
            3. The DLQ retry processor handles transient/permanent classification and exponential backoff

            This architecture prevents silent automation failures while allowing the event bridge
            to be non-blocking (critical for the sync event adapter callback pattern).
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

                # Create task to handle event publishing with dead letter queue fallback
                # Add done callback to log any unhandled exceptions (safety net for failures
                # in _handle_column_changed_event itself, such as DLQ unavailability)
                task = loop.create_task(_handle_column_changed_event(domain_event, event.work_item_id, event.to_column))

                def task_done_callback(task_result: asyncio.Task[None]) -> None:
                    """Log any unhandled exceptions from the bridge task."""
                    try:
                        task_result.result()
                    except asyncio.CancelledError:
                        # Task was cancelled - this is normal during shutdown
                        pass
                    except Exception as task_exception:
                        # Unhandled exception in the bridge handler (e.g., DLQ failure)
                        # This logs the failure so it's not silently swallowed
                        logger.error(
                            f"Unhandled exception in board column event bridge for {event.work_item_id}: "
                            f"{task_exception}",
                            exc_info=True,
                            extra={
                                "work_item_id": event.work_item_id,
                                "error_type": type(task_exception).__name__,
                                "error_id": ErrorRegistry.ERR_INTERNAL_ERROR,
                            },
                        )

                task.add_done_callback(task_done_callback)

            except RuntimeError as e:
                logger.error(
                    f"Failed to schedule board column event bridge task: {e}",
                    exc_info=True,
                    extra={"error_id": ErrorRegistry.ERR_INTERNAL_ERROR},
                )

        async def _handle_column_changed_event(
            domain_event: WorkItemColumnChanged, work_item_id: str, to_column: str
        ) -> None:
            """Handle publishing WorkItemColumnChanged event with dead letter queue fallback.

            This function:
            1. Publishes the event to the event bus (which triggers automation)
            2. Syncs work item status in the ticket adapter
            3. On failure, sends the event to the dead letter queue for retry

            Awaiting this function ensures that if publishing fails, we capture the
            failure properly instead of silently losing the event.
            """
            try:
                # Publish the event - this will trigger BoardColumnEventHandler and automation
                await event_bus.publish(domain_event)
                logger.debug(
                    f"Successfully published WorkItemColumnChanged event for {work_item_id}",
                    extra={"work_item_id": work_item_id, "event_type": "WorkItemColumnChanged"},
                )
            except Exception as publish_error:
                # Publishing failed - send to failed event store for retry
                # This preserves the event and allows operators to investigate/recover
                from codetoreum.infrastructure.event_bus import EventBusError
                from codetoreum.ports.output.failed_event_store import FailureReason

                event_type = domain_event.event_type

                # Classify the error as transient or permanent
                # EventBusError wraps the original error in __cause__
                is_transient = False
                original_error_type = type(publish_error).__name__

                if isinstance(publish_error, EventBusError) and publish_error.__cause__:
                    # Check the wrapped cause for transient error types
                    cause = publish_error.__cause__
                    if isinstance(cause, (ConnectionError, TimeoutError)):
                        is_transient = True
                        original_error_type = type(cause).__name__
                elif isinstance(publish_error, (ConnectionError, TimeoutError)):
                    # Direct transient error (not wrapped)
                    is_transient = True

                await failed_event_store.add_failed_event(
                    event_type=event_type,
                    event_data=domain_event.payload,
                    failure_reason=FailureReason.TRANSIENT_ERROR if is_transient else FailureReason.PROCESSING_ERROR,
                    error_message=str(publish_error),
                    metadata={
                        "work_item_id": work_item_id,
                        "original_error": original_error_type,
                    },
                )

                logger.error(
                    f"Event publishing failed for work_item {work_item_id} - "
                    f"queued to dead letter queue: {publish_error}",
                    exc_info=True,
                    extra={
                        "work_item_id": work_item_id,
                        "event_type": event_type,
                        "error_type": type(publish_error).__name__,
                        "error_id": ErrorRegistry.ERR_INTERNAL_ERROR,
                    },
                )

            # Sync work item status based on target column (best-effort, separate from publishing)
            # This is fire-and-forget because it's non-critical UI sync, separate from core automation
            target_status = _column_to_status.get(to_column)
            if target_status is not None:
                try:
                    await _sync_work_item_status(work_item_id, target_status)
                except Exception as sync_error:
                    # Status sync failures are best-effort and don't affect automation
                    logger.warning(
                        f"Best-effort status sync failed for {work_item_id} -> {target_status.value}: {sync_error}",
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
            """Translate BoardReconciledEvent (CodetoreumEvent) to BoardReconciled (DomainEvent).

            CRITICAL: This bridge runs as a fire-and-forget async task created via loop.create_task().
            However, failures within the task are NOT silent:
            1. Event publishing failures are caught and sent to the dead letter queue for automatic retry
            2. Task exceptions are logged via a done callback, preventing silent swallowing of errors
            3. The DLQ retry processor handles transient/permanent classification and exponential backoff

            This architecture prevents silent automation failures while allowing the event bridge
            to be non-blocking (critical for the sync event adapter callback pattern).
            """
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

                # Create task to handle event publishing with dead letter queue fallback
                # Add done callback to log any unhandled exceptions (safety net for failures
                # in _handle_board_reconciled_event itself, such as DLQ unavailability)
                task = loop.create_task(_handle_board_reconciled_event(domain_event, event.board_id))

                def task_done_callback(task_result: asyncio.Task[None]) -> None:
                    """Log any unhandled exceptions from the bridge task."""
                    try:
                        task_result.result()
                    except asyncio.CancelledError:
                        # Task was cancelled - this is normal during shutdown
                        pass
                    except Exception as task_exception:
                        # Unhandled exception in the bridge handler (e.g., DLQ failure)
                        # This logs the failure so it's not silently swallowed
                        logger.error(
                            f"Unhandled exception in board reconciliation event bridge for {event.board_id}: "
                            f"{task_exception}",
                            exc_info=True,
                            extra={
                                "board_id": event.board_id,
                                "error_type": type(task_exception).__name__,
                                "error_id": ErrorRegistry.ERR_INTERNAL_ERROR,
                            },
                        )

                task.add_done_callback(task_done_callback)

            except RuntimeError as e:
                logger.error(
                    f"Failed to schedule board reconciliation event bridge task: {e}",
                    exc_info=True,
                    extra={"error_id": ErrorRegistry.ERR_INTERNAL_ERROR},
                )

        async def _handle_board_reconciled_event(domain_event: BoardReconciled, board_id: str) -> None:
            """Handle publishing BoardReconciled event with dead letter queue fallback.

            Awaiting this function ensures that if publishing fails, we capture the
            failure properly instead of silently losing the event.
            """
            try:
                await event_bus.publish(domain_event)
                logger.debug(
                    f"Successfully published BoardReconciled event for {board_id}",
                    extra={"board_id": board_id, "event_type": "BoardReconciled"},
                )
            except Exception as publish_error:
                # Publishing failed - send to failed event store for retry
                from codetoreum.infrastructure.event_bus import EventBusError
                from codetoreum.ports.output.failed_event_store import FailureReason

                event_type = domain_event.event_type

                # Classify the error as transient or permanent
                # EventBusError wraps the original error in __cause__
                is_transient = False
                original_error_type = type(publish_error).__name__

                if isinstance(publish_error, EventBusError) and publish_error.__cause__:
                    # Check the wrapped cause for transient error types
                    cause = publish_error.__cause__
                    if isinstance(cause, (ConnectionError, TimeoutError)):
                        is_transient = True
                        original_error_type = type(cause).__name__
                elif isinstance(publish_error, (ConnectionError, TimeoutError)):
                    # Direct transient error (not wrapped)
                    is_transient = True

                await failed_event_store.add_failed_event(
                    event_type=event_type,
                    event_data=domain_event.payload,
                    failure_reason=FailureReason.TRANSIENT_ERROR if is_transient else FailureReason.PROCESSING_ERROR,
                    error_message=str(publish_error),
                    metadata={
                        "board_id": board_id,
                        "original_error": original_error_type,
                    },
                )

                logger.error(
                    f"Event publishing failed for board {board_id} - queued to failed event store: {publish_error}",
                    exc_info=True,
                    extra={
                        "board_id": board_id,
                        "event_type": event_type,
                        "error_type": original_error_type,
                        "error_id": ErrorRegistry.ERR_INTERNAL_ERROR,
                    },
                )

        self.adapters.board.on("workitem.column_changed", board_column_changed_bridge)
        self.adapters.board.on("board.reconciled", board_reconciled_bridge)
        logger.info("Registered board event bridge to central EventBus")

    def _register_board_column_handler(self) -> None:
        """Register BoardColumnEventHandler for automated column processing.

        Creates the handler with its 5 dependencies (plus optional recovery_service)
        and wires the agent executor's completion callback to the handler's
        handle_agent_completion method. This closes the loop: column change ->
        agent execution -> completion callback -> auto-progress to next column.
        """
        if not self.adapters or not self.infrastructure:
            logger.warning("Cannot register board column handler: components not ready")
            return

        # At this point, agent_executor is ExecutionServiceAgentExecutor (assigned in Phase 3)
        if self.adapters.agent_executor is None:
            logger.warning("Cannot register board column handler: agent_executor not yet initialized")
            return

        # Retrieve the recovery_service that was created in Phase 3a and stored in SimulationServices
        # The recovery_service is needed for handling agent execution failures in the handler
        recovery_service = None
        if self.services:
            recovery_service = self.services.agent_execution_recovery_service

        handler = BoardColumnEventHandler(
            board_service=self.adapters.board,
            lock_service=self.adapters.lock_service,
            workflow_config=self.adapters.workflow_config,
            event_store=self.adapters.event_store,
            agent_executor=self.adapters.agent_executor,
            event_bus=self.infrastructure.event_bus,
            run_registry=self.adapters.run_registry,
            event_emitter=self.adapters.event_emitter,
            recovery_service=recovery_service,
        )

        # Wire completion callback on ExecutionServiceAgentExecutor for auto-progression
        # This method is not part of the IAgentExecutor port interface (lifecycle concern)
        # but is provided by concrete implementations for bootstrap initialization.
        if hasattr(self.adapters.agent_executor, "set_completion_handler"):
            self.adapters.agent_executor.set_completion_handler(handler.handle_agent_completion, "board-1")

        # Store reference to handler for potential future reference
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
