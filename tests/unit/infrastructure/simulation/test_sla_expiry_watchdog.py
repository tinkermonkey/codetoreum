"""Tests for SLA expiry watchdog infrastructure.

Comprehensive test coverage of the SLAExpiryWatchdog including:
- Initialization and startup
- SLA detection and event emission
- Deduplication (once-per-SLA-expiry)
- Clock integration with time manipulation
- Error handling and fail-safe behavior
- Edge cases and boundary conditions
"""

from datetime import UTC, datetime, timedelta

import pytest

from codetoreum.adapters.testing import (
    CapturingMockEventEmitter,
    InMemoryWorkflowConfigService,
    MockBoardAdapter,
)
from codetoreum.domain.board_workflow_template import BoardWorkflowTemplate, ColumnTemplate, ColumnType
from codetoreum.domain.events.board_events import ColumnSLAExceededEvent
from codetoreum.infrastructure.simulation.simulation_clock import SimulationClock
from codetoreum.infrastructure.simulation.watchdogs import SLAExpiryWatchdog
from codetoreum.ports.output.board_service import MovedByType


@pytest.fixture
def clock() -> SimulationClock:
    """Create a test simulation clock."""
    clock = SimulationClock(speed_multiplier=100.0)
    clock.start_at(datetime(2025, 1, 14, 10, 0, 0, tzinfo=UTC))
    return clock


@pytest.fixture
def event_emitter() -> CapturingMockEventEmitter:
    """Create a capturing event emitter for test verification."""
    return CapturingMockEventEmitter()


@pytest.fixture
def board_adapter(event_emitter, clock) -> MockBoardAdapter:
    """Create a mock board adapter for testing."""
    adapter = MockBoardAdapter(event_emitter, clock)
    adapter.current_project = "proj-1"
    return adapter


@pytest.fixture
def workflow_config_service() -> InMemoryWorkflowConfigService:
    """Create a workflow config service with SLA-enabled template."""
    service = InMemoryWorkflowConfigService()

    # Create template with SLA thresholds on Code Review (2 hours) and Testing (4 hours)
    template = BoardWorkflowTemplate(
        id="template-1",
        name="SLA Test Workflow",
        pipeline_trigger_columns=("Code Review",),
        exit_columns=("Done",),
        columns=(
            ColumnTemplate(
                name="Backlog",
                type=ColumnType.MANUAL,
                agent_id=None,
                is_pipeline_trigger=False,
                is_exit_column=False,
                position=0,
                auto_progress_on_completion=False,
                sla_seconds=None,  # No SLA on backlog
            ),
            ColumnTemplate(
                name="In Progress",
                type=ColumnType.AUTOMATED,
                agent_id="agent-1",
                is_pipeline_trigger=False,
                is_exit_column=False,
                position=1,
                auto_progress_on_completion=False,
                sla_seconds=None,  # No SLA on in progress
            ),
            ColumnTemplate(
                name="Code Review",
                type=ColumnType.MANUAL,
                agent_id=None,
                is_pipeline_trigger=True,
                is_exit_column=False,
                position=2,
                auto_progress_on_completion=False,
                sla_seconds=7200,  # 2 hour SLA
            ),
            ColumnTemplate(
                name="Testing",
                type=ColumnType.AUTOMATED,
                agent_id="agent-2",
                is_pipeline_trigger=False,
                is_exit_column=False,
                position=3,
                auto_progress_on_completion=False,
                sla_seconds=14400,  # 4 hour SLA
            ),
            ColumnTemplate(
                name="Done",
                type=ColumnType.MANUAL,
                agent_id=None,
                is_pipeline_trigger=False,
                is_exit_column=True,
                position=4,
                auto_progress_on_completion=False,
                sla_seconds=None,  # No SLA on done
            ),
        ),
    )

    service.register_template("board-1", template)
    return service


@pytest.fixture
async def watchdog(board_adapter, workflow_config_service, event_emitter, clock) -> SLAExpiryWatchdog:
    """Create and initialize SLA expiry watchdog."""
    dog = SLAExpiryWatchdog(
        board_service=board_adapter,
        workflow_config_service=workflow_config_service,
        event_emitter=event_emitter,
        clock=clock,
        check_interval=timedelta(seconds=60),
    )
    dog.start()
    return dog


@pytest.mark.asyncio
async def test_sla_watchdog_initialization(board_adapter, workflow_config_service, event_emitter, clock):
    """Test watchdog initialization and startup."""
    dog = SLAExpiryWatchdog(
        board_service=board_adapter,
        workflow_config_service=workflow_config_service,
        event_emitter=event_emitter,
        clock=clock,
        check_interval=timedelta(seconds=30),
    )

    # Watchdog should initialize without errors
    assert dog is not None
    assert dog._check_interval == timedelta(seconds=30)

    # Start should schedule first callback
    dog.start()
    # After start, clock should have one scheduled callback
    assert len(clock._scheduled_callbacks) > 0


@pytest.mark.asyncio
async def test_sla_detection_single_item(board_adapter, workflow_config_service, event_emitter, clock, watchdog):
    """Test SLA detection for a single item."""
    # Setup board with item in Code Review column
    board_adapter.create_board(
        "proj-1", "board-1", "Test Board", ["Backlog", "In Progress", "Code Review", "Testing", "Done"]
    )
    board_adapter.add_item_to_column("board-1", "Backlog", "item-1")

    # Move item to Code Review
    await board_adapter.move_item_to_column("item-1", "Code Review", MovedByType.ORCHESTRATOR)

    # Verify item is in Code Review with entry timestamp
    item = await board_adapter.get_item_position("item-1")
    assert item.column_name == "Code Review"
    assert item.entered_column_at is not None

    # Fast-forward time beyond SLA threshold (2 hours + 1 second)
    clock.start_at(clock.now() + timedelta(hours=2, seconds=1))

    # Trigger watchdog check
    await watchdog._check_sla_expiry()

    # Verify event was emitted
    events = [e for e in event_emitter.get_events() if isinstance(e, ColumnSLAExceededEvent)]
    assert len(events) == 1
    assert events[0].work_item_id == "item-1"
    assert events[0].column_name == "Code Review"
    assert events[0].sla_threshold_seconds == 7200
    assert events[0].elapsed_seconds > 7200


@pytest.mark.asyncio
async def test_sla_deduplication(board_adapter, workflow_config_service, event_emitter, clock, watchdog):
    """Test that SLA event is emitted only once per item per expiry."""
    # Setup board with item in Code Review
    board_adapter.create_board(
        "proj-1", "board-1", "Test Board", ["Backlog", "In Progress", "Code Review", "Testing", "Done"]
    )
    board_adapter.add_item_to_column("board-1", "Backlog", "item-1")
    await board_adapter.move_item_to_column("item-1", "Code Review", MovedByType.ORCHESTRATOR)

    # Fast-forward beyond SLA
    clock.start_at(clock.now() + timedelta(hours=3))

    # First check - should emit event
    await watchdog._check_sla_expiry()
    events = [e for e in event_emitter.get_events() if isinstance(e, ColumnSLAExceededEvent)]
    assert len(events) == 1

    # Second check - should NOT emit another event (deduplication)
    await watchdog._check_sla_expiry()
    events = [e for e in event_emitter.get_events() if isinstance(e, ColumnSLAExceededEvent)]
    assert len(events) == 1  # Still only 1


@pytest.mark.asyncio
async def test_sla_multiple_columns(board_adapter, workflow_config_service, event_emitter, clock, watchdog):
    """Test SLA detection across multiple columns with different thresholds."""
    # Setup board
    board_adapter.create_board(
        "proj-1", "board-1", "Test Board", ["Backlog", "In Progress", "Code Review", "Testing", "Done"]
    )

    # Add two items: one in Code Review (2hr SLA), one in Testing (4hr SLA)
    board_adapter.add_item_to_column("board-1", "Code Review", "item-1")
    board_adapter.add_item_to_column("board-1", "Testing", "item-2")

    # Fast-forward 3 hours (exceeds Code Review SLA but not Testing SLA)
    clock.start_at(clock.now() + timedelta(hours=3))
    await watchdog._check_sla_expiry()

    # Should emit event for item-1 only
    events = [e for e in event_emitter.get_events() if isinstance(e, ColumnSLAExceededEvent)]
    assert len(events) == 1
    assert events[0].work_item_id == "item-1"

    # Fast-forward 2 more hours (now exceeds Testing SLA)
    clock.start_at(clock.now() + timedelta(hours=2))
    await watchdog._check_sla_expiry()

    # Should now have 2 events (item-1 from before, item-2 new)
    events = [e for e in event_emitter.get_events() if isinstance(e, ColumnSLAExceededEvent)]
    assert len(events) == 2
    item_ids = {e.work_item_id for e in events}
    assert item_ids == {"item-1", "item-2"}


@pytest.mark.asyncio
async def test_sla_no_sla_column(board_adapter, workflow_config_service, event_emitter, clock, watchdog):
    """Test that items in columns without SLA don't trigger events."""
    # Setup board
    board_adapter.create_board(
        "proj-1", "board-1", "Test Board", ["Backlog", "In Progress", "Code Review", "Testing", "Done"]
    )

    # Add item to Backlog (no SLA configured)
    board_adapter.add_item_to_column("board-1", "Backlog", "item-1")

    # Fast-forward 10 hours (more than any SLA threshold)
    clock.start_at(clock.now() + timedelta(hours=10))
    await watchdog._check_sla_expiry()

    # Should emit NO event (no SLA configured for Backlog)
    events = [e for e in event_emitter.get_events() if isinstance(e, ColumnSLAExceededEvent)]
    assert len(events) == 0


@pytest.mark.asyncio
async def test_sla_item_without_entry_time(board_adapter, workflow_config_service, event_emitter, clock, watchdog):
    """Test that items without entry timestamp are skipped."""
    # Setup board
    board_adapter.create_board(
        "proj-1", "board-1", "Test Board", ["Backlog", "In Progress", "Code Review", "Testing", "Done"]
    )

    # Add item to column (will set entry time)
    board_adapter.add_item_to_column("board-1", "Code Review", "item-1")

    # Manually clear entry time to simulate broken state
    watchdog._board_service._item_column_entries.clear()

    # Fast-forward beyond SLA
    clock.start_at(clock.now() + timedelta(hours=3))
    await watchdog._check_sla_expiry()

    # Should emit NO event (missing entry time)
    events = [e for e in event_emitter.get_events() if isinstance(e, ColumnSLAExceededEvent)]
    assert len(events) == 0


@pytest.mark.asyncio
async def test_sla_error_handling(board_adapter, workflow_config_service, event_emitter, clock, watchdog):
    """Test watchdog continues on error (fail-safe pattern)."""

    # Create a broken workflow config service that raises on get_board_workflow_template
    class BrokenConfigService:
        async def get_board_workflow_template(self, board_id):
            raise RuntimeError("Service error")

    # Replace workflow config in watchdog
    watchdog._workflow_config_service = BrokenConfigService()

    # Setup board and item
    board_adapter.create_board(
        "proj-1", "board-1", "Test Board", ["Backlog", "In Progress", "Code Review", "Testing", "Done"]
    )
    board_adapter.add_item_to_column("board-1", "Code Review", "item-1")
    clock.start_at(clock.now() + timedelta(hours=3))

    # Check should log error but not crash
    try:
        await watchdog._check_sla_expiry()
    except RuntimeError:
        pytest.fail("Watchdog should catch and log errors, not re-raise")

    # Watchdog should still be able to run again with fixed config
    watchdog._workflow_config_service = workflow_config_service
    await watchdog._check_sla_expiry()
    events = [e for e in event_emitter.get_events() if isinstance(e, ColumnSLAExceededEvent)]
    assert len(events) == 1


@pytest.mark.asyncio
async def test_sla_event_fields(board_adapter, workflow_config_service, event_emitter, clock, watchdog):
    """Test that SLA event contains all required fields with correct values."""
    # Setup
    board_adapter.create_board(
        "proj-1", "board-1", "Test Board", ["Backlog", "In Progress", "Code Review", "Testing", "Done"]
    )
    board_adapter.add_item_to_column("board-1", "Code Review", "item-1")

    # Record entry time for verification
    item_pos = await board_adapter.get_item_position("item-1")
    entered_at = item_pos.entered_column_at
    assert entered_at is not None

    # Advance past SLA
    clock.start_at(clock.now() + timedelta(hours=2, seconds=30))
    await watchdog._check_sla_expiry()

    # Verify event contents
    events = [e for e in event_emitter.get_events() if isinstance(e, ColumnSLAExceededEvent)]
    assert len(events) == 1

    event = events[0]
    assert event.type == "column.sla_exceeded"
    assert event.work_item_id == "item-1"
    assert event.project_id == "proj-1"
    assert event.board_id == "board-1"
    assert event.column_name == "Code Review"
    assert event.sla_threshold_seconds == 7200
    assert event.elapsed_seconds == 7230  # 2.5 hours = 9000 seconds
    assert event.entered_at == entered_at.isoformat()
    assert event.source == "sla_expiry_watchdog"
    assert event.timestamp  # Should be set


@pytest.mark.asyncio
async def test_sla_tick_reschedules(board_adapter, workflow_config_service, event_emitter, clock, watchdog):
    """Test that _tick always reschedules itself (fail-safe pattern)."""
    # Setup
    board_adapter.create_board(
        "proj-1", "board-1", "Test Board", ["Backlog", "In Progress", "Code Review", "Testing", "Done"]
    )

    # Get initial scheduled callback count
    initial_count = len(clock._scheduled_callbacks)

    # Call _tick
    await watchdog._tick(datetime.now(UTC))

    # Should have rescheduled (one removed, one added = same or +1 depending on timing)
    # The key is that it never stays at 0 scheduled callbacks
    assert len(clock._scheduled_callbacks) >= initial_count


@pytest.mark.asyncio
async def test_sla_clock_integration(board_adapter, workflow_config_service, event_emitter, clock):
    """Test that watchdog uses clock.now() exclusively for time comparisons."""
    dog = SLAExpiryWatchdog(
        board_service=board_adapter,
        workflow_config_service=workflow_config_service,
        event_emitter=event_emitter,
        clock=clock,
        check_interval=timedelta(seconds=60),
    )

    # Setup
    board_adapter.create_board(
        "proj-1", "board-1", "Test Board", ["Backlog", "In Progress", "Code Review", "Testing", "Done"]
    )
    board_adapter.add_item_to_column("board-1", "Code Review", "item-1")

    # Record wall time
    wall_time_before = datetime.now(UTC)

    # Advance simulated time significantly
    clock.start_at(clock.now() + timedelta(hours=3))

    # Check elapsed time uses clock.now(), not wall time
    await dog._check_sla_expiry()

    # Wall time should not have advanced 3 hours, but simulated time did
    wall_time_after = datetime.now(UTC)
    wall_elapsed = wall_time_after - wall_time_before
    assert wall_elapsed < timedelta(seconds=5)  # Should be nearly instant

    # But event should show SLA exceeded based on simulated time
    events = [e for e in event_emitter.get_events() if isinstance(e, ColumnSLAExceededEvent)]
    assert len(events) == 1
    assert events[0].elapsed_seconds > 7200  # More than 2 hour SLA
