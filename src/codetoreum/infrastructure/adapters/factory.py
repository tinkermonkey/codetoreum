"""
Adapter factory for creating fully configured adapter instances.

Provides:
- Configuration-driven adapter instantiation
- Automatic resilience decorator application
- Dependency injection support
- Registry integration
"""

import logging
import threading
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, TypeVar

# Import production adapters
from codetoreum.adapters.secondary import (
    CachedConfigStore,
    ClaudeCodeAdapter,
    DockerContainerAdapter,
    ElasticsearchConfigStorage,
    GitHubBoardAdapter,
    GitHubCIPipelineAdapter,
    GitHubCodeReviewAdapter,
    GitHubTicketAdapter,
    GitRepositoryAdapter,
    MockEventEmitter,
)
from codetoreum.adapters.secondary.in_memory_queue_lock_service import (
    InMemoryLockService,
)

# Import testing adapters
from codetoreum.adapters.testing import (
    CapturingMockEventEmitter,
    ConfigurableIdentityService,
    FakeContainerAdapter,
    InMemoryActiveWorkflowRunRegistry,
    InMemoryAgentRepository,
    InMemoryCheckpointStore,
    InMemoryCodeReviewAdapter,
    InMemoryConfigStore,
    InMemoryEventStore,
    InMemoryMessageBroker,
    InMemoryMetricsAdapter,
    InMemoryQueueService,
    InMemoryRepositoryAdapter,
    InMemoryStorageAdapter,
    InMemoryTicketAdapter,
    InMemoryVersionControlService,
    InMemoryWorkflowConfigService,
    InMemoryWorkItemBranchTracker,
    MockAgentExecutor,
    MockBoardAdapter,
    MockCIPipelineAdapter,
    MockContainerRecoveryAdapter,
    MockDiscussionAdapter,
    MockEnvironmentRepairAdapter,
    MockLLMAdapter,
    MockNotifierAdapter,
    MockProjectManagerAdapter,
    MockRepairCycleAdapter,
    MockReviewCycleAdapter,
    MockSystemicAnalysisAdapter,
    MockWorkItemService,
    SimpleEncryptionAdapter,
)

logger = logging.getLogger(__name__)

try:
    from codetoreum.adapters.testing.mock_pr_review_cycle_adapter import (
        MockPRReviewCycleAdapter,
    )
except ImportError:
    logger.warning(
        "Optional adapter MockPRReviewCycleAdapter not available, skipping registration",
        exc_info=True,
        extra={"adapter": "MockPRReviewCycleAdapter"},
    )
    MockPRReviewCycleAdapter = None  # type: ignore

try:
    from codetoreum.adapters.secondary.prometheus_metrics_adapter import (
        PrometheusMetricsAdapter,
    )
except ImportError:
    logger.warning(
        "Optional adapter PrometheusMetricsAdapter not available, skipping registration",
        exc_info=True,
        extra={"adapter": "PrometheusMetricsAdapter"},
    )
    PrometheusMetricsAdapter = None  # type: ignore

try:
    from codetoreum.adapters.secondary.redis_pubsub_adapter import (
        RedisPubSubAdapter,
    )
except ImportError:
    logger.warning(
        "Optional adapter RedisPubSubAdapter not available, skipping registration",
        exc_info=True,
        extra={"adapter": "RedisPubSubAdapter"},
    )
    RedisPubSubAdapter = None  # type: ignore

try:
    from codetoreum.adapters.secondary.github_discussion_adapter import (
        GitHubDiscussionAdapter,
    )
except ImportError:
    logger.warning(
        "Optional adapter GitHubDiscussionAdapter not available, skipping registration",
        exc_info=True,
        extra={"adapter": "GitHubDiscussionAdapter"},
    )
    GitHubDiscussionAdapter = None  # type: ignore

try:
    from codetoreum.adapters.secondary.elasticsearch_event_store import (
        ElasticsearchEventStore,
    )
except ImportError:
    logger.warning(
        "Optional adapter ElasticsearchEventStore not available, skipping registration",
        exc_info=True,
        extra={"adapter": "ElasticsearchEventStore"},
    )
    ElasticsearchEventStore = None  # type: ignore

try:
    from codetoreum.adapters.secondary.docker_container_recovery_adapter import (
        DockerContainerRecoveryAdapter,
    )
except ImportError:
    logger.warning(
        "Optional adapter DockerContainerRecoveryAdapter not available, skipping registration",
        exc_info=True,
        extra={"adapter": "DockerContainerRecoveryAdapter"},
    )
    DockerContainerRecoveryAdapter = None  # type: ignore

try:
    from codetoreum.adapters.secondary.production_repair_cycle_adapter import (
        ProductionRepairCycleAdapter,
    )
except ImportError:
    logger.warning(
        "Optional adapter ProductionRepairCycleAdapter not available, skipping registration",
        exc_info=True,
        extra={"adapter": "ProductionRepairCycleAdapter"},
    )
    ProductionRepairCycleAdapter = None  # type: ignore

try:
    from codetoreum.adapters.secondary.llm_systemic_analysis_adapter import (
        LLMSystemicAnalysisAdapter,
    )
except ImportError:
    logger.warning(
        "Optional adapter LLMSystemicAnalysisAdapter not available, skipping registration",
        exc_info=True,
        extra={"adapter": "LLMSystemicAnalysisAdapter"},
    )
    LLMSystemicAnalysisAdapter = None  # type: ignore

try:
    from codetoreum.adapters.secondary.production_environment_repair_adapter import (
        ProductionEnvironmentRepairAdapter,
    )
except ImportError:
    logger.warning(
        "Optional adapter ProductionEnvironmentRepairAdapter not available, skipping registration",
        exc_info=True,
        extra={"adapter": "ProductionEnvironmentRepairAdapter"},
    )
    ProductionEnvironmentRepairAdapter = None  # type: ignore

from codetoreum.infrastructure.adapters.registries import (
    ActiveWorkflowRunRegistryRegistry,
    AgentExecutorRegistry,
    AgentRepositoryRegistry,
    BoardServiceRegistry,
    CIPipelineServiceRegistry,
    CodeReviewServiceRegistry,
    ConfigStoreRegistry,
    ContainerRecoveryRegistry,
    ContainerRegistry,
    DiscussionAdapterRegistry,
    EncryptionRegistry,
    EnvironmentRepairRegistry,
    EventEmitterRegistry,
    EventStoreRegistry,
    IdentityServiceRegistry,
    LLMProviderRegistry,
    MessageBrokerRegistry,
    MetricsAdapterRegistry,
    NotifierRegistry,
    PipelineLockServiceRegistry,
    PipelineQueueServiceRegistry,
    ProjectManagerServiceRegistry,
    PRReviewCycleServiceRegistry,
    RepairCycleCheckpointStoreRegistry,
    RepairCycleRegistry,
    RepositoryRegistry,
    ReviewCycleServiceRegistry,
    StorageRegistry,
    SystemicAnalysisRegistry,
    TicketSystemRegistry,
    VersionControlServiceRegistry,
    WorkflowConfigServiceRegistry,
    WorkItemBranchTrackerRegistry,
    WorkItemServiceRegistry,
)
from codetoreum.infrastructure.adapters.registry_base import (
    AdapterCredentialRequirement,
    AdapterRegistry,
)
from codetoreum.infrastructure.resilience import (
    CLAUDE_RESILIENCE_CONFIG,
    CONTAINER_RESILIENCE_CONFIG,
    GITHUB_RESILIENCE_CONFIG,
    REPOSITORY_RESILIENCE_CONFIG,
    OperationMode,
    ResilienceFactory,
    ServiceResilienceConfig,
)
from codetoreum.ports.output.active_workflow_run_registry import IActiveWorkflowRunRegistry
from codetoreum.ports.output.agent_executor import IAgentExecutor
from codetoreum.ports.output.agent_repository import IAgentRepository
from codetoreum.ports.output.board_service import IBoardService
from codetoreum.ports.output.ci_pipeline_service import ICIPipelineService
from codetoreum.ports.output.code_review_service import ICodeReviewService
from codetoreum.ports.output.config_store import IConfigStore
from codetoreum.ports.output.container import IContainer
from codetoreum.ports.output.container_recovery import IAgentContainerRecoveryService
from codetoreum.ports.output.discussion_adapter import IDiscussionAdapter
from codetoreum.ports.output.encryption_service import IEncryptionService
from codetoreum.ports.output.environment_repair_service import IEnvironmentRepairService
from codetoreum.ports.output.event_emitter import IEventEmitter
from codetoreum.ports.output.event_store import IEventStore
from codetoreum.ports.output.identity_service import IIdentityService
from codetoreum.ports.output.llm_provider import ILLMProvider
from codetoreum.ports.output.message_broker import IMessageBroker
from codetoreum.ports.output.metrics import IMetrics
from codetoreum.ports.output.notifier import INotifier
from codetoreum.ports.output.pipeline_lock_service import IPipelineLockService
from codetoreum.ports.output.pipeline_queue_service import IPipelineQueueService
from codetoreum.ports.output.pr_review_cycle_service import IPRReviewCycle
from codetoreum.ports.output.project_manager_service import IProjectManagerService
from codetoreum.ports.output.repair_cycle_checkpoint_store import IRepairCycleCheckpointStore
from codetoreum.ports.output.repair_cycle_service import IRepairCycle
from codetoreum.ports.output.repository import IRepository
from codetoreum.ports.output.review_cycle_service import IReviewCycle
from codetoreum.ports.output.storage import IStorage
from codetoreum.ports.output.systemic_analysis_service import ISystemicAnalysisService
from codetoreum.ports.output.ticket_system import ITicketSystem
from codetoreum.ports.output.version_control_service import IVersionControlService
from codetoreum.ports.output.work_item_branch_tracker import IWorkItemBranchTracker
from codetoreum.ports.output.work_item_service import IWorkItemService
from codetoreum.ports.output.workflow_config_service import IWorkflowConfigService

T = TypeVar("T")


@dataclass
class AdapterFactoryConfig:
    """Configuration for the adapter factory."""

    operation_mode: OperationMode = OperationMode.PRODUCTION
    enable_resilience: bool = True
    custom_resilience_configs: dict[str, ServiceResilienceConfig] | None = None


class AdapterFactory:
    """
    Factory for creating fully configured adapter instances.

    Handles:
    - Adapter instantiation from registries
    - Configuration management
    - Resilience decorator application
    - Dependency injection

    Thread-safe for concurrent adapter creation and configuration changes.
    """

    def __init__(self, config: AdapterFactoryConfig | None = None):
        """
        Initialize the adapter factory.

        Args:
            config: Factory configuration
        """
        self._config = config or AdapterFactoryConfig()
        self._resilience_factory = ResilienceFactory(mode=self._config.operation_mode)

        # Thread safety lock
        self._lock = threading.RLock()

        # Initialize registries
        self._ticket_system_registry = TicketSystemRegistry()
        self._llm_provider_registry = LLMProviderRegistry()
        self._container_registry = ContainerRegistry()
        self._repository_registry = RepositoryRegistry()
        self._event_store_registry = EventStoreRegistry()
        self._storage_registry = StorageRegistry()
        self._board_service_registry = BoardServiceRegistry()
        self._code_review_registry = CodeReviewServiceRegistry()
        self._discussion_adapter_registry = DiscussionAdapterRegistry()
        self._version_control_registry = VersionControlServiceRegistry()
        self._metrics_registry = MetricsAdapterRegistry()
        self._notifier_registry = NotifierRegistry()
        self._message_broker_registry = MessageBrokerRegistry()
        self._config_store_registry = ConfigStoreRegistry()
        self._repair_cycle_registry = RepairCycleRegistry()
        self._review_cycle_registry = ReviewCycleServiceRegistry()
        self._pr_review_cycle_registry = PRReviewCycleServiceRegistry()
        self._container_recovery_registry = ContainerRecoveryRegistry()
        self._encryption_registry = EncryptionRegistry()
        self._pipeline_lock_registry = PipelineLockServiceRegistry()
        self._pipeline_queue_registry = PipelineQueueServiceRegistry()
        self._project_manager_registry = ProjectManagerServiceRegistry()
        self._workflow_config_registry = WorkflowConfigServiceRegistry()
        self._event_emitter_registry = EventEmitterRegistry()
        self._identity_service_registry = IdentityServiceRegistry()
        self._agent_executor_registry = AgentExecutorRegistry()
        self._agent_repository_registry = AgentRepositoryRegistry()
        self._work_item_branch_tracker_registry = WorkItemBranchTrackerRegistry()
        self._work_item_service_registry = WorkItemServiceRegistry()
        self._repair_cycle_checkpoint_registry = RepairCycleCheckpointStoreRegistry()
        self._active_workflow_run_registry_registry = ActiveWorkflowRunRegistryRegistry()
        self._systemic_analysis_registry = SystemicAnalysisRegistry()
        self._environment_repair_registry = EnvironmentRepairRegistry()
        self._ci_pipeline_registry = CIPipelineServiceRegistry()

        # Dependency injection container
        self._dependencies: dict[str, Any] = {}

        # Register default adapters
        self._register_default_adapters()

    def _register_default_adapters(self) -> None:
        """Register default adapter implementations."""
        # Ticket System Adapters
        self._ticket_system_registry.register(
            name="github",
            adapter_type=GitHubTicketAdapter,
            description="GitHub Issues and Projects integration",
            version="1.0.0",
            tags=["production", "github", "issues"],
            config_schema=AdapterCredentialRequirement(
                env_vars=("GITHUB_TOKEN", "GITHUB_ORG"),
                description="GitHub personal access token with repo scope",
            ),
            set_as_default=True,
        )
        self._ticket_system_registry.register(
            name="in_memory",
            adapter_type=InMemoryTicketAdapter,
            description="In-memory ticket system for testing",
            version="1.0.0",
            tags=["testing", "simulation", "mock"],
            config_schema=AdapterCredentialRequirement(
                simulation_only=True,
                description="Simulation-only adapter, no credentials required",
            ),
        )

        # LLM Provider Adapters
        self._llm_provider_registry.register(
            name="claude_code",
            adapter_type=ClaudeCodeAdapter,
            description="Claude Code CLI integration",
            version="1.0.0",
            tags=["production", "claude", "anthropic"],
            config_schema=AdapterCredentialRequirement(
                env_vars=("CLAUDE_CODE_OAUTH_TOKEN",),
                description="Claude Code OAuth token for authentication",
            ),
            set_as_default=True,
        )
        self._llm_provider_registry.register(
            name="mock",
            adapter_type=MockLLMAdapter,
            description="Mock LLM provider for testing",
            version="1.0.0",
            tags=["testing", "simulation", "mock"],
            config_schema=AdapterCredentialRequirement(
                simulation_only=True,
                description="Simulation-only adapter, no credentials required",
            ),
        )

        # Container Adapters
        self._container_registry.register(
            name="docker",
            adapter_type=DockerContainerAdapter,
            description="Docker container runtime",
            version="1.0.0",
            tags=["production", "docker"],
            config_schema=AdapterCredentialRequirement(
                env_vars=("DOCKER_HOST",),
                description="Docker daemon connection string",
            ),
            set_as_default=True,
        )
        self._container_registry.register(
            name="fake",
            adapter_type=FakeContainerAdapter,
            description="Fake container adapter for testing",
            version="1.0.0",
            tags=["testing", "simulation", "mock"],
            config_schema=AdapterCredentialRequirement(
                simulation_only=True,
                description="Simulation-only adapter, no credentials required",
            ),
        )

        # Repository Adapters
        self._repository_registry.register(
            name="git",
            adapter_type=GitRepositoryAdapter,
            description="Git repository operations",
            version="1.0.0",
            tags=["production", "git"],
            config_schema=AdapterCredentialRequirement(
                env_vars=("GIT_USER", "GIT_EMAIL"),
                description="Git user credentials for commits",
            ),
            set_as_default=True,
        )
        self._repository_registry.register(
            name="in_memory",
            adapter_type=InMemoryRepositoryAdapter,
            description="In-memory repository for testing",
            version="1.0.0",
            tags=["testing", "simulation", "mock"],
            config_schema=AdapterCredentialRequirement(
                simulation_only=True,
                description="Simulation-only adapter, no credentials required",
            ),
        )

        # Event Store Adapters
        self._event_store_registry.register(
            name="in_memory",
            adapter_type=InMemoryEventStore,
            description="In-memory event store",
            version="1.0.0",
            tags=["testing", "simulation", "production"],
            config_schema=AdapterCredentialRequirement(
                simulation_only=True,
                description="Simulation-only adapter, no credentials required",
            ),
            set_as_default=True,
        )

        # Storage Adapters
        self._storage_registry.register(
            name="in_memory",
            adapter_type=InMemoryStorageAdapter,
            description="In-memory storage for testing",
            version="1.0.0",
            tags=["testing", "simulation", "mock"],
            config_schema=AdapterCredentialRequirement(
                simulation_only=True,
                description="Simulation-only adapter, no credentials required",
            ),
            set_as_default=True,
        )

        # Board Service Adapters
        self._board_service_registry.register(
            name="mock",
            adapter_type=MockBoardAdapter,
            description="Mock board adapter for testing",
            version="1.0.0",
            tags=["testing", "simulation", "mock"],
            config_schema=AdapterCredentialRequirement(
                simulation_only=True,
                description="Simulation-only adapter, no credentials required",
            ),
            set_as_default=True,
        )
        self._board_service_registry.register(
            name="github",
            adapter_type=GitHubBoardAdapter,
            description="GitHub Projects board adapter",
            version="1.0.0",
            tags=["production", "github"],
            config_schema=AdapterCredentialRequirement(
                env_vars=("GITHUB_TOKEN", "GITHUB_ORG"),
                description="GitHub personal access token with repo scope",
            ),
        )

        # Code Review Service Adapters
        self._code_review_registry.register(
            name="github",
            adapter_type=GitHubCodeReviewAdapter,
            description="GitHub code review adapter",
            version="1.0.0",
            tags=["production", "github"],
            config_schema=AdapterCredentialRequirement(
                env_vars=("GITHUB_TOKEN", "GITHUB_ORG"),
                description="GitHub personal access token with repo scope",
            ),
            set_as_default=True,
        )
        self._code_review_registry.register(
            name="mock",
            adapter_type=InMemoryCodeReviewAdapter,
            description="In-memory code review adapter for testing",
            version="1.0.0",
            tags=["testing", "simulation", "mock"],
            config_schema=AdapterCredentialRequirement(
                simulation_only=True,
                description="Simulation-only adapter, no credentials required",
            ),
        )

        # Discussion Adapter
        self._discussion_adapter_registry.register(
            name="mock",
            adapter_type=MockDiscussionAdapter,
            description="Mock discussion adapter for testing",
            version="1.0.0",
            tags=["testing", "simulation", "mock"],
            config_schema=AdapterCredentialRequirement(
                simulation_only=True,
                description="Simulation-only adapter, no credentials required",
            ),
            set_as_default=True,
        )
        if GitHubDiscussionAdapter:
            self._discussion_adapter_registry.register(
                name="github",
                adapter_type=GitHubDiscussionAdapter,
                description="GitHub discussion adapter",
                version="1.0.0",
                tags=["production", "github"],
                config_schema=AdapterCredentialRequirement(
                    env_vars=("GITHUB_TOKEN", "GITHUB_ORG"),
                    description="GitHub personal access token with repo scope",
                ),
            )

        # Version Control Service Adapters
        self._version_control_registry.register(
            name="in_memory",
            adapter_type=InMemoryVersionControlService,
            description="In-memory version control for testing",
            version="1.0.0",
            tags=["testing", "simulation", "mock"],
            config_schema=AdapterCredentialRequirement(
                simulation_only=True,
                description="Simulation-only adapter, no credentials required",
            ),
            set_as_default=True,
        )

        # Metrics Adapters
        self._metrics_registry.register(
            name="in_memory",
            adapter_type=InMemoryMetricsAdapter,
            description="In-memory metrics adapter for testing",
            version="1.0.0",
            tags=["testing", "simulation", "mock"],
            config_schema=AdapterCredentialRequirement(
                simulation_only=True,
                description="Simulation-only adapter, no credentials required",
            ),
            set_as_default=True,
        )
        if PrometheusMetricsAdapter:
            self._metrics_registry.register(
                name="prometheus",
                adapter_type=PrometheusMetricsAdapter,
                description="Prometheus metrics adapter",
                version="1.0.0",
                tags=["production", "prometheus"],
                config_schema=AdapterCredentialRequirement(
                    env_vars=("PROMETHEUS_URL",),
                    description="Prometheus server URL",
                ),
            )

        # Notifier Adapters
        self._notifier_registry.register(
            name="mock",
            adapter_type=MockNotifierAdapter,
            description="Mock notifier for testing",
            version="1.0.0",
            tags=["testing", "simulation", "mock"],
            config_schema=AdapterCredentialRequirement(
                simulation_only=True,
                description="Simulation-only adapter, no credentials required",
            ),
            set_as_default=True,
        )

        # Message Broker Adapters
        self._message_broker_registry.register(
            name="in_memory",
            adapter_type=InMemoryMessageBroker,
            description="In-memory message broker for testing",
            version="1.0.0",
            tags=["testing", "simulation", "mock"],
            config_schema=AdapterCredentialRequirement(
                simulation_only=True,
                description="Simulation-only adapter, no credentials required",
            ),
            set_as_default=True,
        )
        if RedisPubSubAdapter:
            self._message_broker_registry.register(
                name="redis",
                adapter_type=RedisPubSubAdapter,
                description="Redis Pub/Sub message broker",
                version="1.0.0",
                tags=["production", "redis"],
                config_schema=AdapterCredentialRequirement(
                    env_vars=("REDIS_URL",),
                    description="Redis connection string",
                ),
            )

        # Config Store Adapters
        self._config_store_registry.register(
            name="in_memory",
            adapter_type=InMemoryConfigStore,
            description="In-memory config store for testing",
            version="1.0.0",
            tags=["testing", "simulation", "mock"],
            config_schema=AdapterCredentialRequirement(
                simulation_only=True,
                description="Simulation-only adapter, no credentials required",
            ),
            set_as_default=True,
        )
        self._config_store_registry.register(
            name="cached",
            adapter_type=CachedConfigStore,
            description="Cached config store",
            version="1.0.0",
            tags=["production", "cache"],
            config_schema=AdapterCredentialRequirement(
                config_keys=("database_url", "cache_ttl"),
                description="Database configuration for config storage",
            ),
        )
        if ElasticsearchConfigStorage:
            self._config_store_registry.register(
                name="elasticsearch",
                adapter_type=ElasticsearchConfigStorage,
                description="Elasticsearch configuration storage",
                version="1.0.0",
                tags=["production", "elasticsearch"],
                config_schema=AdapterCredentialRequirement(
                    env_vars=("ELASTICSEARCH_URL",),
                    description="Elasticsearch cluster URL",
                ),
            )

        # Repair Cycle Adapters
        self._repair_cycle_registry.register(
            name="mock",
            adapter_type=MockRepairCycleAdapter,
            description="Mock repair cycle for testing",
            version="1.0.0",
            tags=["testing", "simulation", "mock"],
            config_schema=AdapterCredentialRequirement(
                simulation_only=True,
                description="Simulation-only adapter, no credentials required",
            ),
            set_as_default=True,
        )
        if ProductionRepairCycleAdapter:
            self._repair_cycle_registry.register(
                name="production",
                adapter_type=ProductionRepairCycleAdapter,
                description="Production repair cycle adapter",
                version="1.0.0",
                tags=["production"],
            )

        # Review Cycle Service Adapters
        self._review_cycle_registry.register(
            name="mock",
            adapter_type=MockReviewCycleAdapter,
            description="Mock review cycle for testing",
            version="1.0.0",
            tags=["testing", "simulation", "mock"],
            config_schema=AdapterCredentialRequirement(
                simulation_only=True,
                description="Simulation-only adapter, no credentials required",
            ),
            set_as_default=True,
        )

        # PR Review Cycle Service Adapters
        if MockPRReviewCycleAdapter:
            self._pr_review_cycle_registry.register(
                name="mock",
                adapter_type=MockPRReviewCycleAdapter,
                description="Mock PR review cycle for testing",
                version="1.0.0",
                tags=["testing", "simulation", "mock"],
                config_schema=AdapterCredentialRequirement(
                    simulation_only=True,
                    description="Simulation-only adapter, no credentials required",
                ),
                set_as_default=True,
            )

        # Container Recovery Adapters
        self._container_recovery_registry.register(
            name="mock",
            adapter_type=MockContainerRecoveryAdapter,
            description="Mock container recovery for testing",
            version="1.0.0",
            tags=["testing", "simulation", "mock"],
            config_schema=AdapterCredentialRequirement(
                simulation_only=True,
                description="Simulation-only adapter, no credentials required",
            ),
            set_as_default=True,
        )
        if DockerContainerRecoveryAdapter:
            self._container_recovery_registry.register(
                name="docker",
                adapter_type=DockerContainerRecoveryAdapter,
                description="Docker container recovery adapter",
                version="1.0.0",
                tags=["production", "docker"],
            )

        # Encryption Service Adapters
        self._encryption_registry.register(
            name="simple",
            adapter_type=SimpleEncryptionAdapter,
            description="Simple encryption adapter for testing",
            version="1.0.0",
            tags=["simulation", "mock"],
            config_schema=AdapterCredentialRequirement(
                simulation_only=True,
                description="Simulation-only adapter, no credentials required",
            ),
            set_as_default=True,
        )

        # Pipeline Lock Service Adapters
        self._pipeline_lock_registry.register(
            name="in_memory",
            adapter_type=InMemoryLockService,
            description="In-memory pipeline lock service with position-based queue ordering",
            version="1.0.0",
            tags=["testing", "simulation", "mock", "production"],
            config_schema=AdapterCredentialRequirement(
                simulation_only=True,
                description="Simulation-only adapter, no credentials required",
            ),
            set_as_default=True,
        )

        # Pipeline Queue Service Adapters
        self._pipeline_queue_registry.register(
            name="in_memory",
            adapter_type=InMemoryQueueService,
            description="In-memory queue service for testing",
            version="1.0.0",
            tags=["testing", "simulation", "mock"],
            config_schema=AdapterCredentialRequirement(
                simulation_only=True,
                description="Simulation-only adapter, no credentials required",
            ),
            set_as_default=True,
        )

        # Project Manager Service Adapters
        self._project_manager_registry.register(
            name="mock",
            adapter_type=MockProjectManagerAdapter,
            description="Mock project manager for testing",
            version="1.0.0",
            tags=["testing", "simulation", "mock"],
            config_schema=AdapterCredentialRequirement(
                simulation_only=True,
                description="Simulation-only adapter, no credentials required",
            ),
            set_as_default=True,
        )

        # Workflow Config Service Adapters
        self._workflow_config_registry.register(
            name="in_memory",
            adapter_type=InMemoryWorkflowConfigService,
            description="In-memory workflow config service for testing",
            version="1.0.0",
            tags=["testing", "simulation", "mock"],
            config_schema=AdapterCredentialRequirement(
                simulation_only=True,
                description="Simulation-only adapter, no credentials required",
            ),
            set_as_default=True,
        )

        # Event Emitter Adapters
        self._event_emitter_registry.register(
            name="mock",
            adapter_type=MockEventEmitter,
            description="Mock event emitter for testing",
            version="1.0.0",
            tags=["testing", "simulation", "mock"],
            config_schema=AdapterCredentialRequirement(
                simulation_only=True,
                description="Simulation-only adapter, no credentials required",
            ),
            set_as_default=True,
        )
        self._event_emitter_registry.register(
            name="capturing",
            adapter_type=CapturingMockEventEmitter,
            description="Capturing mock event emitter for assertions",
            version="1.0.0",
            tags=["testing", "simulation", "mock"],
            config_schema=AdapterCredentialRequirement(
                simulation_only=True,
                description="Simulation-only adapter, no credentials required",
            ),
        )

        # Identity Service Adapters
        self._identity_service_registry.register(
            name="configurable",
            adapter_type=ConfigurableIdentityService,
            description="Configurable identity service for testing",
            version="1.0.0",
            tags=["testing", "simulation", "mock", "production"],
            config_schema=AdapterCredentialRequirement(
                simulation_only=True,
                description="Simulation-only adapter, no credentials required",
            ),
            set_as_default=True,
        )

        # Agent Executor Adapters
        self._agent_executor_registry.register(
            name="mock",
            adapter_type=MockAgentExecutor,
            description="Mock agent executor for testing",
            version="1.0.0",
            tags=["testing", "simulation", "mock"],
            config_schema=AdapterCredentialRequirement(
                simulation_only=True,
                description="Simulation-only adapter, no credentials required",
            ),
            set_as_default=True,
        )

        # Agent Repository Adapters
        self._agent_repository_registry.register(
            name="in_memory",
            adapter_type=InMemoryAgentRepository,
            description="In-memory agent repository for testing",
            version="1.0.0",
            tags=["testing", "simulation", "mock"],
            config_schema=AdapterCredentialRequirement(
                simulation_only=True,
                description="Simulation-only adapter, no credentials required",
            ),
            set_as_default=True,
        )

        # Work Item Branch Tracker Adapters
        self._work_item_branch_tracker_registry.register(
            name="in_memory",
            adapter_type=InMemoryWorkItemBranchTracker,
            description="In-memory work item branch tracker for testing",
            version="1.0.0",
            tags=["testing", "simulation", "mock"],
            config_schema=AdapterCredentialRequirement(
                simulation_only=True,
                description="Simulation-only adapter, no credentials required",
            ),
            set_as_default=True,
        )

        # Work Item Service Adapters
        self._work_item_service_registry.register(
            name="mock",
            adapter_type=MockWorkItemService,
            description="Mock work item service for testing",
            version="1.0.0",
            tags=["testing", "simulation", "mock"],
            config_schema=AdapterCredentialRequirement(
                simulation_only=True,
                description="Simulation-only adapter, no credentials required",
            ),
            set_as_default=True,
        )

        # Repair Cycle Checkpoint Store Adapters
        self._repair_cycle_checkpoint_registry.register(
            name="in_memory",
            adapter_type=InMemoryCheckpointStore,
            description="In-memory checkpoint store for testing",
            version="1.0.0",
            tags=["testing", "simulation", "mock"],
            config_schema=AdapterCredentialRequirement(
                simulation_only=True,
                description="Simulation-only adapter, no credentials required",
            ),
            set_as_default=True,
        )

        # Active Workflow Run Registry Adapters
        self._active_workflow_run_registry_registry.register(
            name="in_memory",
            adapter_type=InMemoryActiveWorkflowRunRegistry,
            description="In-memory active workflow run registry for testing",
            version="1.0.0",
            tags=["testing", "simulation", "mock"],
            config_schema=AdapterCredentialRequirement(
                simulation_only=True,
                description="Simulation-only adapter, no credentials required",
            ),
            set_as_default=True,
        )

        # Systemic Analysis Service Adapters
        self._systemic_analysis_registry.register(
            name="mock",
            adapter_type=MockSystemicAnalysisAdapter,
            description="Mock systemic analysis for testing",
            version="1.0.0",
            tags=["testing", "simulation", "mock"],
            config_schema=AdapterCredentialRequirement(
                simulation_only=True,
                description="Simulation-only adapter, no credentials required",
            ),
            set_as_default=True,
        )
        if LLMSystemicAnalysisAdapter:
            self._systemic_analysis_registry.register(
                name="llm",
                adapter_type=LLMSystemicAnalysisAdapter,
                description="LLM-based systemic analysis for production",
                version="1.0.0",
                tags=["production", "llm"],
            )

        # Environment Repair Adapters
        self._environment_repair_registry.register(
            name="mock",
            adapter_type=MockEnvironmentRepairAdapter,
            description="Mock environment repair for testing",
            version="1.0.0",
            tags=["testing", "simulation", "mock"],
            config_schema=AdapterCredentialRequirement(
                simulation_only=True,
                description="Simulation-only adapter, no credentials required",
            ),
            set_as_default=True,
        )
        if ProductionEnvironmentRepairAdapter:
            self._environment_repair_registry.register(
                name="production",
                adapter_type=ProductionEnvironmentRepairAdapter,
                description="Production environment repair with LLM integration",
                version="1.0.0",
                tags=["production", "llm"],
            )

        # CI Pipeline Adapters
        self._ci_pipeline_registry.register(
            name="mock",
            adapter_type=MockCIPipelineAdapter,
            description="Mock CI pipeline adapter for testing",
            version="1.0.0",
            tags=["testing", "simulation", "mock"],
            config_schema=AdapterCredentialRequirement(
                simulation_only=True,
                description="Simulation-only adapter, no credentials required",
            ),
            set_as_default=True,
        )
        self._ci_pipeline_registry.register(
            name="github",
            adapter_type=GitHubCIPipelineAdapter,
            description="GitHub CI pipeline adapter for PR status queries",
            version="1.0.0",
            tags=["production", "github"],
            config_schema=AdapterCredentialRequirement(
                env_vars=("GITHUB_TOKEN", "GITHUB_ORG"),
                description="GitHub personal access token with repo scope",
            ),
        )

    # Registry access methods

    @property
    def ticket_system_registry(self) -> TicketSystemRegistry:
        """Get the ticket system registry."""
        return self._ticket_system_registry

    @property
    def llm_provider_registry(self) -> LLMProviderRegistry:
        """Get the LLM provider registry."""
        return self._llm_provider_registry

    @property
    def container_registry(self) -> ContainerRegistry:
        """Get the container registry."""
        return self._container_registry

    @property
    def repository_registry(self) -> RepositoryRegistry:
        """Get the repository registry."""
        return self._repository_registry

    @property
    def event_store_registry(self) -> EventStoreRegistry:
        """Get the event store registry."""
        return self._event_store_registry

    @property
    def storage_registry(self) -> StorageRegistry:
        """Get the storage registry."""
        return self._storage_registry

    @property
    def board_service_registry(self) -> BoardServiceRegistry:
        """Get the board service registry."""
        return self._board_service_registry

    @property
    def code_review_registry(self) -> CodeReviewServiceRegistry:
        """Get the code review service registry."""
        return self._code_review_registry

    @property
    def discussion_adapter_registry(self) -> DiscussionAdapterRegistry:
        """Get the discussion adapter registry."""
        return self._discussion_adapter_registry

    @property
    def version_control_registry(self) -> VersionControlServiceRegistry:
        """Get the version control service registry."""
        return self._version_control_registry

    @property
    def metrics_registry(self) -> MetricsAdapterRegistry:
        """Get the metrics adapter registry."""
        return self._metrics_registry

    @property
    def notifier_registry(self) -> NotifierRegistry:
        """Get the notifier registry."""
        return self._notifier_registry

    @property
    def message_broker_registry(self) -> MessageBrokerRegistry:
        """Get the message broker registry."""
        return self._message_broker_registry

    @property
    def config_store_registry(self) -> ConfigStoreRegistry:
        """Get the config store registry."""
        return self._config_store_registry

    @property
    def repair_cycle_registry(self) -> RepairCycleRegistry:
        """Get the repair cycle registry."""
        return self._repair_cycle_registry

    @property
    def review_cycle_registry(self) -> ReviewCycleServiceRegistry:
        """Get the review cycle service registry."""
        return self._review_cycle_registry

    @property
    def pr_review_cycle_registry(self) -> PRReviewCycleServiceRegistry:
        """Get the PR review cycle service registry."""
        return self._pr_review_cycle_registry

    @property
    def container_recovery_registry(self) -> ContainerRecoveryRegistry:
        """Get the container recovery registry."""
        return self._container_recovery_registry

    @property
    def encryption_registry(self) -> EncryptionRegistry:
        """Get the encryption service registry."""
        return self._encryption_registry

    @property
    def pipeline_lock_registry(self) -> PipelineLockServiceRegistry:
        """Get the pipeline lock service registry."""
        return self._pipeline_lock_registry

    @property
    def pipeline_queue_registry(self) -> PipelineQueueServiceRegistry:
        """Get the pipeline queue service registry."""
        return self._pipeline_queue_registry

    @property
    def project_manager_registry(self) -> ProjectManagerServiceRegistry:
        """Get the project manager service registry."""
        return self._project_manager_registry

    @property
    def workflow_config_registry(self) -> WorkflowConfigServiceRegistry:
        """Get the workflow config service registry."""
        return self._workflow_config_registry

    @property
    def event_emitter_registry(self) -> EventEmitterRegistry:
        """Get the event emitter registry."""
        return self._event_emitter_registry

    @property
    def identity_service_registry(self) -> IdentityServiceRegistry:
        """Get the identity service registry."""
        return self._identity_service_registry

    @property
    def agent_executor_registry(self) -> AgentExecutorRegistry:
        """Get the agent executor registry."""
        return self._agent_executor_registry

    @property
    def agent_repository_registry(self) -> AgentRepositoryRegistry:
        """Get the agent repository registry."""
        return self._agent_repository_registry

    @property
    def work_item_branch_tracker_registry(self) -> WorkItemBranchTrackerRegistry:
        """Get the work item branch tracker registry."""
        return self._work_item_branch_tracker_registry

    @property
    def work_item_service_registry(self) -> WorkItemServiceRegistry:
        """Get the work item service registry."""
        return self._work_item_service_registry

    @property
    def repair_cycle_checkpoint_registry(self) -> RepairCycleCheckpointStoreRegistry:
        """Get the repair cycle checkpoint store registry."""
        return self._repair_cycle_checkpoint_registry

    @property
    def active_workflow_run_registry_registry(self) -> ActiveWorkflowRunRegistryRegistry:
        """Get the active workflow run registry."""
        return self._active_workflow_run_registry_registry

    @property
    def systemic_analysis_registry(self) -> SystemicAnalysisRegistry:
        """Get the systemic analysis registry."""
        return self._systemic_analysis_registry

    @property
    def environment_repair_registry(self) -> EnvironmentRepairRegistry:
        """Get the environment repair registry."""
        return self._environment_repair_registry

    def get_registry(self, slot_name: str) -> Any:
        """
        Get the registry for a given adapter slot name.

        Args:
            slot_name: Name of the adapter slot (e.g., "board", "ticket", "llm")

        Returns:
            The AdapterRegistry for the specified slot

        Raises:
            KeyError: If slot_name is not recognized
        """
        registry_map = {
            "board": self._board_service_registry,
            "ticket": self._ticket_system_registry,
            "llm": self._llm_provider_registry,
            "version_control": self._version_control_registry,
            "container": self._container_registry,
            "event_store": self._event_store_registry,
            "metrics": self._metrics_registry,
            "storage": self._storage_registry,
            "config_store": self._config_store_registry,
            "notifier": self._notifier_registry,
            "encryption": self._encryption_registry,
            "discussion_adapter": self._discussion_adapter_registry,
            "review_cycle": self._review_cycle_registry,
            "pr_review_cycle": self._pr_review_cycle_registry,
            "repair_cycle": self._repair_cycle_registry,
            "code_review": self._code_review_registry,
            "container_recovery": self._container_recovery_registry,
            "agent_executor": self._agent_executor_registry,
            "project_manager": self._project_manager_registry,
            "lock_service": self._pipeline_lock_registry,
            "workflow_config": self._workflow_config_registry,
            "queue_service": self._pipeline_queue_registry,
            "event_emitter": self._event_emitter_registry,
            "message_broker": self._message_broker_registry,
            "identity_service": self._identity_service_registry,
            "checkpoint_store": self._repair_cycle_checkpoint_registry,
            "agent_repository": self._agent_repository_registry,
            "run_registry": self._active_workflow_run_registry_registry,
            "branch_tracker": self._work_item_branch_tracker_registry,
            "work_item_service": self._work_item_service_registry,
            "repository": self._repository_registry,
            "systemic_analysis": self._systemic_analysis_registry,
            "environment_repair": self._environment_repair_registry,
            "ci_pipeline": self._ci_pipeline_registry,
        }

        if slot_name not in registry_map:
            raise KeyError(f"Unknown adapter slot: '{slot_name}'")

        return registry_map[slot_name]

    # Dependency injection methods

    def register_dependency(self, name: str, instance: Any) -> None:
        """
        Register a dependency for injection.

        Args:
            name: Dependency name
            instance: Dependency instance
        """
        with self._lock:
            self._dependencies[name] = instance
            logger.debug(f"Registered dependency: {name}")

    def get_dependency(self, name: str) -> Any:
        """
        Get a registered dependency.

        Args:
            name: Dependency name

        Returns:
            The dependency instance

        Raises:
            KeyError: If dependency is not registered
        """
        with self._lock:
            if name not in self._dependencies:
                message = f"Dependency '{name}' is not registered"
                raise KeyError(message)
            return self._dependencies[name]

    def has_dependency(self, name: str) -> bool:
        """
        Check if a dependency is registered.

        Args:
            name: Dependency name

        Returns:
            True if dependency is registered
        """
        with self._lock:
            return name in self._dependencies

    # Adapter creation methods

    def create_ticket_system(
        self,
        adapter_name: str | None = None,
        adapter_config: Any | None = None,
        resilience_config: ServiceResilienceConfig | None = None,
        **kwargs,
    ) -> ITicketSystem:
        """
        Create a ticket system adapter instance.

        Args:
            adapter_name: Name of adapter to use (default: registry default)
            adapter_config: Configuration for the adapter
            resilience_config: Custom resilience configuration
            **kwargs: Additional arguments for adapter constructor

        Returns:
            Configured ticket system adapter with resilience applied

        Raises:
            KeyError: If adapter is not registered
        """
        # Determine adapter name
        if adapter_name is None:
            adapter_name = self._ticket_system_registry.get_default_name()
            if adapter_name is None:
                message = "No default ticket system adapter configured"
                raise ValueError(message)

        logger.info(f"Creating ticket system adapter: {adapter_name}")

        # Create base adapter instance
        if adapter_config is not None:
            kwargs["config"] = adapter_config

        adapter = self._ticket_system_registry.create_instance(adapter_name, **kwargs)

        # Apply resilience if enabled
        return self._apply_resilience_wrapper(
            adapter,
            "ticket_system",
            GITHUB_RESILIENCE_CONFIG,
            resilience_config,
            self._resilience_factory.create_resilient_ticket_system,
        )

    def create_llm_provider(
        self,
        adapter_name: str | None = None,
        adapter_config: Any | None = None,
        resilience_config: ServiceResilienceConfig | None = None,
        **kwargs,
    ) -> ILLMProvider:
        """
        Create an LLM provider adapter instance.

        Args:
            adapter_name: Name of adapter to use (default: registry default)
            adapter_config: Configuration for the adapter
            resilience_config: Custom resilience configuration
            **kwargs: Additional arguments for adapter constructor

        Returns:
            Configured LLM provider adapter with resilience applied

        Raises:
            KeyError: If adapter is not registered
        """
        # Determine adapter name
        if adapter_name is None:
            adapter_name = self._llm_provider_registry.get_default_name()
            if adapter_name is None:
                message = "No default LLM provider adapter configured"
                raise ValueError(message)

        logger.info(f"Creating LLM provider adapter: {adapter_name}")

        # Create base adapter instance
        if adapter_config is not None:
            kwargs["config"] = adapter_config

        # Map 'model' parameter to 'model_name' for backward compatibility with adapters
        if "model" in kwargs:
            kwargs["model_name"] = kwargs.pop("model")

        adapter = self._llm_provider_registry.create_instance(adapter_name, **kwargs)

        # Apply resilience if enabled
        return self._apply_resilience_wrapper(
            adapter,
            "llm_provider",
            CLAUDE_RESILIENCE_CONFIG,
            resilience_config,
            self._resilience_factory.create_resilient_llm_provider,
        )

    def create_container(
        self,
        adapter_name: str | None = None,
        adapter_config: Any | None = None,
        resilience_config: ServiceResilienceConfig | None = None,
        **kwargs,
    ) -> IContainer:
        """
        Create a container adapter instance.

        Args:
            adapter_name: Name of adapter to use (default: registry default)
            adapter_config: Configuration for the adapter
            resilience_config: Custom resilience configuration
            **kwargs: Additional arguments for adapter constructor

        Returns:
            Configured container adapter with resilience applied

        Raises:
            KeyError: If adapter is not registered
        """
        # Determine adapter name
        if adapter_name is None:
            adapter_name = self._container_registry.get_default_name()
            if adapter_name is None:
                message = "No default container adapter configured"
                raise ValueError(message)

        logger.info(f"Creating container adapter: {adapter_name}")

        # Create base adapter instance
        if adapter_config is not None:
            kwargs["config"] = adapter_config

        adapter = self._container_registry.create_instance(adapter_name, **kwargs)

        # Apply resilience if enabled
        return self._apply_resilience_wrapper(
            adapter,
            "container",
            CONTAINER_RESILIENCE_CONFIG,
            resilience_config,
            self._resilience_factory.create_resilient_container,
        )

    def create_repository(
        self,
        adapter_name: str | None = None,
        adapter_config: Any | None = None,
        resilience_config: ServiceResilienceConfig | None = None,
        **kwargs,
    ) -> IRepository:
        """
        Create a repository adapter instance.

        Args:
            adapter_name: Name of adapter to use (default: registry default)
            adapter_config: Configuration for the adapter
            resilience_config: Custom resilience configuration
            **kwargs: Additional arguments for adapter constructor

        Returns:
            Configured repository adapter with resilience applied

        Raises:
            KeyError: If adapter is not registered
        """
        # Determine adapter name
        if adapter_name is None:
            adapter_name = self._repository_registry.get_default_name()
            if adapter_name is None:
                message = "No default repository adapter configured"
                raise ValueError(message)

        logger.info(f"Creating repository adapter: {adapter_name}")

        # Create base adapter instance
        if adapter_config is not None:
            kwargs["config"] = adapter_config

        adapter = self._repository_registry.create_instance(adapter_name, **kwargs)

        # Apply resilience if enabled
        return self._apply_resilience_wrapper(
            adapter,
            "repository",
            REPOSITORY_RESILIENCE_CONFIG,
            resilience_config,
            self._resilience_factory.create_resilient_repository,
        )

    def _create_adapter(
        self, registry: AdapterRegistry[Any], adapter_name: str | None, adapter_type_name: str, **kwargs
    ) -> Any:
        """
        Generic helper for creating simple adapters without resilience.

        Eliminates boilerplate code across 32 create_* methods.

        Args:
            registry: The adapter registry to use
            adapter_name: Name of adapter to use (None = use default)
            adapter_type_name: Human-readable type name for logging and errors
            **kwargs: Additional arguments for adapter constructor

        Returns:
            The created adapter instance

        Raises:
            ValueError: If no default adapter is configured
        """
        resolved_name = adapter_name or registry.get_default_name()
        if not resolved_name:
            raise ValueError(f"No default {adapter_type_name} adapter configured")

        logger.info(f"Creating {adapter_type_name} adapter: {resolved_name}")
        return registry.create_instance(resolved_name, **kwargs)

    def create_event_store(self, adapter_name: str | None = None, **kwargs) -> IEventStore:
        """
        Create an event store adapter instance.

        Note: Event stores do not have resilience decorators applied because they
        are internal infrastructure components with different reliability requirements.
        Event stores should implement their own internal retry logic and persistence
        guarantees. Applying external resilience patterns like circuit breakers could
        interfere with event sourcing semantics (e.g., event ordering, causality).

        Args:
            adapter_name: Name of adapter to use (default: registry default)
            **kwargs: Additional arguments for adapter constructor

        Returns:
            Configured event store adapter (without resilience decorators)

        Raises:
            KeyError: If adapter is not registered
            ValueError: If no default adapter is configured
        """
        return self._create_adapter(self._event_store_registry, adapter_name, "event store", **kwargs)

    def create_storage(self, adapter_name: str | None = None, **kwargs) -> IStorage:
        """Create a storage adapter instance."""
        return self._create_adapter(self._storage_registry, adapter_name, "storage", **kwargs)

    def create_board_service(self, adapter_name: str | None = None, **kwargs) -> IBoardService:
        """Create a board service adapter instance."""
        return self._create_adapter(self._board_service_registry, adapter_name, "board service", **kwargs)

    def create_code_review_service(self, adapter_name: str | None = None, **kwargs) -> ICodeReviewService:
        """Create a code review service adapter instance."""
        return self._create_adapter(self._code_review_registry, adapter_name, "code review service", **kwargs)

    def create_discussion_adapter(self, adapter_name: str | None = None, **kwargs) -> IDiscussionAdapter:
        """Create a discussion adapter instance."""
        return self._create_adapter(self._discussion_adapter_registry, adapter_name, "discussion", **kwargs)

    def create_version_control_service(self, adapter_name: str | None = None, **kwargs) -> IVersionControlService:
        """Create a version control service adapter instance."""
        return self._create_adapter(self._version_control_registry, adapter_name, "version control service", **kwargs)

    def create_metrics(self, adapter_name: str | None = None, **kwargs) -> IMetrics:
        """Create a metrics adapter instance."""
        return self._create_adapter(self._metrics_registry, adapter_name, "metrics", **kwargs)

    def create_notifier(self, adapter_name: str | None = None, **kwargs) -> INotifier:
        """Create a notifier adapter instance."""
        return self._create_adapter(self._notifier_registry, adapter_name, "notifier", **kwargs)

    def create_message_broker(self, adapter_name: str | None = None, **kwargs) -> IMessageBroker:
        """Create a message broker adapter instance."""
        return self._create_adapter(self._message_broker_registry, adapter_name, "message broker", **kwargs)

    def create_config_store(self, adapter_name: str | None = None, **kwargs) -> IConfigStore:
        """Create a config store adapter instance."""
        return self._create_adapter(self._config_store_registry, adapter_name, "config store", **kwargs)

    def create_repair_cycle(self, adapter_name: str | None = None, **kwargs) -> IRepairCycle:
        """Create a repair cycle adapter instance."""
        return self._create_adapter(self._repair_cycle_registry, adapter_name, "repair cycle", **kwargs)

    def create_review_cycle_service(self, adapter_name: str | None = None, **kwargs) -> IReviewCycle:
        """Create a review cycle service adapter instance."""
        return self._create_adapter(self._review_cycle_registry, adapter_name, "review cycle service", **kwargs)

    def create_pr_review_cycle_service(self, adapter_name: str | None = None, **kwargs) -> "IPRReviewCycle":
        """Create a PR review cycle service adapter instance."""
        return self._create_adapter(self._pr_review_cycle_registry, adapter_name, "PR review cycle service", **kwargs)

    def create_container_recovery(self, adapter_name: str | None = None, **kwargs) -> IAgentContainerRecoveryService:
        """Create a container recovery adapter instance."""
        return self._create_adapter(self._container_recovery_registry, adapter_name, "container recovery", **kwargs)

    def create_encryption_service(self, adapter_name: str | None = None, **kwargs) -> IEncryptionService:
        """Create an encryption service adapter instance."""
        return self._create_adapter(self._encryption_registry, adapter_name, "encryption service", **kwargs)

    def create_pipeline_lock_service(self, adapter_name: str | None = None, **kwargs) -> IPipelineLockService:
        """Create a pipeline lock service adapter instance."""
        return self._create_adapter(self._pipeline_lock_registry, adapter_name, "pipeline lock service", **kwargs)

    def create_pipeline_queue_service(self, adapter_name: str | None = None, **kwargs) -> IPipelineQueueService:
        """Create a pipeline queue service adapter instance."""
        return self._create_adapter(self._pipeline_queue_registry, adapter_name, "pipeline queue service", **kwargs)

    def create_project_manager_service(self, adapter_name: str | None = None, **kwargs) -> IProjectManagerService:
        """Create a project manager service adapter instance."""
        return self._create_adapter(self._project_manager_registry, adapter_name, "project manager service", **kwargs)

    def create_workflow_config_service(self, adapter_name: str | None = None, **kwargs) -> IWorkflowConfigService:
        """Create a workflow config service adapter instance."""
        return self._create_adapter(self._workflow_config_registry, adapter_name, "workflow config service", **kwargs)

    def create_event_emitter(self, adapter_name: str | None = None, **kwargs) -> IEventEmitter:
        """Create an event emitter adapter instance."""
        return self._create_adapter(self._event_emitter_registry, adapter_name, "event emitter", **kwargs)

    def create_identity_service(self, adapter_name: str | None = None, **kwargs) -> IIdentityService:
        """Create an identity service adapter instance."""
        return self._create_adapter(self._identity_service_registry, adapter_name, "identity service", **kwargs)

    def create_agent_executor(self, adapter_name: str | None = None, **kwargs) -> IAgentExecutor:
        """Create an agent executor adapter instance."""
        return self._create_adapter(self._agent_executor_registry, adapter_name, "agent executor", **kwargs)

    def create_agent_repository(self, adapter_name: str | None = None, **kwargs) -> IAgentRepository:
        """Create an agent repository adapter instance."""
        return self._create_adapter(self._agent_repository_registry, adapter_name, "agent repository", **kwargs)

    def create_work_item_branch_tracker(self, adapter_name: str | None = None, **kwargs) -> IWorkItemBranchTracker:
        """Create a work item branch tracker adapter instance."""
        return self._create_adapter(
            self._work_item_branch_tracker_registry, adapter_name, "work item branch tracker", **kwargs
        )

    def create_work_item_service(self, adapter_name: str | None = None, **kwargs) -> IWorkItemService:
        """Create a work item service adapter instance."""
        return self._create_adapter(self._work_item_service_registry, adapter_name, "work item service", **kwargs)

    def create_repair_cycle_checkpoint_store(
        self, adapter_name: str | None = None, **kwargs
    ) -> IRepairCycleCheckpointStore:
        """Create a repair cycle checkpoint store adapter instance."""
        return self._create_adapter(
            self._repair_cycle_checkpoint_registry, adapter_name, "repair cycle checkpoint store", **kwargs
        )

    def create_active_workflow_run_registry(
        self, adapter_name: str | None = None, **kwargs
    ) -> IActiveWorkflowRunRegistry:
        """Create an active workflow run registry adapter instance."""
        return self._create_adapter(
            self._active_workflow_run_registry_registry, adapter_name, "active workflow run registry", **kwargs
        )

    def create_systemic_analysis_service(self, adapter_name: str | None = None, **kwargs) -> ISystemicAnalysisService:
        """Create a systemic analysis service adapter instance."""
        return self._create_adapter(
            self._systemic_analysis_registry, adapter_name, "systemic analysis service", **kwargs
        )

    def create_environment_repair_service(self, adapter_name: str | None = None, **kwargs) -> IEnvironmentRepairService:
        """Create an environment repair service adapter instance."""
        return self._create_adapter(
            self._environment_repair_registry, adapter_name, "environment repair service", **kwargs
        )

    def create_ci_pipeline_service(self, adapter_name: str | None = None, **kwargs) -> ICIPipelineService:
        """Create a CI pipeline service adapter instance."""
        return self._create_adapter(self._ci_pipeline_registry, adapter_name, "CI pipeline service", **kwargs)

    def _apply_resilience_wrapper(
        self,
        adapter: Any,
        service_type: str,
        default_config: ServiceResilienceConfig,
        resilience_config: ServiceResilienceConfig | None,
        resilience_factory_method: Callable[[Any, dict[str, Any]], Any],
    ) -> Any:
        """
        Apply resilience wrapping to an adapter with standardized error handling.

        Consolidates the identical ~15-line resilience-wrapping pattern used across
        multiple create_* methods (ticket_system, llm_provider, container, repository).

        Args:
            adapter: The base adapter instance to wrap
            service_type: Service type key for config lookup (e.g., "ticket_system")
            default_config: Default resilience configuration for this service
            resilience_config: Custom resilience configuration (None = use default)
            resilience_factory_method: Callable to apply resilience wrapping

        Returns:
            The adapter wrapped with resilience decorators

        Raises:
            Exception: Re-raised if resilience application fails
        """
        if not self._config.enable_resilience:
            return adapter

        try:
            service_config = None
            if resilience_config:
                service_config = self._convert_resilience_config_to_dict(resilience_config)
            else:
                default_resilience = self._get_resilience_config(service_type, default_config)
                service_config = self._convert_resilience_config_to_dict(default_resilience)

            return resilience_factory_method(adapter, service_config=service_config)
        except Exception as e:
            logger.error(
                f"Failed to apply resilience to {service_type} adapter: {e}",
                exc_info=True,
                extra={"error_id": "ERR_CONFIGURATION_ERROR"},
            )
            raise

    def _convert_resilience_config_to_dict(
        self, resilience_config: ServiceResilienceConfig | None
    ) -> dict[str, Any] | None:
        """
        Convert a ServiceResilienceConfig to a dict for resilience factory consumption.

        Uses isinstance() instead of hasattr() for type safety and clarity.

        Args:
            resilience_config: ServiceResilienceConfig instance or None

        Returns:
            Dictionary representation of config, or None if input is None

        Raises:
            TypeError: If config is not a ServiceResilienceConfig instance
        """
        if resilience_config is None:
            return None

        if not isinstance(resilience_config, ServiceResilienceConfig):
            message = f"resilience_config must be ServiceResilienceConfig, got {type(resilience_config).__name__}"
            raise TypeError(message)

        return resilience_config.to_dict()

    def _get_resilience_config(
        self, service_type: str, default_config: ServiceResilienceConfig
    ) -> ServiceResilienceConfig:
        """
        Get resilience configuration for a service type.

        Args:
            service_type: Type of service
            default_config: Default configuration

        Returns:
            Resilience configuration
        """
        if self._config.custom_resilience_configs and service_type in self._config.custom_resilience_configs:
            return self._config.custom_resilience_configs[service_type]
        return default_config

    def set_operation_mode(self, mode: OperationMode) -> None:
        """
        Set the operation mode for the factory.

        This affects which resilience components are used.
        Thread-safe operation.

        Args:
            mode: Operation mode
        """
        with self._lock:
            self._config.operation_mode = mode
            self._resilience_factory = ResilienceFactory(mode=mode)
            logger.info(f"Set operation mode to: {mode.value}")

    def get_operation_mode(self) -> OperationMode:
        """
        Get the current operation mode.

        Returns:
            Current operation mode
        """
        with self._lock:
            return self._config.operation_mode

    def enable_resilience(self, enable: bool = True) -> None:
        """
        Enable or disable resilience decorator application.

        Thread-safe operation.

        Args:
            enable: Whether to enable resilience
        """
        with self._lock:
            self._config.enable_resilience = enable
            logger.info(f"Resilience {'enabled' if enable else 'disabled'}")

    def is_resilience_enabled(self) -> bool:
        """
        Check if resilience is enabled.

        Returns:
            True if resilience is enabled
        """
        with self._lock:
            return self._config.enable_resilience
