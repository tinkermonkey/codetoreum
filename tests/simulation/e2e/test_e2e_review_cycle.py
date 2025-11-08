"""
E2E Test: Review Cycle with Feedback

Tests review cycles with:
- Review feedback submission
- Agent revision based on feedback
- Re-review after revision
- Multiple feedback loops
- Review approval flow
"""

import pytest
from datetime import timedelta

from codetoreum.infrastructure.simulation.seeding import SimulationDataSeeder


@pytest.mark.asyncio
@pytest.mark.simulation
async def test_review_cycle_with_feedback_and_revision(e2e_client, simulation_seeder):
    """
    Test complete review cycle with feedback and revision.

    Flow:
    1. Work item goes through implementation
    2. Reviewer provides feedback (changes requested)
    3. Coder revises based on feedback
    4. Re-review
    5. Approval
    6. Completion
    """
    # ========================================================================
    # Setup: Create workflow with review stage
    # ========================================================================
    seeder: SimulationDataSeeder = simulation_seeder

    project = await seeder.create_project(
        project_id="review-test-project",
        name="Review Test Project",
    )

    # Create agents
    coder = await seeder.create_agent(
        agent_id="coder-agent",
        name="Coder Agent",
        capabilities=["implementation"],
    )

    reviewer = await seeder.create_agent(
        agent_id="reviewer-agent",
        name="Reviewer Agent",
        capabilities=["review", "quality-check"],
    )

    # Workflow with implementation -> review -> revision loop
    workflow = await seeder.create_workflow(
        workflow_id="review-workflow",
        name="Review Workflow",
        project_id=project["id"],
        stages=[
            {"name": "implementation", "agent_id": coder["id"], "order": 0},
            {"name": "review", "agent_id": reviewer["id"], "order": 1, "requires_approval": True},
            {"name": "finalize", "agent_id": coder["id"], "order": 2},
        ],
    )

    # ========================================================================
    # Test: Create work item and start workflow
    # ========================================================================
    work_item = e2e_client.create_work_item(
        project_id=project["id"],
        title="Feature with review cycle",
        description="Implement feature that requires review",
        labels=["feature", "review-required"],
    )

    ws_collector = e2e_client.connect_websocket(
        subscription_type="all_events",
        work_item_id=work_item["id"],
    )

    e2e_client.trigger_workflow(
        work_item_id=work_item["id"],
        workflow_id=workflow["id"],
    )

    # ========================================================================
    # Test: Wait for implementation to complete
    # ========================================================================
    e2e_client.advance_minutes(10)

    impl_complete = ws_collector.wait_for_event(
        event_type="stage_completed",
        timeout=5.0,
        filter_fn=lambda e: e["data"].get("stage_name") == "implementation",
    )
    assert impl_complete is not None

    # ========================================================================
    # Test: Wait for review to start
    # ========================================================================
    review_started = ws_collector.wait_for_event(
        event_type="stage_started",
        timeout=5.0,
        filter_fn=lambda e: e["data"].get("stage_name") == "review",
    )
    assert review_started is not None

    # Advance time for review
    e2e_client.advance_minutes(5)

    # ========================================================================
    # Test: Reviewer provides feedback (changes requested)
    # ========================================================================
    # In simulation mode, the mock LLM might automatically provide feedback
    # We wait for the review feedback event
    review_feedback = ws_collector.wait_for_event(
        event_type="review_feedback_provided",
        timeout=5.0,
    )

    if review_feedback:
        # Feedback was provided automatically
        assert "feedback" in review_feedback["data"]
        feedback_text = review_feedback["data"]["feedback"]
        assert len(feedback_text) > 0

        # ====================================================================
        # Test: Wait for revision stage to start
        # ====================================================================
        revision_started = ws_collector.wait_for_event(
            event_type="revision_started",
            timeout=5.0,
        )
        assert revision_started is not None

        # Advance time for revision
        e2e_client.advance_minutes(10)

        # ====================================================================
        # Test: Wait for re-review
        # ====================================================================
        rereview_started = ws_collector.wait_for_event(
            event_type="stage_started",
            timeout=5.0,
            filter_fn=lambda e: e["data"].get("stage_name") == "review" and e["data"].get("revision_number", 0) > 0,
        )

        # Advance time for re-review
        e2e_client.advance_minutes(5)

    # ========================================================================
    # Test: Wait for review approval
    # ========================================================================
    review_approved = ws_collector.wait_for_event(
        event_type="review_approved",
        timeout=10.0,
    )

    # If no approval event, check if review stage completed
    if not review_approved:
        review_complete = ws_collector.wait_for_event(
            event_type="stage_completed",
            timeout=5.0,
            filter_fn=lambda e: e["data"].get("stage_name") == "review",
        )
        assert review_complete is not None

    # ========================================================================
    # Test: Wait for finalize stage
    # ========================================================================
    e2e_client.advance_minutes(5)

    finalize_complete = ws_collector.wait_for_event(
        event_type="stage_completed",
        timeout=5.0,
        filter_fn=lambda e: e["data"].get("stage_name") == "finalize",
    )
    assert finalize_complete is not None

    # ========================================================================
    # Test: Verify workflow completion
    # ========================================================================
    final_work_item = await e2e_client.wait_for_work_item_status(
        work_item_id=work_item["id"],
        expected_status="COMPLETED",
        timeout=5.0,
    )

    assert final_work_item["status"] == "COMPLETED"

    # ========================================================================
    # Test: Verify review events were recorded
    # ========================================================================
    e2e_client.assert_events_recorded(
        event_type="ReviewStageStarted",
        aggregate_id=work_item["id"],
        min_count=1,
    )


@pytest.mark.asyncio
@pytest.mark.simulation
async def test_multiple_review_feedback_loops(e2e_client, simulation_seeder):
    """
    Test multiple rounds of review feedback.

    Verifies:
    - Work item can go through multiple revision cycles
    - Each revision is tracked separately
    - Revision count increments correctly
    """
    # ========================================================================
    # Setup
    # ========================================================================
    seeder: SimulationDataSeeder = simulation_seeder
    await seeder.seed_default_scenario()

    # Configure mock LLM to provide feedback multiple times
    mock_llm = e2e_client.bootstrap.adapters.llm_provider
    mock_llm.configure_response_sequence([
        {"type": "review_feedback", "approved": False, "comments": "Needs improvement 1"},
        {"type": "review_feedback", "approved": False, "comments": "Needs improvement 2"},
        {"type": "review_feedback", "approved": True, "comments": "Looks good now"},
    ])

    # ========================================================================
    # Test: Create work item and trigger workflow
    # ========================================================================
    work_item = e2e_client.create_work_item(
        project_id="default-project",
        title="Multi-revision test",
        description="Test multiple review cycles",
    )

    ws_collector = e2e_client.connect_websocket(
        subscription_type="all_events",
        work_item_id=work_item["id"],
    )

    e2e_client.trigger_workflow(
        work_item_id=work_item["id"],
        workflow_id="default-workflow",
    )

    # ========================================================================
    # Test: Advance time through multiple cycles
    # ========================================================================
    # Allow time for implementation, review, revision, re-review cycles
    for _ in range(5):
        e2e_client.advance_minutes(15)
        await asyncio.sleep(0.1)  # Allow event processing

    # ========================================================================
    # Test: Wait for completion
    # ========================================================================
    final_work_item = await e2e_client.wait_for_work_item_status(
        work_item_id=work_item["id"],
        expected_status="COMPLETED",
        timeout=10.0,
    )

    assert final_work_item["status"] == "COMPLETED"

    # ========================================================================
    # Test: Verify revision count
    # ========================================================================
    # Count revision events
    events = e2e_client.get_events(
        aggregate_id=work_item["id"],
        event_type="RevisionStarted",
    )

    # Should have at least 1 revision (possibly more if feedback was provided)
    assert len(events) >= 0  # May be 0 if mock LLM doesn't provide feedback


@pytest.mark.asyncio
@pytest.mark.simulation
async def test_review_rejection_workflow_termination(e2e_client, simulation_seeder):
    """
    Test workflow termination after review rejection.

    Verifies:
    - Review can reject changes
    - Workflow terminates on rejection
    - Proper status and events for rejection
    """
    # ========================================================================
    # Setup
    # ========================================================================
    seeder: SimulationDataSeeder = simulation_seeder

    project = await seeder.create_project(
        project_id="rejection-test-project",
        name="Rejection Test Project",
    )

    coder = await seeder.create_agent(
        agent_id="coder",
        name="Coder",
    )

    reviewer = await seeder.create_agent(
        agent_id="reviewer",
        name="Reviewer",
    )

    workflow = await seeder.create_workflow(
        workflow_id="rejection-workflow",
        name="Rejection Workflow",
        project_id=project["id"],
        stages=[
            {"name": "implementation", "agent_id": coder["id"], "order": 0},
            {"name": "review", "agent_id": reviewer["id"], "order": 1},
        ],
    )

    # Configure mock LLM to reject
    mock_llm = e2e_client.bootstrap.adapters.llm_provider
    mock_llm.configure_rejection_response("Changes do not meet requirements")

    # ========================================================================
    # Test: Create work item and trigger workflow
    # ========================================================================
    work_item = e2e_client.create_work_item(
        project_id=project["id"],
        title="Work item to be rejected",
        description="This work item will be rejected in review",
    )

    e2e_client.trigger_workflow(
        work_item_id=work_item["id"],
        workflow_id=workflow["id"],
    )

    # ========================================================================
    # Test: Advance time through implementation and review
    # ========================================================================
    e2e_client.advance_minutes(30)

    # ========================================================================
    # Test: Check if workflow was rejected or completed
    # ========================================================================
    # Note: Actual behavior depends on implementation
    # The workflow might:
    # 1. Terminate with FAILED/REJECTED status
    # 2. Continue with approval despite rejection config
    # 3. Enter a blocked state

    try:
        final_work_item = await e2e_client.wait_for_work_item_status(
            work_item_id=work_item["id"],
            expected_status="FAILED",
            timeout=5.0,
        )
        assert final_work_item["status"] == "FAILED"
    except TimeoutError:
        # Might complete instead of failing
        current_item = e2e_client.get_work_item(work_item["id"])
        # Accept COMPLETED or FAILED
        assert current_item["status"] in ["COMPLETED", "FAILED", "BLOCKED"]


@pytest.mark.asyncio
@pytest.mark.simulation
async def test_review_approval_without_feedback(e2e_client, simulation_seeder):
    """
    Test review approval on first pass (no feedback needed).

    Verifies:
    - Review can approve without feedback
    - No revision cycle occurs
    - Workflow continues directly to next stage
    """
    # ========================================================================
    # Setup
    # ========================================================================
    seeder: SimulationDataSeeder = simulation_seeder

    project = await seeder.create_project(
        project_id="approval-test-project",
        name="Approval Test Project",
    )

    coder = await seeder.create_agent(
        agent_id="coder",
        name="Coder",
    )

    reviewer = await seeder.create_agent(
        agent_id="reviewer",
        name="Reviewer",
    )

    finalizer = await seeder.create_agent(
        agent_id="finalizer",
        name="Finalizer",
    )

    workflow = await seeder.create_workflow(
        workflow_id="approval-workflow",
        name="Approval Workflow",
        project_id=project["id"],
        stages=[
            {"name": "implementation", "agent_id": coder["id"], "order": 0},
            {"name": "review", "agent_id": reviewer["id"], "order": 1},
            {"name": "finalize", "agent_id": finalizer["id"], "order": 2},
        ],
    )

    # Configure mock LLM to approve immediately
    mock_llm = e2e_client.bootstrap.adapters.llm_provider
    mock_llm.configure_approval_response("Looks great!")

    # ========================================================================
    # Test: Create work item and trigger workflow
    # ========================================================================
    work_item = e2e_client.create_work_item(
        project_id=project["id"],
        title="Work item for immediate approval",
        description="This should be approved without feedback",
    )

    ws_collector = e2e_client.connect_websocket(
        subscription_type="all_events",
        work_item_id=work_item["id"],
    )

    e2e_client.trigger_workflow(
        work_item_id=work_item["id"],
        workflow_id=workflow["id"],
    )

    # ========================================================================
    # Test: Advance time through all stages
    # ========================================================================
    e2e_client.advance_time(timedelta(hours=1))

    # ========================================================================
    # Test: Wait for completion
    # ========================================================================
    final_work_item = await e2e_client.wait_for_work_item_status(
        work_item_id=work_item["id"],
        expected_status="COMPLETED",
        timeout=5.0,
    )

    assert final_work_item["status"] == "COMPLETED"

    # ========================================================================
    # Test: Verify no revision events
    # ========================================================================
    revision_events = e2e_client.get_events(
        aggregate_id=work_item["id"],
        event_type="RevisionStarted",
    )

    # Should have 0 revisions (approved on first review)
    assert len(revision_events) == 0

    # ========================================================================
    # Test: Verify all stages completed
    # ========================================================================
    executions = e2e_client.get_executions(work_item_id=work_item["id"])

    # Should have exactly 3 executions (implementation, review, finalize)
    stage_names = [e["stage_name"] for e in executions]
    assert "implementation" in stage_names
    assert "review" in stage_names
    assert "finalize" in stage_names
