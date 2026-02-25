"""
Integration tests for WorkflowRunQueryService.

Tests the real WorkflowRunQueryService implementation with an in-memory event store,
validating event sourcing, filtering, pagination, and error handling.
"""

from datetime import datetime, timezone
from uuid import uuid4

import pytest

from codetoreum.adapters.testing import InMemoryEventStore, InMemoryTicketAdapter
from codetoreum.application.workflow_run_query_service import WorkflowRunQueryService
from codetoreum.domain.events import (
    WorkflowCompleted,
    WorkflowCreated,
    WorkflowFailed,
    WorkflowStageAdvanced,
    WorkflowStarted,
)
from codetoreum.domain.work_item import WorkItem, WorkItemPriority, WorkItemStatus
from codetoreum.ports.exceptions import ResourceNotFoundError
from codetoreum.ports.input.workflow_run_query import (
    SortOrder,
    WorkflowRunFilters,
    WorkflowRunPaginationParams,
    WorkflowRunSortField,
    WorkflowRunStatus,
)


@pytest.fixture
def event_store():
    """Fixture providing in-memory event store."""
    return InMemoryEventStore()


@pytest.fixture
def ticket_system():
    """Fixture providing in-memory ticket system with sample work items."""
    ticket_system = InMemoryTicketAdapter()
    return ticket_system


@pytest.fixture
async def query_service(event_store, ticket_system):
    """Fixture providing workflow run query service."""
    return WorkflowRunQueryService(
        event_store=event_store,
        ticket_system=ticket_system,
    )


@pytest.fixture
async def sample_workflow_events(event_store):
    """Fixture creating sample workflow events in event store."""
    workflow_id = str(uuid4())
    work_item_id = "work-item-1"

    # Create workflow events
    events = [
        WorkflowCreated(
            aggregate_id=workflow_id,
            payload={
                "work_item_id": work_item_id,
                "template_id": "template-1",
                "project_id": "project-1",
                "stage_count": 3,
            },
        ),
        WorkflowStarted(
            aggregate_id=workflow_id,
            payload={
                "started_at": datetime.now(timezone.utc).isoformat(),
                "work_item_id": work_item_id,
                "first_stage": "stage-1",
            },
        ),
        WorkflowCompleted(
            aggregate_id=workflow_id,
            payload={
                "completed_at": datetime.now(timezone.utc).isoformat(),
                "work_item_id": work_item_id,
                "duration_seconds": 120.5,
            },
        ),
    ]

    # Append events to store
    await event_store.append(workflow_id, events)

    return {
        "workflow_id": workflow_id,
        "work_item_id": work_item_id,
        "events": events,
    }


@pytest.fixture
async def multiple_workflows(event_store):
    """Fixture creating multiple workflow runs for pagination/filtering tests."""
    workflows = []

    for i in range(5):
        workflow_id = str(uuid4())
        work_item_id = f"work-item-{i}"
        project_id = "project-1" if i < 3 else "project-2"

        events = [
            WorkflowCreated(
                aggregate_id=workflow_id,
                payload={
                    "work_item_id": work_item_id,
                    "template_id": "template-1",
                    "project_id": project_id,
                    "stage_count": 2,
                },
            ),
            WorkflowStarted(
                aggregate_id=workflow_id,
                payload={
                    "started_at": datetime.now(timezone.utc).isoformat(),
                    "work_item_id": work_item_id,
                    "first_stage": "stage-1",
                },
            ),
        ]

        # Complete some workflows, fail others
        if i < 2:
            events.append(
                WorkflowCompleted(
                    aggregate_id=workflow_id,
                    payload={
                        "completed_at": datetime.now(timezone.utc).isoformat(),
                        "work_item_id": work_item_id,
                        "duration_seconds": 100.0 + i * 10,
                    },
                )
            )
        elif i == 2:
            events.append(
                WorkflowFailed(
                    aggregate_id=workflow_id,
                    payload={
                        "failed_at": datetime.now(timezone.utc).isoformat(),
                        "reason": "Agent execution failed",
                        "failed_stage": "stage-2",
                        "completed_stages": ["stage-1"],
                    },
                )
            )

        await event_store.append(workflow_id, events)
        workflows.append({
            "workflow_id": workflow_id,
            "work_item_id": work_item_id,
            "project_id": project_id,
            "status": WorkflowRunStatus.COMPLETED if i < 2 else (
                WorkflowRunStatus.FAILED if i == 2 else WorkflowRunStatus.RUNNING
            ),
        })

    return workflows


class TestGetWorkflowRun:
    """Tests for get_workflow_run method."""

    @pytest.mark.asyncio
    async def test_get_workflow_run_success(self, query_service, sample_workflow_events):
        """Test successful workflow run retrieval."""
        workflow_id = sample_workflow_events["workflow_id"]

        # Act
        result = await query_service.get_workflow_run(workflow_id)

        # Assert
        assert result.id == workflow_id
        assert result.work_item_id == sample_workflow_events["work_item_id"]
        assert result.workflow_id == "template-1"
        assert result.project_id == "project-1"
        assert result.status == WorkflowRunStatus.COMPLETED
        assert result.started_at is not None
        assert result.completed_at is not None
        assert result.duration is not None

    @pytest.mark.asyncio
    async def test_get_workflow_run_not_found(self, query_service):
        """Test workflow run not found error."""
        with pytest.raises(ResourceNotFoundError) as exc_info:
            await query_service.get_workflow_run("nonexistent-id")

        # Just check that the error mentions the ID
        assert "nonexistent-id" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_get_workflow_run_with_work_item_metadata(
        self, event_store, ticket_system, sample_workflow_events
    ):
        """Test workflow run enriched with work item metadata."""
        # Create work item in ticket system
        work_item = await ticket_system.create_work_item(
            title="Test Issue",
            description="Test description",
            project_id="project-1",
            priority=WorkItemPriority.HIGH,
        )
        # Store with the expected work_item_id
        work_item.id = sample_workflow_events["work_item_id"]
        work_item.external_id = "123"
        ticket_system._work_items[work_item.id] = work_item

        # Create query service with ticket system
        query_service = WorkflowRunQueryService(
            event_store=event_store,
            ticket_system=ticket_system,
        )

        # Act
        result = await query_service.get_workflow_run(
            sample_workflow_events["workflow_id"]
        )

        # Assert
        assert result.issue_title == "Test Issue"
        assert result.issue_number == 123
        assert result.project == "project-1"


class TestListWorkflowRuns:
    """Tests for list_workflow_runs method."""

    @pytest.mark.asyncio
    async def test_list_all_workflow_runs(self, query_service, multiple_workflows):
        """Test listing all workflow runs without filters."""
        # Act
        result = await query_service.list_workflow_runs()

        # Assert
        assert result.total_count == 5
        assert len(result.runs) == 5
        assert result.offset == 0
        assert result.limit == 20  # default
        assert result.has_next is False

    @pytest.mark.asyncio
    async def test_list_workflow_runs_with_pagination(self, query_service, multiple_workflows):
        """Test workflow run listing with pagination."""
        # Act - Page 1
        page1 = await query_service.list_workflow_runs(
            pagination=WorkflowRunPaginationParams(offset=0, limit=2)
        )

        # Act - Page 2
        page2 = await query_service.list_workflow_runs(
            pagination=WorkflowRunPaginationParams(offset=2, limit=2)
        )

        # Assert
        assert page1.total_count == 5
        assert len(page1.runs) == 2
        assert page1.has_next is True

        assert page2.total_count == 5
        assert len(page2.runs) == 2
        assert page2.has_next is True

        # Ensure different workflows in each page
        page1_ids = {run.id for run in page1.runs}
        page2_ids = {run.id for run in page2.runs}
        assert page1_ids.isdisjoint(page2_ids)

    @pytest.mark.asyncio
    async def test_list_workflow_runs_filter_by_status(self, query_service, multiple_workflows):
        """Test filtering workflow runs by status."""
        # Act - Filter completed workflows
        result = await query_service.list_workflow_runs(
            filters=WorkflowRunFilters(status=(WorkflowRunStatus.COMPLETED,))
        )

        # Assert
        assert result.total_count == 2
        assert all(run.status == WorkflowRunStatus.COMPLETED for run in result.runs)

    @pytest.mark.asyncio
    async def test_list_workflow_runs_filter_by_project(self, query_service, multiple_workflows):
        """Test filtering workflow runs by project."""
        # Act
        result = await query_service.list_workflow_runs(
            filters=WorkflowRunFilters(project_id="project-1")
        )

        # Assert
        assert result.total_count == 3
        assert all(run.project_id == "project-1" for run in result.runs)

    @pytest.mark.asyncio
    async def test_list_workflow_runs_filter_by_work_item(self, query_service, multiple_workflows):
        """Test filtering workflow runs by work item."""
        work_item_id = multiple_workflows[0]["work_item_id"]

        # Act
        result = await query_service.list_workflow_runs(
            filters=WorkflowRunFilters(work_item_id=work_item_id)
        )

        # Assert
        assert result.total_count == 1
        assert result.runs[0].work_item_id == work_item_id

    @pytest.mark.asyncio
    async def test_list_workflow_runs_sort_by_started_at_desc(
        self, query_service, multiple_workflows
    ):
        """Test sorting workflow runs by started_at descending (default)."""
        # Act
        result = await query_service.list_workflow_runs(
            pagination=WorkflowRunPaginationParams(
                sort_by=WorkflowRunSortField.STARTED_AT,
                sort_order=SortOrder.DESC,
            )
        )

        # Assert
        assert len(result.runs) == 5

        # Verify descending order (most recent first)
        for i in range(len(result.runs) - 1):
            if result.runs[i].started_at and result.runs[i + 1].started_at:
                assert result.runs[i].started_at >= result.runs[i + 1].started_at

    @pytest.mark.asyncio
    async def test_list_workflow_runs_sort_by_duration(
        self, query_service, multiple_workflows
    ):
        """Test sorting workflow runs by duration."""
        # Act
        result = await query_service.list_workflow_runs(
            filters=WorkflowRunFilters(status=(WorkflowRunStatus.COMPLETED,)),
            pagination=WorkflowRunPaginationParams(
                sort_by=WorkflowRunSortField.DURATION,
                sort_order=SortOrder.ASC,
            )
        )

        # Assert - completed workflows sorted by duration ascending
        assert len(result.runs) == 2
        if result.runs[0].duration and result.runs[1].duration:
            assert result.runs[0].duration <= result.runs[1].duration

    @pytest.mark.asyncio
    async def test_list_workflow_runs_empty_result(self, query_service, multiple_workflows):
        """Test listing with filters that match no workflows."""
        # Act
        result = await query_service.list_workflow_runs(
            filters=WorkflowRunFilters(project_id="nonexistent-project")
        )

        # Assert
        assert result.total_count == 0
        assert len(result.runs) == 0
        assert result.has_next is False


class TestGetWorkflowRunEvents:
    """Tests for get_workflow_run_events method."""

    @pytest.mark.asyncio
    async def test_get_workflow_run_events_success(self, query_service, sample_workflow_events):
        """Test successful event retrieval for workflow run."""
        workflow_id = sample_workflow_events["workflow_id"]

        # Act
        result = await query_service.get_workflow_run_events(workflow_id)

        # Assert
        assert hasattr(result, "events")
        assert hasattr(result, "total_count")
        assert result.total_count == 3  # Created, Started, Completed
        assert len(result.events) == 3
        assert result.has_next is False

    @pytest.mark.asyncio
    async def test_get_workflow_run_events_with_pagination(
        self, query_service, sample_workflow_events
    ):
        """Test event retrieval with pagination."""
        workflow_id = sample_workflow_events["workflow_id"]

        # Act
        result = await query_service.get_workflow_run_events(
            workflow_id, offset=0, limit=2
        )

        # Assert
        assert result.total_count == 3
        assert len(result.events) == 2
        assert result.has_next is True

    @pytest.mark.asyncio
    async def test_get_workflow_run_events_filter_by_type(
        self, query_service, sample_workflow_events
    ):
        """Test filtering events by event type."""
        workflow_id = sample_workflow_events["workflow_id"]

        # Act
        result = await query_service.get_workflow_run_events(
            workflow_id,
            event_types=["WorkflowStarted", "WorkflowCompleted"],
        )

        # Assert
        assert result.total_count == 2
        assert len(result.events) == 2
        event_types = [e["event_type"] for e in result.events]
        assert "WorkflowStarted" in event_types
        assert "WorkflowCompleted" in event_types

    @pytest.mark.asyncio
    async def test_get_workflow_run_events_not_found(self, query_service):
        """Test event retrieval for nonexistent workflow run."""
        with pytest.raises(ResourceNotFoundError) as exc_info:
            await query_service.get_workflow_run_events("nonexistent-id")

        assert "WorkflowRun" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_get_workflow_run_events_structure(
        self, query_service, sample_workflow_events
    ):
        """Test event data structure in response."""
        workflow_id = sample_workflow_events["workflow_id"]

        # Act
        result = await query_service.get_workflow_run_events(workflow_id, limit=1)

        # Assert
        event = result.events[0]
        assert "id" in event
        assert "event_type" in event
        assert "aggregate_id" in event
        assert "aggregate_type" in event
        assert "timestamp" in event
        assert "data" in event
        assert event["aggregate_id"] == workflow_id
        assert event["aggregate_type"] == "Workflow"


class TestCaching:
    """Tests for work item metadata caching."""

    @pytest.mark.asyncio
    async def test_work_item_metadata_cached(
        self, event_store, ticket_system, sample_workflow_events
    ):
        """Test that work item metadata is cached across queries."""
        # Create work item
        work_item = await ticket_system.create_work_item(
            title="Cached Issue",
            description="Test",
            project_id="project-1",
            priority=WorkItemPriority.MEDIUM,
        )
        # Store with the expected work_item_id
        work_item.id = sample_workflow_events["work_item_id"]
        work_item.external_id = "456"
        ticket_system._work_items[work_item.id] = work_item

        # Create query service
        query_service = WorkflowRunQueryService(
            event_store=event_store,
            ticket_system=ticket_system,
        )

        # First query
        result1 = await query_service.get_workflow_run(
            sample_workflow_events["workflow_id"]
        )

        # Second query (should use cache)
        result2 = await query_service.get_workflow_run(
            sample_workflow_events["workflow_id"]
        )

        # Assert metadata is the same (verifies caching behavior)
        assert result1.issue_title == result2.issue_title == "Cached Issue"
        assert result1.issue_number == result2.issue_number == 456

        # Verify cache size increased (indicates work item was cached)
        cache_size = await query_service._work_item_cache.size()
        assert cache_size > 0

    @pytest.mark.asyncio
    async def test_graceful_degradation_on_ticket_system_error(
        self, event_store, sample_workflow_events
    ):
        """Test that service works even if ticket system fails."""
        # Create query service without ticket system
        query_service = WorkflowRunQueryService(
            event_store=event_store,
            ticket_system=None,
        )

        # Act
        result = await query_service.get_workflow_run(
            sample_workflow_events["workflow_id"]
        )

        # Assert - metadata fields are None but query succeeds
        assert result.id == sample_workflow_events["workflow_id"]
        assert result.issue_title is None
        assert result.issue_number is None
        assert result.project == "project-1"  # from workflow, not work item


class TestStageOutputFields:
    """Tests for stage output fields in audit API."""

    @pytest.mark.asyncio
    async def test_stage_info_includes_output_fields(self, event_store):
        """Test that WorkflowRunStageInfo includes output, error_message, and metadata fields."""
        from codetoreum.ports.input.workflow_run_query import WorkflowRunStageInfo

        # Create a stage info with all fields
        stage = WorkflowRunStageInfo(
            name="implementation",
            agent_name="developer_agent",
            status="completed",
            started_at=datetime.now(timezone.utc),
            completed_at=datetime.now(timezone.utc),
            execution_id="exec-123",
            output="Implementation completed successfully",
            error_message=None,
            metadata={"iterations": 3, "files_changed": 5},
        )

        # Assert all fields are present
        assert stage.name == "implementation"
        assert stage.output == "Implementation completed successfully"
        assert stage.error_message is None
        assert stage.metadata == {"iterations": 3, "files_changed": 5}

    @pytest.mark.asyncio
    async def test_stage_info_with_error_message(self):
        """Test that stage info can contain error messages."""
        from codetoreum.ports.input.workflow_run_query import WorkflowRunStageInfo

        stage = WorkflowRunStageInfo(
            name="testing",
            agent_name="test_agent",
            status="failed",
            started_at=datetime.now(timezone.utc),
            completed_at=datetime.now(timezone.utc),
            execution_id="exec-456",
            output=None,
            error_message="Test suite failed with 3 errors",
            metadata={"failed_tests": 3},
        )

        assert stage.status == "failed"
        assert stage.output is None
        assert stage.error_message == "Test suite failed with 3 errors"
        assert stage.metadata["failed_tests"] == 3

    @pytest.mark.asyncio
    async def test_stage_dto_mapping_includes_output_fields(self):
        """Test that WorkflowRunStageResponse DTO includes output fields."""
        from codetoreum.adapters.primary.workflow_run_dtos import (
            WorkflowRunStageResponse,
        )

        response = WorkflowRunStageResponse(
            name="review",
            agentName="reviewer_agent",
            status="completed",
            startedAt=datetime.now(timezone.utc),
            completedAt=datetime.now(timezone.utc),
            executionId="exec-789",
            output="Code review passed",
            errorMessage=None,
            metadata={"approval_count": 2},
        )

        assert response.output == "Code review passed"
        assert response.errorMessage is None
        assert response.metadata == {"approval_count": 2}

    @pytest.mark.asyncio
    async def test_audit_stage_info_includes_output_fields(self):
        """Test that AuditStageInfo DTO includes output fields."""
        from codetoreum.adapters.primary.audit_dtos import AuditStageInfo

        stage_info = AuditStageInfo(
            name="deployment",
            status="completed",
            startedAt=datetime.now(timezone.utc),
            completedAt=datetime.now(timezone.utc),
            durationSeconds=45.5,
            events=[],
            output="Deployment successful",
            errorMessage=None,
            metadata={"environment": "production"},
        )

        assert stage_info.output == "Deployment successful"
        assert stage_info.errorMessage is None
        assert stage_info.metadata == {"environment": "production"}

    @pytest.mark.asyncio
    async def test_mapper_preserves_output_fields(self):
        """Test that WorkflowRunMapper preserves output fields during mapping."""
        from codetoreum.adapters.primary.workflow_run_mappers import WorkflowRunMapper
        from codetoreum.ports.input.workflow_run_query import WorkflowRunStageInfo

        stage = WorkflowRunStageInfo(
            name="build",
            agent_name="build_agent",
            status="completed",
            started_at=datetime.now(timezone.utc),
            completed_at=datetime.now(timezone.utc),
            execution_id="exec-build-1",
            output="Build artifacts created",
            error_message=None,
            metadata={"build_number": 42},
        )

        response = WorkflowRunMapper.to_stage_response(stage)

        assert response.output == "Build artifacts created"
        assert response.errorMessage is None
        assert response.metadata == {"build_number": 42}
