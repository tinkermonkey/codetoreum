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
import subprocess
from datetime import UTC, datetime
from typing import Any

from fastapi import FastAPI

from codetoreum.adapters.primary.fastapi_app import create_app
from codetoreum.adapters.primary.input_port_adapters.mock.mock_task_query_adapter import (
    MockTaskQueryAdapter,
)
from codetoreum.adapters.secondary.elasticsearch_workflow_config_service import (
    ElasticsearchWorkflowConfigService,
)
from codetoreum.adapters.secondary.failed_event_store_adapter import (
    DeadLetterQueueFailedEventStoreAdapter,
)
from codetoreum.adapters.testing.execution_service_agent_executor import ExecutionServiceAgentExecutor
from codetoreum.application.agent_execution_recovery_service import AgentExecutionRecoveryService
from codetoreum.application.agent_scheduler import (
    AgentScheduler,
    IProjectConfiguration,
    IRateLimiter as ISchedulerRateLimiter,
    IResourceMonitor,
    ISchedulingEvents,
    ITaskQueue,
    Task,
)
from codetoreum.application.configuration_service import ConfigurationService
from codetoreum.application.container_recovery_service import ContainerRecoveryService
from codetoreum.application.conversational_loop_orchestrator import ConversationalLoopOrchestrator
from codetoreum.application.execution_service import ExecutionService
from codetoreum.application.feedback_processor import FeedbackProcessor
from codetoreum.application.multi_project_orchestrator import MultiProjectOrchestrator
from codetoreum.application.pipeline_manager import PipelineManager
from codetoreum.application.review_service import ReviewService
from codetoreum.application.work_item_service import WorkItemService
from codetoreum.application.workflow_orchestrator import WorkflowOrchestrator
from codetoreum.application.workflow_run_query_service import WorkflowRunQueryService
from codetoreum.application.workspace_router import WorkspaceRouter
from codetoreum.config.codetoreum_pipeline import create_codetoreum_pipeline_template
from codetoreum.infrastructure.adapters.factory import AdapterFactory, AdapterFactoryConfig
from codetoreum.infrastructure.adapters.resolver import AdapterDependencies, AdapterResolver
from codetoreum.infrastructure.bootstrap.production_config import create_production_adapter_config
from codetoreum.infrastructure.dead_letter_queue import DeadLetterQueue
from codetoreum.infrastructure.error_ids import ErrorRegistry
from codetoreum.infrastructure.event_bus import EventBus
from codetoreum.infrastructure.resilience import OperationMode
from codetoreum.infrastructure.resilience.factory import ResilienceFactory
from codetoreum.ports.output.config_store import AgentConfig, IConfigStore

logger = logging.getLogger(__name__)


# Production implementations for AgentScheduler dependencies


class ProductionTaskQueue(ITaskQueue):
    """Production task queue implementation.

    Maintains an in-memory queue of tasks for agent execution.
    Tasks are enqueued and retrieved by the agent scheduler.
    """

    def __init__(self, queue_service: Any = None) -> None:
        """Initialize task queue.

        Args:
            queue_service: Optional queue service adapter (currently unused)
        """
        self.queue_service = queue_service
        self._task_store: dict[str, Task] = {}
        self._agent_queues: dict[str, list[str]] = {}

    async def enqueue(self, task: Task) -> str:
        """Enqueue a task for agent execution.

        Stores the task and tracks it by agent queue.

        Args:
            task: Task to enqueue

        Returns:
            Task ID
        """
        # Store task
        self._task_store[task.id] = task

        # Add to agent queue
        if task.agent not in self._agent_queues:
            self._agent_queues[task.agent] = []
        self._agent_queues[task.agent].append(task.id)

        logger.info(
            f"Task {task.id} enqueued for agent {task.agent}",
            extra={"task_id": task.id, "agent": task.agent, "project": task.project},
        )
        return task.id

    async def get_queue_depth(self, agent: str) -> int:
        """Get number of queued tasks for an agent.

        Args:
            agent: Agent identifier

        Returns:
            Number of queued tasks
        """
        return len(self._agent_queues.get(agent, []))


class ProductionRateLimiter(ISchedulerRateLimiter):
    """Production rate limiter implementation.

    Uses sliding window algorithm to enforce request-per-minute limits.
    """

    def __init__(self, rate_limit_rpm: int = 60) -> None:
        """Initialize rate limiter with rate limit.

        Args:
            rate_limit_rpm: Requests per minute limit
        """
        self.rate_limit_rpm = rate_limit_rpm
        self._call_times: dict[str, list[float]] = {}

    async def acquire(self, agent: str, tokens: int = 1) -> bool:
        """Try to acquire rate limit tokens.

        Uses sliding window algorithm to track calls over 1-minute windows.

        Args:
            agent: Agent identifier
            tokens: Number of tokens to acquire (default 1)

        Returns:
            True if tokens acquired, False if rate limited
        """
        import time

        now = time.time()
        if agent not in self._call_times:
            self._call_times[agent] = []

        # Remove calls older than 1 minute
        minute_ago = now - 60
        self._call_times[agent] = [t for t in self._call_times[agent] if t > minute_ago]

        # Check if within limit
        if len(self._call_times[agent]) < self.rate_limit_rpm:
            self._call_times[agent].append(now)
            logger.debug(
                f"Rate limit acquired for agent {agent}",
                extra={"agent": agent, "calls_in_window": len(self._call_times[agent])},
            )
            return True

        logger.warning(
            f"Rate limit exceeded for agent {agent}",
            extra={"agent": agent, "limit": self.rate_limit_rpm},
        )
        return False

    async def get_retry_after(self, agent: str) -> int | None:
        """Get retry after seconds if rate limited.

        Args:
            agent: Agent identifier

        Returns:
            Seconds to wait before retry, or None if not rate limited
        """
        import time

        if self._call_times.get(agent):
            oldest_call = min(self._call_times[agent])
            retry_after_time = oldest_call + 60
            seconds_to_wait = int(retry_after_time - time.time())
            return max(1, seconds_to_wait)
        return None


class ProductionResourceMonitor(IResourceMonitor):
    """Production resource monitor implementation.

    Monitors Docker resource availability and tracks running agent instances.
    """

    def __init__(self) -> None:
        """Initialize resource monitor."""
        self._docker_available: bool | None = None

    async def check_dev_container_available(self, project: str) -> bool:
        """Check if Docker is available for running containers.

        Performs a health check on Docker daemon to ensure containers
        can be started.

        Args:
            project: Project identifier

        Returns:
            True if Docker is available, False otherwise
        """
        # Check Docker availability once per lifecycle
        if self._docker_available is None:
            self._docker_available = await self._check_docker_health()
        return self._docker_available

    async def get_running_agents(self, agent: str) -> int:
        """Get number of currently running agent containers.

        Queries Docker API to count containers running for this agent.

        Args:
            agent: Agent identifier

        Returns:
            Number of running agent containers
        """
        try:
            # Query Docker for containers with agent label
            result = subprocess.run(
                [
                    "docker",
                    "ps",
                    "--filter",
                    f"label=agent={agent}",
                    "--quiet",
                ],
                capture_output=True,
                text=True,
                timeout=5,
            )

            if result.returncode == 0:
                # Count lines (each line is a container ID)
                container_count = len([line for line in result.stdout.strip().split("\n") if line])
                logger.debug(
                    f"Found {container_count} running containers for agent {agent}",
                    extra={"agent": agent, "count": container_count},
                )
                return container_count
            else:
                logger.warning(
                    f"Failed to query Docker for agent {agent}: {result.stderr}",
                    extra={"agent": agent, "error": result.stderr},
                )
                return 0
        except subprocess.TimeoutExpired:
            logger.error(
                f"Docker query timeout for agent {agent}",
                extra={"agent": agent, "error_id": ErrorRegistry.ERR_DOCKER_TIMEOUT},
            )
            return 0
        except Exception as e:
            logger.error(
                f"Error querying Docker for agent {agent}: {e}",
                exc_info=True,
                extra={"agent": agent, "error_id": ErrorRegistry.ERR_DOCKER_ERROR},
            )
            return 0

    async def _check_docker_health(self) -> bool:
        """Check if Docker daemon is responsive.

        Attempts a Docker info command to verify daemon connectivity.

        Returns:
            True if Docker is available and responsive
        """
        try:
            result = subprocess.run(
                ["docker", "info"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            is_healthy = result.returncode == 0
            if is_healthy:
                logger.info("Docker health check passed")
            else:
                logger.warning(f"Docker health check failed: {result.stderr}")
            return is_healthy
        except subprocess.TimeoutExpired:
            logger.error(
                "Docker health check timeout",
                extra={"error_id": ErrorRegistry.ERR_DOCKER_TIMEOUT},
            )
            return False
        except Exception as e:
            logger.error(
                f"Docker health check failed: {e}",
                exc_info=True,
                extra={"error_id": ErrorRegistry.ERR_DOCKER_ERROR},
            )
            return False


class ProductionSchedulingEvents(ISchedulingEvents):
    """Production scheduling events implementation.

    Emits domain events to the event bus for all scheduling state changes.
    This ensures that task scheduling decisions are permanently recorded
    in the event store and can be audited.
    """

    def __init__(self, event_bus: EventBus) -> None:
        """Initialize with event bus for emitting events.

        Args:
            event_bus: Event bus for publishing scheduling events
        """
        self.event_bus = event_bus

    async def emit_task_queued(
        self,
        task_id: str,
        agent: str,
        project: str,
        priority: Any,
        reason: str,
    ) -> None:
        """Emit task queued event to event bus.

        Records that a task was successfully enqueued for agent execution.

        Args:
            task_id: Unique task identifier
            agent: Agent that will execute the task
            project: Project context for the task
            priority: Task priority level
            reason: Reason for queueing the task
        """
        # Create and publish event
        from codetoreum.domain.events.adapter_events import CodetoreumEvent
        from uuid import uuid4

        event = CodetoreumEvent(
            type="task.queued",
            timestamp=datetime.now(UTC).isoformat(),
            source="agent_scheduler",
            event_id=str(uuid4()),
            correlation_id=task_id,
        )

        try:
            await self.event_bus.publish(event)
            logger.info(
                f"Task queued event published: {task_id}",
                extra={"task_id": task_id, "agent": agent, "project": project, "priority": str(priority)},
            )
        except Exception as e:
            logger.error(
                f"Failed to publish task queued event for {task_id}: {e}",
                exc_info=True,
                extra={"task_id": task_id, "error_id": ErrorRegistry.ERR_EVENT_BUS_ERROR},
            )

    async def emit_task_throttled(self, agent: str, project: str, reason: str, retry_after: int) -> None:
        """Emit task throttled event to event bus.

        Records that a task was throttled due to rate limiting.

        Args:
            agent: Agent that was throttled
            project: Project context
            reason: Reason for throttling
            retry_after: Seconds to wait before retry
        """
        from codetoreum.domain.events.adapter_events import CodetoreumEvent
        from uuid import uuid4

        event = CodetoreumEvent(
            type="task.throttled",
            timestamp=datetime.now(UTC).isoformat(),
            source="agent_scheduler",
            event_id=str(uuid4()),
        )

        try:
            await self.event_bus.publish(event)
            logger.warning(
                f"Task throttled event published for agent {agent}",
                extra={"agent": agent, "project": project, "reason": reason, "retry_after": retry_after},
            )
        except Exception as e:
            logger.error(
                f"Failed to publish task throttled event for agent {agent}: {e}",
                exc_info=True,
                extra={"agent": agent, "error_id": ErrorRegistry.ERR_EVENT_BUS_ERROR},
            )

    async def emit_task_rejected(self, agent: str, project: str, reason: str) -> None:
        """Emit task rejected event to event bus.

        Records that a task was rejected and cannot be executed.

        Args:
            agent: Agent that rejected the task
            project: Project context
            reason: Reason for rejection
        """
        from codetoreum.domain.events.adapter_events import CodetoreumEvent
        from uuid import uuid4

        event = CodetoreumEvent(
            type="task.rejected",
            timestamp=datetime.now(UTC).isoformat(),
            source="agent_scheduler",
            event_id=str(uuid4()),
        )

        try:
            await self.event_bus.publish(event)
            logger.error(
                f"Task rejected event published for agent {agent}",
                extra={"agent": agent, "project": project, "reason": reason},
            )
        except Exception as e:
            logger.error(
                f"Failed to publish task rejected event for agent {agent}: {e}",
                exc_info=True,
                extra={"agent": agent, "error_id": ErrorRegistry.ERR_EVENT_BUS_ERROR},
            )


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
    adapters that expect a SimulationEngine-like object. Despite the name,
    this is used in production to provide time source compatibility.
    The method name is constrained by the SimulationEngine interface contract
    that some adapters depend on.
    """

    def __init__(self) -> None:
        """Initialize production engine."""
        self._clock = _ProductionClock()

    def get_clock_for_testing(self) -> _ProductionClock:
        """
        Get production clock.

        Note: Despite the "for_testing" name, this method is called in
        production contexts. The name is inherited from the SimulationEngine
        interface that adapters expect. In production, this returns a real
        system clock, not a simulated one.
        """
        return self._clock


class ProductionProjectConfigurationWrapper(IProjectConfiguration):
    """
    Wrapper that implements IProjectConfiguration interface for AgentScheduler.

    The IProjectConfiguration interface expects a get_agent_config(agent_name) method.
    This wrapper adapts the configuration store to provide that interface by querying
    for agent configuration directly.

    Agent configuration includes Claude Code CLI parameters:
    - model: LLM model selection (e.g., "claude-opus-4-6", "claude-sonnet-4-5")
    - timeout: Execution timeout in seconds
    - mcp_servers: MCP (Model Context Protocol) servers for tool availability
    - capabilities: Agent capabilities (e.g., "code_review", "testing", "analysis")
    - constraints: Tool-specific permissions and restrictions
    - metadata: Additional stage-specific configuration (prompt templates, context paths, etc.)
    """

    def __init__(self, config_store: IConfigStore, project_id: str = "default") -> None:
        """
        Initialize the wrapper.

        Args:
            config_store: The IConfigStore instance to query for agent configurations
            project_id: Default project ID for agent config lookups
        """
        self.config_store = config_store
        self.project_id = project_id

    async def get_agent_config(self, agent_name: str) -> AgentConfig:
        """
        Get agent configuration from configuration store.

        Queries the configuration store for the agent's Claude Code CLI parameters,
        including model, timeout, MCP servers, and capabilities. If agent config
        is not found in the store, returns a sensible production default.

        Args:
            agent_name: Name of the agent to get config for

        Returns:
            Agent configuration with Claude Code CLI parameters
        """
        try:
            # Try to get agent config from configuration store
            config = await self.config_store.get_agent_config(
                project_id=self.project_id,
                agent_name=agent_name,
            )
            logger.info(
                f"Retrieved agent config for {agent_name} from store",
                extra={"project_id": self.project_id, "agent": agent_name},
            )
            return config
        except Exception as e:
            # If agent config is not found or store query fails, return sensible production default
            logger.warning(
                f"Failed to retrieve agent config from store for {agent_name}, using production default: {e}",
                exc_info=True,
                extra={"error_id": ErrorRegistry.ERR_CONFIG_NOT_FOUND, "project_id": self.project_id},
            )
            # Return production-sensible defaults
            return AgentConfig(
                project_id=self.project_id,
                agent_name=agent_name,
                model="claude-opus-4-6",  # Latest production-capable model
                timeout=300,  # 5 minutes default timeout
                requires_docker=True,
                makes_code_changes=True,
                mcp_servers=(),
                capabilities=(),
            )


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
        self._resolver: AdapterResolver | None = None
        self._adapter_dependencies: AdapterDependencies | None = None

    async def setup(self) -> FastAPI:
        """
        Set up the entire production application stack.

        This method executes bootstrap phases:
        - Phase 0: Read and validate environment variables
        - Phase 1: Create infrastructure (event bus, logger)
        - Phase 2: Create adapter factory and resolver
        - Phase 3: Validate credentials (pre-flight check)
        - Phase 4: Resolve all adapters with dependency ordering
        - Phase 5: Apply resilience decorators
        - Phase 6: Create application services
        - Phase 6b: Register event handlers
        - Phase 7: Create input ports
        - Phase 8: Create FastAPI app and wire all ports

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
        self._create_resolver()

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

        # Phase 6b: Register event handlers
        logger.info("Phase 6b: Registering event handlers...")
        self._register_event_handlers()

        # Phase 7: Create ports
        logger.info("Phase 7: Creating input ports...")
        self._create_ports()

        # Phase 8: Create FastAPI app
        logger.info("Phase 8: Creating FastAPI application...")
        await self._create_fastapi_app()

        logger.info("Production bootstrap completed successfully")
        return self.app

    def _read_environment_variables(self) -> None:
        """
        Read and validate required environment variables.

        Required variables:
        - CODETOREUM_AUTH_SECRET_KEY: JWT signing key for authentication

        Raises:
            ValueError: If required variables are missing
        """
        required_vars = [
            "CODETOREUM_AUTH_SECRET_KEY",
        ]

        missing_vars = [var for var in required_vars if not os.getenv(var)]
        if missing_vars:
            msg = f"Missing required environment variables: {', '.join(missing_vars)}"
            logger.error(msg, extra={"error_id": ErrorRegistry.ERR_MISSING_CONFIGURATION})
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

    def _register_event_handlers(self) -> None:
        """
        Register event handlers with the event bus.

        These handlers subscribe to domain events and trigger downstream workflows:
        - Board column changes trigger workflow state updates
        - PR review status changes trigger review cycles
        - Review events trigger code review processes

        Raises:
            RuntimeError: If services or adapters are not yet initialized
        """
        from codetoreum.application.event_handlers.board_event_handler import BoardColumnEventHandler
        from codetoreum.application.event_handlers.pr_review_cycle_dispatch_handler import (
            PRReviewCycleDispatchHandler,
        )
        from codetoreum.application.event_handlers.pr_review_cycle_event_handler import PRReviewCycleEventHandler
        from codetoreum.application.event_handlers.review_event_handler import ReviewEventHandler

        if not self.services or not self.adapters:
            msg = "Services and adapters must be initialized before registering event handlers"
            logger.error(msg, extra={"error_id": ErrorRegistry.ERR_HANDLER_REGISTRATION})
            raise RuntimeError(msg)

        # Create event handlers with correct parameters
        board_handler = BoardColumnEventHandler(
            board_service=self.adapters.board,
            lock_service=self.adapters.lock_service,
            workflow_config=self.adapters.workflow_config,
            agent_executor=self.adapters.agent_executor,
            event_bus=self.event_bus,
            event_store=self.adapters.event_store,
            run_registry=self.adapters.run_registry,
            event_emitter=self.adapters.event_emitter,
        )

        pr_review_dispatch_handler = PRReviewCycleDispatchHandler(
            pr_review_cycle=self.adapters.pr_review_cycle,
            workflow_config=self.adapters.workflow_config,
            work_item_service=self.services["work_item_service"],
            active_workflow_run_registry=self.adapters.run_registry,
        )

        pr_review_handler = PRReviewCycleEventHandler(
            board_service=self.adapters.board,
        )

        review_handler = ReviewEventHandler(
            review_service=self.services["review_service"],
            ci_pipeline_service=self.adapters.ci_pipeline,
        )

        # Register handlers with event bus
        self.event_bus.register_handler(board_handler)
        logger.info("Registered BoardColumnEventHandler with event bus")

        self.event_bus.register_handler(pr_review_dispatch_handler)
        logger.info("Registered PRReviewCycleDispatchHandler with event bus")

        self.event_bus.register_handler(pr_review_handler)
        logger.info("Registered PRReviewCycleEventHandler with event bus")

        self.event_bus.register_handler(review_handler)
        logger.info("Registered ReviewEventHandler with event bus")

    def _create_adapter_factory(self) -> None:
        """Create adapter factory with production configuration."""
        factory_config = AdapterFactoryConfig(operation_mode=OperationMode.PRODUCTION)
        self.adapter_factory = AdapterFactory(factory_config)
        self._resilience_factory = ResilienceFactory(mode=OperationMode.PRODUCTION)
        logger.info("Adapter factory created")

    def _create_resolver(self, engine: Any | None = None) -> None:
        """
        Create AdapterResolver and dependencies once for reuse.

        Args:
            engine: Optional engine for time source compatibility. If None, uses _ProductionEngine.
        """
        adapter_config = create_production_adapter_config()

        self._adapter_dependencies = AdapterDependencies(
            event_bus=self.event_bus,
            event_emitter=None,  # Will be resolved in phase 2
            logger=logger,
            engine=engine or _ProductionEngine(),  # Provides time_source compatibility
            config=None,  # Production doesn't use SimulationConfig
        )

        self._resolver = AdapterResolver(
            adapter_config=adapter_config,
            factory=self.adapter_factory,
            dependencies=self._adapter_dependencies,
        )

    def _validate_credentials(self) -> None:
        """
        Validate all adapter credentials before instantiation.

        This is a pre-flight check that aggregates all missing credentials
        and fails fast, preventing partial bootstrap failures.

        Uses the shared resolver created in _create_resolver().

        Raises:
            AdapterConfigurationError: If any credentials are missing/invalid
        """
        if not self._resolver:
            msg = "Resolver must be created before credential validation"
            logger.error(msg, extra={"error_id": ErrorRegistry.ERR_INTERNAL_ERROR})
            raise RuntimeError(msg)

        # Pre-flight credential validation
        self._resolver.validate_credentials()
        logger.info("All adapter credentials validated successfully")

    async def _resolve_adapters(self) -> None:
        """
        Resolve all adapters using AdapterResolver.

        Follows 11-phase dependency ordering to ensure adapters that depend
        on others are constructed after their dependencies.

        Uses the shared resolver created in _create_resolver().

        Raises:
            AdapterConfigurationError: If resolution fails
        """
        if not self._resolver:
            msg = "Resolver must be created before adapter resolution"
            logger.error(msg, extra={"error_id": ErrorRegistry.ERR_INTERNAL_ERROR})
            raise RuntimeError(msg)

        adapter_config = create_production_adapter_config()

        # Resolve all adapters following dependency order
        self.adapters = self._resolver.resolve_all()

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

        Raises:
            RuntimeError: If adapters or resilience factory not initialized
        """
        if not self.adapters or not self._resilience_factory:
            msg = "Adapters and resilience factory must be initialized before applying decorators"
            logger.error(msg, extra={"error_id": ErrorRegistry.ERR_INFRASTRUCTURE_ERROR})
            raise RuntimeError(msg)

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

        # Create configuration_service FIRST (required by agent_scheduler)
        configuration_service = ConfigurationService(
            config_store=self.adapters.config_store,
            event_bus=self.event_bus,
        )

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

        # Create wrapper for IConfigStore to implement IProjectConfiguration
        config_wrapper = ProductionProjectConfigurationWrapper(self.adapters.config_store)

        agent_scheduler = AgentScheduler(
            task_queue=ProductionTaskQueue(self.adapters.queue_service),
            config=config_wrapper,  # Use wrapper that implements IProjectConfiguration
            rate_limiter=ProductionRateLimiter(rate_limit_rpm=60),
            resource_monitor=ProductionResourceMonitor(),
            scheduling_events=ProductionSchedulingEvents(self.event_bus),
            event_store=self.adapters.event_store,
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
            vcs=self.adapters.repository,
            container=self.adapters.container,
            event_store=self.adapters.event_store,
            branch_resolution_service=self.adapters.branch_resolution_service,
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

        # Create failed event store for tracking completion callback failures
        # Using DeadLetterQueue with production defaults for memory safety and retry tracking
        dead_letter_queue = DeadLetterQueue()
        failed_event_store = DeadLetterQueueFailedEventStoreAdapter(dead_letter_queue)

        # Create AgentExecutionRecoveryService to handle agent execution failures
        # This is separate from ContainerRecoveryService (which handles container issues)
        # Injected into ExecutionServiceAgentExecutor for completion callback failure recovery
        agent_execution_recovery_service = AgentExecutionRecoveryService(
            board_service=self.adapters.board,
            event_store=self.adapters.event_store,
            run_registry=self.adapters.run_registry,
            failed_event_store=failed_event_store,
        )

        # Create ExecutionServiceAgentExecutor to wire into BoardColumnEventHandler
        # This drives the full LLM → Container → VCS execution chain in production
        production_clock = _ProductionClock()
        agent_executor = ExecutionServiceAgentExecutor(
            execution_service=execution_service,
            workspace_router=workspace_router,
            config_store=self.adapters.config_store,
            agent_repository=self.adapters.agent_repository,
            work_item_service=work_item_service,
            run_registry=self.adapters.run_registry,
            branch_tracker=self.adapters.branch_tracker,
            vcs=self.adapters.repository,
            clock=production_clock,  # Production clock (real system time)
            recovery_service=agent_execution_recovery_service,
        )
        # Store executor in adapters for BoardColumnEventHandler access
        self.adapters.agent_executor = agent_executor

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
            "agent_executor": agent_executor,
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

        # MVP task query implementation: MockTaskQueryAdapter for placeholder data
        # TODO: Implement real ITaskQueryPort adapter that queries ExecutionService and event store
        task_query_impl = MockTaskQueryAdapter()

        # Store ports for create_app()
        self.ports = {
            "workflow_command": self.services["workflow_orchestrator"],
            "task_query": task_query_impl,  # MVP: Mock implementation, see TODO above
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

    async def _create_fastapi_app(self) -> None:
        """
        Create FastAPI application with all ports wired.

        Calls create_app() with 16 required ports and optional audit_query_port,
        then wires the 2 input ports that are not handled by create_app().
        Also initializes the workflow configuration service and seeds the
        Codetoreum pipeline configuration.
        """
        if not self.ports or not self.adapters or not self.services:
            msg = "Ports, adapters, and services must be created first"
            logger.error(msg, extra={"error_id": ErrorRegistry.ERR_INTERNAL_ERROR})
            raise RuntimeError(msg)

        # Create and initialize workflow config service
        workflow_config_service = None
        try:
            workflow_config_service = ElasticsearchWorkflowConfigService(
                es_client=self.adapters.event_store.client
                if hasattr(self.adapters.event_store, "client")
                else None,
                create_index_templates=True,
                shard_count=1,
                replica_count=1,
            )
            await workflow_config_service.initialize()
            logger.info("Elasticsearch workflow configuration service initialized")

            # Seed the Codetoreum pipeline configuration
            codetoreum_template = create_codetoreum_pipeline_template()
            await workflow_config_service.save_board_workflow_template(codetoreum_template)
            logger.info("Codetoreum pipeline configuration seeded successfully")

        except Exception as e:
            msg = f"Failed to initialize workflow config service or seed pipeline: {e}"
            logger.error(
                msg,
                exc_info=True,
                extra={"error_id": ErrorRegistry.ERR_ELASTICSEARCH_ERROR},
            )
            raise RuntimeError(msg) from e

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
            config_service=self.services["configuration_service"],
            logger=logger,
            workflow_config_service=workflow_config_service,
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
