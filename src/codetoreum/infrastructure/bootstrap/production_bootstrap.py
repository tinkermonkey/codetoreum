"""
Production Application Bootstrap

Wires up the entire application stack in production mode through 7 phases:

**Phase 1**: Infrastructure creation (event bus, adapter factory, resolver setup)
**Phase 2**: Adapter resolution (creates all 33 adapters with credential validation)
**Phase 3**: Critical path enforcement (validates no mocks on critical execution paths)
**Phase 4**: Resilience decoration (wraps adapters with rate limiting, circuit breaking, timeouts, retries)
**Phase 5**: Application service instantiation (creates 11 services with production adapters)
**Phase 6**: Input port creation (creates 17 input port implementations)
**Phase 7**: FastAPI app creation (creates app with all ports wired)

This bootstrap ensures:
- Hard enforcement that no mock adapters reach critical paths
- All credentials validated during Phase 2 (before any adapter is instantiated)
- Resilience patterns applied consistently
- No simulation-specific code or routes included
- All input port parameters are non-None before app creation
"""

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from fastapi import FastAPI

from codetoreum.adapters.primary.fastapi_app import create_app
from codetoreum.adapters.primary.input_port_adapters.mock import (
    MockAgentCommandAdapter,
    MockAgentQueryAdapter,
    MockAuditQueryAdapter,
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
    MockWorkspaceQueryAdapter,
)
from codetoreum.adapters.secondary.failed_event_store_adapter import (
    DeadLetterQueueFailedEventStoreAdapter,
)
from codetoreum.application.agent_execution_recovery_service import (
    AgentExecutionRecoveryService,
)
from codetoreum.application.agent_scheduler import (
    AgentScheduler,
    InMemoryTaskQueue,
)
from codetoreum.application.configuration_service import ConfigurationService
from codetoreum.application.container_recovery_service import ContainerRecoveryService
from codetoreum.application.conversational_loop_orchestrator import (
    ConversationalLoopOrchestrator,
)
from codetoreum.application.event_handlers.board_event_handler import (
    BoardColumnEventHandler,
)
from codetoreum.application.event_handlers.pr_review_cycle_dispatch_handler import (
    PRReviewCycleDispatchHandler,
)
from codetoreum.application.event_handlers.pr_review_cycle_event_handler import (
    PRReviewCycleEventHandler,
)
from codetoreum.application.event_handlers.review_event_handler import (
    ReviewEventHandler,
)
from codetoreum.application.execution_service import ExecutionService
from codetoreum.application.feedback_processor import FeedbackProcessor
from codetoreum.application.issue_intake_service import IssueIntakeService
from codetoreum.application.multi_project_orchestrator import MultiProjectOrchestrator
from codetoreum.application.pipeline_manager import PipelineManager
from codetoreum.application.prompt_building import DefaultPromptBuilder
from codetoreum.application.review_service import ReviewService
from codetoreum.application.work_item_service import WorkItemService
from codetoreum.application.workflow_orchestrator import WorkflowOrchestrator
from codetoreum.application.workflow_run_query_service import WorkflowRunQueryService
from codetoreum.application.workspace_router import WorkspaceRouter
from codetoreum.infrastructure.adapters.factory import (
    AdapterFactory,
)
from codetoreum.infrastructure.adapters.resolver import (
    AdapterConfigurationError,
    AdapterDependencies,
    AdapterResolver,
)
from codetoreum.infrastructure.audit.stores import InMemoryAuditStore
from codetoreum.infrastructure.bootstrap.codetoreum_board_setup import (
    CODETOREUM_BOARD_ID,
)
from codetoreum.infrastructure.dead_letter_queue import DeadLetterQueue
from codetoreum.infrastructure.error_ids import ErrorRegistry
from codetoreum.infrastructure.event_bus import EventBus
from codetoreum.infrastructure.event_store_poller import EventStorePoller
from codetoreum.infrastructure.resilience.config import OperationMode
from codetoreum.infrastructure.resilience.factory import ResilienceFactory
from codetoreum.infrastructure.simulation.bootstrap import SimulationAdapters
from codetoreum.infrastructure.simulation.simulation_config import AdapterSelectionConfig
from codetoreum.ports.input.agent_command import IAgentCommandPort
from codetoreum.ports.input.agent_query import IAgentQueryPort
from codetoreum.ports.input.audit_query import IAuditQueryPort
from codetoreum.ports.input.config_command import IConfigurationCommandPort
from codetoreum.ports.input.config_query import IConfigurationQueryPort
from codetoreum.ports.input.execution_command import IExecutionCommandPort
from codetoreum.ports.input.execution_query import IExecutionQueryPort
from codetoreum.ports.input.issue_intake import IIssueIntakePort
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
from codetoreum.ports.output.prompt_builder import IPromptBuilder

logger = logging.getLogger(__name__)

# Critical execution path slots (6 total)
# event_store excluded: InMemoryEventStore is acceptable for MVP
CRITICAL_ADAPTER_SLOTS = {
    "board",
    "ticket",
    "llm",
    "version_control",
    "container",
    "code_review",
}

# Slots without production implementations (not on MVP critical path)
NON_CRITICAL_SLOTS = {
    "event_store",  # InMemoryEventStore acceptable for MVP
    "review_cycle",
    "pr_review_cycle",
    "systemic_analysis",
    "environment_repair",
}


@dataclass
class ProductionServices:
    """Container for all instantiated production application services."""

    workflow_orchestrator: WorkflowOrchestrator
    execution_service: ExecutionService
    agent_scheduler: AgentScheduler
    pipeline_manager: PipelineManager
    review_service: ReviewService
    feedback_processor: FeedbackProcessor
    workspace_router: WorkspaceRouter
    configuration_service: ConfigurationService
    work_item_service: WorkItemService
    agent_execution_recovery_service: AgentExecutionRecoveryService
    multi_project_orchestrator: MultiProjectOrchestrator
    container_recovery_service: ContainerRecoveryService
    # Default IPromptBuilder implementation (Phase D2). Currently unused;
    # D3 wires it into the rewritten ClaudeCodeAdapter.
    prompt_builder: IPromptBuilder


@dataclass
class ProductionPorts:
    """Container for all input port implementations."""

    workflow_command: IWorkflowCommandPort
    work_item_command: IWorkItemCommandPort
    workflow_definition_command: IWorkflowDefinitionCommandPort
    orchestration_command: IOrchestrationCommandPort
    agent_command: IAgentCommandPort
    execution_command: IExecutionCommandPort
    config_command: IConfigurationCommandPort
    task_query: ITaskQueryPort
    work_item_query: IWorkItemQueryPort
    workflow_query: IWorkflowQueryPort
    workflow_run_query: IWorkflowRunQueryPort
    agent_query: IAgentQueryPort
    execution_query: IExecutionQueryPort
    config_query: IConfigurationQueryPort
    metrics_query: IMetricsQueryPort
    workspace_query: IWorkspaceQueryPort
    audit_query: IAuditQueryPort | None = None


@dataclass
class ProductionInfrastructure:
    """Container for core infrastructure components."""

    event_bus: EventBus
    failed_event_store: Any
    audit_store: Any


@dataclass
class ProductionCredentials:
    """Credentials read from os.environ once at bootstrap Phase 1b.

    Centralises all credential reads so adapters and resolvers never call
    os.environ directly during request processing.
    """

    github_token: str
    anthropic_api_key: str
    claude_code_oauth_token: str
    workspace_base: str


class ProductionApplicationBootstrap:
    """
    Bootstrap the entire application stack in production mode.

    This class wires up:
    1. Validates all adapter credentials before instantiation
    2. Creates all 33 production adapters via AdapterResolver
    3. Validates no mocks exist on critical execution paths
    4. Applies resilience decorators (rate limiting, circuit breaking, timeouts, retries)
    5. Instantiates all 11 application services
    6. Registers event handlers for cross-cutting concerns
    7. Creates FastAPI application with all ports wired

    Usage:
        bootstrap = ProductionApplicationBootstrap(adapter_config)
        await bootstrap.setup()
        app = bootstrap.app
        # ... use app for production
    """

    def __init__(self, adapter_config: AdapterSelectionConfig | None = None):
        """
        Initialize production bootstrap with adapter configuration.

        Args:
            adapter_config: Adapter selection config (uses production defaults if None)

        Raises:
            ValueError: If adapter_config is provided with simulation defaults
        """
        # Create production adapter config with real adapters on critical path
        if adapter_config is None:
            adapter_config = AdapterSelectionConfig(
                board="github",
                ticket="github",
                llm="claude_code",
                version_control="github",
                container="docker",
                code_review="github",
                event_store="elasticsearch",  # Shared event bus for cross-process event distribution
                event_emitter="mock",  # Use mock emitter (in-memory, not capturing for tests).
                # Multi-instance deployments should set this to "redis_pubsub"
                # to propagate domain events across processes via Redis.
                # The single-instance bootstrap does not exercise cross-process
                # event distribution; the in-memory MockEventEmitter remains
                # the default until that scenario becomes part of the harness.
                config_store="elasticsearch",  # Persist project/agent/board configs to ES
                project_manager="elasticsearch",  # Read live project configs from ES
                encryption="local_key",  # Fernet keyed by ENCRYPTION_KEY_BASE64 env var
                lock_service="redis",  # Persistent pipeline lock; survives restart, coordinates instances
                run_registry="redis",  # Persistent active-run records; closes DEF-002 across restart
                agent_repository="elasticsearch",  # Agent catalog survives restart (DEF-008)
                workflow_config="elasticsearch",  # BoardWorkflowTemplate survives restart (DEF-008)
                storage="minio",  # Real S3-compatible artifact persistence (DEF-009)
                # Non-critical slots use mocks (logged as warnings)
                review_cycle="basic",
                pr_review_cycle="basic",
                systemic_analysis="llm",
                environment_repair="mock",
            )

        self.config = adapter_config

        # Components (initialized by setup())
        self.adapters: SimulationAdapters | None = None
        self.infrastructure: ProductionInfrastructure | None = None
        self.services: ProductionServices | None = None
        self.ports: ProductionPorts | None = None
        self.app: FastAPI | None = None

        # Internal state
        self._is_setup = False
        self._adapter_factory: AdapterFactory | None = None
        self._slot_info: dict[str, str] = {}

    def get_adapter_slot_info(self) -> dict[str, str]:
        """
        Get information about all 33 adapter slots and their implementations.

        Returns:
            Dict mapping slot name to concrete class name.

        Raises:
            RuntimeError: If called before setup() completes
        """
        if not self._slot_info:
            message = "get_adapter_slot_info() called before setup() completed"
            raise RuntimeError(message)
        return dict(self._slot_info)

    async def setup(self) -> FastAPI:
        """
        Set up the entire production application stack.

        This method executes bootstrap phases in order:
        - Phase 1: Infrastructure creation (event bus, adapter factory, resolver)
        - Phase 2: Adapter resolution (create all 33 adapters, validate credentials)
        - Phase 3: Critical path enforcement (validate no mocks on critical slots)
        - Phase 4: Resilience decoration (wrap adapters with resilience patterns)
        - Phase 5: Application service instantiation (create 11 services)
        - Phase 5e: Start MultiProjectOrchestrator poll loop (sole orchestration entry point)
        - Phase 6: Input port creation (create 17 port implementations)
        - Phase 7: FastAPI app creation (wire all ports to API endpoints)

        Returns:
            Fully configured FastAPI application ready for production

        Raises:
            AdapterConfigurationError: If credentials are missing/invalid (Phase 1)
            RuntimeError: If critical path validation fails (Phase 3) or already set up
        """
        if self._is_setup:
            message = "Bootstrap already set up"
            raise RuntimeError(message)

        try:
            logger.info("Starting production bootstrap...")

            # Phase 0: Register all domain event types so the event store can deserialize them.
            from codetoreum.infrastructure.event_serialization import auto_register_event_types

            auto_register_event_types()
            logger.info("Phase 0: Registered all domain event types with EventSerializer.")

            # Phase 1: Create infrastructure (event bus first for subscriptions)
            logger.info("Phase 1a: Creating infrastructure...")
            self.infrastructure = self._create_infrastructure()

            # Phase 1b: Create adapter factory and resolver
            logger.info("Phase 1b: Initializing adapter factory and resolver...")
            # Read all credentials once here so no adapter or resolver reads os.environ later.
            import os as _cred_os

            credentials = ProductionCredentials(
                github_token=_cred_os.environ.get("GITHUB_TOKEN", ""),
                anthropic_api_key=_cred_os.environ.get("ANTHROPIC_API_KEY", ""),
                claude_code_oauth_token=_cred_os.environ.get("CLAUDE_CODE_OAUTH_TOKEN", ""),
                workspace_base=_cred_os.environ.get("AGENT_WORKSPACE_BASE", "/tmp/codetoreum-workspaces"),
            )
            self._credentials = credentials
            logger.info("Phase 1b: Credentials loaded from environment.")
            # AdapterFactoryConfig defaults to PRODUCTION mode, which is what we need
            self._adapter_factory = AdapterFactory()

            # Create a fallback event emitter for resolver dependencies
            # (this is used temporarily during adapter resolution, then replaced by the actual resolved emitter)
            from codetoreum.adapters.testing import CapturingMockEventEmitter

            fallback_event_emitter = CapturingMockEventEmitter()

            # Create a minimal engine stub for production
            # (used by resolver to create mocks for non-critical slots like review_cycle)
            from codetoreum.infrastructure.bootstrap.production_engine_stub import ProductionEngineStub

            engine_stub = ProductionEngineStub()

            # Create dependencies for resolver
            adapter_deps = AdapterDependencies(
                event_bus=self.infrastructure.event_bus,
                event_emitter=fallback_event_emitter,
                logger=logger,
                engine=engine_stub,  # type: ignore  # Minimal engine for non-critical mocks
                config=None,  # type: ignore  # No simulation config in production
            )

            resolver = AdapterResolver(self.config, self._adapter_factory, adapter_deps, credentials=credentials)

            # Phase 2: Adapter resolution
            logger.info("Phase 2: Creating 33 adapters (credential validation + resolution)...")
            self.adapters = resolver.resolve_all()

            self._capture_adapter_slot_info(resolver)

            # Phase 2b: Initialize event store (critical for cross-process event distribution)
            logger.info("Phase 2b: Initializing event store for cross-process event distribution...")
            await self._initialize_event_store()

            # Phase 3: Critical path enforcement
            logger.info("Phase 3: Validating no mocks on critical execution paths...")
            self._validate_no_mocks_on_critical_path()

            # Phase 3b: Verify event_emitter is not a test capture adapter
            logger.info("Phase 3b: Verifying production event_emitter is not test-only...")
            self._validate_event_emitter_is_production()

            # Phase 4: Resilience decoration
            logger.info("Phase 4: Applying resilience decorators...")
            self._apply_resilience_decorators()

            # Phase 4b: Create branch_resolution_service with resilience-wrapped adapters
            # Must be constructed after Phase 4 so it holds the decorated ticket_system and
            # version_control references, ensuring rate limiting and circuit breaking apply.
            logger.info("Phase 4b: Creating BranchResolutionAdapter with resilience-wrapped adapters...")
            from codetoreum.adapters.secondary.branch_resolution_adapter import BranchResolutionAdapter

            self.adapters.branch_resolution_service = BranchResolutionAdapter(
                ticket_system=self.adapters.ticket_system,
                version_control=self.adapters.version_control,
                event_emitter=self.adapters.event_emitter,
            )  # type: ignore
            self._slot_info["branch_resolution_service"] = type(self.adapters.branch_resolution_service).__name__

            # Phase 4c: Wire the new ICodingAgent slot (Phase D3/D4).
            # Production uses the new ClaudeCodeAdapter wrapped by
            # ResilientCodingAgentDecorator (constructed inside
            # AdapterResolver.resolve_coding_agent). Must run after Phase 4
            # so the wrapped adapter sees the resilience-decorated container.
            logger.info("Phase 4c: Resolving coding-agent (ICodingAgent) adapter...")
            self.adapters.coding_agent = resolver.resolve_coding_agent(
                prompt_builder=DefaultPromptBuilder(),
                agent_repository=self.adapters.agent_repository,
                work_item_service=self.adapters.work_item_service,
                container=self.adapters.container,
            )
            self._slot_info["coding_agent"] = type(self.adapters.coding_agent).__name__

            # Log non-critical slots with mock implementations
            self._log_non_critical_slots()

            # Phase 5: Create services
            logger.info("Phase 5: Creating 11 application services...")
            self.services = await self._create_services()

            # Phase 5a: Start agent scheduler consumer loop
            logger.info("Phase 5a: Starting agent scheduler consumer loop...")
            await self.services.agent_scheduler.start()

            # Phase 5b: Initialize codetoreum board configuration
            logger.info("Phase 5b: Initializing codetoreum board configuration...")
            await self._initialize_codetoreum_board()

            # Phase 5c: Load user-registered project bootstrap configurations
            logger.info("Phase 5c: Loading project bootstrap configurations...")
            await self._load_bootstrap_projects()

            # Phase 5d removed: WorkItemService is now constructor-injected into
            # the executor in _create_services (see "WorkItemService must be
            # constructed BEFORE the executor" block). No post-hoc swap is
            # required. The phase ordering log line is retained for parity with
            # log-grep checkpoints in the deficiency log; the architectural
            # seam it documented is gone.
            logger.info("Phase 5d: WorkItemService is constructor-injected into executor (no swap needed)")

            # Phase 5e: Start multi-project orchestrator poll loop
            # MPO is the sole orchestration entry point. It polls all enabled projects
            # every 30s, reconciles boards, and delegates per-project work to
            # WorkflowOrchestrator. Starting it here (after Phase 5d) ensures WorkItemService
            # is fully wired before the first poll cycle runs.
            logger.info("Phase 5e: Starting multi-project orchestrator poll loop...")
            import asyncio as _asyncio

            _asyncio.ensure_future(self.services.multi_project_orchestrator.start())
            logger.info("Phase 5e: Multi-project orchestrator poll loop started (background task)")

            # Phase 6: Create ports
            logger.info("Phase 6: Creating 17 input port implementations...")
            self.ports = self._create_ports()

            # Phase 7: Create FastAPI app
            logger.info("Phase 7: Creating FastAPI application...")
            self.app = self._create_fastapi_app()

            self._is_setup = True

            logger.info("Production bootstrap completed successfully")
            return self.app

        except AdapterConfigurationError:
            logger.error(
                "Adapter configuration error during bootstrap",
                exc_info=True,
                extra={"error_id": ErrorRegistry.ERR_INTERNAL_ERROR},
            )
            raise
        except Exception as e:
            logger.error(
                f"Bootstrap setup failed: {e}",
                exc_info=True,
                extra={"error_id": ErrorRegistry.ERR_INTERNAL_ERROR},
            )
            raise

    # =========================================================================
    # Phase 1: Create Infrastructure
    # =========================================================================

    def _create_infrastructure(self) -> ProductionInfrastructure:
        """
        Create core infrastructure components.

        Returns:
            ProductionInfrastructure with event bus and failed event store
        """
        event_bus = EventBus()
        audit_store = InMemoryAuditStore()
        dead_letter_queue = DeadLetterQueue()
        failed_event_store = DeadLetterQueueFailedEventStoreAdapter(dead_letter_queue)

        return ProductionInfrastructure(
            event_bus=event_bus,
            failed_event_store=failed_event_store,
            audit_store=audit_store,
        )

    # =========================================================================
    # Phase 2b: Event Store Initialization
    # =========================================================================

    async def _initialize_event_store(self) -> None:
        """
        Initialize event store for cross-process event distribution.

        This is critical for the trigger CLI and application server to share
        events across process boundaries. Without initialization:
        - Elasticsearch indices won't be created
        - Event publication may fail or events may be lost
        - The trigger→handler cross-process path will be non-functional

        Raises:
            RuntimeError: If adapters not resolved or event store initialization fails
        """
        if not self.adapters or not self.adapters.event_store:
            message = "Event store must be created in Phase 2 before initialization"
            raise RuntimeError(message)

        try:
            from codetoreum.infrastructure.adapters.event_store_factory import initialize_event_store

            logger.debug(f"Initializing event store: {type(self.adapters.event_store).__name__}")
            await initialize_event_store(self.adapters.event_store)
            logger.info(
                "Event store initialized successfully",
                extra={
                    "event_store_type": type(self.adapters.event_store).__name__,
                    "config": str(self.config.event_store),
                },
            )
        except Exception as e:
            message = f"Failed to initialize event store ({self.config.event_store}): {e}"
            logger.error(
                message,
                exc_info=True,
                extra={"error_id": ErrorRegistry.ERR_INTERNAL_ERROR},
            )
            raise RuntimeError(message) from e

    # =========================================================================
    # Phase 3: Critical Path Enforcement
    # =========================================================================

    def _validate_no_mocks_on_critical_path(self) -> None:
        """
        Validate that no mock/in-memory/fake adapters exist on critical paths.

        Inspects the concrete class name of each critical adapter and raises
        RuntimeError if any contains Mock, InMemory, Fake, or Null.

        Raises:
            RuntimeError: If any critical adapter is a mock variant
        """
        if not self.adapters:
            message = "Adapters must be resolved before validation"
            raise RuntimeError(message)

        forbidden_patterns = ("Mock", "InMemory", "Fake", "Null")
        violations = []

        for slot_name in CRITICAL_ADAPTER_SLOTS:
            class_name = self._slot_info.get(slot_name, "")
            for pattern in forbidden_patterns:
                if pattern in class_name:
                    violations.append(f"{slot_name}: {class_name} contains '{pattern}' (not allowed on critical path)")
                    break

        if violations:
            error_msg = "Mock adapters detected on critical execution path:\n" + "\n".join(
                f"  - {v}" for v in violations
            )
            logger.error(
                error_msg,
                exc_info=False,
                extra={"error_id": ErrorRegistry.ERR_INTERNAL_ERROR},
            )
            raise RuntimeError(error_msg)

        logger.info(f"Critical path validation passed ({len(CRITICAL_ADAPTER_SLOTS)} adapters)")

    def _capture_adapter_slot_info(self, resolver: AdapterResolver) -> None:
        """
        Capture concrete class names for all 33 adapter slots.

        Args:
            resolver: Resolver with resolved adapters
        """
        self._slot_info = {}
        for field_name in AdapterSelectionConfig.__dataclass_fields__:
            adapter = self.adapters.__dict__.get(field_name)
            if adapter:
                self._slot_info[field_name] = type(adapter).__name__
            else:
                self._slot_info[field_name] = "None"

        # Also capture branch_resolution_service (not in AdapterSelectionConfig, created separately)
        if self.adapters.branch_resolution_service:
            self._slot_info["branch_resolution_service"] = type(self.adapters.branch_resolution_service).__name__

    def _validate_event_emitter_is_production(self) -> None:
        """
        Validate that the resolved event_emitter is not a test-only capture adapter.

        The production bootstrap creates a CapturingMockEventEmitter as a fallback
        during adapter resolution. This method verifies that it was replaced with
        the actual configured event_emitter (e.g., "mock" not "capturing").

        Raises:
            RuntimeError: If event_emitter is CapturingMockEventEmitter (test-only)
        """
        if not self.adapters or not self.adapters.event_emitter:
            message = "event_emitter not resolved"
            raise RuntimeError(message)

        from codetoreum.adapters.testing import CapturingMockEventEmitter

        if isinstance(self.adapters.event_emitter, CapturingMockEventEmitter):
            message = (
                "Production event_emitter is CapturingMockEventEmitter (test-only). "
                "This means the fallback adapter from resolver dependencies is still in use. "
                "Verify that ProductionApplicationBootstrap.adapter_config sets "
                "event_emitter to a production implementation (e.g., 'mock', not 'capturing'). "
                "Events emitted through this adapter will go to in-memory test storage "
                "instead of production systems."
            )
            logger.error(
                message,
                exc_info=False,
                extra={"error_id": ErrorRegistry.ERR_INTERNAL_ERROR},
            )
            raise RuntimeError(message)

        logger.debug(f"Production event_emitter verified: {type(self.adapters.event_emitter).__name__}")

    def _log_non_critical_slots(self) -> None:
        """Log warnings for non-critical slots with mock implementations."""
        for slot_name in NON_CRITICAL_SLOTS:
            class_name = self._slot_info.get(slot_name, "Unknown")
            if any(pattern in class_name for pattern in ("Mock", "InMemory")):
                logger.warning(
                    f"Adapter slot '{slot_name}' is using {class_name} "
                    f"(simulation stub, not required for MVP execution path)",
                    extra={"slot_name": slot_name, "adapter": class_name},
                )

    # =========================================================================
    # Phase 4: Resilience Decoration
    # =========================================================================

    def _apply_resilience_decorators(self) -> None:
        """
        Apply resilience decorators to critical adapters.

        Wraps adapters in order: rate limiter → circuit breaker → timeout → retry
        """
        if not self.adapters:
            message = "Adapters must be resolved before applying resilience"
            raise RuntimeError(message)

        resilience_factory = ResilienceFactory(mode=OperationMode.PRODUCTION)

        # Apply resilience to critical adapters that support it
        # Ticket system (board and ticket both interact with external system)
        if self.adapters.ticket_system:
            # Store raw adapter before wrapping so bootstrap can call lifecycle methods
            # (e.g. register_project_repo) that are not part of the ITicketSystem port.
            self._raw_ticket_adapter = self.adapters.ticket_system
            self.adapters.ticket_system = resilience_factory.create_resilient_ticket_system(self.adapters.ticket_system)
            logger.debug("Applied resilience to ticket system adapter")

        # LLM provider resilience retired in Phase D5 — the ICodingAgent
        # adapter is wrapped by ResilientCodingAgentDecorator instead.

        # Repository
        if self.adapters.repository:
            self.adapters.repository = resilience_factory.create_resilient_repository(self.adapters.repository)
            logger.debug("Applied resilience to repository adapter")

        # Container
        if self.adapters.container:
            self.adapters.container = resilience_factory.create_resilient_container(self.adapters.container)
            logger.debug("Applied resilience to container adapter")

        # Version control (used by BranchResolutionAdapter constructed in Phase 4b)
        if self.adapters.version_control:
            self.adapters.version_control = resilience_factory.create_resilient_version_control(
                self.adapters.version_control
            )
            logger.debug("Applied resilience to version control adapter")

        logger.info("Resilience decorators applied to critical adapters")

    # =========================================================================
    # Phase 5: Create Application Services
    # =========================================================================

    async def _create_services(self) -> ProductionServices:
        """
        Create all 11 application services with proper dependencies.

        Returns:
            ProductionServices with all services configured
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

        # Execution Service — Phase D5: container/log/storage concerns
        # retired; ExecutionService delegates to ICodingAgent. Credentials
        # injection moved into the coding-agent adapter chain (it owns
        # subprocess invocation now).
        execution_service = ExecutionService(
            coding_agent=self.adapters.coding_agent,
            event_store=self.adapters.event_store,
            vcs=self.adapters.version_control,
        )

        # Workspace Router
        workspace_router = WorkspaceRouter(
            vcs=self.adapters.version_control,
            container=self.adapters.container,
            event_store=self.adapters.event_store,
            branch_resolution_service=self.adapters.branch_resolution_service,
        )

        # Agent Execution Recovery Service
        recovery_service = AgentExecutionRecoveryService(
            board_service=self.adapters.board,
            event_store=self.adapters.event_store,
            run_registry=self.adapters.run_registry,
            failed_event_store=self.infrastructure.failed_event_store,
        )

        # WorkItemService must be constructed BEFORE the executor so it can
        # be passed in as a constructor argument. Previously this lived later
        # in _create_services and Phase 5d swapped self.adapters.agent_executor
        # ._work_item_service after the fact. The post-hoc swap depended on a
        # private attribute and broke if the executor cached the reference.
        work_item_service = WorkItemService(
            event_store=self.adapters.event_store,
        )

        # For production, use the execution service executor with a real time clock
        import os as _os

        from codetoreum.adapters.secondary.execution_service_agent_executor import (
            ExecutionServiceAgentExecutor,
        )
        from codetoreum.infrastructure.simulation.simulation_clock import RealTimeClock

        _workspace_base = _os.getenv("AGENT_WORKSPACE_BASE", "/tmp/codetoreum-workspaces")
        Path(_workspace_base).mkdir(parents=True, exist_ok=True)
        execution_service_executor = ExecutionServiceAgentExecutor(
            execution_service=execution_service,
            workspace_router=workspace_router,
            config_store=self.adapters.config_store,
            agent_repository=self.adapters.agent_repository,
            work_item_service=work_item_service,
            run_registry=self.adapters.run_registry,
            branch_tracker=self.adapters.branch_tracker,
            vcs=self.adapters.version_control,
            clock=RealTimeClock(),
            event_bus=self.infrastructure.event_bus,
            recovery_service=recovery_service,
            workflow_config_service=self.adapters.workflow_config,
            workspace_base_dir=_workspace_base,
            default_board_id=CODETOREUM_BOARD_ID,
        )
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

        # Agent Scheduler
        task_queue = InMemoryTaskQueue()
        from codetoreum.infrastructure.bootstrap.agent_scheduler_implementations import (
            ProductionProjectConfiguration,
            ProductionRateLimiter,
            ProductionResourceMonitor,
            ProductionSchedulingEvents,
        )

        resource_monitor = ProductionResourceMonitor()
        rate_limiter = ProductionRateLimiter()
        project_config = ProductionProjectConfiguration()
        scheduling_events = ProductionSchedulingEvents(event_emitter=self.adapters.event_emitter)

        # NOTE: The scheduler is constructed with an executor and its consumer
        # loop is started below, but `WorkflowOrchestrator` is built with
        # `dispatch_via_task_queue=False` so nothing actually enqueues to it.
        # BoardColumnEventHandler is the production dispatch path. Flipping
        # the orchestrator flag without first disabling BEH's direct dispatch
        # would produce double-dispatch (INV-06). This wiring is the "armed
        # but unused" seam — see AgentScheduler class docstring.
        agent_scheduler = AgentScheduler(
            task_queue=task_queue,
            resource_monitor=resource_monitor,
            rate_limiter=rate_limiter,
            config=project_config,
            scheduling_events=scheduling_events,
            event_store=self.adapters.event_store,
            agent_executor=execution_service_executor,
        )

        # Workflow Orchestrator dependencies
        from codetoreum.infrastructure.bootstrap.workflow_services import (
            ProductionDecisionEvents,
            ProductionProjectsAPI,
            ProductionWorkflowStateManager,
        )

        workflow_state_manager = ProductionWorkflowStateManager()
        decision_events = ProductionDecisionEvents()
        projects_api = ProductionProjectsAPI()

        # Conversational Loop Orchestrator — deferred in Phase D5. The
        # orchestrator's continue_conversation call site still expects a
        # retired ILLMProvider; wiring it to ICodingAgent is a separate
        # migration. Until then, conversational columns are not wired in
        # the production bootstrap. WorkflowOrchestrator accepts
        # conversational_loop_orchestrator=None and skips the conversational
        # initialization path when the column type matches.
        conversational_loop_orchestrator: ConversationalLoopOrchestrator | None = None
        self.conversational_loop_orchestrator = conversational_loop_orchestrator

        workflow_orchestrator = WorkflowOrchestrator(
            task_queue=task_queue,
            config=project_config,
            workflow_state=workflow_state_manager,
            decision_events=decision_events,
            event_store=self.adapters.event_store,
            ticket_system=self.adapters.ticket_system,
            projects_api=projects_api,
            event_bus=self.infrastructure.event_bus,
            board_service=self.adapters.board,
            workflow_config=self.adapters.workflow_config,
            conversational_loop_orchestrator=conversational_loop_orchestrator,
            dispatch_via_task_queue=False,  # BoardColumnEventHandler owns dispatch in production
        )

        # WorkItemService was instantiated earlier (before the executor) so it
        # could be passed via constructor. No second creation needed.

        # Container Recovery Service
        container_recovery_service = ContainerRecoveryService(
            recovery_adapter=self.adapters.container_recovery,
            event_emitter=self.adapters.event_emitter,
            container_timeout_hours=2,
        )

        # Multi-Project Orchestrator
        multi_project_orchestrator = MultiProjectOrchestrator(
            project_manager=self.adapters.project_manager,
            workflow_orchestrator=workflow_orchestrator,
            board_service=self.adapters.board,
            event_emitter=self.adapters.event_emitter,
            poll_interval_seconds=30,
        )

        logger.info("Created all 11 application services with production adapters")

        return ProductionServices(
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
            prompt_builder=DefaultPromptBuilder(),
        )

    # =========================================================================
    # Phase 6: Create Input Ports
    # =========================================================================

    def _create_ports(self) -> ProductionPorts:
        """
        Create all 17 input port implementations.

        Returns:
            ProductionPorts with all port implementations
        """
        if not self.adapters or not self.services:
            message = "Adapters and services must be created first"
            raise RuntimeError(message)

        # Use event-store-backed WorkItemService for both command and query ports
        # so REST API callers and the executor share the same persistence layer.
        work_item_command = self.services.work_item_service
        work_item_query = self.services.work_item_service
        agent_command = MockAgentCommandAdapter()
        agent_query = MockAgentQueryAdapter()
        for _agent in self.adapters.agent_repository.get_all_sync():
            agent_query.add_agent(_agent)
        execution_command = MockExecutionCommandAdapter()
        execution_query = MockExecutionQueryAdapter(
            agent_executor=self.adapters.agent_executor,
        )
        config_query = MockConfigQueryAdapter(
            config_store=self.adapters.config_store,
        )
        metrics_query = self._create_metrics_query_adapter()
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
        audit_query = MockAuditQueryAdapter(audit_store=self.infrastructure.audit_store)

        logger.info("Created all 17 input port implementations")

        return ProductionPorts(
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

    def _create_metrics_query_adapter(self) -> IMetricsQueryPort:
        """
        Create metrics query adapter.

        For production, we can't use the engine-based approach.
        Import the base class and create a simple adapter.
        """
        from codetoreum.adapters.primary.input_port_adapters.mock import (
            MockMetricsQueryAdapter,
        )

        return MockMetricsQueryAdapter(metrics_adapter=self.adapters.metrics)

    # =========================================================================
    # Phase 5c: Load User-Registered Bootstrap Projects
    # =========================================================================

    async def _load_bootstrap_projects(self) -> None:
        """Load project registrations from bootstrap/ JSON files into in-memory services."""
        from pathlib import Path

        from codetoreum.infrastructure.bootstrap.project_bootstrap_loader import load_bootstrap_dir

        bootstrap_dir = Path(__file__).parents[4] / "bootstrap"
        try:
            count = await load_bootstrap_dir(
                bootstrap_dir,
                agent_repository=self.adapters.agent_repository,
                workflow_config=self.adapters.workflow_config,
                config_store=self.adapters.config_store,
                coding_agent=getattr(self.adapters, "coding_agent", None),
            )
            if count:
                logger.info(f"Loaded {count} project bootstrap configuration(s) from {bootstrap_dir}")
        except Exception as e:
            logger.warning(
                f"Failed to load bootstrap projects: {e}",
                exc_info=True,
                extra={"error_id": "ERR_BOOTSTRAP_PROJECT_LOAD_FAILURE"},
            )

        # Register each project's github_repo with the raw ticket adapter so the
        # adapter resolves per-project repos without a global GITHUB_REPO env var.
        # The factory already wraps the adapter with resilience, so unwrap to the
        # concrete adapter that has register_project_repo().
        raw_adapter = getattr(self, "_raw_ticket_adapter", None)
        while raw_adapter is not None and not hasattr(raw_adapter, "register_project_repo"):
            raw_adapter = getattr(raw_adapter, "_wrapped", None)
        if raw_adapter is not None and hasattr(raw_adapter, "register_project_repo") and self.adapters.config_store:
            try:
                project_configs = await self.adapters.config_store.list_projects()
                for cfg in project_configs:
                    if cfg.github_repo:
                        raw_adapter.register_project_repo(cfg.id, cfg.github_repo)
                        logger.info(
                            f"Registered project repo '{cfg.github_repo}' for project '{cfg.id}' " "with ticket adapter"
                        )
            except Exception as e:
                logger.warning(
                    f"Failed to register project repos with ticket adapter: {e}",
                    exc_info=True,
                    extra={"error_id": "ERR_BOOTSTRAP_PROJECT_REPO_REGISTRATION_FAILURE"},
                )

    # =========================================================================
    # Phase 5b: Initialize Codetoreum Board Configuration
    # =========================================================================

    async def _initialize_codetoreum_board(self) -> None:
        """
        Initialize the workflow template for the codetoreum repository board.

        This enables dogfooding of the orchestration platform. The board configuration
        is stored in the workflow_config service (in-memory for MVP, database-backed
        in future versions).

        CRITICAL: Board initialization failure disables all workflow automation.
        If the board template cannot be created or saved, BoardColumnEventHandler
        will receive no configuration (None) for every event and silently skip
        all automation. This is a hard failure requiring immediate attention.

        Safe to call multiple times (idempotent) — overwrites existing template
        with the same board_id.

        Raises:
            RuntimeError: If board initialization fails (prevents silent automation failure)
        """
        if not self.adapters:
            message = "Adapters must be created first"
            raise RuntimeError(message)

        try:
            from codetoreum.infrastructure.bootstrap.codetoreum_board_setup import (
                create_codetoreum_board_template,
            )

            template = create_codetoreum_board_template()
            await self.adapters.workflow_config.save_board_workflow_template(template)

            logger.info(
                "Initialized codetoreum board workflow template",
                extra={
                    "board_id": template.board_id,
                    "project_id": template.project_id,
                    "column_count": len(template.columns),
                },
            )
        except Exception as e:
            message = (
                f"Failed to initialize codetoreum board configuration: {e}\n"
                "This is CRITICAL: Without board configuration, BoardColumnEventHandler "
                "cannot find the workflow template and will silently skip ALL workflow automation."
            )
            logger.error(
                message,
                exc_info=True,
                extra={"error_id": ErrorRegistry.ERR_INTERNAL_ERROR},
            )
            raise RuntimeError(message) from e

    # =========================================================================
    # Phase 7: Create FastAPI Application and Register Event Handlers
    # =========================================================================

    def _create_fastapi_app(self) -> FastAPI:
        """
        Create FastAPI application with all ports wired.

        Returns:
            Configured FastAPI application ready for production
        """
        if not self.adapters or not self.ports or not self.infrastructure or not self.services:
            message = "All components must be created first"
            raise RuntimeError(message)

        # Validate no None ports before creating app
        port_fields = {
            "workflow_command": self.ports.workflow_command,
            "task_query": self.ports.task_query,
            "config_command": self.ports.config_command,
            "config_query": self.ports.config_query,
            "metrics_query": self.ports.metrics_query,
            "workspace_query": self.ports.workspace_query,
            "work_item_command": self.ports.work_item_command,
            "work_item_query": self.ports.work_item_query,
            "workflow_query": self.ports.workflow_query,
            "workflow_run_query": self.ports.workflow_run_query,
            "workflow_definition_command": self.ports.workflow_definition_command,
            "orchestration_command": self.ports.orchestration_command,
            "agent_command": self.ports.agent_command,
            "agent_query": self.ports.agent_query,
            "execution_command": self.ports.execution_command,
            "execution_query": self.ports.execution_query,
        }

        none_ports = [name for name, port in port_fields.items() if port is None]
        if none_ports:
            message = f"Cannot create app with None ports: {', '.join(none_ports)}"
            raise RuntimeError(message)

        # Create config service adapter
        config_service_interface = MockConfigServiceAdapter(self.services.configuration_service)

        # Create logger adapter
        logger_interface = MockLoggerAdapter()

        # Create event store poller for cross-process event distribution
        event_store_poller = EventStorePoller(
            event_store=self.adapters.event_store,
            event_bus=self.infrastructure.event_bus,
            poll_interval_seconds=5.0,
        )
        logger.debug("Created event store poller for cross-process event distribution")

        # Create issue intake service for GitHub webhook event handling
        issue_intake_service: IIssueIntakePort = IssueIntakeService(
            board_service=self.adapters.board,
            workflow_config_service=self.adapters.workflow_config,
        )
        logger.debug("Created issue intake service for webhook event handling")

        # Create FastAPI app
        import os as _os

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
            auth_secret_key=_os.getenv("CODETOREUM_SECRET_KEY"),
            disable_auth=False,  # Production auth enabled
            cors_origins=None,  # Use environment-based CORS config
            container_recovery_service=self.services.container_recovery_service,
            adapter_slot_info=self._slot_info,
            event_store_poller=event_store_poller,
            issue_intake_port=issue_intake_service,
        )

        logger.info("Created FastAPI application with all ports wired")

        # Register event handlers
        self._register_board_column_handler()
        self._register_conversational_loop_orchestrator()
        self._register_pr_review_cycle_handlers()
        self._register_review_event_handler()

        return app

    def _register_board_column_handler(self) -> None:
        """Register board column event handler for agent execution and auto-progression."""
        if not self.adapters or not self.infrastructure or not self.services:
            logger.warning("Cannot register board column handler: components not ready")
            return

        handler = BoardColumnEventHandler(
            board_service=self.adapters.board,
            lock_service=self.adapters.lock_service,
            workflow_config=self.adapters.workflow_config,
            agent_executor=self.adapters.agent_executor,
            event_bus=self.infrastructure.event_bus,
            event_store=self.adapters.event_store,
            run_registry=self.adapters.run_registry,
            event_emitter=self.adapters.event_emitter,
            recovery_service=self.services.agent_execution_recovery_service,
            work_item_service=self.services.work_item_service,
        )

        self.infrastructure.event_bus.register_handler(handler)
        # `register_handler` subscribes BoardColumnEventHandler to both
        # WorkItemColumnChangedEvent and AgentExecutionCompletedEvent. The
        # latter replaces the legacy `set_completion_handler` callback wiring:
        # ExecutionServiceAgentExecutor publishes AgentExecutionCompletedEvent
        # on the event bus when it finishes processing a work item, and the
        # handler runs auto-progression in its handle_agent_execution_completed
        # bridge. See INV-05 in `bootstrap/ARCHITECTURE.md` §6.
        logger.info(
            "Registered BoardColumnEventHandler with event bus "
            "(WorkItemColumnChangedEvent + AgentExecutionCompletedEvent)"
        )

    def _register_conversational_loop_orchestrator(self) -> None:
        """Register conversational loop orchestrator to handle column changes."""
        if not self.infrastructure or not getattr(self, "conversational_loop_orchestrator", None):
            # Deferred in Phase D5 — see the wiring site above for context.
            return

        self.infrastructure.event_bus.subscribe(
            "WorkItemColumnChangedEvent",
            self.conversational_loop_orchestrator.handle_column_change_event,
        )
        logger.info("Registered ConversationalLoopOrchestrator to WorkItemColumnChangedEvent")

    def _register_pr_review_cycle_handlers(self) -> None:
        """Register PR review cycle event handlers."""
        if not self.adapters or not self.infrastructure:
            logger.warning("Cannot register PR review cycle handlers: components not ready")
            return

        # PR Review Cycle Dispatch Handler
        pr_dispatch_handler = PRReviewCycleDispatchHandler(
            pr_review_cycle=self.adapters.pr_review_cycle,
            workflow_config=self.adapters.workflow_config,
            work_item_service=self.services.work_item_service,
            active_workflow_run_registry=self.adapters.run_registry,
        )
        self.infrastructure.event_bus.register_handler(pr_dispatch_handler)
        logger.info("Registered PRReviewCycleDispatchHandler with event bus")

        # PR Review Cycle Event Handler
        pr_event_handler = PRReviewCycleEventHandler(
            board_service=self.adapters.board,
        )
        self.infrastructure.event_bus.register_handler(pr_event_handler)
        logger.info("Registered PRReviewCycleEventHandler with event bus")

    def _register_review_event_handler(self) -> None:
        """Register review cycle event handler."""
        if not self.adapters or not self.infrastructure:
            logger.warning("Cannot register review event handler: components not ready")
            return

        handler = ReviewEventHandler(
            review_service=self.services.review_service,
            ci_pipeline_service=self.adapters.ci_pipeline,
        )
        self.infrastructure.event_bus.register_handler(handler)
        logger.info("Registered ReviewEventHandler with event bus")

    # =========================================================================
    # Teardown
    # =========================================================================

    async def teardown(self) -> None:
        """
        Clean up all resources.

        Performs cleanup in order:
        - Stop agent scheduler consumer loop
        - Stop multi-project orchestrator poll loop
        - Close event store (closes Elasticsearch client if applicable)
        - Log final event bus statistics
        - Clear adapter references
        - Reset state

        Raises:
            Exception: Re-raises any exception with full context during cleanup.
                     The _is_setup flag is only cleared if all cleanup steps succeed.
        """
        if not self._is_setup:
            return

        try:
            logger.info("Tearing down production bootstrap...")

            # Stop agent scheduler consumer loop
            if self.services and self.services.agent_scheduler:
                logger.info("Stopping agent scheduler consumer loop...")
                try:
                    await self.services.agent_scheduler.stop()
                except Exception as e:
                    logger.error(
                        f"Error stopping agent scheduler: {e}",
                        extra={"error_id": ErrorRegistry.ERR_INTERNAL_ERROR},
                        exc_info=True,
                    )
                    # Continue with other cleanup even if scheduler stop fails

            # Stop multi-project orchestrator poll loop
            if self.services and self.services.multi_project_orchestrator:
                logger.info("Stopping multi-project orchestrator poll loop...")
                try:
                    await self.services.multi_project_orchestrator.stop()
                except Exception as e:
                    logger.error(
                        f"Error stopping multi-project orchestrator: {e}",
                        extra={"error_id": ErrorRegistry.ERR_INTERNAL_ERROR},
                        exc_info=True,
                    )
                    # Continue with other cleanup even if orchestrator stop fails

            # Close event store (closes Elasticsearch client for production deployments)
            if self.adapters and self.adapters.event_store:
                logger.info("Closing event store...")
                from codetoreum.infrastructure.adapters.event_store_factory import close_event_store

                try:
                    await close_event_store(self.adapters.event_store)
                except Exception as e:
                    logger.error(
                        f"Error closing event store: {e}",
                        extra={"error_id": ErrorRegistry.ERR_INTERNAL_ERROR},
                        exc_info=True,
                    )
                    # Continue with other cleanup even if event store close fails

            # Log final event bus statistics
            if self.infrastructure and self.infrastructure.event_bus:
                stats = self.infrastructure.event_bus.get_statistics()
                logger.info(
                    f"Event bus statistics: "
                    f"events_published={stats.get('events_published', 0)}, "
                    f"events_handled={stats.get('events_handled', 0)}, "
                    f"handler_errors={stats.get('handler_errors', 0)}"
                )

            # Clear references
            self.app = None
            self.ports = None
            self.services = None
            self.infrastructure = None
            self.adapters = None
            self._adapter_factory = None

            self._is_setup = False
            logger.info("Production bootstrap teardown complete")

        except Exception as e:
            logger.error(
                f"Error during teardown: {e}",
                extra={"error_id": ErrorRegistry.ERR_INTERNAL_ERROR},
                exc_info=True,
            )
            # Re-raise to ensure caller (typically CLI) knows teardown failed
            raise
