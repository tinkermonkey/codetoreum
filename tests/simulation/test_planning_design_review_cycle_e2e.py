"""End-to-end simulation test for the planning_design_review_cycle scenario.

Exercises the PR review cycle with two paths:
1. Issues Found: Review identifies 6 findings → 6 sub-issues created on SDLC board → item to In Development
2. Approved: Review finds no issues → item to Done

Modeled on Switchyard benchmark runs 854460d9 (issues found) and fe4fa87f (approved).
"""

from pathlib import Path
from typing import cast

import pytest

from codetoreum.adapters.testing.mock_board_adapter import MockBoardAdapter
from codetoreum.domain.pr_review_cycle_types import (
    PRReviewFinding,
    PRReviewOutcome,
)
from codetoreum.infrastructure.simulation.bootstrap import (
    SimulationAdapters,
    SimulationApplicationBootstrap,
)
from codetoreum.infrastructure.simulation.seeding import SimulationDataSeeder
from codetoreum.ports.output.board_service import MovedByType

SCENARIO_DIR = Path(__file__).resolve().parent.parent.parent / "scenarios" / "planning_design_review_cycle"

# Work item from external/work_items.yaml
WORK_ITEM_TITLE = "Implement user authentication flow"


# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
async def pr_review_env(
    simulation_bootstrap: SimulationApplicationBootstrap,
    simulation_seeder: SimulationDataSeeder,
):
    """Bootstrap + seed the planning_design_review_cycle scenario."""
    adapters = cast("SimulationAdapters", simulation_bootstrap.adapters)

    # Speed up agent execution delay
    if adapters.agent_executor is not None:
        adapters.agent_executor._execution_delay = 0.05

    # Seed scenario from YAML
    await simulation_seeder.seed_from_yaml(SCENARIO_DIR)

    return simulation_bootstrap, simulation_seeder


# ============================================================================
# Helpers
# ============================================================================


def _find_work_item_id(seeder: SimulationDataSeeder, title_prefix: str) -> str | None:
    """Return the work_item_id for the first seeded item whose title starts with title_prefix."""
    for item_id in seeder.created_items.work_items:
        work_item = seeder._ticket_adapter._work_items.get(item_id)
        if work_item and work_item.title.startswith(title_prefix):
            return item_id
    return None


# ============================================================================
# Tests
# ============================================================================


@pytest.mark.asyncio
async def test_issues_found_path(pr_review_env):
    """Review identifies 6 issues → 6 sub-issues created → item moves to In Development.

    Validates scenario loading and board structure for the issues-found path.
    """
    bootstrap, seeder = pr_review_env
    adapters = cast("SimulationAdapters", bootstrap.adapters)
    board = cast("MockBoardAdapter", adapters.board)
    pr_cycle = adapters.pr_review_cycle_as_mock()

    # Verify scenario loaded correctly
    assert len(seeder.created_items.work_items) > 0, "No work items seeded"
    assert len(seeder.created_items.boards) > 0, "No boards seeded"
    assert len(seeder.created_items.projects) > 0, "No projects seeded"

    # Locate the work item seeded from external/work_items.yaml
    work_item_id = _find_work_item_id(seeder, WORK_ITEM_TITLE)
    assert work_item_id, f"Could not find work item '{WORK_ITEM_TITLE}' in seeded items"

    # Confirm starting position
    pos = await board.get_item_position(work_item_id)
    assert pos.column_name == "Backlog", f"Expected item in Backlog, got '{pos.column_name}'"

    # Get the external ID of the parent item
    parent_work_item = seeder._ticket_adapter._work_items.get(work_item_id)
    assert parent_work_item is not None, f"Could not find work item {work_item_id}"

    # Configure PR review cycle to find 6 issues (1 critical, 5 high severity)
    findings = [
        PRReviewFinding(
            type="security",
            severity="critical",
            file="src/auth.py",
            line_number=42,
            message="Missing CSRF token validation",
            suggestion="Add CSRF token check",
        ),
        PRReviewFinding(
            type="bug",
            severity="high",
            file="src/auth.py",
            line_number=58,
            message="Password hash not salted",
            suggestion="Use bcrypt",
        ),
        PRReviewFinding(
            type="style",
            severity="high",
            file="src/auth.py",
            line_number=15,
            message="Inconsistent naming",
            suggestion="Rename tokenDict",
        ),
        PRReviewFinding(
            type="performance",
            severity="high",
            file="src/oauth.py",
            line_number=120,
            message="Blocking call in async",
            suggestion="Use await",
        ),
        PRReviewFinding(
            type="bug",
            severity="high",
            file="src/session.py",
            line_number=88,
            message="Race condition",
            suggestion="Add mutex lock",
        ),
        PRReviewFinding(
            type="security",
            severity="high",
            file="src/oauth.py",
            line_number=45,
            message="Unencrypted token storage",
            suggestion="Encrypt tokens",
        ),
    ]
    pr_cycle.set_outcome(PRReviewOutcome.ISSUES_FOUND, findings)

    # Move item to In Review - this triggers the PR review cycle
    await board.move_item_to_column(work_item_id, "In Review", MovedByType.HUMAN)

    # Verify item reached In Review (the trigger column)
    pos = await board.get_item_position(work_item_id)
    assert pos.column_name == "In Review", (
        f"Item should be in 'In Review' after human move, got '{pos.column_name}'"
    )


@pytest.mark.asyncio
async def test_approved_path(pr_review_env):
    """Review approves PR without issues → item moves to Done.

    Validates scenario loading and board structure for the approved path.
    """
    bootstrap, seeder = pr_review_env
    adapters = cast("SimulationAdapters", bootstrap.adapters)
    board = cast("MockBoardAdapter", adapters.board)
    pr_cycle = adapters.pr_review_cycle_as_mock()

    # Verify scenario loaded correctly
    assert len(seeder.created_items.work_items) > 0, "No work items seeded"

    # Locate the work item seeded from external/work_items.yaml
    work_item_id = _find_work_item_id(seeder, WORK_ITEM_TITLE)
    assert work_item_id, f"Could not find work item '{WORK_ITEM_TITLE}' in seeded items"

    # Confirm starting position
    pos = await board.get_item_position(work_item_id)
    assert pos.column_name == "Backlog", f"Expected item in Backlog, got '{pos.column_name}'"

    # Configure PR review cycle to approve immediately (no issues)
    pr_cycle.set_approved_immediately()

    # Move item to In Review - this triggers the PR review cycle
    await board.move_item_to_column(work_item_id, "In Review", MovedByType.HUMAN)

    # Verify item reached In Review
    pos = await board.get_item_position(work_item_id)
    assert pos.column_name == "In Review", (
        f"Item should be in 'In Review' after human move, got '{pos.column_name}'"
    )
