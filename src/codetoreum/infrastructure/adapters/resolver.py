"""
Adapter Resolver - Configuration-driven adapter instantiation with credential validation.

This module provides:
- AdapterDependencies: Dataclass holding infrastructure dependencies
- AdapterConfigurationError: Aggregated error for missing credentials/invalid config
- AdapterResolver: Per-adapter config entries to concrete adapter instances with validation
"""

import logging
import os
from collections.abc import Awaitable, Callable
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
from codetoreum.ports.output.systemic_analysis_service import ISystemicAnalysisService
from codetoreum.ports.output.ticket_system import ITicketSystem
from codetoreum.ports.output.version_control_service import IVersionControlService
from codetoreum.ports.output.work_item_branch_tracker import IWorkItemBranchTracker
from codetoreum.ports.output.work_item_service import IWorkItemService
from codetoreum.ports.output.workflow_config_service import IWorkflowConfigService

if TYPE_CHECKING:
    from codetoreum.infrastructure.adapters.factory import AdapterFactory
    from codetoreum.infrastructure.bootstrap.production_bootstrap import ProductionCredentials
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
        credentials: "ProductionCredentials | None" = None,
    ) -> None:
        """
        Initialize the adapter resolver.

        Args:
            adapter_config: Per-adapter implementation selector
            factory: Adapter factory with registries
            dependencies: Infrastructure dependencies to inject
            credentials: Production credentials read from os.environ at bootstrap Phase 1b.
                When provided, resolve_board() and resolve_project_manager() use these
                instead of reading os.environ inline.
        """
        self._config = adapter_config
        self._factory = factory
        self._deps = dependencies
        self._credentials = credentials
        self._resolved: dict[str, Any] = {}

    def validate_credentials(self) -> None:
        """
        Pre-flight check: aggregate all missing credential errors.

        Validates all 32 adapter slots before constructing any adapter.
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
    # Resolve methods for all 32 adapter slots
    # =========================================================================

    def resolve_event_store(self) -> IEventStore:
        """Resolve event store adapter."""
        return self._factory.create_event_store(adapter_name=self._config.event_store)

    def resolve_config_store(self) -> IConfigStore:
        """Resolve config store adapter.

        For "elasticsearch", construct an AsyncElasticsearch client from
        ELASTICSEARCH_URL so the same backing storage instance can be
        reused for the ES-backed agent repository and workflow config
        service (passed in via ``self._resolved['config_store']``).
        """
        if self._config.config_store == "elasticsearch":
            import os

            from elasticsearch import AsyncElasticsearch

            es_url = os.environ.get("ELASTICSEARCH_URL", "http://localhost:9200")
            es_client = AsyncElasticsearch([es_url])
            return self._factory.create_config_store(
                adapter_name=self._config.config_store,
                es_client=es_client,
            )
        return self._factory.create_config_store(adapter_name=self._config.config_store)

    def resolve_metrics(self) -> IMetrics:
        """Resolve metrics adapter."""
        return self._factory.create_metrics(adapter_name=self._config.metrics)

    def resolve_encryption(self) -> IEncryptionService:
        """Resolve encryption service adapter."""
        return self._factory.create_encryption_service(adapter_name=self._config.encryption)

    def resolve_identity_service(self) -> IIdentityService:
        """Resolve identity service adapter."""
        return self._factory.create_identity_service(adapter_name=self._config.identity_service)

    def resolve_event_emitter(self) -> IEventEmitter:
        """Resolve event emitter adapter.

        For "redis_pubsub", constructs an aioredis client from REDIS_URL so
        emitted CodetoreumEvents propagate to subscribers in other processes.
        Local in-process handlers continue to receive events synchronously.
        """
        if self._config.event_emitter == "redis_pubsub":
            import os

            import redis.asyncio as aioredis

            redis_url = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
            redis_client = aioredis.from_url(redis_url)
            return self._factory.create_event_emitter(
                adapter_name=self._config.event_emitter,
                redis_client=redis_client,
            )
        return self._factory.create_event_emitter(adapter_name=self._config.event_emitter)

    def resolve_message_broker(self) -> IMessageBroker:
        """Resolve message broker adapter."""
        return self._factory.create_message_broker(adapter_name=self._config.message_broker)

    def resolve_ticket(self) -> ITicketSystem:
        """Resolve ticket system adapter."""
        return self._factory.create_ticket_system(adapter_name=self._config.ticket)

    def resolve_coding_agent(
        self,
        *,
        prompt_builder: Any,
        agent_repository: Any | None = None,
        work_item_service: Any | None = None,
        container: Any | None = None,
        config: Any | None = None,
    ) -> Any:
        """Resolve the new :class:`ICodingAgent` adapter (D3).

        Constructs a production :class:`ClaudeCodeAdapter` directly (or, for
        simulation mode, a :class:`MockClaudeCodeAdapter`). Wraps the result
        with :class:`ResilientCodingAgentDecorator` so the standard
        resilience patterns (rate-limit, circuit breaker, timeout, retry)
        apply across both invocation modes.

        Sole agent-execution port after Phase D5 (the historical IAgentLauncher /
        ILLMProvider ports retired in chunk 5).

        Args:
            prompt_builder: :class:`IPromptBuilder` injected by the caller.
                Created in the application layer (D2 default:
                ``DefaultPromptBuilder``).
            agent_repository: Defaults to the already-resolved
                ``agent_repository`` (production wiring) when ``None``.
            work_item_service: Defaults to the already-resolved
                ``work_item_service`` when ``None``.
            container: Optional :class:`IContainer`. When ``None`` the
                resolver supplies the already-resolved one (or ``None`` if
                the container slot was never resolved); only ``HOST`` mode
                is then supported by the resulting adapter.
            config: Optional :class:`ClaudeCodeAdapterConfig`.

        Note:
            D6 retired the ``workspace_path_resolver`` callable —
            strategies now read ``WorkspaceContext.workspace_path``
            directly (orchestrator must call
            :meth:`WorkspaceContext.with_workspace_path` before
            dispatch).

        Returns:
            A resilience-wrapped :class:`ICodingAgent` for the configured
            implementation. Implementation today: production constructs
            :class:`ClaudeCodeAdapter`; simulation can override by passing
            an alternative wrapped object via ``prompt_builder`` plumbing.
        """
        # Imports are local to avoid hard-coupling the resolver module to
        # the D3 adapter package — the resolver loads in environments that
        # might not yet have the new ports.
        from codetoreum.adapters.secondary.claude_code import (
            ClaudeCodeAdapter,
            EnvironmentCredentialProvider,
        )
        from codetoreum.infrastructure.resilience.decorators import (
            ResilientCodingAgentDecorator,
        )

        ar = agent_repository or self._resolved.get("agent_repository")
        wis = work_item_service or self._resolved.get("work_item_service")
        if ar is None or wis is None:
            raise AdapterConfigurationError(
                [
                    "resolve_coding_agent requires agent_repository and "
                    "work_item_service to be resolved first (or passed in).",
                ]
            )

        cont = container if container is not None else self._resolved.get("container")

        adapter = ClaudeCodeAdapter(
            prompt_builder=prompt_builder,
            event_bus=self._deps.event_bus,
            credential_provider=EnvironmentCredentialProvider(),
            agent_repository=ar,
            work_item_service=wis,
            container=cont,
            config=config,
        )
        # Resilience wraps the adapter (INV-11). The decorator is structural
        # — it just needs supported_invocation_modes() and execute().
        return ResilientCodingAgentDecorator(wrapped=adapter)

    def resolve_container(self) -> IContainer:
        """Resolve container adapter."""
        return self._factory.create_container(
            adapter_name=self._config.container,
            event_emitter=self._resolved["event_emitter"],
            event_bus=self._deps.event_bus,
        )

    def resolve_board(self) -> IBoardService:
        """Resolve board service adapter."""
        if self._config.board == "github":
            from codetoreum.infrastructure.http.github_graphql_client import GitHubGraphQLClient, GitHubGraphQLConfig

            # Use credentials injected at bootstrap; fall back to os.environ only when
            # running outside production bootstrap (e.g. integration tests).
            if self._credentials is not None:
                github_token = self._credentials.github_token
            else:
                import os

                github_token = os.environ.get("GITHUB_TOKEN", "")

            graphql_client = GitHubGraphQLClient(GitHubGraphQLConfig(token=github_token))
            return self._factory.create_board_service(
                adapter_name="github",
                ticket_adapter=self._resolved.get("ticket"),
                graphql_client=graphql_client,
                event_emitter=self._resolved["event_emitter"],
            )
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
            time_source=lambda: self._deps.engine.get_clock_for_testing().now(),
        )

    def resolve_lock_service(self) -> IPipelineLockService:
        """Resolve pipeline lock service adapter.

        For "redis", an aioredis client is constructed from REDIS_URL
        (defaulting to redis://localhost:6379/0) and the EventBus from
        ``_deps`` is wired so lock events flow into the in-process pub/sub
        bus alongside the persistent Redis state.
        """
        if self._config.lock_service == "redis":
            import os

            import redis.asyncio as aioredis

            redis_url = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
            redis_client = aioredis.from_url(redis_url)
            return self._factory.create_pipeline_lock_service(
                adapter_name=self._config.lock_service,
                redis_client=redis_client,
                event_bus=self._deps.event_bus,
            )
        return self._factory.create_pipeline_lock_service(adapter_name=self._config.lock_service)

    def resolve_queue_service(self) -> IPipelineQueueService:
        """Resolve pipeline queue service adapter."""
        return self._factory.create_pipeline_queue_service(
            adapter_name=self._config.queue_service,
            event_emitter=self._resolved["event_emitter"],
            event_bus=self._deps.event_bus,
            time_source=lambda: self._deps.engine.get_clock_for_testing().now(),
        )

    def resolve_checkpoint_store(self) -> IRepairCycleCheckpointStore:
        """Resolve repair cycle checkpoint store adapter."""
        return self._factory.create_repair_cycle_checkpoint_store(
            adapter_name=self._config.checkpoint_store,
            time_source=lambda: self._deps.engine.get_clock_for_testing().now(),
        )

    def resolve_agent_repository(self) -> IAgentRepository:
        """Resolve agent repository adapter.

        For "elasticsearch", inject the already-resolved
        ``ElasticsearchConfigStorage`` (from ``self._resolved['config_store']``)
        so agent configs round-trip through the same backing store as
        ``IConfigStore``.
        """
        if self._config.agent_repository == "elasticsearch":
            config_storage = self._resolved.get("config_store")
            if config_storage is None:
                raise AdapterConfigurationError(
                    [
                        "agent_repository='elasticsearch' requires config_store to be resolved first; "
                        "ensure resolve_all() runs config_store before agent_repository.",
                    ]
                )
            return self._factory.create_agent_repository(
                adapter_name=self._config.agent_repository,
                config_storage=config_storage,
            )
        return self._factory.create_agent_repository(adapter_name=self._config.agent_repository)

    def resolve_run_registry(self) -> IActiveWorkflowRunRegistry:
        """Resolve active workflow run registry adapter.

        For "redis", constructs an aioredis client from REDIS_URL so
        ActiveRunInfo records survive restart and coordinate across instances.
        """
        if self._config.run_registry == "redis":
            import os

            import redis.asyncio as aioredis

            redis_url = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
            redis_client = aioredis.from_url(redis_url)
            return self._factory.create_active_workflow_run_registry(
                adapter_name=self._config.run_registry,
                redis_client=redis_client,
            )
        return self._factory.create_active_workflow_run_registry(adapter_name=self._config.run_registry)

    def resolve_branch_tracker(self) -> IWorkItemBranchTracker:
        """Resolve work item branch tracker adapter.

        For "redis", constructs an aioredis client from REDIS_URL so the
        work_item -> branch mapping survives restart.
        """
        if self._config.branch_tracker == "redis":
            import os

            import redis.asyncio as aioredis

            redis_url = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
            redis_client = aioredis.from_url(redis_url)
            return self._factory.create_work_item_branch_tracker(
                adapter_name=self._config.branch_tracker,
                redis_client=redis_client,
            )
        return self._factory.create_work_item_branch_tracker(adapter_name=self._config.branch_tracker)

    def resolve_work_item_service(self) -> IWorkItemService:
        """Resolve work item service adapter."""
        return self._factory.create_work_item_service(
            adapter_name=self._config.work_item_service,
            time_source=lambda: self._deps.engine.get_clock_for_testing().now(),
        )

    def resolve_workflow_config(self) -> IWorkflowConfigService:
        """Resolve workflow config service adapter.

        For "elasticsearch", inject the already-resolved
        ``ElasticsearchConfigStorage`` (from ``self._resolved['config_store']``)
        so board workflow templates persist alongside the rest of the
        config plane.
        """
        if self._config.workflow_config == "elasticsearch":
            config_storage = self._resolved.get("config_store")
            if config_storage is None:
                raise AdapterConfigurationError(
                    [
                        "workflow_config='elasticsearch' requires config_store to be resolved first; "
                        "ensure resolve_all() runs config_store before workflow_config.",
                    ]
                )
            return self._factory.create_workflow_config_service(
                adapter_name=self._config.workflow_config,
                config_storage=config_storage,
            )
        return self._factory.create_workflow_config_service(adapter_name=self._config.workflow_config)

    def resolve_notifier(self) -> INotifier:
        """Resolve notifier adapter."""
        return self._factory.create_notifier(adapter_name=self._config.notifier)

    def resolve_version_control(self) -> IVersionControlService:
        """Resolve version control service adapter."""
        kwargs = {}
        if self._config.version_control == "in_memory":
            kwargs["time_source"] = lambda: self._deps.engine.get_clock_for_testing().now()
            kwargs["event_emitter"] = self._resolved["event_emitter"]
        return self._factory.create_version_control_service(
            adapter_name=self._config.version_control,
            **kwargs,
        )

    # FIXME: Latent time_source pattern throughout resolver
    # The above conditional guard pattern for time_source is also needed in:
    # - resolve_project_manager (line ~334)
    # - resolve_code_review (line ~410)
    # - resolve_container_recovery (line ~417)
    # - resolve_work_item_service (line ~309)
    # - resolve_checkpoint_store (line ~290)
    # - resolve_repository (line ~515)
    # - resolve_discussion_adapter (line ~270)
    # - resolve_queue_service (line ~283)
    # All currently unconditionally pass time_source, which will TypeError when
    # production adapters are registered for any slot if their constructors don't
    # accept time_source. See issue #851 fix for the pattern. File a follow-up
    # issue to apply this pattern systematically across all resolver methods.

    def resolve_project_manager(self) -> IProjectManagerService:
        """Resolve project manager service adapter."""
        adapter_name = self._config.project_manager
        if adapter_name == "elasticsearch":
            if self._credentials is not None:
                workspace_base = self._credentials.workspace_base
            else:
                import os

                workspace_base = os.getenv("AGENT_WORKSPACE_BASE", "/tmp/codetoreum-workspaces")

            return self._factory.create_project_manager_service(
                adapter_name=adapter_name,
                config_store=self._resolved.get("config_store"),
                base_workspace=workspace_base,
                event_emitter=self._resolved.get("event_emitter"),
            )
        return self._factory.create_project_manager_service(
            adapter_name=adapter_name,
            time_source=lambda: self._deps.engine.get_clock_for_testing().now(),
        )

    def resolve_review_cycle(self) -> IReviewCycle:
        """
        Resolve review cycle adapter.

        Special handling for SimulationEngine-coupled adapters:
        - If mock variant selected: use engine to create time-aware mock
        - If real variant: create directly without engine
        """
        if self._config.review_cycle == "mock":
            # Engine creates a time-aware mock. Causal linking against
            # ``ICodingAgent`` can be added back if a scenario needs it.
            return self._deps.engine.create_review_cycle_adapter()
        if self._config.review_cycle == "basic":
            from codetoreum.adapters.secondary.basic_review_cycle_adapter import BasicReviewCycleAdapter

            return BasicReviewCycleAdapter(
                event_emitter=self._resolved.get("event_emitter"),
                event_bus=self._deps.event_bus,
            )
        # Real adapter: bypass engine, use factory directly
        return self._factory.create_review_cycle_service(adapter_name=self._config.review_cycle)

    def resolve_pr_review_cycle(self) -> IPRReviewCycle:
        """
        Resolve PR review cycle adapter.

        Special handling for SimulationEngine-coupled adapters:
        - If mock variant selected: use engine to create time-aware mock
        - If real variant: create directly without engine

        Dependencies (ticket_system, board_service) are resolved separately
        in resolve_all() before PR review cycle creation and injected in
        bootstrap post-processing to ensure proper initialization order.
        """
        if self._config.pr_review_cycle == "mock":
            # Engine creates time-aware mock with None dependencies initially
            # Dependencies are injected in bootstrap post-processing
            return self._deps.engine.create_pr_review_cycle_adapter()
        if self._config.pr_review_cycle == "basic":
            from codetoreum.adapters.secondary.basic_pr_review_cycle_adapter import BasicPRReviewCycleAdapter

            return BasicPRReviewCycleAdapter(
                ticket_system=self._resolved.get("ticket"),
                board_service=self._resolved.get("board"),
                event_emitter=self._resolved.get("event_emitter"),
                event_bus=self._deps.event_bus,
            )
        # Real adapter: bypass engine, use factory directly
        return self._factory.create_pr_review_cycle_service(adapter_name=self._config.pr_review_cycle)

    def resolve_repair_cycle(self) -> IRepairCycle:
        """
        Resolve repair cycle adapter.

        Special handling for SimulationEngine-coupled adapters:
        - If mock variant selected: use engine to create time-aware mock.
        - If real variant: create directly without engine, wiring the
          ``coding_agent_factory``.

        The systemic_analysis_service and environment_repair_service are resolved separately
        in resolve_all() before repair_cycle creation to ensure centralized adapter resolution
        and proper dependency injection at construction time.
        """
        if self._config.repair_cycle == "mock":
            # Engine creates a time-aware mock. The mock's coding_agent_factory
            # parameter is left unset so it falls back to its own inert default
            # — the mock never invokes the factory result.
            checkpoint_store = self._resolved.get("checkpoint_store")
            container_adapter = self._resolved.get("container")

            return self._deps.engine.create_repair_cycle_adapter(
                checkpoint_store=checkpoint_store,
                container_adapter=container_adapter,
            )

        systemic_analysis_service = self._resolved.get("systemic_analysis_service")
        environment_repair_service = self._resolved.get("environment_repair_service")

        return self._factory.create_repair_cycle(
            adapter_name=self._config.repair_cycle,
            coding_agent_factory=self._create_coding_agent_factory(),
            systemic_analysis_service=systemic_analysis_service,
            environment_repair_service=environment_repair_service,
            invocation_defaults_resolver=self._create_invocation_defaults_resolver(),
        )

    def resolve_code_review(self) -> ICodeReviewService:
        """Resolve code review service adapter."""
        if self._config.code_review == "github":
            import os

            from codetoreum.adapters.secondary.github_code_review_adapter import GitHubCodeReviewAdapter
            from codetoreum.infrastructure.http.github_graphql_client import GitHubGraphQLClient, GitHubGraphQLConfig

            graphql_client = GitHubGraphQLClient(GitHubGraphQLConfig(token=os.environ.get("GITHUB_TOKEN", "")))
            return GitHubCodeReviewAdapter(
                ticket_adapter=self._resolved.get("ticket"),
                graphql_client=graphql_client,
            )
        return self._factory.create_code_review_service(
            adapter_name=self._config.code_review,
            time_source=lambda: self._deps.engine.get_clock_for_testing().now(),
        )

    def resolve_container_recovery(self) -> IAgentContainerRecoveryService:
        """Resolve container recovery adapter."""
        return self._factory.create_container_recovery(
            adapter_name=self._config.container_recovery,
            time_source=lambda: self._deps.engine.get_clock_for_testing().now(),
        )

    def resolve_ci_pipeline(self) -> ICIPipelineService:
        """Resolve CI pipeline service adapter."""
        return self._factory.create_ci_pipeline_service(
            adapter_name=self._config.ci_pipeline,
            event_emitter=self._resolved["event_emitter"],
        )

    def resolve_systemic_analysis_service(self) -> ISystemicAnalysisService:
        """Resolve systemic analysis service adapter.

        The ``"production"`` variant uses the :class:`ICodingAgent`-based
        factory injected via ``coding_agent_factory``. The bootstrap also
        wires ``invocation_defaults_resolver`` so each call honours the
        per-project coding-agent configuration instead of the adapter's
        server-wide hardcoded fallbacks.

        Returns:
            ISystemicAnalysisService implementation.
        """
        if self._config.systemic_analysis == "production":
            return self._factory.create_systemic_analysis_service(
                adapter_name=self._config.systemic_analysis,
                coding_agent_factory=self._create_coding_agent_factory(),
                invocation_defaults_resolver=self._create_invocation_defaults_resolver(),
            )

        return self._factory.create_systemic_analysis_service(
            adapter_name=self._config.systemic_analysis,
        )

    def resolve_environment_repair_service(self) -> IEnvironmentRepairService:
        """Resolve environment repair service adapter.

        The ``"production"`` variant uses the :class:`ICodingAgent`-based
        factory injected via ``coding_agent_factory``. The bootstrap also
        wires ``invocation_defaults_resolver`` so each call honours the
        per-project coding-agent configuration.

        Returns:
            IEnvironmentRepairService implementation.
        """
        if self._config.environment_repair == "production":
            return self._factory.create_environment_repair_service(
                adapter_name=self._config.environment_repair,
                coding_agent_factory=self._create_coding_agent_factory(),
                event_emitter=self._resolved["event_emitter"],
                invocation_defaults_resolver=self._create_invocation_defaults_resolver(),
            )

        return self._factory.create_environment_repair_service(
            adapter_name=self._config.environment_repair,
            event_emitter=self._resolved["event_emitter"],
        )

    def resolve_repository(self) -> IRepository:
        """Resolve repository adapter.

        Uses the resolved event_emitter (from step 2) instead of the placeholder
        to ensure consistency with SimulationAdapters.event_emitter.
        """
        return self._factory.create_repository(
            adapter_name=self._config.repository,
            event_emitter=self._resolved["event_emitter"],
            time_source=lambda: self._deps.engine.get_clock_for_testing().now(),
        )

    # =========================================================================
    # Coding-agent factory for repair-cycle / systemic-analysis / env-repair
    # =========================================================================
    #
    # The three repair adapters take a
    # ``coding_agent_factory: Callable[[IFreeFormPromptBuilder], ICodingAgent]``
    # construction dep. The factory is invoked once per free-form call
    # (analyze failures, rebuild env, fix file, etc.) and returns a fresh
    # ``FreeFormCodingAgent`` wrapped in the resilience decorator, bound
    # to the per-call adapter-local prompt builder.
    #
    def _create_coding_agent_factory(
        self,
    ) -> "Callable[[Any], Any]":
        """Build a coding-agent factory for the repair / analysis adapters.

        The returned callable matches the
        ``Callable[[IFreeFormPromptBuilder], ICodingAgent]`` shape the
        repair adapters expect. Each call constructs a fresh
        :class:`~codetoreum.adapters.secondary.free_form_coding_agent.FreeFormCodingAgent`
        bound to the supplied prompt builder, wrapped in
        :class:`ResilientCodingAgentDecorator` so the standard resilience
        patterns (rate-limit, circuit breaker, timeout, retry) apply to
        each free-form call independently.

        Note:
            The factory closure captures the resolver's resolved
            event_bus, container, and the configured Claude Code
            credential provider. The container is the same one the
            primary :class:`ClaudeCodeAdapter` uses; the credential
            provider resolves ``ANTHROPIC_API_KEY`` /
            ``CLAUDE_CODE_OAUTH_TOKEN`` from the environment.
        """
        from codetoreum.adapters.secondary.claude_code.credentials import (
            EnvironmentCredentialProvider,
        )
        from codetoreum.adapters.secondary.free_form_coding_agent import (
            FreeFormCodingAgent,
        )
        from codetoreum.infrastructure.resilience.decorators import (
            ResilientCodingAgentDecorator,
        )

        event_bus = self._deps.event_bus
        container = self._resolved.get("container")
        credential_provider = EnvironmentCredentialProvider()

        def factory(prompt_builder: Any) -> Any:
            adapter = FreeFormCodingAgent(
                prompt_builder=prompt_builder,
                event_bus=event_bus,
                credential_provider=credential_provider,
                container=container,
            )
            return ResilientCodingAgentDecorator(wrapped=adapter)

        return factory

    # =========================================================================
    # Workflow-step invocation-defaults resolver
    # =========================================================================
    #
    # Each repair adapter consults this resolver per call so each
    # sub-task (test_execution, code_fix, systemic_fix, systemic_analysis,
    # env_rebuild, env_verification, ...) honours the model / container /
    # mode configured for the agent assigned to *that* workflow step.
    # The adapter awaits ``resolve(work_item_id, agent_name)`` with the
    # resolved sub-task agent name; the closure below loads the work
    # item to derive its project, then looks up
    # ``IConfigStore.get_agent_config(project_id, agent_name)`` and
    # returns that agent's :class:`AgentInvocationConfig`.
    #
    # ``agent_name=None`` (caller has no agent context — e.g. a
    # systemic-analysis call from a context that wasn't populated)
    # short-circuits to ``None`` so the adapter falls back to its
    # constructor defaults. Any failure in the lookup chain (no work
    # item service / config store, missing project, agent config not
    # found) also returns ``None``.
    def _create_invocation_defaults_resolver(
        self,
    ) -> "Callable[[str, str | None], Awaitable[Any]]":
        """Build a per-call workflow-step resolver.

        Returns a coroutine ``async def resolve(work_item_id, agent_name)
        -> AgentInvocationConfig | None``. The closure captures the
        resolved ``work_item_service`` and ``config_store``; both are
        looked up at call time so they can be ``None`` during early
        bootstrap phases without crashing the adapter wiring.
        """
        work_item_service = self._resolved.get("work_item_service")
        config_store = self._resolved.get("config_store")

        async def resolve(work_item_id: str, agent_name: str | None) -> Any:
            if work_item_service is None or config_store is None:
                return None
            if not agent_name:
                # No agent context for this call — fall through to the
                # adapter's constructor defaults rather than guessing.
                return None
            try:
                work_item = await work_item_service.get_work_item(work_item_id)
            except Exception:
                logger.debug(
                    "Workflow-step invocation lookup: could not load work item %s; " "falling back to adapter defaults",
                    work_item_id,
                    exc_info=True,
                )
                return None
            project_id = getattr(work_item, "project_id", None)
            if not project_id:
                return None
            try:
                agent_config = await config_store.get_agent_config(project_id, agent_name)
            except Exception:
                logger.debug(
                    "Workflow-step invocation lookup: no agent config for "
                    "project=%s agent=%s; falling back to adapter defaults",
                    project_id,
                    agent_name,
                    exc_info=True,
                )
                return None
            return agent_config.invocation

        return resolve

    def resolve_all(self) -> "SimulationAdapters":
        """
        Resolve all adapters in dependency order.

        Constructs adapters following a partial ordering that respects
        adapter dependencies. Ensures adapters that depend on others
        are constructed after their dependencies.

        Returns:
            SimulationAdapters instance with all 32 adapters fully typed (includes systemic_analysis_service, environment_repair_service, and ci_pipeline)

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
        self._resolved["container"] = self.resolve_container()
        self._resolved["version_control"] = self.resolve_version_control()
        self._resolved["board"] = self.resolve_board()
        self._resolved["queue_service"] = self.resolve_queue_service()
        self._resolved["ci_pipeline"] = self.resolve_ci_pipeline()

        # 4. External system adapters
        self._resolved["ticket"] = self.resolve_ticket()
        # The ``ICodingAgent`` adapter is constructed in Phase 4c by
        # ``ProductionApplicationBootstrap``, not via this resolver.

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

        # 9. Systemic analysis service (uses a coding agent in production, used by repair_cycle)
        self._resolved["systemic_analysis_service"] = self.resolve_systemic_analysis_service()

        # 9b. Environment repair service (uses a coding agent in production, used by repair_cycle)
        self._resolved["environment_repair_service"] = self.resolve_environment_repair_service()

        # 10. Review and repair cycles depend on previously resolved adapters
        # (repair_cycle depends on checkpoint_store, container, and systemic_analysis_service)
        self._resolved["review_cycle"] = self.resolve_review_cycle()
        self._resolved["repair_cycle"] = self.resolve_repair_cycle()
        self._resolved["pr_review_cycle"] = self.resolve_pr_review_cycle()

        # 11. Code review and container recovery adapters
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
            container=self._resolved["container"],
            repository=self._resolved["repository"],
            event_store=self._resolved["event_store"],
            metrics=self._resolved["metrics"],
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
            pr_review_cycle=self._resolved["pr_review_cycle"],
            code_review=self._resolved["code_review"],
            identity_service=self._resolved["identity_service"],
            checkpoint_store=self._resolved["checkpoint_store"],
            ci_pipeline=self._resolved["ci_pipeline"],
            # Phase 3 adapters
            agent_repository=self._resolved["agent_repository"],
            run_registry=self._resolved["run_registry"],
            branch_tracker=self._resolved["branch_tracker"],
            work_item_service=self._resolved["work_item_service"],
            branch_resolution_service=self._resolved.get(
                "branch_resolution_service"
            ),  # Created in bootstrap post-processing
            # Container recovery
            container_recovery=self._resolved["container_recovery"],
            # Systemic analysis service (resolved in phase 9)
            systemic_analysis_service=self._resolved["systemic_analysis_service"],
            # Environment repair service (resolved in phase 9b)
            environment_repair_service=self._resolved["environment_repair_service"],
        )
