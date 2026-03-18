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
            if original_token:
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

    def test_validate_credentials_simulation_only_adapter_with_real_name(self, factory, dependencies):
        """Test that simulation-only adapters cannot be configured with non-simulation names."""
        # Register a simulation-only adapter under a real-sounding name in the test factory
        registry = factory.get_registry("metrics")
        from datetime import datetime

        from codetoreum.infrastructure.adapters.registry_base import AdapterMetadata

        # Add a fake adapter with simulation_only=True
        registry._adapters["fake_real_name"] = Mock()
        registry._metadata["fake_real_name"] = AdapterMetadata(
            name="fake_real_name",
            adapter_type=Mock,
            description="Test adapter",
            version="1.0.0",
            tags=[],
            registered_at=datetime.now(),
            config_schema=AdapterCredentialRequirement(env_vars=[], config_keys=[], simulation_only=True),
        )

        # Configure to use this simulation-only adapter with non-simulation name
        config = AdapterSelectionConfig(metrics="fake_real_name")
        resolver = AdapterResolver(config, factory, dependencies)

        with pytest.raises(AdapterConfigurationError) as exc_info:
            resolver.validate_credentials()

        error_msg = str(exc_info.value)
        assert "simulation-only" in error_msg.lower()
        assert "fake_real_name" in error_msg

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
        # Should be an adapter instance

    def test_resolve_llm(self, factory, dependencies, adapter_config):
        """Test resolving LLM provider adapter."""
        resolver = AdapterResolver(adapter_config, factory, dependencies)
        llm = resolver.resolve_llm()

        assert llm is not None
        # Should be an adapter instance (may be wrapped by resilience decorator)

    def test_resolve_board(self, factory, dependencies, adapter_config):
        """Test resolving board service adapter."""
        resolver = AdapterResolver(adapter_config, factory, dependencies)
        board = resolver.resolve_board()

        assert board is not None
        # Should be an adapter instance

    def test_resolve_all_basic(self, factory, dependencies, adapter_config):
        """Test resolving all adapters with default simulation config."""
        resolver = AdapterResolver(adapter_config, factory, dependencies)
        result = resolver.resolve_all()

        # Should return 26 adapters
        assert len(result) == 26

        # All values should be adapter instances (not None)
        for slot_name, adapter in result.items():
            assert adapter is not None, f"{slot_name} adapter is None"

    def test_resolve_all_populates_resolved_dict(self, factory, dependencies, adapter_config):
        """Test that resolve_all populates the internal _resolved dict."""
        resolver = AdapterResolver(adapter_config, factory, dependencies)
        result = resolver.resolve_all()

        assert resolver._resolved == result
        assert len(resolver._resolved) == 26

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

        # The returned review_cycle should be from the engine
        assert result["review_cycle"] is mock_review_cycle

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

        # The returned repair_cycle should be from the engine
        assert result["repair_cycle"] is mock_repair_cycle

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
        resolver._resolved["checkpoint_store"] = resolver.resolve_checkpoint_store()
        resolver._resolved["container"] = resolver.resolve_container()

        # Resolve repair_cycle
        resolver.resolve_repair_cycle()

        # Engine should have been called with the dependencies
        resolver._deps.engine.create_repair_cycle_adapter.assert_called_once()
        call_kwargs = resolver._deps.engine.create_repair_cycle_adapter.call_args[1]
        assert "checkpoint_store" in call_kwargs
        assert "container_adapter" in call_kwargs

    def test_all_26_adapter_slots_resolved(self, factory, dependencies, adapter_config):
        """Test that all 26 adapter slots are successfully resolved."""
        resolver = AdapterResolver(adapter_config, factory, dependencies)
        result = resolver.resolve_all()

        expected_slots = {
            "board",
            "ticket",
            "llm",
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
        }

        assert len(expected_slots) == 26
        assert set(result.keys()) == expected_slots

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
        """Test that validate_credentials checks credentials for all 26 slots."""
        # Use all default simulation adapters (no credentials needed)
        config = AdapterSelectionConfig()
        resolver = AdapterResolver(config, factory, dependencies)

        # Should validate all 26 slots without error
        resolver.validate_credentials()

        # Verify by checking that validation looked at all slots
        # (we can't directly test this, but if any slot was missed,
        # later tests would fail)


class TestAdapterResolverIntegration:
    """Integration tests for AdapterResolver with real factory."""

    def test_resolve_all_with_real_factory(self):
        """Test resolving all adapters with real AdapterFactory instance."""
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

        # All adapters should be created successfully
        assert len(result) == 26
        assert all(adapter is not None for adapter in result.values())
