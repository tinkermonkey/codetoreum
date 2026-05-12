"""Unit tests for aggregate inference logic in event store and query service.

Tests coverage for:
- InMemoryEventStore._infer_aggregate_type() - all 6 branches
- WorkflowRunQueryService._event_to_dict() - all aggregate type branches
- Consistency verification between the two implementations
"""

from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import uuid4

import pytest

from codetoreum.adapters.testing import InMemoryEventStore
from codetoreum.application.workflow_run_query_service import WorkflowRunQueryService
from codetoreum.domain.events import CodetoreumEvent, now_iso
from codetoreum.ports.output.event_store import IEventStore
from codetoreum.ports.output.ticket_system import ITicketSystem


@dataclass(frozen=True)
class WorkflowTestEvent(CodetoreumEvent):
    """Test event with workflow_id."""

    workflow_id: str = ""


@dataclass(frozen=True)
class ExecutionTestEvent(CodetoreumEvent):
    """Test event with execution_id."""

    execution_id: str = ""


@dataclass(frozen=True)
class ReviewCycleTestEvent(CodetoreumEvent):
    """Test event with review_cycle_id."""

    review_cycle_id: str = ""


@dataclass(frozen=True)
class WorkItemTestEvent(CodetoreumEvent):
    """Test event with work_item_id only."""

    work_item_id: str = ""


@dataclass(frozen=True)
class RepairCycleTestEvent(CodetoreumEvent):
    """Test event with repair_cycle_id."""

    repair_cycle_id: str = ""


@dataclass(frozen=True)
class FallbackTestEvent(CodetoreumEvent):
    """Test event with no specific aggregate ID field (fallback case)."""

    pass


def create_event_with_id(event_class, aggregate_id: str, **kwargs):
    """Helper to create a test event with the appropriate aggregate ID."""
    id_field = None
    if event_class == WorkflowTestEvent:
        id_field = "workflow_id"
    elif event_class == ExecutionTestEvent:
        id_field = "execution_id"
    elif event_class == ReviewCycleTestEvent:
        id_field = "review_cycle_id"
    elif event_class == WorkItemTestEvent:
        id_field = "work_item_id"
    elif event_class == RepairCycleTestEvent:
        id_field = "repair_cycle_id"

    event_kwargs = {
        "type": f"test.{event_class.__name__.lower()}",
        "timestamp": now_iso(),
        "source": "test",
        "correlation_id": kwargs.get("correlation_id"),
    }

    if id_field:
        event_kwargs[id_field] = aggregate_id

    return event_class(**event_kwargs)


class TestInferAggregateType:
    """Tests for InMemoryEventStore._infer_aggregate_type() method."""

    def test_infer_workflow_id_branch(self):
        """Test inferring aggregate type from workflow_id field."""
        event = create_event_with_id(WorkflowTestEvent, "workflow-123")
        result = InMemoryEventStore._infer_aggregate_type(event)
        assert result == "Workflow"

    def test_infer_execution_id_branch(self):
        """Test inferring aggregate type from execution_id field."""
        event = create_event_with_id(ExecutionTestEvent, "execution-456")
        result = InMemoryEventStore._infer_aggregate_type(event)
        assert result == "AgentExecution"

    def test_infer_review_cycle_id_branch(self):
        """Test inferring aggregate type from review_cycle_id field."""
        event = create_event_with_id(ReviewCycleTestEvent, "review-789")
        result = InMemoryEventStore._infer_aggregate_type(event)
        assert result == "ReviewCycle"

    def test_infer_work_item_id_branch(self):
        """Test inferring aggregate type from work_item_id field."""
        event = create_event_with_id(WorkItemTestEvent, "work-item-111")
        result = InMemoryEventStore._infer_aggregate_type(event)
        assert result == "WorkItem"

    def test_infer_repair_cycle_id_branch(self):
        """Test inferring aggregate type from repair_cycle_id field."""
        event = create_event_with_id(RepairCycleTestEvent, "repair-222")
        result = InMemoryEventStore._infer_aggregate_type(event)
        assert result == "RepairCycle"

    def test_infer_fallback_from_class_name(self):
        """Test fallback: infer aggregate type from event class name."""
        event = create_event_with_id(FallbackTestEvent, "")
        result = InMemoryEventStore._infer_aggregate_type(event)
        # Class name is "FallbackTestEvent", remove "Event" -> "FallbackTest"
        assert result == "FallbackTest"

    def test_infer_priority_workflow_over_execution(self):
        """Test that workflow_id takes priority over execution_id."""

        @dataclass(frozen=True)
        class MultiIdEvent(CodetoreumEvent):
            workflow_id: str = ""
            execution_id: str = ""

        event = MultiIdEvent(
            type="test.multievent",
            timestamp=now_iso(),
            source="test",
            workflow_id="workflow-1",
            execution_id="execution-1",
        )
        result = InMemoryEventStore._infer_aggregate_type(event)
        assert result == "Workflow"

    def test_infer_priority_execution_over_review(self):
        """Test that execution_id takes priority over review_cycle_id."""

        @dataclass(frozen=True)
        class MultiIdEvent(CodetoreumEvent):
            execution_id: str = ""
            review_cycle_id: str = ""

        event = MultiIdEvent(
            type="test.multievent",
            timestamp=now_iso(),
            source="test",
            execution_id="execution-1",
            review_cycle_id="review-1",
        )
        result = InMemoryEventStore._infer_aggregate_type(event)
        assert result == "AgentExecution"

    def test_infer_priority_review_over_work_item(self):
        """Test that review_cycle_id takes priority over work_item_id."""

        @dataclass(frozen=True)
        class MultiIdEvent(CodetoreumEvent):
            review_cycle_id: str = ""
            work_item_id: str = ""

        event = MultiIdEvent(
            type="test.multievent",
            timestamp=now_iso(),
            source="test",
            review_cycle_id="review-1",
            work_item_id="work-item-1",
        )
        result = InMemoryEventStore._infer_aggregate_type(event)
        assert result == "ReviewCycle"

    def test_infer_priority_work_item_over_repair(self):
        """Test that work_item_id takes priority over repair_cycle_id."""

        @dataclass(frozen=True)
        class MultiIdEvent(CodetoreumEvent):
            work_item_id: str = ""
            repair_cycle_id: str = ""

        event = MultiIdEvent(
            type="test.multievent",
            timestamp=now_iso(),
            source="test",
            work_item_id="work-item-1",
            repair_cycle_id="repair-1",
        )
        result = InMemoryEventStore._infer_aggregate_type(event)
        assert result == "WorkItem"

    def test_empty_field_values_treated_as_missing(self):
        """Test that empty string field values are treated as missing."""

        @dataclass(frozen=True)
        class MultiIdEvent(CodetoreumEvent):
            workflow_id: str = ""
            work_item_id: str = ""

        event = MultiIdEvent(
            type="test.multievent",
            timestamp=now_iso(),
            source="test",
            workflow_id="",  # Empty string
            work_item_id="work-item-1",
        )
        result = InMemoryEventStore._infer_aggregate_type(event)
        # Empty workflow_id should be skipped, work_item_id should be used
        assert result == "WorkItem"

    def test_none_values_treated_as_missing(self):
        """Test that None field values are treated as missing."""

        @dataclass(frozen=True)
        class MultiIdEvent(CodetoreumEvent):
            execution_id: str | None = None
            work_item_id: str = ""

        event = MultiIdEvent(
            type="test.multievent",
            timestamp=now_iso(),
            source="test",
            execution_id=None,
            work_item_id="work-item-1",
        )
        result = InMemoryEventStore._infer_aggregate_type(event)
        assert result == "WorkItem"


class TestEventToDict:
    """Tests for WorkflowRunQueryService._event_to_dict() method.

    Also tests consistency with InMemoryEventStore._infer_aggregate_type()
    """

    @pytest.fixture
    def mock_ticket_system(self):
        """Create a mock ticket system."""

        class MockTicketSystem:
            async def get_board(self, project_id: str):
                pass

            async def search_work_items(self, query: str):
                pass

        return MockTicketSystem()

    @pytest.fixture
    def mock_event_store(self):
        """Create a mock event store."""

        class MockEventStore:
            async def get_events(self, stream_id: str, from_version: int = 0, to_version: int | None = None):
                return []

            async def get_events_since(self, since: datetime, stream_id: str | None = None):
                return []

            async def get_all_stream_ids(self, aggregate_type: str | None = None):
                return []

            async def get_events_by_type(
                self, event_type: str, since: datetime | None = None, limit: int = 1000
            ):
                return []

            async def get_events_by_correlation_id(self, correlation_id: str):
                return []

            async def query_streams_by_latest_event(
                self,
                aggregate_type: str,
                event_type_filters: list[str] | None = None,
                event_data_filters: dict | None = None,
                sort_by: str = "timestamp",
                sort_order: str = "desc",
                offset: int = 0,
                limit: int = 100,
            ):
                return [], 0

        return MockEventStore()

    @pytest.fixture
    def query_service(self, mock_event_store, mock_ticket_system):
        """Create a WorkflowRunQueryService instance."""
        return WorkflowRunQueryService(mock_event_store, mock_ticket_system)

    def test_event_to_dict_workflow_id_branch(self, query_service):
        """Test converting event with workflow_id to dict."""
        event = create_event_with_id(WorkflowTestEvent, "workflow-123")
        result = query_service._event_to_dict(event)

        assert result["aggregate_type"] == "Workflow"
        assert result["aggregate_id"] == "workflow-123"
        assert result["event_type"] == event.event_type

    def test_event_to_dict_execution_id_branch(self, query_service):
        """Test converting event with execution_id to dict."""
        event = create_event_with_id(ExecutionTestEvent, "execution-456")
        result = query_service._event_to_dict(event)

        assert result["aggregate_type"] == "AgentExecution"
        assert result["aggregate_id"] == "execution-456"

    def test_event_to_dict_review_cycle_id_branch(self, query_service):
        """Test converting event with review_cycle_id to dict."""
        event = create_event_with_id(ReviewCycleTestEvent, "review-789")
        result = query_service._event_to_dict(event)

        assert result["aggregate_type"] == "ReviewCycle"
        assert result["aggregate_id"] == "review-789"

    def test_event_to_dict_work_item_id_branch(self, query_service):
        """Test converting event with work_item_id to dict."""
        event = create_event_with_id(WorkItemTestEvent, "work-item-111")
        result = query_service._event_to_dict(event)

        assert result["aggregate_type"] == "WorkItem"
        assert result["aggregate_id"] == "work-item-111"

    def test_event_to_dict_repair_cycle_id_branch(self, query_service):
        """Test converting event with repair_cycle_id to dict."""
        event = create_event_with_id(RepairCycleTestEvent, "repair-222")
        result = query_service._event_to_dict(event)

        assert result["aggregate_type"] == "RepairCycle"
        assert result["aggregate_id"] == "repair-222"

    def test_event_to_dict_fallback_class_name(self, query_service):
        """Test converting event without specific ID field (fallback case)."""
        event = create_event_with_id(FallbackTestEvent, "")
        result = query_service._event_to_dict(event)

        # Fallback should infer from class name
        assert result["aggregate_type"] == "FallbackTest"
        # Fallback case should use event_id as aggregate_id
        assert result["aggregate_id"] == event.event_id

    def test_event_to_dict_contains_required_fields(self, query_service):
        """Test that converted dict contains all required fields."""
        event = create_event_with_id(WorkflowTestEvent, "workflow-123")
        result = query_service._event_to_dict(event)

        assert "id" in result
        assert "event_type" in result
        assert "aggregate_id" in result
        assert "aggregate_type" in result
        assert "timestamp" in result
        assert "data" in result
        assert "correlation_id" in result
        assert isinstance(result["data"], dict)

    def test_event_to_dict_excludes_internal_fields(self, query_service):
        """Test that internal fields are excluded from data dict."""
        event = create_event_with_id(WorkflowTestEvent, "workflow-123")
        result = query_service._event_to_dict(event)

        # These fields should not be in the data section
        assert "event_id" not in result["data"]
        assert "type" not in result["data"]
        assert "timestamp" not in result["data"]
        assert "source" not in result["data"]
        assert "correlation_id" not in result["data"]


class TestAggregateInferenceConsistency:
    """Tests for consistency between _infer_aggregate_type() and _event_to_dict()."""

    @pytest.fixture
    def mock_ticket_system(self):
        """Create a mock ticket system."""

        class MockTicketSystem:
            async def get_board(self, project_id: str):
                pass

        return MockTicketSystem()

    @pytest.fixture
    def mock_event_store(self):
        """Create a mock event store."""

        class MockEventStore:
            async def get_events(self, stream_id: str, from_version: int = 0, to_version: int | None = None):
                return []

            async def get_events_since(self, since: datetime, stream_id: str | None = None):
                return []

            async def get_all_stream_ids(self, aggregate_type: str | None = None):
                return []

            async def get_events_by_type(
                self, event_type: str, since: datetime | None = None, limit: int = 1000
            ):
                return []

            async def get_events_by_correlation_id(self, correlation_id: str):
                return []

            async def query_streams_by_latest_event(
                self,
                aggregate_type: str,
                event_type_filters: list[str] | None = None,
                event_data_filters: dict | None = None,
                sort_by: str = "timestamp",
                sort_order: str = "desc",
                offset: int = 0,
                limit: int = 100,
            ):
                return [], 0

        return MockEventStore()

    @pytest.fixture
    def query_service(self, mock_event_store, mock_ticket_system):
        """Create a WorkflowRunQueryService instance."""
        return WorkflowRunQueryService(mock_event_store, mock_ticket_system)

    def test_consistency_workflow_id(self, query_service):
        """Test that both methods agree on workflow_id inference."""
        event = create_event_with_id(WorkflowTestEvent, "workflow-123")

        inferred_type = InMemoryEventStore._infer_aggregate_type(event)
        event_dict = query_service._event_to_dict(event)

        assert inferred_type == event_dict["aggregate_type"]
        assert inferred_type == "Workflow"

    def test_consistency_execution_id(self, query_service):
        """Test that both methods agree on execution_id inference."""
        event = create_event_with_id(ExecutionTestEvent, "execution-456")

        inferred_type = InMemoryEventStore._infer_aggregate_type(event)
        event_dict = query_service._event_to_dict(event)

        assert inferred_type == event_dict["aggregate_type"]
        assert inferred_type == "AgentExecution"

    def test_consistency_review_cycle_id(self, query_service):
        """Test that both methods agree on review_cycle_id inference."""
        event = create_event_with_id(ReviewCycleTestEvent, "review-789")

        inferred_type = InMemoryEventStore._infer_aggregate_type(event)
        event_dict = query_service._event_to_dict(event)

        assert inferred_type == event_dict["aggregate_type"]
        assert inferred_type == "ReviewCycle"

    def test_consistency_work_item_id(self, query_service):
        """Test that both methods agree on work_item_id inference."""
        event = create_event_with_id(WorkItemTestEvent, "work-item-111")

        inferred_type = InMemoryEventStore._infer_aggregate_type(event)
        event_dict = query_service._event_to_dict(event)

        assert inferred_type == event_dict["aggregate_type"]
        assert inferred_type == "WorkItem"

    def test_consistency_repair_cycle_id(self, query_service):
        """Test that both methods agree on repair_cycle_id inference."""
        event = create_event_with_id(RepairCycleTestEvent, "repair-222")

        inferred_type = InMemoryEventStore._infer_aggregate_type(event)
        event_dict = query_service._event_to_dict(event)

        assert inferred_type == event_dict["aggregate_type"]
        assert inferred_type == "RepairCycle"

    def test_consistency_fallback_case(self, query_service):
        """Test that both methods agree on fallback inference."""
        event = create_event_with_id(FallbackTestEvent, "")

        inferred_type = InMemoryEventStore._infer_aggregate_type(event)
        event_dict = query_service._event_to_dict(event)

        assert inferred_type == event_dict["aggregate_type"]
        assert inferred_type == "FallbackTest"

    def test_consistency_with_priority_order(self, query_service):
        """Test that both methods use the same priority order."""

        @dataclass(frozen=True)
        class MultiIdEvent(CodetoreumEvent):
            workflow_id: str = ""
            execution_id: str = ""
            review_cycle_id: str = ""
            work_item_id: str = ""
            repair_cycle_id: str = ""

        # All fields set - should use workflow_id (highest priority)
        event = MultiIdEvent(
            type="test.multievent",
            timestamp=now_iso(),
            source="test",
            workflow_id="workflow-1",
            execution_id="execution-1",
            review_cycle_id="review-1",
            work_item_id="work-item-1",
            repair_cycle_id="repair-1",
        )

        inferred_type = InMemoryEventStore._infer_aggregate_type(event)
        event_dict = query_service._event_to_dict(event)

        assert inferred_type == "Workflow"
        assert event_dict["aggregate_type"] == "Workflow"
        assert inferred_type == event_dict["aggregate_type"]

    def test_consistency_aggregate_id_priority(self, query_service):
        """Test that aggregate_id follows same priority as aggregate_type."""

        @dataclass(frozen=True)
        class MultiIdEvent(CodetoreumEvent):
            workflow_id: str = ""
            work_item_id: str = ""

        event = MultiIdEvent(
            type="test.multievent",
            timestamp=now_iso(),
            source="test",
            workflow_id="workflow-123",
            work_item_id="work-item-456",
        )

        event_dict = query_service._event_to_dict(event)

        # When both fields present, workflow_id should win for both type and ID
        assert event_dict["aggregate_type"] == "Workflow"
        assert event_dict["aggregate_id"] == "workflow-123"
