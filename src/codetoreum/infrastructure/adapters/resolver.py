"""
Adapter Resolver - Configuration-driven adapter instantiation with credential validation.

This module provides:
- AdapterDependencies: Dataclass holding infrastructure dependencies
- AdapterConfigurationError: Aggregated error for missing credentials/invalid config
- AdapterResolver: Per-adapter config entries to concrete adapter instances with validation
"""

import asyncio
import logging
import os
import threading
from collections.abc import Callable, Coroutine
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from codetoreum.domain.agent import Agent
from codetoreum.infrastructure.adapters.registry_base import (
    AdapterCredentialRequirement,
)
from codetoreum.infrastructure.event_bus import EventBus
from codetoreum.infrastructure.simulation.simulation_config import AdapterSelectionConfig
from codetoreum.ports.exceptions import ResourceNotFoundError
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

    def resolve_storage(self) -> IStorage:
        """Resolve storage adapter.

        For "minio", construct a ``minio.Minio`` client from the
        MINIO_* env vars (endpoint, access key, secret key, secure
        flag) and inject the bucket name (default
        ``codetoreum-artifacts``).
        """
        if self._config.storage == "minio":
            import os

            from minio import Minio

            endpoint = os.environ.get("MINIO_ENDPOINT", "localhost:9000")
            access_key = os.environ.get("MINIO_ACCESS_KEY", "minioadmin")
            secret_key = os.environ.get("MINIO_SECRET_KEY", "minioadmin")
            bucket = os.environ.get("MINIO_BUCKET", "codetoreum-artifacts")
            secure = os.environ.get("MINIO_SECURE", "false").strip().lower() in {
                "true",
                "1",
                "yes",
                "on",
            }
            client = Minio(
                endpoint,
                access_key=access_key,
                secret_key=secret_key,
                secure=secure,
            )
            return self._factory.create_storage(
                adapter_name=self._config.storage,
                client=client,
                bucket=bucket,
                event_emitter=self._resolved["event_emitter"],
                event_bus=self._deps.event_bus,
            )
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
        """Resolve work item branch tracker adapter."""
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
            # Engine creates time-aware mock with optional LLM adapter
            llm_adapter = self._resolved.get("llm")
            return self._deps.engine.create_review_cycle_adapter(llm_adapter=llm_adapter)
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
        - If mock variant selected: use engine to create time-aware mock with llm_factory
        - If real variant: create directly without engine

        The systemic_analysis_service and environment_repair_service are resolved separately
        in resolve_all() before repair_cycle creation to ensure centralized adapter resolution
        and proper dependency injection at construction time.
        """
        if self._config.repair_cycle == "mock":
            # Engine creates time-aware mock with llm_factory for contract enforcement
            checkpoint_store = self._resolved.get("checkpoint_store")
            container_adapter = self._resolved.get("container")
            return self._deps.engine.create_repair_cycle_adapter(
                llm_factory=self._create_agent_llm_factory(),
                checkpoint_store=checkpoint_store,
                container_adapter=container_adapter,
            )
        # Real adapter: inject agent-aware factory and pre-resolved services
        # Use the pre-resolved systemic_analysis_service (resolved in phase 9)
        # Use the pre-resolved environment_repair_service (resolved in phase 9b)
        systemic_analysis_service = self._resolved.get("systemic_analysis_service")
        environment_repair_service = self._resolved.get("environment_repair_service")

        return self._factory.create_repair_cycle(
            adapter_name=self._config.repair_cycle,
            llm_factory=self._create_agent_llm_factory(),
            agent_repository=self._resolved["agent_repository"],
            systemic_analysis_service=systemic_analysis_service,
            environment_repair_service=environment_repair_service,
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

        Follows the standard resolver pattern: reads from own config key (`systemic_analysis`)
        and delegates to factory method.

        When the configured adapter requires dependencies (e.g., LLM provider for production):
        - Ensures those dependencies are already resolved
        - Passes them to the factory method
        - Raises AdapterConfigurationError if dependencies are missing in production

        Returns:
            ISystemicAnalysisService implementation

        Raises:
            AdapterConfigurationError: If production adapter is configured but required
                                        dependencies (llm_provider) are missing
        """
        # For "llm" adapter, we need the resolved LLM provider
        if self._config.systemic_analysis == "llm":
            llm_provider = self._resolved.get("llm")
            if not llm_provider:
                raise AdapterConfigurationError(
                    [
                        "systemic_analysis adapter set to 'llm' but llm_provider is not resolved. "
                        "Ensure llm_provider is resolved before systemic_analysis service.",
                    ]
                )
            return self._factory.create_systemic_analysis_service(
                adapter_name=self._config.systemic_analysis,
                llm_factory=lambda: llm_provider,
            )

        # For all other adapters (mock, in_memory, etc.), use factory with no extra args
        return self._factory.create_systemic_analysis_service(
            adapter_name=self._config.systemic_analysis,
        )

    def resolve_environment_repair_service(self) -> IEnvironmentRepairService:
        """Resolve environment repair service adapter.

        Follows the standard resolver pattern: reads from adapter config
        and delegates to factory method.

        For "production" adapter, injects the LLM factory for environment
        rebuild and verification operations. Uses _create_agent_llm_factory()
        to provide agent-aware LLM resolution, matching the pattern used
        for repair_cycle adapter.

        Returns:
            IEnvironmentRepairService implementation

        Raises:
            AdapterConfigurationError: If production adapter is configured but agent_repository
                                        is not yet resolved
        """
        # For "production" adapter, we need the agent-aware LLM factory
        if self._config.environment_repair == "production":
            # Ensure agent_repository is resolved before creating the factory
            agent_repo = self._resolved.get("agent_repository")
            if not agent_repo:
                raise AdapterConfigurationError(
                    [
                        "environment_repair adapter set to 'production' but agent_repository is not resolved. "
                        "Ensure agent_repository is resolved before environment_repair service.",
                    ]
                )
            return self._factory.create_environment_repair_service(
                adapter_name=self._config.environment_repair,
                llm_factory=self._create_agent_llm_factory(),
                event_emitter=self._resolved["event_emitter"],
            )

        # For all other adapters (mock, in_memory, etc.), use factory with optional event_emitter
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
    # Private factory construction helpers for repair cycle
    # =========================================================================

    def _create_agent_llm_factory(
        self,
    ) -> Callable[[str], Coroutine[Any, Any, ILLMProvider]]:
        """Create an async factory closure that resolves agents and returns LLM providers.

        Returns an async-safe factory function that can be called from both sync and async
        contexts. The factory is safe because:

        1. Cache Pre-population (at factory creation time):
           - For sync repositories (e.g., InMemoryAgentRepository): Cache is eagerly
             populated by fetching all agents synchronously via get_all_sync()
           - For async repositories: Cache population is attempted but may be incomplete;
             on-demand fetching will complete any cache misses

        2. Async-Safe Design:
           - Factory returns a coroutine, allowing callers to use 'await factory(agent_name)'
           - Cache lookups are synchronous (return immediately if cached)
           - Only cache misses trigger async lookups, which are safe from async contexts
           - Eliminates asyncio.run() which cannot be called from existing event loops

        3. On-Demand Population (when factory is called):
           - If agent is in cache, return immediately (synchronous path)
           - If cache miss and sync method available: fetch synchronously
           - If cache miss and async method: await the async call (safe from async context)

        Returns:
            Async callable Callable[[str], Coroutine[Any, Any, ILLMProvider]] that takes
            agent_name and returns a coroutine resolving to an ILLMProvider configured
            for that agent

        Raises:
            KeyError: If agent_repository not yet resolved when factory is created
            ResourceNotFoundError: If factory is awaited with unknown agent name
        """
        # Guard check: agent_repository must be resolved before we create the factory
        agent_repo = self._resolved["agent_repository"]
        if agent_repo is None:
            raise KeyError("agent_repository not resolved before repair_cycle")

        # Pre-populate cache at resolve time (synchronously)
        llm_provider_cache: dict[str, ILLMProvider] = {}
        llm_provider_cache_lock = threading.Lock()

        # Attempt synchronous cache population at factory creation time
        # For InMemoryAgentRepository, use get_all_sync() directly
        if hasattr(agent_repo, "get_all_sync") and callable(agent_repo.get_all_sync):
            try:
                agents = agent_repo.get_all_sync()
                with llm_provider_cache_lock:
                    for agent in agents:
                        llm_provider_cache[agent.name] = self._build_llm_provider(agent)
                logger.debug(
                    f"Pre-populated LLM provider cache with {len(agents)} agents",
                    extra={
                        "agent_count": len(agents),
                        "repo_type": type(agent_repo).__name__,
                    },
                )
            except Exception as e:
                logger.warning(
                    f"Failed to pre-populate LLM provider cache using get_all_sync: {e}",
                    extra={
                        "error": str(e),
                        "repo_type": type(agent_repo).__name__,
                        "error_id": "ERR_CACHE_POPULATION_FAILED",
                    },
                    exc_info=True,
                )

        async def factory(agent_name: str) -> ILLMProvider:
            """Async factory function that resolves an agent's LLM provider.

            Implements async-safe resolution with cache checking and on-demand fetching.
            Safe to call from both sync and async contexts (via 'await factory(name)').

            Args:
                agent_name: Name of the agent to look up

            Returns:
                Coroutine that resolves to an ILLMProvider configured for the agent

            Raises:
                ResourceNotFoundError: If agent with given name not found in repository
            """
            # Check cache first (thread-safe, synchronous)
            with llm_provider_cache_lock:
                if agent_name in llm_provider_cache:
                    return llm_provider_cache[agent_name]

            # On-demand population: fetch the agent and build its provider
            try:
                agent = None

                # Prefer synchronous method if available (InMemoryAgentRepository)
                if hasattr(agent_repo, "get_by_name_sync") and callable(agent_repo.get_by_name_sync):
                    agent = agent_repo.get_by_name_sync(agent_name)
                # Check if get_by_name is async
                elif asyncio.iscoroutinefunction(agent_repo.get_by_name):
                    # Async repository: await the coroutine (safe from async context)
                    agent = await agent_repo.get_by_name(agent_name)
                else:
                    # Sync call - safe to make directly
                    agent = agent_repo.get_by_name(agent_name)

                if agent is None:
                    raise ResourceNotFoundError("Agent", agent_name)

                # Build and cache the provider (thread-safe)
                provider = self._build_llm_provider(agent)
                with llm_provider_cache_lock:
                    llm_provider_cache[agent_name] = provider
                return provider

            except (KeyError, AttributeError, ResourceNotFoundError) as e:
                # Expected exceptions from repository access or missing agents
                if isinstance(e, ResourceNotFoundError):
                    raise
                # Log and convert other expected errors
                logger.error(
                    f"Failed to resolve agent '{agent_name}': {e}",
                    extra={
                        "agent_name": agent_name,
                        "available_agents_in_cache": list(llm_provider_cache.keys()),
                        "error_id": "ERR_AGENT_LOOKUP_FAILED",
                    },
                    exc_info=True,
                )
                raise ResourceNotFoundError("Agent", agent_name) from e

        return factory

    def _build_llm_provider(self, agent: Agent) -> ILLMProvider:
        """Build an LLM provider configured for a specific agent.

        Uses the agent's LLM configuration (model, temperature, max_tokens,
        system_prompt) to create a specialized provider instance.

        Args:
            agent: Agent domain object with LLM configuration

        Returns:
            ILLMProvider instance configured for the agent

        Raises:
            Exception: If provider creation fails
        """
        try:
            return self._factory.create_llm_provider(
                adapter_name=self._config.llm,
                model=agent.model,
                temperature=agent.temperature,
                max_tokens=agent.max_tokens,
                system_prompt=agent.system_prompt,
            )
        except Exception as e:
            logger.error(
                f"Failed to build LLM provider for agent '{agent.name}': {e}",
                extra={
                    "agent_id": agent.id,
                    "agent_name": agent.name,
                    "model": agent.model,
                    "error_id": "ERR_LLM_PROVIDER_CREATION_FAILED",
                },
                exc_info=True,
            )
            raise

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
        self._resolved["storage"] = self.resolve_storage()
        self._resolved["container"] = self.resolve_container()
        self._resolved["version_control"] = self.resolve_version_control()
        self._resolved["board"] = self.resolve_board()
        self._resolved["queue_service"] = self.resolve_queue_service()
        self._resolved["ci_pipeline"] = self.resolve_ci_pipeline()

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

        # 9. Systemic analysis service (depends on llm, used by repair_cycle)
        self._resolved["systemic_analysis_service"] = self.resolve_systemic_analysis_service()

        # 9b. Environment repair service (depends on llm, used by repair_cycle)
        self._resolved["environment_repair_service"] = self.resolve_environment_repair_service()

        # 10. Review and repair cycles depend on previously resolved adapters
        # (review_cycle depends on llm, repair_cycle depends on checkpoint_store, container, and systemic_analysis_service)
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
