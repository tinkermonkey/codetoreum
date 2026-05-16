"""Tests for ProductionApplicationBootstrap critical path enforcement."""

import pytest

from codetoreum.infrastructure.bootstrap import ProductionApplicationBootstrap
from codetoreum.infrastructure.simulation.simulation_config import AdapterSelectionConfig


@pytest.mark.asyncio
async def test_critical_path_mock_detection_raises_error() -> None:
    """Verify that critical path validation detects and rejects mock adapters."""
    # Create a config with a mock on a critical path (intentionally violates production requirements)
    bad_config = AdapterSelectionConfig(
        board="mock",  # Use available adapter
        ticket="in_memory",  # Use available adapter
        llm="mock",  # Critical path slot with mock - should fail validation
        version_control="in_memory",  # Use available adapter
        container="fake",  # Use available adapter
        code_review="mock",  # Use available adapter
        event_store="in_memory",
    )

    bootstrap = ProductionApplicationBootstrap(adapter_config=bad_config)

    # Setup should fail during critical path validation (Phase 3)
    with pytest.raises(RuntimeError, match="Mock adapters detected on critical execution path"):
        await bootstrap.setup()


def test_in_memory_event_store_not_on_critical_path() -> None:
    """Verify that in-memory event store is in NON_CRITICAL_SLOTS, not CRITICAL_ADAPTER_SLOTS."""
    from codetoreum.infrastructure.bootstrap.production_bootstrap import (
        CRITICAL_ADAPTER_SLOTS,
        NON_CRITICAL_SLOTS,
    )

    # Verify event_store is not in critical slots
    assert "event_store" not in CRITICAL_ADAPTER_SLOTS, "event_store should not be on critical path for MVP"
    # Verify event_store is in non-critical slots
    assert "event_store" in NON_CRITICAL_SLOTS, "event_store should be in non-critical slots for MVP"


def test_get_adapter_slot_info_before_setup_raises() -> None:
    """Verify that get_adapter_slot_info raises if called before setup."""
    bootstrap = ProductionApplicationBootstrap()

    with pytest.raises(RuntimeError, match="get_adapter_slot_info.*before setup"):
        bootstrap.get_adapter_slot_info()


@pytest.mark.asyncio
async def test_adapter_selection_config_has_33_slots() -> None:
    """Verify that AdapterSelectionConfig has exactly 33 slots."""
    config = AdapterSelectionConfig()
    slots = list(AdapterSelectionConfig.__dataclass_fields__.keys())

    assert len(slots) == 33, f"Expected 33 slots, got {len(slots)}: {slots}"


def test_critical_adapter_slots_defined() -> None:
    """Verify that critical adapter slots are correctly defined."""
    from codetoreum.infrastructure.bootstrap.production_bootstrap import CRITICAL_ADAPTER_SLOTS

    expected_critical = {
        "board",
        "ticket",
        "llm",
        "version_control",
        "container",
        "code_review",
    }

    assert expected_critical == CRITICAL_ADAPTER_SLOTS


def test_non_critical_adapter_slots_defined() -> None:
    """Verify that non-critical adapter slots are correctly defined."""
    from codetoreum.infrastructure.bootstrap.production_bootstrap import NON_CRITICAL_SLOTS

    expected_non_critical = {
        "event_store",  # InMemoryEventStore acceptable for MVP
        "review_cycle",
        "pr_review_cycle",
        "systemic_analysis",
        "environment_repair",
    }

    assert expected_non_critical == NON_CRITICAL_SLOTS


@pytest.mark.asyncio
async def test_validate_event_emitter_raises_when_capturing_mock_detected() -> None:
    """Verify that _validate_event_emitter_is_production raises RuntimeError when CapturingMockEventEmitter is detected."""
    from codetoreum.adapters.testing import CapturingMockEventEmitter

    bootstrap = ProductionApplicationBootstrap()
    # Manually set adapters with CapturingMockEventEmitter to simulate the misconfiguration
    bootstrap.adapters = type("Adapters", (), {"event_emitter": CapturingMockEventEmitter()})()

    with pytest.raises(RuntimeError, match="CapturingMockEventEmitter"):
        bootstrap._validate_event_emitter_is_production()


@pytest.mark.asyncio
async def test_validate_event_emitter_raises_when_none() -> None:
    """Verify that _validate_event_emitter_is_production raises RuntimeError when event_emitter is None."""
    bootstrap = ProductionApplicationBootstrap()
    # Manually set adapters with None event_emitter
    bootstrap.adapters = type("Adapters", (), {"event_emitter": None})()

    with pytest.raises(RuntimeError, match="event_emitter not resolved"):
        bootstrap._validate_event_emitter_is_production()


@pytest.mark.asyncio
async def test_validate_event_emitter_raises_when_adapters_none() -> None:
    """Verify that _validate_event_emitter_is_production raises RuntimeError when adapters is None."""
    bootstrap = ProductionApplicationBootstrap()
    bootstrap.adapters = None

    with pytest.raises(RuntimeError, match="event_emitter not resolved"):
        bootstrap._validate_event_emitter_is_production()


@pytest.mark.asyncio
async def test_validate_event_emitter_passes_with_non_capturing_adapter() -> None:
    """Verify that _validate_event_emitter_is_production passes validation with non-capturing emitter."""

    # Create a simple non-capturing mock object (not CapturingMockEventEmitter)
    class MockEventEmitter:
        pass

    bootstrap = ProductionApplicationBootstrap()
    # Manually set adapters with a non-capturing adapter
    bootstrap.adapters = type("Adapters", (), {"event_emitter": MockEventEmitter()})()

    # Should not raise any exception
    bootstrap._validate_event_emitter_is_production()
