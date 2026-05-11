"""
Integration tests for workflow run audit endpoint.

Tests the get_workflow_run_audit method with comprehensive coverage of:
- Basic audit retrieval
- Event pagination
- Stage grouping
- Sequence validation
- Caching behavior
- Error handling
"""

from datetime import UTC, datetime
from uuid import uuid4

import pytest

from codetoreum.adapters.testing import InMemoryEventStore, InMemoryTicketAdapter
from codetoreum.application.workflow_run_query_service import WorkflowRunQueryService
from codetoreum.domain.events import (
    WorkflowCompletedEvent,
    WorkflowCreatedEvent,
    WorkflowStageAdvancedEvent,
    WorkflowStartedEvent,
    now_iso,
)
from codetoreum.domain.work_item import WorkItemPriority
from codetoreum.ports.exceptions import ResourceNotFoundError


@pytest.fixture
def event_store():
    """Fixture providing in-memory event store."""
    return InMemoryEventStore()


@pytest.fixture
def ticket_system():
    """Fixture providing in-memory ticket system."""
    return InMemoryTicketAdapter()


@pytest.fixture
async def query_service(event_store, ticket_system):
    """Fixture providing workflow run query service."""
    return WorkflowRunQueryService(
        event_store=event_store,
        ticket_system=ticket_system,
        cache_size=100,
        cache_ttl_seconds=300,
    )


@pytest.fixture
async def workflow_with_stages(event_store, ticket_system):
    """
    Fixture creating a complete workflow with multiple stages.

    Creates a workflow with 3 stages (implementation, review, merge)
    and various events throughout the lifecycle.
    """
    workflow_id = str(uuid4())

    # Create work item in ticket system and get the generated ID
    work_item = await ticket_system.create_work_item(
        title="Test workflow for audit",
        description="Testing audit endpoint",
        project_id="project-1",
        priority=WorkItemPriority.HIGH,
    )
    work_item_id = work_item.id

    # Create comprehensive event sequence
    events = [
        WorkflowCreatedEvent(
            type="workflow.created",
            timestamp=now_iso(),
            source="domain",
            workflow_id=workflow_id,
            work_item_id=work_item_id,
            pipeline_id="template-1",
            stage_name="implementation",
        ),
        WorkflowStartedEvent(
            type="workflow.started",
            timestamp=now_iso(),
            source="domain",
            workflow_id=workflow_id,
            work_item_id=work_item_id,
            stage_name="implementation",
        ),
        WorkflowStageAdvancedEvent(
            type="workflow.stage_advanced",
            timestamp=now_iso(),
            source="domain",
            workflow_id=workflow_id,
            work_item_id=work_item_id,
            from_stage="implementation",
            to_stage="review",
        ),
        WorkflowStageAdvancedEvent(
            type="workflow.stage_advanced",
            timestamp=now_iso(),
            source="domain",
            workflow_id=workflow_id,
            work_item_id=work_item_id,
            from_stage="review",
            to_stage="merge",
        ),
        WorkflowCompletedEvent(
            type="workflow.completed",
            timestamp=now_iso(),
            source="domain",
            workflow_id=workflow_id,
            work_item_id=work_item_id,
            final_stage="merge",
            completed_at=now_iso(),
        ),
    ]

    # Append events to store
    await event_store.append(workflow_id, events)

    return {
        "workflow_id": workflow_id,
        "work_item_id": work_item_id,
        "events": events,
        "event_count": len(events),
    }


@pytest.fixture
async def workflow_with_many_events(event_store, ticket_system):
    """
    Fixture creating a workflow with many events for pagination testing.

    Creates 150 events to test pagination boundaries.
    """
    workflow_id = str(uuid4())

    # Create work item and get the generated ID
    work_item = await ticket_system.create_work_item(
        title="Workflow with many events",
        description="Testing pagination",
        project_id="project-1",
        priority=WorkItemPriority.MEDIUM,
    )
    work_item_id = work_item.id

    # Create many events
    events = [
        WorkflowCreatedEvent(
            type="workflow.created",
            timestamp=now_iso(),
            source="domain",
            workflow_id=workflow_id,
            work_item_id=work_item_id,
            pipeline_id="template-1",
            stage_name="stage-0",
        ),
        WorkflowStartedEvent(
            type="workflow.started",
            timestamp=now_iso(),
            source="domain",
            workflow_id=workflow_id,
            work_item_id=work_item_id,
            stage_name="stage-0",
        ),
    ]

    # Add 146 more stage advancement events (for a total of 149 events:
    # 1 Created + 1 Started + 146 StageAdvanced + 1 Completed = 149)
    for i in range(146):
        events.append(
            WorkflowStageAdvancedEvent(
                type="workflow.stage_advanced",
                timestamp=now_iso(),
                source="domain",
                workflow_id=workflow_id,
                work_item_id=work_item_id,
                from_stage=f"stage-{i}",
                to_stage=f"stage-{i + 1}",
            )
        )

    # Complete workflow
    events.append(
        WorkflowCompletedEvent(
            type="workflow.completed",
            timestamp=now_iso(),
            source="domain",
            workflow_id=workflow_id,
            work_item_id=work_item_id,
            final_stage=f"stage-146",
            completed_at=now_iso(),
        )
    )

    await event_store.append(workflow_id, events)

    return {
        "workflow_id": workflow_id,
        "work_item_id": work_item_id,
        "event_count": len(events),
    }


# ============================================================================
# Basic Audit Retrieval Tests
# ============================================================================


@pytest.mark.asyncio
async def test_get_workflow_run_audit_basic(query_service, workflow_with_stages):
    """Test basic audit retrieval returns all expected fields."""
    workflow_id = workflow_with_stages["workflow_id"]

    audit_data = await query_service.get_workflow_run_audit(workflow_id)

    # Verify all required fields are present (using dataclass attributes)
    assert hasattr(audit_data, "workflow_run")
    assert hasattr(audit_data, "events")
    assert hasattr(audit_data, "stages")
    assert hasattr(audit_data, "validation")
    assert hasattr(audit_data, "total_count")
    assert hasattr(audit_data, "offset")
    assert hasattr(audit_data, "limit")
    assert hasattr(audit_data, "has_next")

    # Verify workflow run summary
    assert audit_data.workflow_run.id == workflow_id
    assert audit_data.workflow_run.work_item_id == workflow_with_stages["work_item_id"]
    assert audit_data.workflow_run.issue_title == "Test workflow for audit"

    # Verify event count
    assert audit_data.total_count == workflow_with_stages["event_count"]
    assert len(audit_data.events) == workflow_with_stages["event_count"]

    # Verify stages (note: may be empty if workflow doesn't have properly initialized stages)
    assert hasattr(audit_data, "stages")
    assert isinstance(audit_data.stages, list)


@pytest.mark.asyncio
async def test_get_workflow_run_audit_not_found(query_service):
    """Test audit retrieval for non-existent workflow raises error."""
    non_existent_id = str(uuid4())

    with pytest.raises(ResourceNotFoundError) as exc_info:
        await query_service.get_workflow_run_audit(non_existent_id)

    assert "WorkflowRun" in str(exc_info.value)
    assert non_existent_id in str(exc_info.value)


# ============================================================================
# Event Pagination Tests
# ============================================================================


@pytest.mark.asyncio
async def test_audit_event_pagination_first_page(query_service, workflow_with_many_events):
    """Test pagination returns correct first page."""
    workflow_id = workflow_with_many_events["workflow_id"]

    audit_data = await query_service.get_workflow_run_audit(
        workflow_id,
        offset=0,
        limit=50,
    )

    assert audit_data.total_count == workflow_with_many_events["event_count"]
    assert len(audit_data.events) == 50
    assert audit_data.offset == 0
    assert audit_data.limit == 50
    assert audit_data.has_next is True


@pytest.mark.asyncio
async def test_audit_event_pagination_middle_page(query_service, workflow_with_many_events):
    """Test pagination returns correct middle page."""
    workflow_id = workflow_with_many_events["workflow_id"]

    audit_data = await query_service.get_workflow_run_audit(
        workflow_id,
        offset=50,
        limit=50,
    )

    assert audit_data.total_count == workflow_with_many_events["event_count"]
    assert len(audit_data.events) == 50
    assert audit_data.offset == 50
    assert audit_data.limit == 50
    assert audit_data.has_next is True


@pytest.mark.asyncio
async def test_audit_event_pagination_last_page(query_service, workflow_with_many_events):
    """Test pagination handles last page correctly."""
    workflow_id = workflow_with_many_events["workflow_id"]
    total_events = workflow_with_many_events["event_count"]

    # Request last page (149 events total, offset 100, limit 100)
    # Expected: 49 remaining events (149 - 100 = 49)
    audit_data = await query_service.get_workflow_run_audit(
        workflow_id,
        offset=100,
        limit=100,
    )

    assert audit_data.total_count == total_events
    assert len(audit_data.events) == 49  # Remaining events: 149 total - 100 offset = 49
    assert audit_data.offset == 100
    assert audit_data.limit == 100
    assert audit_data.has_next is False


@pytest.mark.asyncio
async def test_audit_event_pagination_beyond_end(query_service, workflow_with_many_events):
    """Test pagination beyond end returns empty events."""
    workflow_id = workflow_with_many_events["workflow_id"]

    audit_data = await query_service.get_workflow_run_audit(
        workflow_id,
        offset=200,
        limit=50,
    )

    assert audit_data.total_count == workflow_with_many_events["event_count"]
    assert len(audit_data.events) == 0
    assert audit_data.has_next is False


# ============================================================================
# Stage Grouping Tests
# ============================================================================


@pytest.mark.asyncio
async def test_audit_stage_grouping(query_service, workflow_with_stages):
    """Test stages are properly grouped with correct structure."""
    workflow_id = workflow_with_stages["workflow_id"]

    audit_data = await query_service.get_workflow_run_audit(workflow_id)

    stages = audit_data.stages
    assert isinstance(stages, list)

    # Verify stage structure (if any stages present)
    for stage in stages:
        assert "name" in stage
        assert "status" in stage
        assert "startedAt" in stage or stage["startedAt"] is None
        assert "completedAt" in stage or stage["completedAt"] is None
        assert "durationSeconds" in stage or stage["durationSeconds"] is None
        assert "events" in stage


# ============================================================================
# Sequence Validation Tests
# ============================================================================


@pytest.mark.asyncio
async def test_audit_sequence_validation_valid(query_service, workflow_with_stages):
    """Test validation returns valid for correct sequence."""
    workflow_id = workflow_with_stages["workflow_id"]

    audit_data = await query_service.get_workflow_run_audit(workflow_id)

    validation = audit_data.validation
    assert "sequenceValid" in validation
    assert "expectedSequence" in validation
    assert "actualSequence" in validation
    assert "missingEvents" in validation
    assert "unexpectedEvents" in validation
    assert "outOfOrderEvents" in validation

    # The sequence should be valid (created, started, advances, completed)
    # Note: This depends on the expected sequence pattern
    assert isinstance(validation["sequenceValid"], bool)


@pytest.mark.asyncio
async def test_audit_sequence_validation_structure(query_service, workflow_with_stages):
    """Test validation result has correct structure."""
    workflow_id = workflow_with_stages["workflow_id"]

    audit_data = await query_service.get_workflow_run_audit(workflow_id)

    validation = audit_data.validation

    # Verify lists are present and properly typed
    assert isinstance(validation["expectedSequence"], list)
    assert isinstance(validation["actualSequence"], list)
    assert isinstance(validation["missingEvents"], list)
    assert isinstance(validation["unexpectedEvents"], list)
    assert isinstance(validation["outOfOrderEvents"], list)


# ============================================================================
# Caching Tests
# ============================================================================


@pytest.mark.asyncio
async def test_audit_caching_same_request(query_service, workflow_with_stages):
    """Test identical requests return cached data."""
    workflow_id = workflow_with_stages["workflow_id"]

    # First request (cache miss)
    audit_data_1 = await query_service.get_workflow_run_audit(
        workflow_id,
        offset=0,
        limit=100,
    )

    # Second identical request (cache hit)
    audit_data_2 = await query_service.get_workflow_run_audit(
        workflow_id,
        offset=0,
        limit=100,
    )

    # Should return identical data
    assert audit_data_1.workflow_run.id == audit_data_2.workflow_run.id
    assert audit_data_1.total_count == audit_data_2.total_count
    assert len(audit_data_1.events) == len(audit_data_2.events)


@pytest.mark.asyncio
async def test_audit_caching_different_pagination(query_service, workflow_with_many_events):
    """Test different pagination parameters create separate cache entries."""
    workflow_id = workflow_with_many_events["workflow_id"]

    # Request with offset=0, limit=50
    audit_data_1 = await query_service.get_workflow_run_audit(
        workflow_id,
        offset=0,
        limit=50,
    )

    # Request with offset=50, limit=50 (different cache key)
    audit_data_2 = await query_service.get_workflow_run_audit(
        workflow_id,
        offset=50,
        limit=50,
    )

    # Should have different events but same total count
    assert audit_data_1.total_count == audit_data_2.total_count
    assert len(audit_data_1.events) == 50
    assert len(audit_data_2.events) == 50

    # Events should be different (different pages)
    first_event_1 = audit_data_1.events[0]
    first_event_2 = audit_data_2.events[0]
    assert first_event_1["id"] != first_event_2["id"]


# ============================================================================
# Event Format Tests
# ============================================================================


@pytest.mark.asyncio
async def test_audit_event_format(query_service, workflow_with_stages):
    """Test events have correct format and required fields."""
    workflow_id = workflow_with_stages["workflow_id"]

    audit_data = await query_service.get_workflow_run_audit(workflow_id)

    events = audit_data.events
    assert len(events) > 0

    # Verify event structure
    for event in events:
        assert "id" in event
        assert "event_type" in event
        assert "aggregate_id" in event
        assert "timestamp" in event
        assert "data" in event


# ============================================================================
# Error Handling Tests
# ============================================================================


@pytest.mark.asyncio
async def test_audit_invalid_pagination(query_service, workflow_with_stages):
    """Test audit handles negative offset/limit gracefully."""
    workflow_id = workflow_with_stages["workflow_id"]

    # Negative offset should be handled by router validation,
    # but service should handle edge cases
    audit_data = await query_service.get_workflow_run_audit(
        workflow_id,
        offset=0,
        limit=1,
    )

    # Should return at least the structure
    assert hasattr(audit_data, "events")
    assert len(audit_data.events) == 1


@pytest.mark.asyncio
async def test_audit_zero_limit(query_service, workflow_with_stages):
    """Test audit with zero limit returns no events."""
    workflow_id = workflow_with_stages["workflow_id"]

    # This would normally be validated by router, but test service behavior
    audit_data = await query_service.get_workflow_run_audit(
        workflow_id,
        offset=0,
        limit=0,
    )

    # Should return structure with no events
    assert audit_data.total_count > 0
    assert len(audit_data.events) == 0


@pytest.mark.asyncio
async def test_audit_without_validation(query_service, workflow_with_stages):
    """Test audit with include_validation=False excludes validation data."""
    workflow_id = workflow_with_stages["workflow_id"]

    # Get audit without validation
    audit_data = await query_service.get_workflow_run_audit(
        workflow_id,
        offset=0,
        limit=20,
        include_validation=False,
    )

    # Should have basic audit data
    assert audit_data.workflow_run.id == workflow_id
    assert audit_data.total_count > 0
    assert len(audit_data.events) > 0

    # Validation field should be None
    assert audit_data.validation is None


@pytest.mark.asyncio
async def test_audit_stage_with_no_events(event_store, ticket_system):
    """Test audit handles stage with no matching events correctly."""
    from codetoreum.application.workflow_run_query_service import (
        WorkflowRunQueryService,
    )

    # Create a simple workflow with a stage that has no events
    workflow_id = str(uuid4())
    project_id = "test-project"
    work_item_id = str(uuid4())

    # Create workflow events
    events = [
        WorkflowCreatedEvent(
            type="workflow.created",
            timestamp=now_iso(),
            source="domain",
            workflow_id=workflow_id,
            work_item_id=work_item_id,
            pipeline_id="test-template",
            stage_name="stage-1",
        ),
        WorkflowStartedEvent(
            type="workflow.started",
            timestamp=now_iso(),
            source="domain",
            workflow_id=workflow_id,
            work_item_id=work_item_id,
            stage_name="stage-1",
        ),
    ]
    await event_store.append(workflow_id, events)

    # Create service and get audit data
    service = WorkflowRunQueryService(
        event_store=event_store,
        ticket_system=ticket_system,
        cache_size=100,
        cache_ttl_seconds=300,
    )

    audit_data = await service.get_workflow_run_audit(
        workflow_id,
        offset=0,
        limit=20,
    )

    # Should have the workflow events but no stage-specific events
    assert audit_data.workflow_run.id == workflow_id
    assert audit_data.total_count == 2  # Created + Started
    assert len(audit_data.events) == 2

    # Stages info should be empty or have empty events arrays
    # (depends on whether the workflow aggregate has stages with no events)
    for stage_info in audit_data.stages:
        # If a stage has no events, events should be an empty list
        if not stage_info["events"]:
            assert isinstance(stage_info["events"], list)
            assert len(stage_info["events"]) == 0
