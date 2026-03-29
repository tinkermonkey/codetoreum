"""
Tests for AdapterResolver - configuration-driven adapter instantiation with validation.

Tests cover:
- AdapterDependencies dataclass creation
- AdapterConfigurationError aggregation
- AdapterResolver credential validation
- Adapter resolution in dependency order
- SimulationEngine coupling for time-aware adapters
"""

import logging
import os
from unittest.mock import Mock, patch

import pytest

from codetoreum.infrastructure.adapters.factory import AdapterFactory, AdapterFactoryConfig
from codetoreum.infrastructure.adapters.registry_base import AdapterCredentialRequirement
from codetoreum.infrastructure.adapters.resolver import (
    AdapterConfigurationError,
    AdapterDependencies,
    AdapterResolver,
)
from codetoreum.infrastructure.simulation.simulation_config import (
    AdapterSelectionConfig,
    SimulationConfig,
)
from codetoreum.infrastructure.simulation.simulation_engine import SimulationEngine
from codetoreum.ports.output.active_workflow_run_registry import IActiveWorkflowRunRegistry
from codetoreum.ports.output.agent_repository import IAgentRepository
from codetoreum.ports.output.code_review_service import ICodeReviewService
from codetoreum.ports.output.container import IContainer
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
from codetoreum.ports.output.repository import IRepository
from codetoreum.ports.output.review_cycle_service import IReviewCycle
from codetoreum.ports.output.storage import IStorage
from codetoreum.ports.output.ticket_system import ITicketSystem
from codetoreum.ports.output.version_control_service import IVersionControlService
from codetoreum.ports.output.work_item_branch_tracker import IWorkItemBranchTracker
from codetoreum.ports.output.work_item_service import IWorkItemService
from codetoreum.ports.output.workflow_config_service import IWorkflowConfigService


class TestAdapterDependencies:
    """Tests for AdapterDependencies dataclass."""

    def test_create_dependencies(self):
        """Test creating AdapterDependencies with all required fields."""
        mock_event_bus = Mock()
        mock_event_emitter = Mock()
        mock_logger = logging.getLogger(__name__)
        mock_engine = Mock()
        mock_config = Mock(spec=SimulationConfig)

        deps = AdapterDependencies(
            event_bus=mock_event_bus,
            event_emitter=mock_event_emitter,
            logger=mock_logger,
            engine=mock_engine,
            config=mock_config,
        )

        assert deps.event_bus is mock_event_bus
        assert deps.event_emitter is mock_event_emitter
        assert deps.logger is mock_logger
        assert deps.engine is mock_engine
        assert deps.config is mock_config


class TestAdapterConfigurationError:
    """Tests for AdapterConfigurationError exception."""

    def test_empty_errors_list(self):
        """Test creating error with empty list."""
        error = AdapterConfigurationError([])
        assert "Adapter configuration errors:" in str(error)
        assert error.errors == []

    def test_single_error(self):
        """Test creating error with single error message."""
        error = AdapterConfigurationError(["missing env var GITHUB_TOKEN"])
        assert "missing env var GITHUB_TOKEN" in str(error)
        assert error.errors == ["missing env var GITHUB_TOKEN"]

    def test_multiple_errors_aggregated(self):
        """Test creating error with multiple aggregated error messages."""
        errors = [
            "board/github: missing env var GITHUB_TOKEN",
            "ticket/github: missing env var GITHUB_ORG",
            "llm/claude_code: missing env var CLAUDE_CODE_TOKEN",
        ]
        error = AdapterConfigurationError(errors)
        error_msg = str(error)

        for err in errors:
            assert err in error_msg

        assert error.errors == errors

    def test_error_message_format(self):
        """Test that error message is readable with bullet points."""
        errors = ["error 1", "error 2", "error 3"]
        error = AdapterConfigurationError(errors)
        error_msg = str(error)

        # Should contain bullet points for each error
        assert error_msg.count("- ") >= 3


class TestAdapterResolver:
    """Tests for AdapterResolver class."""

    @pytest.fixture
    def factory(self):
        """Create a test AdapterFactory."""
        return AdapterFactory(config=AdapterFactoryConfig())

    @pytest.fixture
    def dependencies(self):
        """Create mock AdapterDependencies."""
        config = SimulationConfig.create_fast_config("test")
        return AdapterDependencies(
            event_bus=Mock(),
            event_emitter=Mock(),
            logger=logging.getLogger(__name__),
            engine=Mock(),
            config=config,
        )

    @pytest.fixture
    def adapter_config(self):
        """Create default AdapterSelectionConfig with all simulation adapters."""
        return AdapterSelectionConfig()

    def test_resolver_initialization(self, factory, dependencies, adapter_config):
        """Test creating an AdapterResolver instance."""
        resolver = AdapterResolver(adapter_config, factory, dependencies)

        assert resolver._config is adapter_config
        assert resolver._factory is factory
        assert resolver._deps is dependencies
        assert resolver._resolved == {}

    def test_validate_credentials_all_defaults(self, factory, dependencies, adapter_config):
        """Test credential validation with all default simulation adapters."""
        resolver = AdapterResolver(adapter_config, factory, dependencies)
        # Should not raise - all defaults are simulation adapters with no credentials
        resolver.validate_credentials()

    def test_validate_credentials_missing_env_var(self, factory, dependencies):
        """Test credential validation fails when required env var is missing."""
        # Configure to use github ticket adapter which needs GITHUB_TOKEN
        config = AdapterSelectionConfig(ticket="github")
        resolver = AdapterResolver(config, factory, dependencies)

        # Temporarily ensure GITHUB_TOKEN is not set
        original_token = os.environ.get("GITHUB_TOKEN")
        try:
            if "GITHUB_TOKEN" in os.environ:
                del os.environ["GITHUB_TOKEN"]

            with pytest.raises(AdapterConfigurationError) as exc_info:
                resolver.validate_credentials()

            assert "GITHUB_TOKEN" in str(exc_info.value)
        finally:
            if original_token is not None:
                os.environ["GITHUB_TOKEN"] = original_token

    def test_validate_credentials_unknown_implementation(self, factory, dependencies):
        """Test credential validation fails for unknown implementation name."""
        config = AdapterSelectionConfig(ticket="nonexistent_impl")
        resolver = AdapterResolver(config, factory, dependencies)

        with pytest.raises(AdapterConfigurationError) as exc_info:
            resolver.validate_credentials()

        assert "unknown implementation" in str(exc_info.value).lower()
        assert "nonexistent_impl" in str(exc_info.value)

    def test_validate_credentials_aggregates_errors(self, factory, dependencies):
        """Test that all credential errors are aggregated into single exception."""
        config = AdapterSelectionConfig(
            ticket="nonexistent1",
            llm="nonexistent2",
        )
        resolver = AdapterResolver(config, factory, dependencies)

        with pytest.raises(AdapterConfigurationError) as exc_info:
            resolver.validate_credentials()

        error_msg = str(exc_info.value)
        # Should contain both errors
        assert "nonexistent1" in error_msg or "ticket" in error_msg
        assert "nonexistent2" in error_msg or "llm" in error_msg

    def test_resolve_event_store(self, factory, dependencies, adapter_config):
        """Test resolving event store adapter."""
        resolver = AdapterResolver(adapter_config, factory, dependencies)
        event_store = resolver.resolve_event_store()

        assert event_store is not None
        # Should be an adapter instance
        assert callable(getattr(event_store, "append", None))

    def test_resolve_config_store(self, factory, dependencies, adapter_config):
        """Test resolving config store adapter."""
        resolver = AdapterResolver(adapter_config, factory, dependencies)
        config_store = resolver.resolve_config_store()

        assert config_store is not None
        # Should be an adapter instance
        assert callable(getattr(config_store, "get_project_config", None))

    def test_resolve_metrics(self, factory, dependencies, adapter_config):
        """Test resolving metrics adapter."""
        resolver = AdapterResolver(adapter_config, factory, dependencies)
        metrics = resolver.resolve_metrics()

        assert metrics is not None
        # Should implement the IMetrics interface contract
        assert isinstance(metrics, IMetrics)

    def test_resolve_llm(self, factory, dependencies, adapter_config):
        """Test resolving LLM provider adapter."""
        resolver = AdapterResolver(adapter_config, factory, dependencies)
        llm = resolver.resolve_llm()

        assert llm is not None
        # Should be an adapter instance (may be wrapped by resilience decorator)

    def test_resolve_board(self, factory, dependencies, adapter_config):
        """Test resolving board service adapter."""
        resolver = AdapterResolver(adapter_config, factory, dependencies)
        # Resolve event_emitter first since board depends on it
        resolver._resolved["event_emitter"] = resolver.resolve_event_emitter()
        board = resolver.resolve_board()

        assert board is not None
        # Should be an adapter instance

    def test_resolve_all_basic(self, factory, dependencies, adapter_config):
        """Test resolving all adapters with default simulation config."""
        from codetoreum.infrastructure.simulation.bootstrap import SimulationAdapters

        resolver = AdapterResolver(adapter_config, factory, dependencies)
        result = resolver.resolve_all()

        # Should return a SimulationAdapters dataclass
        assert isinstance(result, SimulationAdapters)

        # All adapter fields should be non-None (except optional ones)
        import dataclasses

        # Optional fields are injected by bootstrap post-processing
        optional_fields = {"agent_executor", "audit_store", "tracer", "systemic_analysis_service"}
        for field in dataclasses.fields(result):
            adapter = getattr(result, field.name)
            if field.name not in optional_fields:
                assert adapter is not None, f"{field.name} adapter is None"

    def test_resolve_all_populates_resolved_dict(self, factory, dependencies, adapter_config):
        """Test that resolve_all populates the internal _resolved dict."""
        from codetoreum.infrastructure.simulation.bootstrap import SimulationAdapters

        resolver = AdapterResolver(adapter_config, factory, dependencies)
        result = resolver.resolve_all()

        # result is a SimulationAdapters dataclass, not a dict
        assert isinstance(result, SimulationAdapters)
        # The internal _resolved dict should have 30 entries (includes systemic_analysis_service)
        assert len(resolver._resolved) == 30

    def test_resolve_all_respects_dependency_order(self, factory, dependencies, adapter_config):
        """Test that adapters are resolved in dependency order."""
        resolver = AdapterResolver(adapter_config, factory, dependencies)

        # Mock resolve methods to track call order
        call_order = []

        original_resolve_event_store = resolver.resolve_event_store
        original_resolve_llm = resolver.resolve_llm
        original_resolve_review_cycle = resolver.resolve_review_cycle

        def track_event_store():
            call_order.append("event_store")
            return original_resolve_event_store()

        def track_llm():
            call_order.append("llm")
            return original_resolve_llm()

        def track_review_cycle():
            call_order.append("review_cycle")
            return original_resolve_review_cycle()

        resolver.resolve_event_store = track_event_store
        resolver.resolve_llm = track_llm
        resolver.resolve_review_cycle = track_review_cycle

        result = resolver.resolve_all()

        # event_store should be resolved before review_cycle
        event_store_idx = call_order.index("event_store")
        review_cycle_idx = call_order.index("review_cycle")
        assert event_store_idx < review_cycle_idx

        # llm should be resolved before review_cycle (since review_cycle depends on llm)
        llm_idx = call_order.index("llm")
        assert llm_idx < review_cycle_idx

    def test_review_cycle_mock_uses_engine(self, factory, dependencies, adapter_config):
        """Test that mock review_cycle uses SimulationEngine."""
        # Keep default mock review_cycle
        assert adapter_config.review_cycle == "mock"

        resolver = AdapterResolver(adapter_config, factory, dependencies)

        # Mock the engine's create_review_cycle_adapter method
        mock_review_cycle = Mock()
        resolver._deps.engine.create_review_cycle_adapter.return_value = mock_review_cycle

        # Resolve everything to populate _resolved with llm
        result = resolver.resolve_all()

        # Engine should have been called to create review cycle
        resolver._deps.engine.create_review_cycle_adapter.assert_called_once()

        # The returned review_cycle should be from the engine (access as attribute)
        assert result.review_cycle is mock_review_cycle

    def test_repair_cycle_mock_uses_engine(self, factory, dependencies, adapter_config):
        """Test that mock repair_cycle uses SimulationEngine."""
        # Keep default mock repair_cycle
        assert adapter_config.repair_cycle == "mock"

        resolver = AdapterResolver(adapter_config, factory, dependencies)

        # Mock the engine's create_repair_cycle_adapter method
        mock_repair_cycle = Mock()
        resolver._deps.engine.create_repair_cycle_adapter.return_value = mock_repair_cycle

        # Resolve everything to populate _resolved with container and checkpoint_store
        result = resolver.resolve_all()

        # Engine should have been called to create repair cycle
        resolver._deps.engine.create_repair_cycle_adapter.assert_called_once()

        # The returned repair_cycle should be from the engine (access as attribute)
        assert result.repair_cycle is mock_repair_cycle

    def test_resolve_review_cycle_passes_llm_to_engine(self, factory, dependencies, adapter_config):
        """Test that review_cycle resolver passes resolved LLM to engine."""
        resolver = AdapterResolver(adapter_config, factory, dependencies)

        # Mock the engine
        mock_review_cycle = Mock()
        resolver._deps.engine.create_review_cycle_adapter.return_value = mock_review_cycle

        # Populate _resolved with LLM first
        resolver._resolved["llm"] = resolver.resolve_llm()

        # Resolve review_cycle
        resolver.resolve_review_cycle()

        # Engine should have been called with the LLM adapter
        resolver._deps.engine.create_review_cycle_adapter.assert_called_once()
        call_kwargs = resolver._deps.engine.create_review_cycle_adapter.call_args[1]
        assert "llm_adapter" in call_kwargs
        assert call_kwargs["llm_adapter"] is resolver._resolved["llm"]

    def test_resolve_repair_cycle_passes_dependencies_to_engine(self, factory, dependencies, adapter_config):
        """Test that repair_cycle resolver passes resolved dependencies to engine."""
        resolver = AdapterResolver(adapter_config, factory, dependencies)

        # Mock the engine
        mock_repair_cycle = Mock()
        resolver._deps.engine.create_repair_cycle_adapter.return_value = mock_repair_cycle

        # Populate _resolved with required adapters
        # container depends on event_emitter, so resolve that first
        resolver._resolved["event_emitter"] = resolver.resolve_event_emitter()
        resolver._resolved["event_bus"] = resolver._deps.event_bus
        resolver._resolved["checkpoint_store"] = resolver.resolve_checkpoint_store()
        resolver._resolved["container"] = resolver.resolve_container()

        # Resolve repair_cycle
        resolver.resolve_repair_cycle()

        # Engine should have been called with the dependencies
        resolver._deps.engine.create_repair_cycle_adapter.assert_called_once()
        call_kwargs = resolver._deps.engine.create_repair_cycle_adapter.call_args[1]
        assert "checkpoint_store" in call_kwargs
        assert "container_adapter" in call_kwargs

    def test_all_29_adapter_slots_resolved(self, factory, dependencies, adapter_config):
        """Test that all 29 adapter slots are successfully resolved."""
        resolver = AdapterResolver(adapter_config, factory, dependencies)
        result = resolver.resolve_all()

        # Result is now a fully typed SimulationAdapters dataclass
        from codetoreum.infrastructure.simulation.bootstrap import SimulationAdapters

        assert isinstance(result, SimulationAdapters)

        # All expected adapters should be assigned (non-None)
        expected_fields = {
            "board",
            "ticket_system",
            "llm_provider",
            "version_control",
            "container",
            "event_store",
            "metrics",
            "storage",
            "config_store",
            "notifier",
            "encryption",
            "discussion_adapter",
            "review_cycle",
            "repair_cycle",
            "code_review",
            "project_manager",
            "lock_service",
            "workflow_config",
            "queue_service",
            "event_emitter",
            "message_broker",
            "identity_service",
            "checkpoint_store",
            "agent_repository",
            "run_registry",
            "branch_tracker",
            "work_item_service",
            "repository",
            "container_recovery",
        }

        assert len(expected_fields) == 29

        # Verify all expected fields are present and non-None (except agent_executor which is assigned in Phase 3)
        for field_name in expected_fields:
            assert hasattr(result, field_name), f"Missing field: {field_name}"
            value = getattr(result, field_name)
            assert value is not None, f"Field {field_name} is None"

    def test_get_registry_method_exists_on_factory(self, factory):
        """Test that AdapterFactory has get_registry method."""
        assert hasattr(factory, "get_registry")
        assert callable(factory.get_registry)

    def test_get_registry_returns_correct_registry(self, factory):
        """Test that get_registry returns correct registry for each slot."""
        # Test a few key registries
        board_registry = factory.get_registry("board")
        assert board_registry is factory.board_service_registry

        ticket_registry = factory.get_registry("ticket")
        assert ticket_registry is factory.ticket_system_registry

        llm_registry = factory.get_registry("llm")
        assert llm_registry is factory.llm_provider_registry

    def test_get_registry_raises_on_unknown_slot(self, factory):
        """Test that get_registry raises KeyError for unknown slot."""
        with pytest.raises(KeyError) as exc_info:
            factory.get_registry("nonexistent_slot")

        assert "nonexistent_slot" in str(exc_info.value)

    def test_validate_credentials_checks_all_slots(self, factory, dependencies):
        """Test that validate_credentials checks credentials for all 29 slots."""
        # Use all default simulation adapters (no credentials needed)
        config = AdapterSelectionConfig()
        resolver = AdapterResolver(config, factory, dependencies)

        # Should validate all 29 slots without error
        resolver.validate_credentials()

        # Verify by checking that validation looked at all slots
        # (we can't directly test this, but if any slot was missed,
        # later tests would fail)

    def test_validate_credentials_accepts_falsy_config_values(self, factory, dependencies):
        """Test that validate_credentials accepts falsy config values (0, '', False)."""
        from codetoreum.infrastructure.simulation.simulation_config import SimulationConfig

        # Create config with falsy values in metadata
        config = SimulationConfig.create_fast_config("test")
        config.metadata["falsy_zero"] = 0
        config.metadata["falsy_empty_string"] = ""
        config.metadata["falsy_false"] = False

        # Register a test adapter that requires these falsy config keys
        from codetoreum.adapters.testing.mock_llm_adapter import MockLLMAdapter

        registry = factory.get_registry("llm")
        registry._adapters["test_falsy"] = MockLLMAdapter
        registry._metadata["test_falsy"] = Mock(
            config_schema=AdapterCredentialRequirement(config_keys=("falsy_zero", "falsy_empty_string", "falsy_false"))
        )

        # Configure to use the test adapter with falsy config values
        adapter_config = AdapterSelectionConfig(llm="test_falsy")
        deps = AdapterDependencies(
            event_bus=Mock(),
            event_emitter=Mock(),
            logger=logging.getLogger(__name__),
            engine=Mock(),
            config=config,
        )
        resolver = AdapterResolver(adapter_config, factory, deps)

        # Should validate successfully without rejecting falsy values
        resolver.validate_credentials()

    def test_validate_credentials_rejects_missing_config_keys(self, factory, dependencies):
        """Test that validate_credentials still rejects missing config keys."""
        from codetoreum.adapters.testing.mock_llm_adapter import MockLLMAdapter

        # Create config without the required key
        config = SimulationConfig.create_fast_config("test")

        registry = factory.get_registry("llm")
        registry._adapters["test_missing"] = MockLLMAdapter
        registry._metadata["test_missing"] = Mock(
            config_schema=AdapterCredentialRequirement(config_keys=("required_key",))
        )

        adapter_config = AdapterSelectionConfig(llm="test_missing")
        deps = AdapterDependencies(
            event_bus=Mock(),
            event_emitter=Mock(),
            logger=logging.getLogger(__name__),
            engine=Mock(),
            config=config,
        )
        resolver = AdapterResolver(adapter_config, factory, deps)

        # Should raise error for missing config key
        with pytest.raises(AdapterConfigurationError) as exc_info:
            resolver.validate_credentials()

        assert "required_key" in str(exc_info.value)

    def test_validate_credentials_accepts_falsy_env_vars(self, factory, dependencies):
        """Test that validate_credentials accepts falsy environment variable values."""
        from codetoreum.adapters.testing.mock_llm_adapter import MockLLMAdapter

        # Register an adapter that requires an env var
        registry = factory.get_registry("llm")
        registry._adapters["test_env_var"] = MockLLMAdapter
        registry._metadata["test_env_var"] = Mock(config_schema=AdapterCredentialRequirement(env_vars=("FALSY_VAR",)))

        adapter_config = AdapterSelectionConfig(llm="test_env_var")
        resolver = AdapterResolver(adapter_config, factory, dependencies)

        # Set env var to empty string (falsy but valid)
        original_value = os.environ.get("FALSY_VAR")
        try:
            os.environ["FALSY_VAR"] = ""
            # Should validate successfully - env var exists even though it's empty
            resolver.validate_credentials()
        finally:
            if original_value is None:
                if "FALSY_VAR" in os.environ:
                    del os.environ["FALSY_VAR"]
            else:
                os.environ["FALSY_VAR"] = original_value

    def test_validate_credentials_rejects_missing_env_vars(self, factory, dependencies):
        """Test that validate_credentials rejects missing environment variables."""
        from codetoreum.adapters.testing.mock_llm_adapter import MockLLMAdapter

        # Register an adapter that requires an env var
        registry = factory.get_registry("llm")
        registry._adapters["test_env_var"] = MockLLMAdapter
        registry._metadata["test_env_var"] = Mock(
            config_schema=AdapterCredentialRequirement(env_vars=("MISSING_VAR_12345",))
        )

        adapter_config = AdapterSelectionConfig(llm="test_env_var")
        resolver = AdapterResolver(adapter_config, factory, dependencies)

        # Ensure the var is truly missing
        if "MISSING_VAR_12345" in os.environ:
            del os.environ["MISSING_VAR_12345"]

        # Should raise error for missing env var
        with pytest.raises(AdapterConfigurationError) as exc_info:
            resolver.validate_credentials()

        assert "MISSING_VAR_12345" in str(exc_info.value)

    def test_validate_credentials_skips_simulation_only_adapters(self, factory, dependencies):
        """Test that simulation-only adapters skip credential validation.

        Verifies that adapters marked with simulation_only=True are not validated
        for credentials, even if they have env_vars or config_keys specified.
        This ensures simulation adapters can optionally define credentials without
        causing production validation failures.
        """
        from codetoreum.adapters.testing.mock_llm_adapter import MockLLMAdapter

        # Register a simulation-only adapter with required env var and config key
        registry = factory.get_registry("llm")
        registry._adapters["test_sim_only"] = MockLLMAdapter
        registry._metadata["test_sim_only"] = Mock(
            config_schema=AdapterCredentialRequirement(
                env_vars=("MISSING_VAR_FOR_SIM_ONLY",),
                config_keys=("missing_config_key",),
                simulation_only=True,  # Mark as simulation-only
            )
        )

        adapter_config = AdapterSelectionConfig(llm="test_sim_only")
        resolver = AdapterResolver(adapter_config, factory, dependencies)

        # Ensure the env var and config key are missing
        if "MISSING_VAR_FOR_SIM_ONLY" in os.environ:
            del os.environ["MISSING_VAR_FOR_SIM_ONLY"]

        # Should NOT raise error even though credentials are missing
        # because this is a simulation-only adapter
        resolver.validate_credentials()

    def test_resolve_storage(self, factory, dependencies, adapter_config):
        """Test resolving storage adapter with event dependencies."""
        resolver = AdapterResolver(adapter_config, factory, dependencies)
        # Resolve event_emitter first since storage depends on it
        resolver._resolved["event_emitter"] = resolver.resolve_event_emitter()
        storage = resolver.resolve_storage()

        assert storage is not None
        # Should implement IStorage interface
        assert isinstance(storage, IStorage)

    def test_resolve_encryption(self, factory, dependencies, adapter_config):
        """Test resolving encryption service adapter."""
        resolver = AdapterResolver(adapter_config, factory, dependencies)
        encryption = resolver.resolve_encryption()

        assert encryption is not None
        # Should implement IEncryptionService interface
        assert isinstance(encryption, IEncryptionService)

    def test_resolve_identity_service(self, factory, dependencies, adapter_config):
        """Test resolving identity service adapter."""
        resolver = AdapterResolver(adapter_config, factory, dependencies)
        identity = resolver.resolve_identity_service()

        assert identity is not None
        # Should implement IIdentityService interface
        assert isinstance(identity, IIdentityService)

    def test_resolve_event_emitter(self, factory, dependencies, adapter_config):
        """Test resolving event emitter adapter."""
        resolver = AdapterResolver(adapter_config, factory, dependencies)
        event_emitter = resolver.resolve_event_emitter()

        assert event_emitter is not None
        # Should implement IEventEmitter interface
        assert isinstance(event_emitter, IEventEmitter)

    def test_resolve_message_broker(self, factory, dependencies, adapter_config):
        """Test resolving message broker adapter."""
        resolver = AdapterResolver(adapter_config, factory, dependencies)
        message_broker = resolver.resolve_message_broker()

        assert message_broker is not None
        # Should implement IMessageBroker interface
        assert isinstance(message_broker, IMessageBroker)

    def test_resolve_ticket(self, factory, dependencies, adapter_config):
        """Test resolving ticket system adapter."""
        resolver = AdapterResolver(adapter_config, factory, dependencies)
        ticket = resolver.resolve_ticket()

        assert ticket is not None
        # Should implement ITicketSystem interface (may be wrapped by decorator)
        assert isinstance(ticket, ITicketSystem)

    def test_resolve_container(self, factory, dependencies, adapter_config):
        """Test resolving container adapter with event dependencies."""
        resolver = AdapterResolver(adapter_config, factory, dependencies)
        # Resolve event_emitter first since container depends on it
        resolver._resolved["event_emitter"] = resolver.resolve_event_emitter()
        container = resolver.resolve_container()

        assert container is not None
        # Should implement IContainer interface
        assert isinstance(container, IContainer)

    def test_resolve_discussion_adapter(self, factory, dependencies, adapter_config):
        """Test resolving discussion adapter with identity service dependency."""
        resolver = AdapterResolver(adapter_config, factory, dependencies)
        # Resolve identity_service first
        resolver._resolved["identity_service"] = resolver.resolve_identity_service()
        discussion = resolver.resolve_discussion_adapter()

        assert discussion is not None
        # Should implement IDiscussionAdapter interface
        assert isinstance(discussion, IDiscussionAdapter)

    def test_resolve_lock_service(self, factory, dependencies, adapter_config):
        """Test resolving pipeline lock service adapter."""
        resolver = AdapterResolver(adapter_config, factory, dependencies)
        lock_service = resolver.resolve_lock_service()

        assert lock_service is not None
        assert isinstance(lock_service, IPipelineLockService)

    def test_resolve_queue_service(self, factory, dependencies, adapter_config):
        """Test resolving pipeline queue service adapter with event dependencies."""
        resolver = AdapterResolver(adapter_config, factory, dependencies)
        # Resolve event_emitter first since queue_service depends on it
        resolver._resolved["event_emitter"] = resolver.resolve_event_emitter()
        queue_service = resolver.resolve_queue_service()

        assert queue_service is not None
        # Should implement IPipelineQueueService interface
        assert isinstance(queue_service, IPipelineQueueService)

    def test_resolve_checkpoint_store(self, factory, dependencies, adapter_config):
        """Test resolving repair cycle checkpoint store adapter."""
        resolver = AdapterResolver(adapter_config, factory, dependencies)
        checkpoint_store = resolver.resolve_checkpoint_store()

        assert checkpoint_store is not None
        # Should implement IRepairCycleCheckpointStore interface
        assert isinstance(checkpoint_store, IRepairCycleCheckpointStore)

    def test_resolve_agent_repository(self, factory, dependencies, adapter_config):
        """Test resolving agent repository adapter."""
        resolver = AdapterResolver(adapter_config, factory, dependencies)
        agent_repo = resolver.resolve_agent_repository()

        assert agent_repo is not None
        # Should implement IAgentRepository interface
        assert isinstance(agent_repo, IAgentRepository)

    def test_resolve_run_registry(self, factory, dependencies, adapter_config):
        """Test resolving active workflow run registry adapter."""
        resolver = AdapterResolver(adapter_config, factory, dependencies)
        run_registry = resolver.resolve_run_registry()

        assert run_registry is not None
        # Should implement IActiveWorkflowRunRegistry interface
        assert isinstance(run_registry, IActiveWorkflowRunRegistry)

    def test_resolve_branch_tracker(self, factory, dependencies, adapter_config):
        """Test resolving work item branch tracker adapter."""
        resolver = AdapterResolver(adapter_config, factory, dependencies)
        branch_tracker = resolver.resolve_branch_tracker()

        assert branch_tracker is not None
        # Should implement IWorkItemBranchTracker interface
        assert isinstance(branch_tracker, IWorkItemBranchTracker)

    def test_resolve_work_item_service(self, factory, dependencies, adapter_config):
        """Test resolving work item service adapter."""
        resolver = AdapterResolver(adapter_config, factory, dependencies)
        work_item_service = resolver.resolve_work_item_service()

        assert work_item_service is not None
        # Should implement IWorkItemService interface
        assert isinstance(work_item_service, IWorkItemService)

    def test_resolve_workflow_config(self, factory, dependencies, adapter_config):
        """Test resolving workflow config service adapter."""
        resolver = AdapterResolver(adapter_config, factory, dependencies)
        workflow_config = resolver.resolve_workflow_config()

        assert workflow_config is not None
        # Should implement IWorkflowConfigService interface
        assert isinstance(workflow_config, IWorkflowConfigService)

    def test_resolve_notifier(self, factory, dependencies, adapter_config):
        """Test resolving notifier adapter."""
        resolver = AdapterResolver(adapter_config, factory, dependencies)
        notifier = resolver.resolve_notifier()

        assert notifier is not None
        # Should implement INotifier interface
        assert isinstance(notifier, INotifier)

    def test_resolve_version_control(self, factory, dependencies, adapter_config):
        """Test resolving version control service adapter with event dependencies."""
        resolver = AdapterResolver(adapter_config, factory, dependencies)
        # Resolve event_emitter first since version_control depends on it
        resolver._resolved["event_emitter"] = resolver.resolve_event_emitter()
        version_control = resolver.resolve_version_control()

        assert version_control is not None
        # Should implement IVersionControlService interface
        assert isinstance(version_control, IVersionControlService)

    def test_resolve_project_manager(self, factory, dependencies, adapter_config):
        """Test resolving project manager service adapter."""
        resolver = AdapterResolver(adapter_config, factory, dependencies)
        project_manager = resolver.resolve_project_manager()

        assert project_manager is not None
        # Should implement IProjectManagerService interface
        assert isinstance(project_manager, IProjectManagerService)

    def test_resolve_code_review(self, factory, dependencies, adapter_config):
        """Test resolving code review service adapter."""
        resolver = AdapterResolver(adapter_config, factory, dependencies)
        code_review = resolver.resolve_code_review()

        assert code_review is not None
        # Should implement ICodeReviewService interface
        assert isinstance(code_review, ICodeReviewService)

    def test_resolve_container_recovery(self, factory, dependencies, adapter_config):
        """Test resolving container recovery adapter."""
        resolver = AdapterResolver(adapter_config, factory, dependencies)
        container_recovery = resolver.resolve_container_recovery()

        assert container_recovery is not None
        # Should implement IAgentContainerRecoveryService interface
        assert isinstance(container_recovery, IAgentContainerRecoveryService)

    def test_resolve_repository(self, factory, dependencies, adapter_config):
        """Test resolving repository adapter with event dependencies."""
        resolver = AdapterResolver(adapter_config, factory, dependencies)
        # Resolve event_emitter first since repository depends on it
        resolver._resolved["event_emitter"] = resolver.resolve_event_emitter()
        repository = resolver.resolve_repository()

        assert repository is not None
        # Should be an adapter instance implementing IRepository
        assert isinstance(repository, IRepository)

    def test_resolve_review_cycle(self, factory, dependencies, adapter_config):
        """Test resolving review cycle service adapter."""
        resolver = AdapterResolver(adapter_config, factory, dependencies)
        # Mock the engine to return a proper IReviewCycle adapter
        mock_review_cycle = Mock(spec=IReviewCycle)
        resolver._deps.engine.create_review_cycle_adapter.return_value = mock_review_cycle

        review_cycle = resolver.resolve_review_cycle()

        assert review_cycle is not None
        # Should implement IReviewCycle interface (ABC - can use isinstance)
        assert isinstance(review_cycle, IReviewCycle)

    def test_resolve_repair_cycle(self, factory, dependencies, adapter_config):
        """Test resolving repair cycle service adapter."""
        resolver = AdapterResolver(adapter_config, factory, dependencies)
        # Mock the engine to return a proper IRepairCycle adapter (Protocol without @runtime_checkable)
        mock_repair_cycle = Mock(spec=IRepairCycle)
        resolver._deps.engine.create_repair_cycle_adapter.return_value = mock_repair_cycle

        repair_cycle = resolver.resolve_repair_cycle()

        assert repair_cycle is not None
        # Verify the engine was called to create the adapter
        assert resolver._deps.engine.create_repair_cycle_adapter.called


class TestAdapterResolverIntegration:
    """Integration tests for AdapterResolver with real factory."""

    def test_resolve_all_with_real_factory(self):
        """Test resolving all adapters with real AdapterFactory instance."""
        from codetoreum.infrastructure.simulation.bootstrap import SimulationAdapters

        factory = AdapterFactory(config=AdapterFactoryConfig())
        config = SimulationConfig.create_fast_config("test_integration")
        dependencies = AdapterDependencies(
            event_bus=Mock(),
            event_emitter=Mock(),
            logger=logging.getLogger(__name__),
            engine=Mock(spec=SimulationEngine),
            config=config,
        )

        # Mock engine's adapter creation methods
        dependencies.engine.create_review_cycle_adapter.return_value = Mock()
        dependencies.engine.create_repair_cycle_adapter.return_value = Mock()

        resolver = AdapterResolver(AdapterSelectionConfig(), factory, dependencies)
        result = resolver.resolve_all()

        # Result should be SimulationAdapters dataclass with all non-optional fields set
        assert isinstance(result, SimulationAdapters)
        import dataclasses

        # Optional fields are injected by bootstrap post-processing
        optional_fields = {"agent_executor", "audit_store", "tracer", "systemic_analysis_service"}
        for field in dataclasses.fields(result):
            adapter = getattr(result, field.name)
            if field.name not in optional_fields:
                assert adapter is not None, f"{field.name} is None"
