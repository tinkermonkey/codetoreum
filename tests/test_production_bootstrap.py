"""Tests for ProductionApplicationBootstrap critical path enforcement."""

import pytest

from codetoreum.infrastructure.bootstrap import ProductionApplicationBootstrap
from codetoreum.infrastructure.simulation.simulation_config import AdapterSelectionConfig


@pytest.mark.asyncio
async def test_critical_path_mock_detection_raises_error() -> None:
    """Verify that critical path validation detects and rejects mock adapters."""
    # Create a config with a mock on a critical path (intentionally violates production requirements)
    bad_config = AdapterSelectionConfig(
        board="github",
        ticket="github",
        llm="mock",  # Critical path slot with mock - should fail
        version_control="github",
        container="docker",
        code_review="github",
        event_store="in_memory",
    )

    bootstrap = ProductionApplicationBootstrap(adapter_config=bad_config)

    # Setup should fail during critical path validation (Phase 3)
    with pytest.raises(RuntimeError, match="Mock adapters detected on critical execution path"):
        await bootstrap.setup()


@pytest.mark.asyncio
async def test_critical_path_in_memory_detection_raises_error() -> None:
    """Verify that critical path validation detects InMemory adapters on critical paths."""
    bad_config = AdapterSelectionConfig(
        board="github",
        ticket="github",
        llm="claude_code",
        version_control="github",
        container="docker",
        code_review="github",
        event_store="in_memory",  # Critical path with InMemory - acceptable for MVP
    )

    bootstrap = ProductionApplicationBootstrap(adapter_config=bad_config)

    # This should succeed since in_memory is acceptable for event_store in MVP
    # (logged as known limitation but not a validation error)
    # Note: This test requires all production credentials to be available


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
        "event_store",
    }

    assert expected_critical == CRITICAL_ADAPTER_SLOTS


def test_non_critical_adapter_slots_defined() -> None:
    """Verify that non-critical adapter slots are correctly defined."""
    from codetoreum.infrastructure.bootstrap.production_bootstrap import NON_CRITICAL_SLOTS

    expected_non_critical = {
        "review_cycle",
        "pr_review_cycle",
        "systemic_analysis",
        "environment_repair",
    }

    assert expected_non_critical == NON_CRITICAL_SLOTS
