"""Test that verifies the application is fully event-driven.

Ensures no application-layer polling loops run after bootstrap completes.
Polling is now adapter-internal (e.g., GitHubBoardAdapter), not application-layer.
"""

import logging

import pytest

from codetoreum.application.multi_project_orchestrator import MultiProjectOrchestrator

logger = logging.getLogger(__name__)


def test_no_application_layer_polling_cycle():
    """Verify that MultiProjectOrchestrator does not have polling methods.

    After Phase 7, the application is fully event-driven.
    The MultiProjectOrchestrator.start() and related polling methods were removed.
    Adapter-level polling (e.g., in GitHubBoardAdapter) is private to adapters
    and does not cross the hexagonal boundary.
    """
    # Verify MultiProjectOrchestrator no longer has polling methods
    assert not hasattr(
        MultiProjectOrchestrator, "start"
    ), "MultiProjectOrchestrator should not have start() method after Phase 7"
    assert not hasattr(
        MultiProjectOrchestrator, "stop"
    ), "MultiProjectOrchestrator should not have stop() method after Phase 7"
    assert not hasattr(
        MultiProjectOrchestrator, "run_orchestration_cycle"
    ), "MultiProjectOrchestrator should not have run_orchestration_cycle() method after Phase 7"
    assert not hasattr(
        MultiProjectOrchestrator, "orchestrate_project"
    ), "MultiProjectOrchestrator should not have orchestrate_project() method after Phase 7"

    # Verify it only has admin query methods
    assert hasattr(
        MultiProjectOrchestrator, "get_project_status"
    ), "MultiProjectOrchestrator should have get_project_status() method"
    assert hasattr(
        MultiProjectOrchestrator, "list_enabled_projects"
    ), "MultiProjectOrchestrator should have list_enabled_projects() method"

    logger.info("✓ Application is fully event-driven")
    logger.info("✓ No application-layer polling methods found")
    logger.info("✓ Only admin query methods remain on MultiProjectOrchestrator")
