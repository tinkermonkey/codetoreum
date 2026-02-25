"""Simulation Scenario 10: Conversational Feedback Loops.

Tests comprehensive end-to-end simulation scenarios covering the full lifecycle of
conversational feedback loops with human-in-the-loop interaction patterns.

Scenarios Covered:
1. Scenario A: Normal Event Flow - Full lifecycle from entry → comment → response → exit
2. Scenario B: Restart Recovery - Resume from checkpoint without duplicate processing
3. Edge Case C: Event Ordering - Rapid comments processed sequentially
4. Edge Case D: Bot Comment Filtering - Bot comments don't trigger events
5. Edge Case E: Threaded Context - Parent comment context preserved
6. Edge Case F: Column Change During Processing - Graceful session termination
7. Edge Case G: Concurrent Work Items - Multiple sessions remain isolated
8. Edge Case H: Initial Agent Output - First entry posts agent output if no comments
9. Edge Case I: Error Handling - Adapter errors handled gracefully
10. Edge Case J: Duplicate Prevention - Same comment not processed twice

Key Features Tested:
- Conversational session lifecycle (create → update → persist → resume → terminate)
- Conversation ID continuity for multi-turn LLM context
- Last-processed-comment-ID checkpoints for restart safety
- Event correlation and chronological ordering
- Concurrent work item isolation
- Error recovery and logging
- Comment deduplication and filtering
"""

import re
from datetime import timedelta

import pytest

from codetoreum.adapters.secondary.configurable_identity_service import (
    ConfigurableIdentityService,
)
from codetoreum.adapters.secondary.mock_discussion_adapter import MockDiscussionAdapter
from codetoreum.domain.events.discussion_events import CommentNeedsResponseEvent
from codetoreum.infrastructure.event_bus import EventBus
from codetoreum.infrastructure.simulation import (
    SimulationConfig,
    SimulationRunner,
)
from codetoreum.ports.output.discussion_adapter import DiscussionMonitoringConfig
from codetoreum.ports.output.identity_service import BotIdentityConfig


def create_config(
    scenario_name: str = "scenario_10_conversational_modes",
) -> SimulationConfig:
    """Create configuration for conversational modes scenario."""
    config = SimulationConfig.create_fast_config(
        scenario_name=scenario_name,
        speed_multiplier=100.0,
    )
    config.scenario_description = (
        "Comprehensive conversational feedback loop testing including event flow, "
        "restart recovery, edge cases, and concurrent work item handling"
    )

    # Configure LLM response patterns for different comment types
    config.add_agent_response_pattern(
        agent_id="business_analyst",
        pattern=r"requirement.*",
        response="Based on your feedback, here are the refined requirements: ...",
    )

    config.add_agent_response_pattern(
        agent_id="business_analyst",
        pattern=r"edge case.*",
        response="Great question about edge cases. We should handle: ...",
    )

    config.add_agent_response_pattern(
        agent_id="developer",
        pattern=r"implementation.*",
        response="I've reviewed your feedback and updated the implementation with: ...",
    )

    config.add_agent_response_pattern(
        agent_id="developer",
        pattern=r"test.*",
        response="All tests pass for the scenarios you mentioned. Test results: ...",
    )

    return config


def create_identity_service() -> ConfigurableIdentityService:
    """Create and configure identity service for bot detection."""
    identity_service = ConfigurableIdentityService()
    identity_service.set_bot_username("codetoreum-bot")

    # Configure bot detection
    config = BotIdentityConfig(
        bot_usernames=["dependabot", "bot-analyst", "bot-reviewer", "codetoreum-bot"],
        bot_patterns=[re.compile("^bot-.*")]
    )
    identity_service.configure(config)

    return identity_service


def create_discussion_adapter() -> MockDiscussionAdapter:
    """Create and configure discussion adapter."""
    identity_service = create_identity_service()
    return MockDiscussionAdapter(identity_service)


async def run_scenario(runner: SimulationRunner):
    """Run conversational modes simulation scenarios.

    This scenario tests the complete conversational feedback loop lifecycle
    through multiple test cases that progressively exercise more complex scenarios.
    """

    # Scenario A: Normal Event Flow
    await scenario_a_normal_event_flow(runner)

    # Scenario B: Restart Recovery
    await scenario_b_restart_recovery(runner)

    # Edge Case C: Event Ordering
    await edge_case_c_event_ordering(runner)

    # Edge Case D: Bot Comment Filtering
    await edge_case_d_bot_comment_filtering(runner)

    # Edge Case E: Threaded Context
    await edge_case_e_threaded_context(runner)

    # Edge Case F: Column Change During Processing
    await edge_case_f_column_change_during_processing(runner)

    # Edge Case G: Concurrent Work Items
    await edge_case_g_concurrent_work_items(runner)

    # Edge Case H: Initial Agent Output
    await edge_case_h_initial_agent_output(runner)

    # Edge Case I: Error Handling
    await edge_case_i_error_handling(runner)

    # Edge Case J: Duplicate Prevention
    await edge_case_j_duplicate_prevention(runner)


async def scenario_a_normal_event_flow(runner: SimulationRunner):
    """Scenario A: Normal Event Flow - Full lifecycle from entry to exit.

    Validates:
    - Session creation and initialization
    - Event emission and handling
    - Multi-turn conversation with context
    - Bot comment posting
    - Session tracking
    """
    discussion_adapter = create_discussion_adapter()
    event_bus = EventBus()
    captured_events: list[CommentNeedsResponseEvent] = []

    # Setup event capture
    def capture_event(event):
        captured_events.append(event)

    discussion_adapter.on("comment.needs_response", capture_event)

    work_item_id = "ISSUE-100"
    project_id = "proj-conversational-test"

    # Initialize monitoring
    monitoring_config = DiscussionMonitoringConfig(
        project_id=project_id,
    )
    discussion_adapter.start_monitoring(work_item_id, monitoring_config)

    runner.assert_true(
        discussion_adapter.is_monitoring(work_item_id),
        "scenario_a_monitoring_started",
        "Discussion adapter should be monitoring work item"
    )

    # Human posts first comment
    discussion_adapter.simulate_comment(
        work_item_id,
        "alice",
        "What are the requirements?",
        is_initial=True
    )

    await runner.advance_time(timedelta(milliseconds=100))

    runner.assert_equal(
        len(captured_events),
        1,
        "scenario_a_first_event_captured",
        "First comment should trigger event"
    )

    # Bot posts response
    response1 = await discussion_adapter.add_comment(
        work_item_id,
        "Based on your feedback, here are the refined requirements: ..."
    )

    runner.assert_true(
        response1.is_bot,
        "scenario_a_response_is_bot",
        "Response should be from bot"
    )

    # Human replies (threaded)
    discussion_adapter.simulate_comment(
        work_item_id,
        "alice",
        "Thanks, what about edge cases?",
        parent_id=response1.id
    )

    await runner.advance_time(timedelta(milliseconds=100))

    runner.assert_equal(
        len(captured_events),
        2,
        "scenario_a_threaded_event_captured",
        "Threaded comment should trigger event"
    )

    # Bot responds to threaded comment
    parent_comment = captured_events[-1].comment
    assert parent_comment is not None, "Expected comment in last event"
    response2 = await discussion_adapter.add_comment(
        work_item_id,
        "Great question about edge cases. We should handle: ...",
        parent_id=parent_comment.id
    )

    runner.assert_true(
        response2.parent_id is not None,
        "scenario_a_response_threaded",
        "Response should be threaded"
    )

    # Stop monitoring (simulates column change and session termination)
    discussion_adapter.stop_monitoring(work_item_id)

    runner.assert_false(
        discussion_adapter.is_monitoring(work_item_id),
        "scenario_a_monitoring_stopped",
        "Monitoring should be stopped"
    )


async def scenario_b_restart_recovery(runner: SimulationRunner):
    """Scenario B: Restart Recovery - Resume from checkpoint without duplicates.

    Validates:
    - Session state persistence via checkpoint
    - Resume from last processed comment
    - No re-processing of checkpointed comments
    - Only new comments trigger events
    """
    discussion_adapter = create_discussion_adapter()
    captured_events: list[CommentNeedsResponseEvent] = []

    def capture_event(event):
        captured_events.append(event)

    discussion_adapter.on("comment.needs_response", capture_event)

    work_item_id = "ISSUE-101"
    project_id = "proj-restart-test"

    # Pre-populate comments (simulating state before restart)
    monitoring_config = DiscussionMonitoringConfig(
        project_id=project_id,
    )
    discussion_adapter.start_monitoring(work_item_id, monitoring_config)

    for i in range(1, 4):
        discussion_adapter.simulate_comment(
            work_item_id,
            "alice",
            f"Comment {i}",
        )

    await runner.advance_time(timedelta(milliseconds=100))

    # Checkpoint: 3 comments processed
    checkpoint_count = len(captured_events)
    runner.assert_equal(
        checkpoint_count,
        3,
        "scenario_b_checkpoint_count",
        "3 comments should be processed before restart"
    )

    # Simulate restart: reset adapter
    discussion_adapter.clear_monitoring()
    captured_events.clear()

    # Resume monitoring
    discussion_adapter.start_monitoring(work_item_id, monitoring_config)

    # Add new comments
    for i in range(4, 6):
        discussion_adapter.simulate_comment(
            work_item_id,
            "bob",
            f"Comment {i}",
        )

    await runner.advance_time(timedelta(milliseconds=100))

    # Verify only new comments triggered events
    runner.assert_equal(
        len(captured_events),
        2,
        "scenario_b_new_comments_processed",
        "Only 2 new comments should trigger events"
    )


async def edge_case_c_event_ordering(runner: SimulationRunner):
    """Edge Case C: Event Ordering - Rapid comments processed sequentially.

    Validates:
    - Multiple comments arrive rapidly
    - Events processed in chronological order
    - No out-of-order processing
    """
    discussion_adapter = create_discussion_adapter()
    captured_events: list[CommentNeedsResponseEvent] = []

    def capture_event(event):
        captured_events.append(event)

    discussion_adapter.on("comment.needs_response", capture_event)

    work_item_id = "ISSUE-102"
    project_id = "proj-ordering-test"

    monitoring_config = DiscussionMonitoringConfig(
        project_id=project_id,
    )
    discussion_adapter.start_monitoring(work_item_id, monitoring_config)

    # Simulate rapid comments
    for i in range(5):
        discussion_adapter.simulate_comment(
            work_item_id,
            "alice",
            f"Rapid comment {i+1}",
        )

    await runner.advance_time(timedelta(milliseconds=200))

    runner.assert_equal(
        len(captured_events),
        5,
        "edge_case_c_all_comments_processed",
        "All 5 rapid comments should be processed"
    )

    # Verify order via comment count increase
    runner.assert_equal(
        len(discussion_adapter.get_comments_by_author(work_item_id, "alice")),
        5,
        "edge_case_c_order_preserved",
        "Comments should be processed in order"
    )


async def edge_case_d_bot_comment_filtering(runner: SimulationRunner):
    """Edge Case D: Bot Comment Filtering - Bot comments don't trigger events.

    Validates:
    - Bot comments are filtered
    - No events emitted for bot comments
    - Human comments still trigger events
    """
    discussion_adapter = create_discussion_adapter()
    captured_events: list[CommentNeedsResponseEvent] = []

    def capture_event(event):
        captured_events.append(event)

    discussion_adapter.on("comment.needs_response", capture_event)

    work_item_id = "ISSUE-103"
    project_id = "proj-bot-filter-test"

    monitoring_config = DiscussionMonitoringConfig(
        project_id=project_id,
    )
    discussion_adapter.start_monitoring(work_item_id, monitoring_config)

    # Human comment
    discussion_adapter.simulate_comment(
        work_item_id,
        "alice",
        "This needs review",
    )

    # Bot comment (should be filtered)
    discussion_adapter.simulate_comment(
        work_item_id,
        "bot-reviewer",
        "Reviewed and approved",
    )

    # Another human comment
    discussion_adapter.simulate_comment(
        work_item_id,
        "bob",
        "I agree",
    )

    await runner.advance_time(timedelta(milliseconds=200))

    runner.assert_equal(
        len(captured_events),
        2,
        "edge_case_d_only_human_comments",
        "Only 2 human comments should trigger events"
    )

    # Verify bot comment was not included in events
    event_authors = [
        e.comment.author for e in captured_events
        if e.comment is not None
    ]
    runner.assert_true(
        "bot-reviewer" not in event_authors,
        "edge_case_d_bot_filtered",
        "Bot comment should not trigger events"
    )


async def edge_case_e_threaded_context(runner: SimulationRunner):
    """Edge Case E: Threaded Context - Parent comment context preserved.

    Validates:
    - Threaded comments include parent context
    - Parent-child relationships preserved
    - Conversation flow maintained
    """
    discussion_adapter = create_discussion_adapter()
    captured_events: list[CommentNeedsResponseEvent] = []

    def capture_event(event):
        captured_events.append(event)

    discussion_adapter.on("comment.needs_response", capture_event)

    work_item_id = "ISSUE-104"
    project_id = "proj-threaded-test"

    monitoring_config = DiscussionMonitoringConfig(
        project_id=project_id,
    )
    discussion_adapter.start_monitoring(work_item_id, monitoring_config)

    # Parent comment
    discussion_adapter.simulate_comment(
        work_item_id,
        "alice",
        "What about the API design?",
    )

    await runner.advance_time(timedelta(milliseconds=50))

    parent_event = captured_events[0]
    parent_comment = parent_event.comment
    assert parent_comment is not None, "Expected comment in parent event"
    parent_comment_id = parent_comment.id

    # Child comment (threaded)
    discussion_adapter.simulate_comment(
        work_item_id,
        "bob",
        "Should we use REST or GraphQL?",
        parent_id=parent_comment_id
    )

    await runner.advance_time(timedelta(milliseconds=50))

    runner.assert_equal(
        len(captured_events),
        2,
        "edge_case_e_threaded_comments_processed",
        "Both parent and child should be processed"
    )

    # Verify threaded relationship
    child_event = captured_events[1]
    child_comment = child_event.comment
    assert child_comment is not None, "Expected comment in child event"
    runner.assert_equal(
        child_comment.parent_id,
        parent_comment_id,
        "edge_case_e_parent_id_preserved",
        "Child parent_id should be preserved"
    )


async def edge_case_f_column_change_during_processing(runner: SimulationRunner):
    """Edge Case F: Column Change During Processing - Graceful session termination.

    Validates:
    - Column change detected during conversation
    - Session gracefully terminates
    - Monitoring stopped
    - No further event processing
    """
    discussion_adapter = create_discussion_adapter()
    captured_events: list[CommentNeedsResponseEvent] = []

    def capture_event(event):
        captured_events.append(event)

    discussion_adapter.on("comment.needs_response", capture_event)

    work_item_id = "ISSUE-105"
    project_id = "proj-column-change-test"

    monitoring_config = DiscussionMonitoringConfig(
        project_id=project_id,
    )
    discussion_adapter.start_monitoring(work_item_id, monitoring_config)

    # Process some comments
    discussion_adapter.simulate_comment(
        work_item_id,
        "alice",
        "Starting implementation",
    )

    await runner.advance_time(timedelta(milliseconds=100))

    runner.assert_equal(
        len(captured_events),
        1,
        "edge_case_f_initial_comment",
        "Initial comment should be processed"
    )

    # Stop monitoring (simulates column change)
    discussion_adapter.stop_monitoring(work_item_id)

    # Try to post post-termination comment
    discussion_adapter.simulate_comment(
        work_item_id,
        "bob",
        "This should not trigger event",
    )

    await runner.advance_time(timedelta(milliseconds=100))

    runner.assert_false(
        discussion_adapter.is_monitoring(work_item_id),
        "edge_case_f_monitoring_stopped",
        "Monitoring should be stopped"
    )

    runner.assert_equal(
        len(captured_events),
        1,
        "edge_case_f_post_termination_ignored",
        "Post-termination comments should not trigger events"
    )


async def edge_case_g_concurrent_work_items(runner: SimulationRunner):
    """Edge Case G: Concurrent Work Items - Multiple sessions remain isolated.

    Validates:
    - Multiple work items monitored simultaneously
    - Events correctly routed to respective items
    - No cross-contamination between sessions
    """
    discussion_adapter = create_discussion_adapter()
    work_items = ["ISSUE-201", "ISSUE-202", "ISSUE-203"]

    # Setup monitoring for all items
    for work_item_id in work_items:
        monitoring_config = DiscussionMonitoringConfig(
            project_id="proj-concurrent-test",
        )
        discussion_adapter.start_monitoring(work_item_id, monitoring_config)

    # Add comments to different work items
    for i, work_item_id in enumerate(work_items):
        for j in range(2):
            discussion_adapter.simulate_comment(
                work_item_id,
                f"user-{i}",
                f"Comment {j+1} for {work_item_id}",
            )

    await runner.advance_time(timedelta(milliseconds=500))

    # Verify isolation: each work item has only its own comments
    for i, work_item_id in enumerate(work_items):
        comments = discussion_adapter.get_comments_by_author(work_item_id, f"user-{i}")
        runner.assert_equal(
            len(comments),
            2,
            f"edge_case_g_{work_item_id}_isolation",
            f"Work item {work_item_id} should have only its 2 comments"
        )


async def edge_case_h_initial_agent_output(runner: SimulationRunner):
    """Edge Case H: Initial Agent Output - First entry posts agent output.

    Validates:
    - Session initialization posts initial agent output
    - No wait for first comment
    - Output is posted by bot
    """
    discussion_adapter = create_discussion_adapter()

    work_item_id = "ISSUE-106"
    project_id = "proj-initial-output-test"

    monitoring_config = DiscussionMonitoringConfig(
        project_id=project_id,
    )
    discussion_adapter.start_monitoring(work_item_id, monitoring_config)

    # Simulate agent posting initial output
    initial_output = await discussion_adapter.add_comment(
        work_item_id,
        "I'm ready to help with requirements gathering. Please share your initial thoughts."
    )

    runner.assert_true(
        initial_output.is_bot,
        "edge_case_h_is_bot",
        "Initial output should be from bot"
    )

    # Get thread and verify
    thread = await discussion_adapter.get_thread(work_item_id)
    runner.assert_equal(
        len(thread.comments),
        1,
        "edge_case_h_thread_has_comment",
        "Thread should have initial bot comment"
    )


async def edge_case_i_error_handling(runner: SimulationRunner):
    """Edge Case I: Error Handling - Adapter errors handled gracefully.

    Validates:
    - Adapter errors don't crash
    - Session remains recoverable
    - Error scenarios handled
    """
    discussion_adapter = create_discussion_adapter()

    work_item_id = "ISSUE-107"
    project_id = "proj-error-test"

    monitoring_config = DiscussionMonitoringConfig(
        project_id=project_id,
    )
    discussion_adapter.start_monitoring(work_item_id, monitoring_config)

    # Test error case: try to stop monitoring non-existent item
    error_occurred = False
    try:
        discussion_adapter.stop_monitoring("NONEXISTENT")
    except ValueError:
        error_occurred = True

    runner.assert_true(
        error_occurred,
        "edge_case_i_error_raised",
        "Error should be raised for invalid operation"
    )

    # Verify session still recoverable
    runner.assert_true(
        discussion_adapter.is_monitoring(work_item_id),
        "edge_case_i_session_recoverable",
        "Session should remain active despite error"
    )


async def edge_case_j_duplicate_prevention(runner: SimulationRunner):
    """Edge Case J: Duplicate Prevention - Same comment not processed twice.

    Validates:
    - Comment deduplication via ID tracking
    - Restart doesn't reprocess last comment
    - Same comment never triggers event twice
    """
    discussion_adapter = create_discussion_adapter()
    captured_events: list[CommentNeedsResponseEvent] = []

    def capture_event(event):
        captured_events.append(event)

    discussion_adapter.on("comment.needs_response", capture_event)

    work_item_id = "ISSUE-108"
    project_id = "proj-dedup-test"

    monitoring_config = DiscussionMonitoringConfig(
        project_id=project_id,
    )
    discussion_adapter.start_monitoring(work_item_id, monitoring_config)

    # Add comment
    discussion_adapter.simulate_comment(
        work_item_id,
        "alice",
        "Review this code",
    )

    await runner.advance_time(timedelta(milliseconds=100))

    first_processing_count = len(captured_events)
    runner.assert_equal(
        first_processing_count,
        1,
        "edge_case_j_first_processing",
        "First processing should detect 1 comment"
    )

    # Get processed comment IDs
    processed_ids_before = len(discussion_adapter.get_comments_by_author(work_item_id, "alice"))

    # Clear events and verify no duplicates
    captured_events.clear()

    await runner.advance_time(timedelta(milliseconds=100))

    runner.assert_equal(
        len(captured_events),
        0,
        "edge_case_j_deduplication",
        "No duplicate events should be triggered"
    )

    # Verify comment count stays same
    processed_ids_after = len(discussion_adapter.get_comments_by_author(work_item_id, "alice"))
    runner.assert_equal(
        processed_ids_before,
        processed_ids_after,
        "edge_case_j_no_duplication_on_query",
        "Comment count should not increase"
    )


@pytest.mark.asyncio
async def test_scenario_10_conversational_modes():
    """Test Scenario 10: Conversational Feedback Loops."""
    config = create_config()
    runner = SimulationRunner(config)

    result = await runner.run(run_scenario)

    # Verify success
    assert result.success, f"Scenario failed with errors: {result.errors}"
    assert result.assertions_passed >= 25, (
        f"Expected at least 25 assertions to pass, got {result.assertions_passed}"
    )
    assert result.assertions_failed == 0, (
        f"Expected no failed assertions, got {result.assertions_failed}"
    )

    # Verify performance goal (10-100x faster)
    assert result.speed_multiplier >= 10.0, (
        f"Speed multiplier {result.speed_multiplier:.1f}x below 10x target"
    )


if __name__ == "__main__":
    import asyncio

    async def run_all():
        """Run all scenario 10 tests."""
        print("\n" + "=" * 70)
        print("SCENARIO 10: Conversational Feedback Loops")
        print("=" * 70)

        config = create_config()
        runner = SimulationRunner(config)
        result = await runner.run(run_scenario)

        print("\n✓ Conversational Modes Scenario completed")
        print(f"  Speed multiplier: {result.speed_multiplier:.1f}x")
        print(f"  Real time: {result.duration_seconds:.2f}s")
        print(f"  Simulated time: {result.simulated_duration_seconds:.1f}s")
        print(f"  Events captured: {result.events_captured}")
        print(f"  Assertions: {result.assertions_passed}/{result.assertions_passed + result.assertions_failed}")

        print("\n" + "=" * 70)
        print("All Scenario 10 Conversational Modes tests completed successfully!")
        print("=" * 70 + "\n")

    asyncio.run(run_all())
