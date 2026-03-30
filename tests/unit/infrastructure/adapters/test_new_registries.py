"""
Unit tests for typed adapter registries.

Tests registry classes covering all adapter slots,
including interface compliance validation and adapter registration.
"""

import pytest

from codetoreum.adapters.secondary import (
    CachedConfigStore,
    GitHubBoardAdapter,
    GitHubCodeReviewAdapter,
    GitHubTicketAdapter,
    GitRepositoryAdapter,
    MockEventEmitter,
)
from codetoreum.adapters.testing import (
    CapturingMockEventEmitter,
    ConfigurableIdentityService,
    InMemoryActiveWorkflowRunRegistry,
    InMemoryAgentRepository,
    InMemoryCheckpointStore,
    InMemoryConfigStore,
    InMemoryMessageBroker,
    InMemoryMetricsAdapter,
    InMemoryQueueService,
    InMemoryStorageAdapter,
    InMemoryVersionControlService,
    InMemoryWorkflowConfigService,
    InMemoryWorkItemBranchTracker,
    MockAgentExecutor,
    MockBoardAdapter,
    MockContainerRecoveryAdapter,
    MockDiscussionAdapter,
    MockNotifierAdapter,
    MockProjectManagerAdapter,
    MockRepairCycleAdapter,
    MockReviewCycleAdapter,
    MockWorkItemService,
    SimpleEncryptionAdapter,
)

# Import optional secondary adapters
try:
    from codetoreum.adapters.secondary.github_discussion_adapter import (
        GitHubDiscussionAdapter,
    )
except ImportError:
    GitHubDiscussionAdapter = None  # type: ignore

try:
    from codetoreum.adapters.secondary.prometheus_metrics_adapter import (
        PrometheusMetricsAdapter,
    )
except ImportError:
    PrometheusMetricsAdapter = None  # type: ignore

try:
    from codetoreum.adapters.secondary.redis_pubsub_adapter import (
        RedisPubSubAdapter,
    )
except ImportError:
    RedisPubSubAdapter = None  # type: ignore
from codetoreum.infrastructure.adapters import AdapterFactory
from codetoreum.infrastructure.adapters.registries import (
    ActiveWorkflowRunRegistryRegistry,
    AgentExecutorRegistry,
    AgentRepositoryRegistry,
    BoardServiceRegistry,
    CodeReviewServiceRegistry,
    ConfigStoreRegistry,
    ContainerRecoveryRegistry,
    DiscussionAdapterRegistry,
    EncryptionRegistry,
    EventEmitterRegistry,
    IdentityServiceRegistry,
    MessageBrokerRegistry,
    MetricsAdapterRegistry,
    NotifierRegistry,
    PipelineLockServiceRegistry,
    PipelineQueueServiceRegistry,
    ProjectManagerServiceRegistry,
    RepairCycleCheckpointStoreRegistry,
    RepairCycleRegistry,
    ReviewCycleServiceRegistry,
    VersionControlServiceRegistry,
    WorkflowConfigServiceRegistry,
    WorkItemBranchTrackerRegistry,
    WorkItemServiceRegistry,
)
from codetoreum.infrastructure.adapters.registry_base import AdapterCredentialRequirement
from codetoreum.ports.output.active_workflow_run_registry import IActiveWorkflowRunRegistry
from codetoreum.ports.output.agent_executor import IAgentExecutor
from codetoreum.ports.output.agent_repository import IAgentRepository
from codetoreum.ports.output.board_service import IBoardService
from codetoreum.ports.output.code_review_service import ICodeReviewService
from codetoreum.ports.output.config_store import IConfigStore
from codetoreum.ports.output.container_recovery import IAgentContainerRecoveryService
from codetoreum.ports.output.discussion_adapter import IDiscussionAdapter
from codetoreum.ports.output.encryption_service import IEncryptionService
from codetoreum.ports.output.event_emitter import IEventEmitter
from codetoreum.ports.output.identity_service import IIdentityService
from codetoreum.ports.output.message_broker import IMessageBroker
from codetoreum.ports.output.metrics import IMetrics
from codetoreum.ports.output.notifier import INotifier
from codetoreum.ports.output.pipeline_lock_service import IPipelineLockService
from codetoreum.ports.output.pipeline_queue_service import IPipelineQueueService
from codetoreum.ports.output.project_manager_service import IProjectManagerService
from codetoreum.ports.output.repair_cycle_checkpoint_store import IRepairCycleCheckpointStore
from codetoreum.ports.output.repair_cycle_service import IRepairCycle
from codetoreum.ports.output.review_cycle_service import IReviewCycle
from codetoreum.ports.output.version_control_service import IVersionControlService
from codetoreum.ports.output.work_item_branch_tracker import IWorkItemBranchTracker
from codetoreum.ports.output.work_item_service import IWorkItemService
from codetoreum.ports.output.workflow_config_service import IWorkflowConfigService


class TestAdapterCredentialRequirement:
    """Test cases for AdapterCredentialRequirement dataclass."""

    def test_default_credential_requirement(self):
        """Test creating credential requirement with defaults."""
        req = AdapterCredentialRequirement()
        assert req.env_vars == ()
        assert req.config_keys == ()
        assert req.description == ""
        assert req.simulation_only is False

    def test_credential_requirement_with_env_vars(self):
        """Test credential requirement with environment variables."""
        req = AdapterCredentialRequirement(env_vars=("GITHUB_TOKEN", "GITHUB_ORG"), description="GitHub authentication")
        assert req.env_vars == ("GITHUB_TOKEN", "GITHUB_ORG")
        assert req.description == "GitHub authentication"
        assert req.simulation_only is False

    def test_credential_requirement_simulation_only(self):
        """Test marking adapter as simulation-only."""
        req = AdapterCredentialRequirement(description="Simulation-only adapter", simulation_only=True)
        assert req.simulation_only is True

    def test_credential_requirement_immutable(self):
        """Test that credential requirement is frozen (immutable)."""
        req = AdapterCredentialRequirement(env_vars=("TOKEN",))
        with pytest.raises(AttributeError):
            req.env_vars = ("NEW_TOKEN",)  # type: ignore


class TestBoardServiceRegistry:
    """Test cases for BoardServiceRegistry."""

    def test_registry_initialization(self):
        """Test board service registry initialization."""
        registry = BoardServiceRegistry()
        assert registry.port_interface == IBoardService
        assert len(registry) == 0

    def test_register_simulation_board_adapter(self):
        """Test registering simulation board adapter."""
        registry = BoardServiceRegistry()
        registry.register(
            name="mock",
            adapter_type=MockBoardAdapter,
            description="Mock board adapter",
            tags=["testing", "simulation"],
            set_as_default=True,
        )

        assert registry.has_adapter("mock")
        assert registry.get_default_name() == "mock"

    def test_register_production_board_adapter(self):
        """Test registering production board adapter."""
        registry = BoardServiceRegistry()
        registry.register(
            name="github",
            adapter_type=GitHubBoardAdapter,
            description="GitHub board adapter",
            tags=["production", "github"],
        )

        assert registry.has_adapter("github")

    def test_board_adapter_validates_interface(self):
        """Test that board adapters validate interface compliance."""
        registry = BoardServiceRegistry()

        # This should succeed - MockBoardAdapter implements IBoardService
        registry.register(
            name="mock",
            adapter_type=MockBoardAdapter,
            tags=["testing"],
        )

        # Verify adapter can be created
        adapter = registry.create_instance("mock")
        assert isinstance(adapter, IBoardService)


class TestCodeReviewServiceRegistry:
    """Test cases for CodeReviewServiceRegistry."""

    def test_registry_initialization(self):
        """Test code review service registry initialization."""
        registry = CodeReviewServiceRegistry()
        assert registry.port_interface == ICodeReviewService
        assert len(registry) == 0

    def test_register_code_review_adapters(self):
        """Test registering code review adapters."""
        registry = CodeReviewServiceRegistry()

        registry.register(
            name="github",
            adapter_type=GitHubCodeReviewAdapter,
            description="GitHub code review",
            tags=["production", "github"],
            set_as_default=True,
        )

        assert registry.has_adapter("github")
        assert registry.get_default_name() == "github"


class TestDiscussionAdapterRegistry:
    """Test cases for DiscussionAdapterRegistry."""

    def test_registry_initialization(self):
        """Test discussion adapter registry initialization."""
        registry = DiscussionAdapterRegistry()
        assert registry.port_interface == IDiscussionAdapter
        assert len(registry) == 0

    def test_register_discussion_adapters(self):
        """Test registering discussion adapters."""
        registry = DiscussionAdapterRegistry()

        registry.register(
            name="mock",
            adapter_type=MockDiscussionAdapter,
            tags=["testing"],
            set_as_default=True,
        )
        if GitHubDiscussionAdapter:
            registry.register(
                name="github",
                adapter_type=GitHubDiscussionAdapter,
                tags=["production", "github"],
            )
            assert registry.has_adapter("github")

        assert registry.has_adapter("mock")
        assert registry.get_default_name() == "mock"


class TestVersionControlServiceRegistry:
    """Test cases for VersionControlServiceRegistry."""

    def test_registry_initialization(self):
        """Test version control service registry initialization."""
        registry = VersionControlServiceRegistry()
        assert registry.port_interface == IVersionControlService
        assert len(registry) == 0

    def test_register_version_control_adapters(self):
        """Test registering version control adapters."""
        registry = VersionControlServiceRegistry()

        registry.register(
            name="in_memory",
            adapter_type=InMemoryVersionControlService,
            tags=["testing", "simulation"],
            set_as_default=True,
        )

        assert registry.has_adapter("in_memory")


class TestMetricsAdapterRegistry:
    """Test cases for MetricsAdapterRegistry."""

    def test_registry_initialization(self):
        """Test metrics adapter registry initialization."""
        registry = MetricsAdapterRegistry()
        assert registry.port_interface == IMetrics
        assert len(registry) == 0

    def test_register_metrics_adapters(self):
        """Test registering metrics adapters."""
        registry = MetricsAdapterRegistry()

        registry.register(
            name="in_memory",
            adapter_type=InMemoryMetricsAdapter,
            tags=["testing", "simulation"],
            set_as_default=True,
        )
        if PrometheusMetricsAdapter:
            registry.register(
                name="prometheus",
                adapter_type=PrometheusMetricsAdapter,
                tags=["production"],
            )
            assert registry.has_adapter("prometheus")

        assert registry.has_adapter("in_memory")


class TestNotifierRegistry:
    """Test cases for NotifierRegistry."""

    def test_registry_initialization(self):
        """Test notifier registry initialization."""
        registry = NotifierRegistry()
        assert registry.port_interface == INotifier
        assert len(registry) == 0

    def test_register_notifier_adapters(self):
        """Test registering notifier adapters."""
        registry = NotifierRegistry()

        registry.register(
            name="mock",
            adapter_type=MockNotifierAdapter,
            description="Mock notifier for testing",
            tags=["testing", "simulation"],
            set_as_default=True,
        )

        assert registry.has_adapter("mock")


class TestMessageBrokerRegistry:
    """Test cases for MessageBrokerRegistry."""

    def test_registry_initialization(self):
        """Test message broker registry initialization."""
        registry = MessageBrokerRegistry()
        assert registry.port_interface == IMessageBroker
        assert len(registry) == 0

    def test_register_message_broker_adapters(self):
        """Test registering message broker adapters."""
        registry = MessageBrokerRegistry()

        registry.register(
            name="in_memory",
            adapter_type=InMemoryMessageBroker,
            tags=["testing", "simulation"],
            set_as_default=True,
        )
        if RedisPubSubAdapter:
            registry.register(
                name="redis",
                adapter_type=RedisPubSubAdapter,
                tags=["production"],
            )
            assert registry.has_adapter("redis")

        assert registry.has_adapter("in_memory")


class TestConfigStoreRegistry:
    """Test cases for ConfigStoreRegistry."""

    def test_registry_initialization(self):
        """Test config store registry initialization."""
        registry = ConfigStoreRegistry()
        assert registry.port_interface == IConfigStore
        assert len(registry) == 0

    def test_register_config_store_adapters(self):
        """Test registering config store adapters."""
        registry = ConfigStoreRegistry()

        registry.register(
            name="in_memory",
            adapter_type=InMemoryConfigStore,
            tags=["testing"],
            set_as_default=True,
        )
        registry.register(
            name="cached",
            adapter_type=CachedConfigStore,
            tags=["production"],
        )

        assert registry.has_adapter("in_memory")
        assert registry.has_adapter("cached")


class TestRepairCycleRegistry:
    """Test cases for RepairCycleRegistry."""

    def test_registry_initialization(self):
        """Test repair cycle registry initialization."""
        registry = RepairCycleRegistry()
        assert registry.port_interface == IRepairCycle
        assert len(registry) == 0

    def test_register_repair_cycle_adapters(self):
        """Test registering repair cycle adapters."""
        registry = RepairCycleRegistry()

        registry.register(
            name="mock",
            adapter_type=MockRepairCycleAdapter,
            tags=["testing", "simulation"],
            set_as_default=True,
        )

        assert registry.has_adapter("mock")


class TestReviewCycleServiceRegistry:
    """Test cases for ReviewCycleServiceRegistry."""

    def test_registry_initialization(self):
        """Test review cycle service registry initialization."""
        registry = ReviewCycleServiceRegistry()
        assert registry.port_interface == IReviewCycle
        assert len(registry) == 0

    def test_register_review_cycle_adapters(self):
        """Test registering review cycle adapters."""
        registry = ReviewCycleServiceRegistry()

        registry.register(
            name="mock",
            adapter_type=MockReviewCycleAdapter,
            tags=["testing", "simulation"],
            set_as_default=True,
        )

        assert registry.has_adapter("mock")


class TestContainerRecoveryRegistry:
    """Test cases for ContainerRecoveryRegistry."""

    def test_registry_initialization(self):
        """Test container recovery registry initialization."""
        registry = ContainerRecoveryRegistry()
        assert registry.port_interface == IAgentContainerRecoveryService
        assert len(registry) == 0

    def test_register_container_recovery_adapters(self):
        """Test registering container recovery adapters."""
        registry = ContainerRecoveryRegistry()

        registry.register(
            name="mock",
            adapter_type=MockContainerRecoveryAdapter,
            tags=["testing", "simulation"],
            set_as_default=True,
        )

        assert registry.has_adapter("mock")


class TestEncryptionRegistry:
    """Test cases for EncryptionRegistry."""

    def test_registry_initialization(self):
        """Test encryption registry initialization."""
        registry = EncryptionRegistry()
        assert registry.port_interface == IEncryptionService
        assert len(registry) == 0

    def test_register_encryption_adapters(self):
        """Test registering encryption adapters."""
        registry = EncryptionRegistry()

        registry.register(
            name="simple",
            adapter_type=SimpleEncryptionAdapter,
            description="Simple encryption for testing",
            tags=["simulation"],
            set_as_default=True,
        )

        assert registry.has_adapter("simple")


class TestPipelineQueueServiceRegistry:
    """Test cases for PipelineQueueServiceRegistry."""

    def test_registry_initialization(self):
        """Test pipeline queue service registry initialization."""
        registry = PipelineQueueServiceRegistry()
        assert registry.port_interface == IPipelineQueueService
        assert len(registry) == 0

    def test_register_pipeline_queue_adapters(self):
        """Test registering pipeline queue adapters."""
        registry = PipelineQueueServiceRegistry()

        registry.register(
            name="in_memory",
            adapter_type=InMemoryQueueService,
            tags=["testing", "simulation"],
            set_as_default=True,
        )

        assert registry.has_adapter("in_memory")


class TestProjectManagerServiceRegistry:
    """Test cases for ProjectManagerServiceRegistry."""

    def test_registry_initialization(self):
        """Test project manager service registry initialization."""
        registry = ProjectManagerServiceRegistry()
        assert registry.port_interface == IProjectManagerService
        assert len(registry) == 0

    def test_register_project_manager_adapters(self):
        """Test registering project manager adapters."""
        registry = ProjectManagerServiceRegistry()

        registry.register(
            name="mock",
            adapter_type=MockProjectManagerAdapter,
            tags=["testing", "simulation"],
            set_as_default=True,
        )

        assert registry.has_adapter("mock")


class TestWorkflowConfigServiceRegistry:
    """Test cases for WorkflowConfigServiceRegistry."""

    def test_registry_initialization(self):
        """Test workflow config service registry initialization."""
        registry = WorkflowConfigServiceRegistry()
        assert registry.port_interface == IWorkflowConfigService
        assert len(registry) == 0

    def test_register_workflow_config_adapters(self):
        """Test registering workflow config adapters."""
        registry = WorkflowConfigServiceRegistry()

        registry.register(
            name="in_memory",
            adapter_type=InMemoryWorkflowConfigService,
            tags=["testing", "simulation"],
            set_as_default=True,
        )

        assert registry.has_adapter("in_memory")


class TestEventEmitterRegistry:
    """Test cases for EventEmitterRegistry."""

    def test_registry_initialization(self):
        """Test event emitter registry initialization."""
        registry = EventEmitterRegistry()
        assert registry.port_interface == IEventEmitter
        assert len(registry) == 0

    def test_register_event_emitter_adapters(self):
        """Test registering event emitter adapters."""
        registry = EventEmitterRegistry()

        registry.register(
            name="mock",
            adapter_type=MockEventEmitter,
            tags=["testing", "simulation"],
            set_as_default=True,
        )
        registry.register(
            name="capturing",
            adapter_type=CapturingMockEventEmitter,
            tags=["testing", "simulation"],
        )

        assert registry.has_adapter("mock")
        assert registry.has_adapter("capturing")


class TestIdentityServiceRegistry:
    """Test cases for IdentityServiceRegistry."""

    def test_registry_initialization(self):
        """Test identity service registry initialization."""
        registry = IdentityServiceRegistry()
        assert registry.port_interface == IIdentityService
        assert len(registry) == 0

    def test_register_identity_service_adapters(self):
        """Test registering identity service adapters."""
        registry = IdentityServiceRegistry()

        registry.register(
            name="configurable",
            adapter_type=ConfigurableIdentityService,
            tags=["testing", "simulation", "production"],
            set_as_default=True,
        )

        assert registry.has_adapter("configurable")


class TestAgentExecutorRegistry:
    """Test cases for AgentExecutorRegistry."""

    def test_registry_initialization(self):
        """Test agent executor registry initialization."""
        registry = AgentExecutorRegistry()
        assert registry.port_interface == IAgentExecutor
        assert len(registry) == 0

    def test_register_agent_executor_adapters(self):
        """Test registering agent executor adapters."""
        registry = AgentExecutorRegistry()

        registry.register(
            name="mock",
            adapter_type=MockAgentExecutor,
            tags=["testing", "simulation"],
            set_as_default=True,
        )

        assert registry.has_adapter("mock")


class TestAgentRepositoryRegistry:
    """Test cases for AgentRepositoryRegistry."""

    def test_registry_initialization(self):
        """Test agent repository registry initialization."""
        registry = AgentRepositoryRegistry()
        assert registry.port_interface == IAgentRepository
        assert len(registry) == 0

    def test_register_agent_repository_adapters(self):
        """Test registering agent repository adapters."""
        registry = AgentRepositoryRegistry()

        registry.register(
            name="in_memory",
            adapter_type=InMemoryAgentRepository,
            tags=["testing", "simulation"],
            set_as_default=True,
        )

        assert registry.has_adapter("in_memory")


class TestWorkItemBranchTrackerRegistry:
    """Test cases for WorkItemBranchTrackerRegistry."""

    def test_registry_initialization(self):
        """Test work item branch tracker registry initialization."""
        registry = WorkItemBranchTrackerRegistry()
        assert registry.port_interface == IWorkItemBranchTracker
        assert len(registry) == 0

    def test_register_work_item_branch_tracker_adapters(self):
        """Test registering work item branch tracker adapters."""
        registry = WorkItemBranchTrackerRegistry()

        registry.register(
            name="in_memory",
            adapter_type=InMemoryWorkItemBranchTracker,
            tags=["testing", "simulation"],
            set_as_default=True,
        )

        assert registry.has_adapter("in_memory")


class TestWorkItemServiceRegistry:
    """Test cases for WorkItemServiceRegistry."""

    def test_registry_initialization(self):
        """Test work item service registry initialization."""
        registry = WorkItemServiceRegistry()
        assert registry.port_interface == IWorkItemService
        assert len(registry) == 0

    def test_register_work_item_service_adapters(self):
        """Test registering work item service adapters."""
        registry = WorkItemServiceRegistry()

        registry.register(
            name="mock",
            adapter_type=MockWorkItemService,
            tags=["testing", "simulation"],
            set_as_default=True,
        )

        assert registry.has_adapter("mock")


class TestRepairCycleCheckpointStoreRegistry:
    """Test cases for RepairCycleCheckpointStoreRegistry."""

    def test_registry_initialization(self):
        """Test repair cycle checkpoint store registry initialization."""
        registry = RepairCycleCheckpointStoreRegistry()
        assert registry.port_interface == IRepairCycleCheckpointStore
        assert len(registry) == 0

    def test_register_checkpoint_store_adapters(self):
        """Test registering checkpoint store adapters."""
        registry = RepairCycleCheckpointStoreRegistry()

        registry.register(
            name="in_memory",
            adapter_type=InMemoryCheckpointStore,
            tags=["testing", "simulation"],
            set_as_default=True,
        )

        assert registry.has_adapter("in_memory")


class TestActiveWorkflowRunRegistryRegistry:
    """Test cases for ActiveWorkflowRunRegistryRegistry."""

    def test_registry_initialization(self):
        """Test active workflow run registry initialization."""
        registry = ActiveWorkflowRunRegistryRegistry()
        assert registry.port_interface == IActiveWorkflowRunRegistry
        assert len(registry) == 0

    def test_register_active_workflow_run_adapters(self):
        """Test registering active workflow run adapters."""
        registry = ActiveWorkflowRunRegistryRegistry()

        registry.register(
            name="in_memory",
            adapter_type=InMemoryActiveWorkflowRunRegistry,
            tags=["testing", "simulation"],
            set_as_default=True,
        )

        assert registry.has_adapter("in_memory")


class TestAdapterFactoryWithNewRegistries:
    """Test cases for AdapterFactory with new registries."""

    def test_factory_has_all_registries(self):
        """Test that factory has all new registries."""
        factory = AdapterFactory()

        # Check all new registries exist
        assert factory.board_service_registry is not None
        assert factory.code_review_registry is not None
        assert factory.discussion_adapter_registry is not None
        assert factory.version_control_registry is not None
        assert factory.metrics_registry is not None
        assert factory.notifier_registry is not None
        assert factory.message_broker_registry is not None
        assert factory.config_store_registry is not None
        assert factory.repair_cycle_registry is not None
        assert factory.review_cycle_registry is not None
        assert factory.container_recovery_registry is not None
        assert factory.encryption_registry is not None
        assert factory.pipeline_lock_registry is not None
        assert factory.pipeline_queue_registry is not None
        assert factory.project_manager_registry is not None
        assert factory.workflow_config_registry is not None
        assert factory.event_emitter_registry is not None
        assert factory.identity_service_registry is not None
        assert factory.agent_executor_registry is not None
        assert factory.agent_repository_registry is not None
        assert factory.work_item_branch_tracker_registry is not None
        assert factory.work_item_service_registry is not None
        assert factory.repair_cycle_checkpoint_registry is not None
        assert factory.active_workflow_run_registry_registry is not None

    def test_factory_registries_have_defaults(self):
        """Test that all factory registries have default adapters registered."""
        factory = AdapterFactory()

        # Board service
        assert factory.board_service_registry.get_default_name() is not None
        # Code review service
        assert factory.code_review_registry.get_default_name() is not None
        # Discussion adapter
        assert factory.discussion_adapter_registry.get_default_name() is not None
        # Version control service
        assert factory.version_control_registry.get_default_name() is not None
        # Metrics
        assert factory.metrics_registry.get_default_name() is not None
        # Notifier
        assert factory.notifier_registry.get_default_name() is not None
        # Message broker
        assert factory.message_broker_registry.get_default_name() is not None
        # Config store
        assert factory.config_store_registry.get_default_name() is not None
        # Repair cycle
        assert factory.repair_cycle_registry.get_default_name() is not None
        # Review cycle
        assert factory.review_cycle_registry.get_default_name() is not None
        # Container recovery
        assert factory.container_recovery_registry.get_default_name() is not None
        # Encryption
        assert factory.encryption_registry.get_default_name() is not None
        # Pipeline queue
        assert factory.pipeline_queue_registry.get_default_name() is not None
        # Project manager
        assert factory.project_manager_registry.get_default_name() is not None
        # Workflow config
        assert factory.workflow_config_registry.get_default_name() is not None
        # Event emitter
        assert factory.event_emitter_registry.get_default_name() is not None
        # Identity service
        assert factory.identity_service_registry.get_default_name() is not None
        # Agent executor
        assert factory.agent_executor_registry.get_default_name() is not None
        # Agent repository
        assert factory.agent_repository_registry.get_default_name() is not None
        # Work item branch tracker
        assert factory.work_item_branch_tracker_registry.get_default_name() is not None
        # Work item service
        assert factory.work_item_service_registry.get_default_name() is not None
        # Repair cycle checkpoint
        assert factory.repair_cycle_checkpoint_registry.get_default_name() is not None
        # Active workflow run registry
        assert factory.active_workflow_run_registry_registry.get_default_name() is not None

    def test_factory_create_methods(self):
        """Test that factory create_* methods work for all adapters."""
        factory = AdapterFactory()

        # Board service (use mock to avoid constructor dependencies)
        board = factory.create_board_service(adapter_name="mock")
        assert isinstance(board, IBoardService)

        # Code review service (use mock if available, otherwise skip)
        try:
            code_review = factory.create_code_review_service()
            assert isinstance(code_review, ICodeReviewService)
        except TypeError:
            pass  # Production adapter needs config

        # Discussion adapter (may need constructor params)
        try:
            discussion = factory.create_discussion_adapter()
            assert isinstance(discussion, IDiscussionAdapter)
        except TypeError:
            pass  # Adapter needs constructor parameters

        # Version control
        version_control = factory.create_version_control_service()
        assert isinstance(version_control, IVersionControlService)

        # Metrics
        metrics = factory.create_metrics()
        assert isinstance(metrics, IMetrics)

        # Notifier
        notifier = factory.create_notifier()
        assert isinstance(notifier, INotifier)

        # Message broker
        message_broker = factory.create_message_broker()
        assert isinstance(message_broker, IMessageBroker)

        # Config store
        config_store = factory.create_config_store()
        assert isinstance(config_store, IConfigStore)

        # Repair cycle (needs llm_factory for mock)
        from codetoreum.adapters.testing.mock_llm_adapter import MockLLMAdapter

        llm_adapter = MockLLMAdapter()

        def llm_factory(agent_name: str):
            return llm_adapter

        # Mock repair cycle should succeed with factory provided
        repair_cycle = factory.create_repair_cycle(
            adapter_name="mock", llm_factory=llm_factory
        )
        assert repair_cycle is not None

        # Review cycle
        review_cycle = factory.create_review_cycle_service()
        assert review_cycle is not None

        # Container recovery
        container_recovery = factory.create_container_recovery()
        assert isinstance(container_recovery, IAgentContainerRecoveryService)

        # Encryption
        encryption = factory.create_encryption_service()
        assert isinstance(encryption, IEncryptionService)

        # Pipeline queue
        queue = factory.create_pipeline_queue_service()
        assert isinstance(queue, IPipelineQueueService)

        # Project manager
        project_manager = factory.create_project_manager_service()
        assert isinstance(project_manager, IProjectManagerService)

        # Workflow config
        workflow_config = factory.create_workflow_config_service()
        assert isinstance(workflow_config, IWorkflowConfigService)

        # Event emitter
        event_emitter = factory.create_event_emitter()
        assert isinstance(event_emitter, IEventEmitter)

        # Identity service
        identity = factory.create_identity_service()
        assert isinstance(identity, IIdentityService)

        # Agent executor
        agent_executor = factory.create_agent_executor()
        assert isinstance(agent_executor, IAgentExecutor)

        # Agent repository
        agent_repo = factory.create_agent_repository()
        assert isinstance(agent_repo, IAgentRepository)

        # Work item branch tracker
        branch_tracker = factory.create_work_item_branch_tracker()
        assert isinstance(branch_tracker, IWorkItemBranchTracker)

        # Work item service
        work_item = factory.create_work_item_service()
        assert isinstance(work_item, IWorkItemService)

        # Repair cycle checkpoint
        checkpoint = factory.create_repair_cycle_checkpoint_store()
        assert isinstance(checkpoint, IRepairCycleCheckpointStore)

        # Active workflow run registry
        active_run = factory.create_active_workflow_run_registry()
        assert isinstance(active_run, IActiveWorkflowRunRegistry)

    def test_create_specific_adapter_by_name(self):
        """Test creating specific adapters by name."""
        factory = AdapterFactory()

        # Create board by specific name
        board = factory.create_board_service(adapter_name="mock")
        assert isinstance(board, IBoardService)

        # Create metrics by specific name
        metrics = factory.create_metrics(adapter_name="in_memory")
        assert isinstance(metrics, IMetrics)

        # Create message broker by specific name
        broker = factory.create_message_broker(adapter_name="in_memory")
        assert isinstance(broker, IMessageBroker)

    def test_create_nonexistent_adapter_raises_error(self):
        """Test that creating nonexistent adapter raises KeyError."""
        factory = AdapterFactory()

        with pytest.raises(KeyError):
            factory.create_board_service(adapter_name="nonexistent")

        with pytest.raises(KeyError):
            factory.create_metrics(adapter_name="nonexistent")


class TestRegistryInterfaceCompliance:
    """Test cases for interface compliance validation."""

    def test_all_registered_adapters_comply_with_interface(self):
        """Test that all registered adapters comply with their interfaces."""
        factory = AdapterFactory()

        # Test board service (skip production adapters that need config)
        for adapter_name in factory.board_service_registry.list_adapters():
            if adapter_name.startswith("github"):
                continue  # Skip GitHub adapter - requires ticket_adapter and graphql_client
            adapter = factory.create_board_service(adapter_name=adapter_name)
            assert isinstance(adapter, IBoardService)

        # Test code review service (skip production adapters that need config)
        for adapter_name in factory.code_review_registry.list_adapters():
            if adapter_name.startswith("github"):
                continue  # Skip GitHub adapter - requires ticket_adapter and graphql_client
            adapter = factory.create_code_review_service(adapter_name=adapter_name)
            assert isinstance(adapter, ICodeReviewService)

        # Test metrics
        for adapter_name in factory.metrics_registry.list_adapters():
            if adapter_name.startswith("prometheus"):
                continue  # Skip Prometheus - may require config
            adapter = factory.create_metrics(adapter_name=adapter_name)
            assert isinstance(adapter, IMetrics)

        # Test message broker
        for adapter_name in factory.message_broker_registry.list_adapters():
            if adapter_name.startswith("redis"):
                continue  # Skip Redis - requires config
            adapter = factory.create_message_broker(adapter_name=adapter_name)
            assert isinstance(adapter, IMessageBroker)
