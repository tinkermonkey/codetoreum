"""Integration tests for ReviewService."""

import pytest
from typing import List

from codetoreum.application.review_service import (
    ReviewService,
    ReviewCycleResult,
    ReviewCompletionResult,
)
from codetoreum.adapters.testing import InMemoryEventStore
from codetoreum.domain.agent import Agent, AgentCapability, AgentType
from codetoreum.domain.agent_execution import AgentExecution
from codetoreum.domain.events import DomainEvent
from codetoreum.domain.exceptions import DomainError
from codetoreum.domain.review_cycle import ReviewDecision, ReviewStatus
from codetoreum.ports.exceptions import EventStoreError


# Fixtures


@pytest.fixture
def event_store():
    """Create event store."""
    return InMemoryEventStore()


@pytest.fixture
def review_service(event_store):
    """Create ReviewService instance."""
    return ReviewService(event_store=event_store)


@pytest.fixture
def maker_agent():
    """Create maker agent."""
    return Agent.create(
        name="coder",
        display_name="Coder Agent",
        agent_type=AgentType.MAKER,
        role_description="Writes code",
        capabilities={
            "code_generation": AgentCapability(
                skill="code_generation",
                proficiency=0.9,
                description="Generates code",
            ),
            "code_editing": AgentCapability(
                skill="code_editing",
                proficiency=0.8,
                description="Edits existing code",
            ),
        },
        model="claude-3-5-sonnet-20250219",
    )


@pytest.fixture
def reviewer_agent():
    """Create reviewer agent."""
    return Agent.create(
        name="code_reviewer",
        display_name="Code Reviewer",
        agent_type=AgentType.REVIEWER,
        role_description="Reviews code",
        capabilities={
            "code_review": AgentCapability(
                skill="code_review",
                proficiency=0.9,
                description="Reviews code quality",
            ),
        },
        model="claude-3-5-sonnet-20250219",
    )


@pytest.fixture
def maker_execution(maker_agent):
    """Create maker execution."""
    return AgentExecution.create(
        agent_id=maker_agent.id,
        work_item_id="work-1",
        workflow_id="workflow-1",
        stage_name="coding",
        prompt="Write a function",
        model=maker_agent.model,
    )


@pytest.fixture
def reviewer_execution(reviewer_agent):
    """Create reviewer execution."""
    return AgentExecution.create(
        agent_id=reviewer_agent.id,
        work_item_id="work-1",
        workflow_id="workflow-1",
        stage_name="review",
        prompt="Review the code",
        model=reviewer_agent.model,
    )


# Tests


@pytest.mark.asyncio
async def test_create_review_cycle(
    review_service, maker_agent, reviewer_agent, event_store
):
    """Test creating a review cycle."""
    result = await review_service.create_review_cycle(
        workflow_id="workflow-1",
        stage_name="coding",
        maker_agent=maker_agent,
        reviewer_agent=reviewer_agent,
        max_iterations=3,
    )

    assert result.success
    assert result.review_cycle is not None
    assert result.review_cycle.workflow_id == "workflow-1"
    assert result.review_cycle.stage_name == "coding"
    assert result.review_cycle.maker_agent_id == maker_agent.id
    assert result.review_cycle.reviewer_agent_id == reviewer_agent.id
    assert result.review_cycle.max_iterations == 3
    assert result.review_cycle.status == ReviewStatus.PENDING
    assert result.review_cycle.current_iteration == 0

    # Verify events were persisted
    assert event_store.get_total_event_count() == 1
    assert event_store.get_all_events_list()[0].aggregate_type == "ReviewCycle"


@pytest.mark.asyncio
async def test_create_review_cycle_same_agent_fails(
    review_service, maker_agent
):
    """Test that creating review cycle with same maker and reviewer fails."""
    with pytest.raises(DomainError, match="Maker and reviewer must be different"):
        await review_service.create_review_cycle(
            workflow_id="workflow-1",
            stage_name="coding",
            maker_agent=maker_agent,
            reviewer_agent=maker_agent,  # Same agent!
            max_iterations=3,
        )


@pytest.mark.asyncio
async def test_start_iteration(
    review_service, maker_agent, reviewer_agent, maker_execution, event_store
):
    """Test starting a review iteration."""
    # Create review cycle
    create_result = await review_service.create_review_cycle(
        workflow_id="workflow-1",
        stage_name="coding",
        maker_agent=maker_agent,
        reviewer_agent=reviewer_agent,
    )

    review_cycle = create_result.review_cycle

    # Start iteration
    result = await review_service.start_iteration(
        review_cycle=review_cycle,
        maker_output="def hello(): return 'world'",
        maker_execution=maker_execution,
    )

    assert result.success
    assert review_cycle.current_iteration == 1
    assert review_cycle.status == ReviewStatus.IN_PROGRESS
    assert len(review_cycle.iterations) == 1

    iteration = review_cycle.iterations[0]
    assert iteration.iteration_number == 1
    assert iteration.maker_output == "def hello(): return 'world'"
    assert iteration.maker_execution_id == maker_execution.id
    assert iteration.reviewer_feedback is None

    # Verify events (1 create + 1 start iteration)
    assert event_store.get_total_event_count() == 2


@pytest.mark.asyncio
async def test_submit_review_approve(
    review_service,
    maker_agent,
    reviewer_agent,
    maker_execution,
    reviewer_execution,
    event_store,
):
    """Test submitting an approval review."""
    # Create and start iteration
    create_result = await review_service.create_review_cycle(
        workflow_id="workflow-1",
        stage_name="coding",
        maker_agent=maker_agent,
        reviewer_agent=reviewer_agent,
    )
    review_cycle = create_result.review_cycle

    await review_service.start_iteration(
        review_cycle=review_cycle,
        maker_output="def hello(): return 'world'",
        maker_execution=maker_execution,
    )

    # Submit approval
    result = await review_service.submit_review(
        review_cycle=review_cycle,
        decision=ReviewDecision.APPROVE,
        comment="Looks good!",
        reviewer_execution=reviewer_execution,
    )

    assert result.success
    assert review_cycle.status == ReviewStatus.APPROVED
    assert review_cycle.is_complete()
    assert review_cycle.final_decision == ReviewDecision.APPROVE

    # Check feedback
    feedback = review_cycle.get_latest_feedback()
    assert feedback is not None
    assert feedback.decision == ReviewDecision.APPROVE
    assert feedback.comment == "Looks good!"

    # Verify events (create + start + submit + approve)
    assert event_store.get_total_event_count() == 4


@pytest.mark.asyncio
async def test_submit_review_request_changes(
    review_service,
    maker_agent,
    reviewer_agent,
    maker_execution,
    reviewer_execution,
):
    """Test submitting a request for changes."""
    # Create and start iteration
    create_result = await review_service.create_review_cycle(
        workflow_id="workflow-1",
        stage_name="coding",
        maker_agent=maker_agent,
        reviewer_agent=reviewer_agent,
    )
    review_cycle = create_result.review_cycle

    await review_service.start_iteration(
        review_cycle=review_cycle,
        maker_output="def hello(): return 'world'",
        maker_execution=maker_execution,
    )

    # Submit request for changes
    result = await review_service.submit_review(
        review_cycle=review_cycle,
        decision=ReviewDecision.REQUEST_CHANGES,
        comment="Please add type hints",
        reviewer_execution=reviewer_execution,
        issues=["Missing type hints", "No docstring"],
        suggestions=["Add return type annotation"],
    )

    assert result.success
    assert review_cycle.status == ReviewStatus.CHANGES_REQUESTED
    assert not review_cycle.is_complete()
    assert review_cycle.needs_maker_revision()

    # Check feedback
    feedback = review_cycle.get_latest_feedback()
    assert feedback is not None
    assert feedback.decision == ReviewDecision.REQUEST_CHANGES
    assert len(feedback.issues) == 2
    assert len(feedback.suggestions) == 1


@pytest.mark.asyncio
async def test_multiple_iterations(
    review_service,
    maker_agent,
    reviewer_agent,
    maker_execution,
    reviewer_execution,
):
    """Test multiple review iterations."""
    # Create review cycle
    create_result = await review_service.create_review_cycle(
        workflow_id="workflow-1",
        stage_name="coding",
        maker_agent=maker_agent,
        reviewer_agent=reviewer_agent,
        max_iterations=3,
    )
    review_cycle = create_result.review_cycle

    # Iteration 1: Request changes
    await review_service.start_iteration(
        review_cycle=review_cycle,
        maker_output="def hello(): return 'world'",
        maker_execution=maker_execution,
    )

    await review_service.submit_review(
        review_cycle=review_cycle,
        decision=ReviewDecision.REQUEST_CHANGES,
        comment="Add type hints",
        reviewer_execution=reviewer_execution,
    )

    assert review_cycle.current_iteration == 1
    assert review_cycle.needs_maker_revision()

    # Iteration 2: Request changes again
    maker_execution_2 = AgentExecution.create(
        agent_id=maker_agent.id,
        work_item_id="work-1",
        workflow_id="workflow-1",
        stage_name="coding",
        prompt="Fix issues",
        model=maker_agent.model,
    )

    await review_service.start_iteration(
        review_cycle=review_cycle,
        maker_output="def hello() -> str: return 'world'",
        maker_execution=maker_execution_2,
    )

    reviewer_execution_2 = AgentExecution.create(
        agent_id=reviewer_agent.id,
        work_item_id="work-1",
        workflow_id="workflow-1",
        stage_name="review",
        prompt="Review again",
        model=reviewer_agent.model,
    )

    await review_service.submit_review(
        review_cycle=review_cycle,
        decision=ReviewDecision.APPROVE,
        comment="Good now!",
        reviewer_execution=reviewer_execution_2,
    )

    assert review_cycle.current_iteration == 2
    assert review_cycle.is_complete()
    assert review_cycle.status == ReviewStatus.APPROVED
    assert len(review_cycle.iterations) == 2


@pytest.mark.asyncio
async def test_max_iterations_escalation(
    review_service,
    maker_agent,
    reviewer_agent,
    maker_execution,
    reviewer_execution,
):
    """Test escalation when max iterations reached."""
    # Create review cycle with max 2 iterations
    create_result = await review_service.create_review_cycle(
        workflow_id="workflow-1",
        stage_name="coding",
        maker_agent=maker_agent,
        reviewer_agent=reviewer_agent,
        max_iterations=2,
    )
    review_cycle = create_result.review_cycle

    # Iteration 1: Request changes
    await review_service.start_iteration(
        review_cycle=review_cycle,
        maker_output="def hello(): return 'world'",
        maker_execution=maker_execution,
    )

    await review_service.submit_review(
        review_cycle=review_cycle,
        decision=ReviewDecision.REQUEST_CHANGES,
        comment="Issues found",
        reviewer_execution=reviewer_execution,
    )

    # Iteration 2: Request changes again (max reached)
    maker_execution_2 = AgentExecution.create(
        agent_id=maker_agent.id,
        work_item_id="work-1",
        workflow_id="workflow-1",
        stage_name="coding",
        prompt="Fix issues",
        model=maker_agent.model,
    )

    await review_service.start_iteration(
        review_cycle=review_cycle,
        maker_output="def hello() -> str: return 'world'",
        maker_execution=maker_execution_2,
    )

    reviewer_execution_2 = AgentExecution.create(
        agent_id=reviewer_agent.id,
        work_item_id="work-1",
        workflow_id="workflow-1",
        stage_name="review",
        prompt="Review again",
        model=reviewer_agent.model,
    )

    await review_service.submit_review(
        review_cycle=review_cycle,
        decision=ReviewDecision.REQUEST_CHANGES,
        comment="Still issues",
        reviewer_execution=reviewer_execution_2,
    )

    # Should auto-escalate
    assert review_cycle.status == ReviewStatus.ESCALATED
    assert review_cycle.is_complete()
    assert review_cycle.escalation_reason == "Max iterations reached"


@pytest.mark.asyncio
async def test_should_escalate(review_service, maker_agent, reviewer_agent):
    """Test should_escalate logic."""
    # Create review cycle
    create_result = await review_service.create_review_cycle(
        workflow_id="workflow-1",
        stage_name="coding",
        maker_agent=maker_agent,
        reviewer_agent=reviewer_agent,
        max_iterations=2,
    )
    review_cycle = create_result.review_cycle

    # Should not escalate initially
    should_escalate = await review_service.should_escalate(review_cycle)
    assert not should_escalate

    # Mark as escalated
    review_cycle.escalate("Test escalation")

    # Should escalate now
    should_escalate = await review_service.should_escalate(review_cycle)
    assert should_escalate


@pytest.mark.asyncio
async def test_complete_cycle_approved(
    review_service,
    maker_agent,
    reviewer_agent,
    maker_execution,
    reviewer_execution,
):
    """Test completing a cycle with approval."""
    # Create and approve cycle
    create_result = await review_service.create_review_cycle(
        workflow_id="workflow-1",
        stage_name="coding",
        maker_agent=maker_agent,
        reviewer_agent=reviewer_agent,
    )
    review_cycle = create_result.review_cycle

    await review_service.start_iteration(
        review_cycle=review_cycle,
        maker_output="def hello(): return 'world'",
        maker_execution=maker_execution,
    )

    await review_service.submit_review(
        review_cycle=review_cycle,
        decision=ReviewDecision.APPROVE,
        comment="LGTM",
        reviewer_execution=reviewer_execution,
    )

    # Complete cycle
    result = await review_service.complete_cycle(
        review_cycle=review_cycle, approved=True
    )

    assert result.success
    assert result.approved
    assert not result.escalated
    assert review_cycle.is_complete()


@pytest.mark.asyncio
async def test_get_review_status(
    review_service,
    maker_agent,
    reviewer_agent,
    maker_execution,
    reviewer_execution,
):
    """Test getting review status."""
    # Create and start review
    create_result = await review_service.create_review_cycle(
        workflow_id="workflow-1",
        stage_name="coding",
        maker_agent=maker_agent,
        reviewer_agent=reviewer_agent,
    )
    review_cycle = create_result.review_cycle

    await review_service.start_iteration(
        review_cycle=review_cycle,
        maker_output="def hello(): return 'world'",
        maker_execution=maker_execution,
    )

    await review_service.submit_review(
        review_cycle=review_cycle,
        decision=ReviewDecision.REQUEST_CHANGES,
        comment="Needs work",
        reviewer_execution=reviewer_execution,
        issues=["Issue 1", "Issue 2"],
    )

    # Get status
    status = review_service.get_review_status(review_cycle)

    assert status["id"] == review_cycle.id
    assert status["status"] == ReviewStatus.CHANGES_REQUESTED.value
    assert status["current_iteration"] == 1
    assert status["max_iterations"] == 3
    assert not status["is_complete"]
    assert status["needs_revision"]
    assert status["latest_feedback"] is not None
    assert status["latest_feedback"]["issues_count"] == 2


# Error Handling Tests


class FailingEventStore(InMemoryEventStore):
    """Event store that fails on append after a specified number of calls."""

    def __init__(self, fail_on_call: int = 1):
        """
        Initialize failing event store.

        Args:
            fail_on_call: Which call number to fail on (1-indexed)
        """
        super().__init__()
        self.call_count = 0
        self.fail_on_call = fail_on_call

    async def append(
        self, stream_id: str, events: List[DomainEvent], expected_version=None
    ) -> None:
        """Append event to store, failing on specified call."""
        self.call_count += 1
        if self.call_count == self.fail_on_call:
            raise EventStoreError("Event store connection failed")
        await super().append(stream_id, events, expected_version)


@pytest.mark.asyncio
async def test_create_review_cycle_event_store_error(maker_agent, reviewer_agent):
    """Test error handling when event store fails during creation."""
    failing_store = FailingEventStore(fail_on_call=1)
    review_service = ReviewService(event_store=failing_store)

    from codetoreum.ports.exceptions import EventStoreError

    with pytest.raises(EventStoreError, match="Event store connection failed"):
        await review_service.create_review_cycle(
            workflow_id="workflow-1",
            stage_name="coding",
            maker_agent=maker_agent,
            reviewer_agent=reviewer_agent,
            max_iterations=3,
        )

    # Verify no events were persisted
    assert failing_store.get_total_event_count() == 0


@pytest.mark.asyncio
async def test_start_iteration_event_store_error(
    maker_agent, reviewer_agent, maker_execution
):
    """Test error handling when event store fails during iteration start."""
    # Create with working store
    working_store = InMemoryEventStore()
    review_service_1 = ReviewService(event_store=working_store)

    result = await review_service_1.create_review_cycle(
        workflow_id="workflow-1",
        stage_name="coding",
        maker_agent=maker_agent,
        reviewer_agent=reviewer_agent,
    )
    review_cycle = result.review_cycle

    # Now fail on start_iteration
    failing_store = FailingEventStore(fail_on_call=1)
    review_service_2 = ReviewService(event_store=failing_store)

    from codetoreum.ports.exceptions import EventStoreError

    with pytest.raises(EventStoreError, match="Event store connection failed"):
        await review_service_2.start_iteration(
            review_cycle=review_cycle,
            maker_output="def hello(): return 'world'",
            maker_execution=maker_execution,
        )

    # Verify no events were persisted
    assert failing_store.get_total_event_count() == 0


@pytest.mark.asyncio
async def test_submit_review_event_store_error(
    maker_agent, reviewer_agent, maker_execution, reviewer_execution
):
    """Test error handling when event store fails during review submission."""
    # Create and start with working store
    working_store = InMemoryEventStore()
    review_service_1 = ReviewService(event_store=working_store)

    result = await review_service_1.create_review_cycle(
        workflow_id="workflow-1",
        stage_name="coding",
        maker_agent=maker_agent,
        reviewer_agent=reviewer_agent,
    )
    review_cycle = result.review_cycle

    await review_service_1.start_iteration(
        review_cycle=review_cycle,
        maker_output="def hello(): return 'world'",
        maker_execution=maker_execution,
    )

    # Now fail on submit_review
    failing_store = FailingEventStore(fail_on_call=1)
    review_service_2 = ReviewService(event_store=failing_store)

    from codetoreum.ports.exceptions import EventStoreError

    with pytest.raises(EventStoreError, match="Event store connection failed"):
        await review_service_2.submit_review(
            review_cycle=review_cycle,
            decision=ReviewDecision.APPROVE,
            comment="Looks good!",
            reviewer_execution=reviewer_execution,
        )

    # Verify no events were persisted
    assert failing_store.get_total_event_count() == 0


@pytest.mark.asyncio
async def test_complete_cycle_event_store_error(
    maker_agent, reviewer_agent, maker_execution, reviewer_execution
):
    """Test error handling when event store fails during cycle completion."""
    # Create review cycle
    working_store = InMemoryEventStore()
    review_service_1 = ReviewService(event_store=working_store)

    result = await review_service_1.create_review_cycle(
        workflow_id="workflow-1",
        stage_name="coding",
        maker_agent=maker_agent,
        reviewer_agent=reviewer_agent,
        max_iterations=3,
    )
    review_cycle = result.review_cycle

    # Start iteration and get it approved
    await review_service_1.start_iteration(
        review_cycle=review_cycle,
        maker_output="def hello(): return 'world'",
        maker_execution=maker_execution,
    )

    await review_service_1.submit_review(
        review_cycle=review_cycle,
        decision=ReviewDecision.APPROVE,
        comment="Looks good!",
        reviewer_execution=reviewer_execution,
    )

    # Manually reset status to test complete_cycle error handling
    # (In real scenario, this wouldn't happen, but we need to test the error path)
    review_cycle.status = ReviewStatus.IN_PROGRESS
    review_cycle.completed_at = None

    # Now try to complete with failing store
    failing_store = FailingEventStore(fail_on_call=1)
    review_service_2 = ReviewService(event_store=failing_store)

    from codetoreum.ports.exceptions import EventStoreError

    with pytest.raises(EventStoreError, match="Event store connection failed"):
        await review_service_2.complete_cycle(review_cycle=review_cycle, approved=True)

    # Verify no events were persisted
    assert failing_store.get_total_event_count() == 0


@pytest.mark.asyncio
async def test_escalate_on_first_iteration(
    review_service, maker_agent, reviewer_agent, maker_execution, reviewer_execution
):
    """Test that explicit escalation works on first iteration."""
    # Create review cycle
    create_result = await review_service.create_review_cycle(
        workflow_id="workflow-1",
        stage_name="coding",
        maker_agent=maker_agent,
        reviewer_agent=reviewer_agent,
        max_iterations=3,
    )
    review_cycle = create_result.review_cycle

    # Start first iteration
    await review_service.start_iteration(
        review_cycle=review_cycle,
        maker_output="def hello(): return 'world'",
        maker_execution=maker_execution,
    )

    # Submit explicit escalation on first iteration
    await review_service.submit_review(
        review_cycle=review_cycle,
        decision=ReviewDecision.ESCALATE,
        comment="This is too complex for me to review properly",
        reviewer_execution=reviewer_execution,
    )

    # Should detect escalation even on first iteration
    should_escalate = await review_service.should_escalate(review_cycle)
    assert should_escalate

    # Complete cycle should escalate
    result = await review_service.complete_cycle(review_cycle=review_cycle, approved=False)
    assert result.escalated
    assert review_cycle.status == ReviewStatus.ESCALATED


@pytest.mark.asyncio
async def test_multiple_file_types_in_feedback():
    """Test FeedbackProcessor with multiple file types."""
    from codetoreum.application.feedback_processor import FeedbackProcessor

    processor = FeedbackProcessor()

    review_output = """
## Issues

1. [Type Error]: Missing type annotation in user_service.ts:45
2. [Security Issue]: SQL injection vulnerability in database.go:123
3. [Memory Leak]: Unfreed pointer in parser.cpp:89
4. [Syntax Error]: Invalid syntax in Main.java:234
"""

    result = await processor.parse_review_output(review_output)

    assert result.success
    assert len(result.parsed_feedback.issues) == 4

    # Check each file type was parsed
    file_paths = [issue.file_path for issue in result.parsed_feedback.issues]
    assert "user_service.ts" in file_paths
    assert "database.go" in file_paths
    assert "parser.cpp" in file_paths
    assert "Main.java" in file_paths

    # Check line numbers
    line_numbers = [issue.line_number for issue in result.parsed_feedback.issues]
    assert 45 in line_numbers
    assert 123 in line_numbers
    assert 89 in line_numbers
    assert 234 in line_numbers


@pytest.mark.asyncio
async def test_custom_severity_keywords():
    """Test FeedbackProcessor with custom severity keywords."""
    from codetoreum.application.feedback_processor import FeedbackProcessor, Severity

    # Custom severity keywords for a specific domain
    custom_keywords = {
        Severity.CRITICAL: ["showstopper", "catastrophic"],
        Severity.HIGH: ["major", "significant"],
        Severity.MEDIUM: ["moderate", "noticeable"],
        Severity.LOW: ["trivial", "cosmetic"],
        Severity.INFO: ["note", "observation"],
    }

    processor = FeedbackProcessor(severity_keywords=custom_keywords)

    review_output = """
## Issues

1. [Database Error]: Showstopper bug in connection pool
2. [UI Bug]: Cosmetic issue with button alignment
"""

    result = await processor.parse_review_output(review_output)

    assert result.success
    assert len(result.parsed_feedback.issues) == 2

    # Check custom severity detection
    severities = [issue.severity for issue in result.parsed_feedback.issues]
    assert Severity.CRITICAL in severities  # "showstopper"
    assert Severity.LOW in severities  # "cosmetic"
