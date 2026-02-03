"""In-memory review cycle adapter with deterministic review sequences for testing.

This module provides a mock implementation of IReviewCycle that simulates review
cycles without actual agent calls. It supports deterministic test results and
configurable review sequences for comprehensive simulation testing.

The mock adapter:
1. Tracks review cycle state (iterations, feedback, decisions)
2. Emits review cycle domain events
3. Provides test helper methods for simulating different review scenarios
4. Supports deterministic time manipulation via SimulationClock
5. Logs all events for assertion verification
6. Manages review cycle state persistence
"""

import logging
import threading
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

from codetoreum.domain.review_cycle import ReviewCycle, ReviewDecision, ReviewStatus
from codetoreum.domain.events.review_cycle_events import (
    ReviewCycleStartedEvent,
    ReviewCycleIterationCompletedEvent,
    ReviewCycleMakerRevisionEvent,
    ReviewCycleEscalatedToHumanEvent,
    ReviewCycleHumanFeedbackReceivedEvent,
    ReviewCycleMaxIterationsReachedEvent,
    ReviewCycleApprovedEvent,
)
from codetoreum.ports.output.review_cycle_service import (
    IReviewCycle,
    ReviewCycleRequest,
    ReviewCycleResult,
    ReviewCycleState,
    ReviewFinding,
    ReviewResult,
    ReviewStatus as ReviewStatusLiteral,
    IterationOutput,
)
from codetoreum.ports.output.monitoring import MonitoringConfig, MonitoringStatus
from codetoreum.infrastructure.simulation.simulation_clock import SimulationClock
from codetoreum.adapters.secondary.mock_event_emitter import MockEventEmitter
from codetoreum.infrastructure.error_ids import ErrorRegistry


logger = logging.getLogger(__name__)


@dataclass
class ReviewSequenceItem:
    """A single item in a review sequence.

    Attributes:
        decision: Reviewer's decision (APPROVE, REQUEST_CHANGES, ESCALATE)
        findings: Optional list of findings from the review
        summary: Optional summary of the review
    """
    decision: ReviewDecision
    findings: List[ReviewFinding] = field(default_factory=list)
    summary: Optional[str] = None

    def to_review_result(self) -> ReviewResult:
        """Convert sequence item to ReviewResult."""
        blocking_count = sum(
            1 for f in self.findings if f.severity == "blocking"
        )

        # Map ReviewDecision to ReviewStatus (literal)
        status_map = {
            ReviewDecision.APPROVE: "APPROVED",
            ReviewDecision.REQUEST_CHANGES: "CHANGES_REQUESTED",
            ReviewDecision.ESCALATE: "BLOCKED",
        }

        return ReviewResult(
            status=status_map[self.decision],
            findings=self.findings,
            blocking_count=blocking_count,
            summary=self.summary,
        )


class MockReviewCycleAdapter(MockEventEmitter, IReviewCycle):
    """Deterministic mock adapter for review cycle simulation testing.

    Provides:
    - Configurable review decision sequences per work item
    - Shorthand configuration methods for common scenarios
    - SimulationClock integration for deterministic time
    - Event logging with simulated timestamps
    - Event log retrieval methods
    - Assertion helpers for test verification
    - State persistence for cycle recovery

    Example:
        # Setup with clock
        clock = SimulationClock()
        adapter = MockReviewCycleAdapter(clock)
        adapter.current_project = "proj-1"

        # Configure via sequence
        adapter.set_review_sequence(
            "item-1",
            [
                ReviewSequenceItem(ReviewDecision.REQUEST_CHANGES),
                ReviewSequenceItem(ReviewDecision.REQUEST_CHANGES),
                ReviewSequenceItem(ReviewDecision.APPROVE),
            ]
        )

        # Or use shorthand
        adapter.set_approve_immediately("item-2")
        adapter.set_always_escalate("item-3")

        # Execute and verify
        result = await adapter.start_review_cycle(request)
        adapter.assert_iteration_count("item-1", 3)
        adapter.assert_final_status("item-1", "APPROVED")
    """

    def __init__(self, clock: Optional[SimulationClock] = None) -> None:
        """Initialize the review cycle adapter with SimulationClock.

        Args:
            clock: SimulationClock instance for deterministic time advancement
        """
        super().__init__()
        self.clock = clock or SimulationClock()
        self._clock = self.clock  # Alias for internal use
        self._current_project: Optional[str] = None

        # Review state tracking
        self._review_cycles: Dict[str, ReviewCycle] = {}
        self._cycle_states: Dict[str, ReviewCycleState] = {}
        self._review_sequences: Dict[str, List[ReviewSequenceItem]] = {}
        self._sequence_indices: Dict[str, int] = {}
        self._human_feedback_queue: Dict[str, List[str]] = {}

        # Event system
        self._events: List[Dict[str, Any]] = []
        self._event_handlers: Dict[str, List] = {}
        self._monitoring: Dict[str, MonitoringStatus] = {}
        self._handler_errors: List[Dict[str, Any]] = []
        self._lock = threading.RLock()

    # Configuration methods

    def set_review_sequence(
        self,
        work_item_id: str,
        sequence: List[ReviewSequenceItem]
    ) -> None:
        """Configure exact review sequence for a work item.

        Args:
            work_item_id: Work item ID to configure
            sequence: List of review decisions in sequence order
        """
        if not sequence:
            raise ValueError("Review sequence cannot be empty")
        self._review_sequences[work_item_id] = sequence
        self._sequence_indices[work_item_id] = 0

    def set_approve_immediately(self, work_item_id: str) -> None:
        """Configure work item to be approved on first iteration.

        Args:
            work_item_id: Work item ID to configure
        """
        self.set_review_sequence(
            work_item_id,
            [ReviewSequenceItem(
                decision=ReviewDecision.APPROVE,
                summary="Approved immediately"
            )]
        )

    def set_request_changes_then_approve(
        self,
        work_item_id: str,
        iterations: int = 2
    ) -> None:
        """Configure work item to request changes then approve.

        Args:
            work_item_id: Work item ID to configure
            iterations: Number of change requests before approval
        """
        sequence = [
            ReviewSequenceItem(
                decision=ReviewDecision.REQUEST_CHANGES,
                summary=f"Please fix iteration {i+1}"
            )
            for i in range(iterations - 1)
        ]
        sequence.append(ReviewSequenceItem(
            decision=ReviewDecision.APPROVE,
            summary="Looks good now"
        ))
        self.set_review_sequence(work_item_id, sequence)

    def set_always_escalate(self, work_item_id: str) -> None:
        """Configure work item to escalate on first iteration.

        Args:
            work_item_id: Work item ID to configure
        """
        self.set_review_sequence(
            work_item_id,
            [ReviewSequenceItem(
                decision=ReviewDecision.ESCALATE,
                summary="Escalating to human review",
                findings=[
                    ReviewFinding(
                        severity="blocking",
                        description="Requires human decision"
                    )
                ]
            )]
        )

    def set_max_iterations_escalation(
        self,
        work_item_id: str,
        max_iterations: int = 3
    ) -> None:
        """Configure work item to escalate after max iterations.

        Args:
            work_item_id: Work item ID to configure
            max_iterations: Number of iterations before escalation
        """
        sequence = [
            ReviewSequenceItem(
                decision=ReviewDecision.REQUEST_CHANGES,
                summary=f"Changes needed - iteration {i+1}/{max_iterations}"
            )
            for i in range(max_iterations)
        ]
        self.set_review_sequence(work_item_id, sequence)

    def queue_human_feedback(self, work_item_id: str, feedback: str) -> None:
        """Queue human feedback for escalation scenarios.

        Stores feedback that will be returned when the review cycle
        is resumed with human feedback. Multiple calls queue feedback
        in FIFO order.

        Args:
            work_item_id: Work item ID to queue feedback for
            feedback: Human feedback text to queue

        Raises:
            ValueError: If feedback is empty
        """
        if not feedback or not feedback.strip():
            raise ValueError("Feedback cannot be empty")
        if work_item_id not in self._human_feedback_queue:
            self._human_feedback_queue[work_item_id] = []
        self._human_feedback_queue[work_item_id].append(feedback)

    @property
    def current_project(self) -> Optional[str]:
        """Get current project ID."""
        return self._current_project

    @current_project.setter
    def current_project(self, project_id: Optional[str]) -> None:
        """Set current project ID for event emission."""
        self._current_project = project_id

    # Core Review Cycle Methods

    async def start_review_cycle(
        self,
        request: ReviewCycleRequest
    ) -> ReviewCycleResult:
        """Start a new review cycle.

        Initiates a maker-checker review loop for the specified work item.
        Uses configured review sequences to simulate reviewer decisions.

        Args:
            request: Review cycle request with configuration

        Returns:
            ReviewCycleResult with the outcome of the review cycle

        Raises:
            ValueError: If request validation fails
        """
        self._validate_request(request)

        work_item_id = request.work_item_id

        # Create ReviewCycle domain model
        cycle = ReviewCycle.create(
            workflow_id=request.board_id,  # Use board_id as workflow_id
            stage_name="review",
            maker_agent_id=request.maker_agent,
            reviewer_agent_id=request.reviewer_agent,
            max_iterations=request.max_iterations
        )

        with self._lock:
            self._review_cycles[work_item_id] = cycle
            self._sequence_indices[work_item_id] = 0

        # Emit cycle started event
        if self._current_project:
            self.emit(ReviewCycleStartedEvent(
                type="review_cycle.started",
                timestamp=self.clock.now().isoformat(),
                source="mock_review_cycle",
                review_cycle_id=cycle.id,
                work_item_id=work_item_id,
                project_id=request.project_id,
                maker_agent=request.maker_agent,
                reviewer_agent=request.reviewer_agent,
                max_iterations=request.max_iterations,
            ))
            self._log_event({
                "type": "REVIEW_CYCLE_STARTED",
                "review_cycle_id": cycle.id,
                "work_item_id": work_item_id,
                "maker_agent": request.maker_agent,
                "reviewer_agent": request.reviewer_agent,
            })

        # Run review iterations
        iteration = 0
        final_status = "APPROVED"
        human_escalation = False

        # Get or use default sequence
        sequence = self._review_sequences.get(work_item_id, None)
        if sequence is None:
            # Default to approve on first iteration
            sequence = [ReviewSequenceItem(
                decision=ReviewDecision.APPROVE,
                summary="Approved by mock reviewer"
            )]

        try:
            for iteration in range(1, request.max_iterations + 1):
                # Get next review decision
                idx = self._sequence_indices.get(work_item_id, 0)
                if idx >= len(sequence):
                    # Sequence exhausted, use last decision
                    decision_item = sequence[-1]
                else:
                    decision_item = sequence[idx]
                    with self._lock:
                        self._sequence_indices[work_item_id] = idx + 1

                # Advance clock for review execution (30 seconds)
                await self.clock.advance(timedelta(seconds=30))

                # Process the decision
                review_result = decision_item.to_review_result()

                if decision_item.decision == ReviewDecision.APPROVE:
                    cycle.start_iteration(
                        maker_output="Maker output iteration",
                        maker_execution_id=f"exec-maker-{iteration}"
                    )
                    cycle.submit_review(
                        decision=ReviewDecision.APPROVE,
                        comment=decision_item.summary or "Approved",
                        reviewer_execution_id=f"exec-reviewer-{iteration}"
                    )
                    final_status = "APPROVED"

                    if self._current_project:
                        self.emit(ReviewCycleIterationCompletedEvent(
                            type="review_cycle.iteration_completed",
                            timestamp=self.clock.now().isoformat(),
                            source="mock_review_cycle",
                            review_cycle_id=cycle.id,
                            work_item_id=work_item_id,
                            iteration=iteration,
                            status="APPROVED",
                            blocking_count=0,
                        ))
                        self.emit(ReviewCycleApprovedEvent(
                            type="review_cycle.approved",
                            timestamp=self.clock.now().isoformat(),
                            source="mock_review_cycle",
                            review_cycle_id=cycle.id,
                            work_item_id=work_item_id,
                            total_iterations=iteration,
                        ))

                    break

                elif decision_item.decision == ReviewDecision.REQUEST_CHANGES:
                    cycle.start_iteration(
                        maker_output="Maker output iteration",
                        maker_execution_id=f"exec-maker-{iteration}"
                    )
                    cycle.submit_review(
                        decision=ReviewDecision.REQUEST_CHANGES,
                        comment=decision_item.summary or "Changes requested",
                        reviewer_execution_id=f"exec-reviewer-{iteration}",
                        issues=[f.description for f in decision_item.findings]
                    )
                    final_status = "CHANGES_REQUESTED"

                    # Check if max iterations reached
                    if iteration >= request.max_iterations:
                        cycle.escalate("Max iterations reached")
                        final_status = "BLOCKED"
                        human_escalation = True

                        if self._current_project:
                            self.emit(ReviewCycleMaxIterationsReachedEvent(
                                type="review_cycle.max_iterations_reached",
                                timestamp=self.clock.now().isoformat(),
                                source="mock_review_cycle",
                                review_cycle_id=cycle.id,
                                work_item_id=work_item_id,
                                max_iterations=request.max_iterations,
                            ))
                            self.emit(ReviewCycleEscalatedToHumanEvent(
                                type="review_cycle.escalated_to_human",
                                timestamp=self.clock.now().isoformat(),
                                source="mock_review_cycle",
                                review_cycle_id=cycle.id,
                                work_item_id=work_item_id,
                                iteration=iteration,
                                blocking_count=0,
                                escalation_reason="MAX_ITERATIONS",
                            ))
                        break
                    else:
                        if self._current_project:
                            self.emit(ReviewCycleIterationCompletedEvent(
                                type="review_cycle.iteration_completed",
                                timestamp=self.clock.now().isoformat(),
                                source="mock_review_cycle",
                                review_cycle_id=cycle.id,
                                work_item_id=work_item_id,
                                iteration=iteration,
                                status="CHANGES_REQUESTED",
                                blocking_count=0,
                            ))
                            self.emit(ReviewCycleMakerRevisionEvent(
                                type="review_cycle.maker_revision",
                                timestamp=self.clock.now().isoformat(),
                                source="mock_review_cycle",
                                review_cycle_id=cycle.id,
                                work_item_id=work_item_id,
                                iteration=iteration,
                            ))

                        # Advance clock for maker revision (2 minutes)
                        await self.clock.advance(timedelta(seconds=120))

                elif decision_item.decision == ReviewDecision.ESCALATE:
                    cycle.start_iteration(
                        maker_output="Maker output iteration",
                        maker_execution_id=f"exec-maker-{iteration}"
                    )
                    cycle.submit_review(
                        decision=ReviewDecision.ESCALATE,
                        comment=decision_item.summary or "Escalating to human",
                        reviewer_execution_id=f"exec-reviewer-{iteration}",
                        issues=[f.description for f in decision_item.findings]
                    )
                    final_status = "BLOCKED"
                    human_escalation = True

                    if self._current_project:
                        blocking_count = sum(
                            1 for f in decision_item.findings if f.severity == "blocking"
                        )
                        self.emit(ReviewCycleIterationCompletedEvent(
                            type="review_cycle.iteration_completed",
                            timestamp=self.clock.now().isoformat(),
                            source="mock_review_cycle",
                            review_cycle_id=cycle.id,
                            work_item_id=work_item_id,
                            iteration=iteration,
                            status="BLOCKED",
                            blocking_count=blocking_count,
                        ))
                        self.emit(ReviewCycleEscalatedToHumanEvent(
                            type="review_cycle.escalated_to_human",
                            timestamp=self.clock.now().isoformat(),
                            source="mock_review_cycle",
                            review_cycle_id=cycle.id,
                            work_item_id=work_item_id,
                            iteration=iteration,
                            blocking_count=blocking_count,
                            escalation_reason="BLOCKED",
                        ))

                    # Check for queued human feedback
                    feedback_queue = self._human_feedback_queue.get(work_item_id, [])
                    if feedback_queue:
                        # Advance clock for human feedback wait (5 minutes)
                        await self.clock.advance(timedelta(seconds=300))
                        feedback = feedback_queue.pop(0)
                        if self._current_project:
                            self.emit(ReviewCycleHumanFeedbackReceivedEvent(
                                type="review_cycle.human_feedback_received",
                                timestamp=self.clock.now().isoformat(),
                                source="mock_review_cycle",
                                review_cycle_id=cycle.id,
                                work_item_id=work_item_id,
                                feedback=feedback,
                            ))
                            self._log_event({
                                "type": "REVIEW_CYCLE_HUMAN_FEEDBACK_RECEIVED",
                                "work_item_id": work_item_id,
                                "feedback": feedback,
                                "iteration": iteration,
                            })
                        # Continue loop to process next iteration with feedback incorporated
                        continue

                    break

        except Exception as e:
            logger.error(
                f"Error during review cycle execution: {e}",
                exc_info=True,
                extra={"error_id": ErrorRegistry.ERR_REPAIR_CYCLE_ERROR}
            )

        # Save cycle state
        cycle_state = ReviewCycleState(
            work_item_id=work_item_id,
            project_id=request.project_id,
            board_id=request.board_id,
            maker_agent=request.maker_agent,
            reviewer_agent=request.reviewer_agent,
            max_iterations=request.max_iterations,
            pipeline_run_id=request.pipeline_run_id,
            current_iteration=iteration,
            maker_outputs=[
                IterationOutput(
                    iteration=i,
                    output=f"Maker output iteration {i}",
                    timestamp=self.clock.now().isoformat()
                )
                for i in range(1, iteration + 1)
            ],
            review_outputs=[
                IterationOutput(
                    iteration=i,
                    output=f"Review iteration {i}",
                    timestamp=self.clock.now().isoformat()
                )
                for i in range(1, iteration + 1)
            ],
            status="completed",
            created_at=self.clock.now().isoformat(),
            updated_at=self.clock.now().isoformat(),
        )

        with self._lock:
            self._cycle_states[work_item_id] = cycle_state

        # Log completion
        if self._current_project:
            self._log_event({
                "type": "REVIEW_CYCLE_COMPLETED",
                "work_item_id": work_item_id,
                "final_status": final_status,
                "total_iterations": iteration,
                "human_escalation": human_escalation,
            })

        return ReviewCycleResult(
            next_column="Testing" if final_status == "APPROVED" else request.board_id,
            cycle_complete=True,
            final_status=final_status,
            total_iterations=iteration,
            human_escalation_occurred=human_escalation
        )

    async def resume_review_cycle(
        self,
        work_item_id: str,
        project_id: str
    ) -> None:
        """Resume an interrupted review cycle.

        Args:
            work_item_id: Work item ID for the cycle to resume
            project_id: Project ID containing the work item
        """
        logger.info(f"Resuming review cycle for work item {work_item_id}")
        # For mock, this is a no-op as we don't interrupt cycles

    async def resume_with_human_feedback(
        self,
        cycle_state: ReviewCycleState,
        feedback: str
    ) -> None:
        """Resume a blocked cycle with human feedback.

        Args:
            cycle_state: Current state of the paused review cycle
            feedback: Human feedback to incorporate
        """
        # Advance clock for human feedback wait (5 minutes)
        await self.clock.advance(timedelta(seconds=300))

        if self._current_project:
            # Generate a cycle ID for the event (use work_item_id as base for consistency)
            cycle_id = f"cycle-{cycle_state.work_item_id}"
            self.emit(ReviewCycleHumanFeedbackReceivedEvent(
                type="review_cycle.human_feedback_received",
                timestamp=self.clock.now().isoformat(),
                source="mock_review_cycle",
                review_cycle_id=cycle_id,
                work_item_id=cycle_state.work_item_id,
                feedback=feedback,
            ))
            self._log_event({
                "type": "REVIEW_CYCLE_HUMAN_FEEDBACK_RECEIVED",
                "work_item_id": cycle_state.work_item_id,
                "feedback": feedback,
            })

    async def get_cycle_state(
        self,
        work_item_id: str
    ) -> Optional[ReviewCycleState]:
        """Retrieve current state of a review cycle.

        Args:
            work_item_id: Work item ID to get cycle state for

        Returns:
            ReviewCycleState if cycle exists, None otherwise
        """
        with self._lock:
            return self._cycle_states.get(work_item_id)

    async def save_cycle_state(self, state: ReviewCycleState) -> None:
        """Persist review cycle state.

        Args:
            state: Review cycle state to persist
        """
        with self._lock:
            self._cycle_states[state.work_item_id] = state

    async def remove_cycle_state(self, state: ReviewCycleState) -> None:
        """Remove completed cycle state.

        Args:
            state: Review cycle state to remove
        """
        with self._lock:
            self._cycle_states.pop(state.work_item_id, None)

    async def load_active_cycles(
        self,
        project_id: str
    ) -> List[ReviewCycleState]:
        """Load all in-progress cycles for a project.

        Args:
            project_id: Project ID to load cycles for

        Returns:
            List of ReviewCycleState objects for active cycles
        """
        with self._lock:
            return [
                state for state in self._cycle_states.values()
                if state.project_id == project_id and state.status != "completed"
            ]

    def parse_review(self, review_output: str) -> ReviewResult:
        """Parse reviewer output to extract status and findings.

        Args:
            review_output: Raw text output from reviewer agent

        Returns:
            ReviewResult with parsed status, findings, and counts
        """
        # Simple parsing for mock
        review_output_lower = review_output.lower()

        if "approve" in review_output_lower:
            status = "APPROVED"
        elif "escalate" in review_output_lower or "blocking" in review_output_lower:
            status = "BLOCKED"
        else:
            status = "CHANGES_REQUESTED"

        findings = []
        if "blocking" in review_output_lower:
            findings.append(ReviewFinding(
                severity="blocking",
                description="Blocking issue found in review output"
            ))

        return ReviewResult(
            status=status,
            findings=findings,
            blocking_count=len([f for f in findings if f.severity == "blocking"]),
            summary=review_output[:100] if review_output else None
        )

    # ==================== IEventEmitter Implementation ====================

    def on(self, event_type: str, handler) -> None:
        """Register event handler."""
        if event_type not in self._event_handlers:
            self._event_handlers[event_type] = []
        self._event_handlers[event_type].append(handler)

    def off(self, event_type: str, handler) -> None:
        """Unregister event handler."""
        if event_type in self._event_handlers:
            try:
                self._event_handlers[event_type].remove(handler)
            except ValueError:
                pass

    def emit(self, event) -> None:
        """Emit an event to all subscribers."""
        event_type = getattr(event, "type", "unknown")
        self._emit_event(event_type, event)

    def _emit_event(self, event_type: str, event: object) -> None:
        """Emit an event and call handlers."""
        with self._lock:
            event_dict = {
                "type": event_type,
                "event": event,
                "timestamp": self.clock.now().isoformat(),
            }
            self._events.append(event_dict)

        # Call handlers
        if event_type in self._event_handlers:
            for handler in self._event_handlers[event_type]:
                try:
                    handler(event)
                except Exception as e:
                    error_record = {
                        "event_type": event_type,
                        "handler": handler.__name__ if hasattr(handler, "__name__") else str(handler),
                        "error": str(e),
                        "timestamp": self.clock.now().isoformat(),
                    }
                    self._handler_errors.append(error_record)
                    logger.error(
                        f"Error in event handler for {event_type}: {e}",
                        exc_info=True,
                        extra={"error_id": ErrorRegistry.ERR_HANDLER_EXECUTION}
                    )

    # ==================== IMonitoredService Implementation ====================

    async def start_monitoring(
        self,
        config: MonitoringConfig,
    ) -> MonitoringStatus:
        """Start monitoring (no-op for mock)."""
        status = MonitoringStatus(
            service_name="MockReviewCycleAdapter",
            is_running=True,
            timestamp=self.clock.now().isoformat(),
        )
        with self._lock:
            self._monitoring["default"] = status
        return status

    async def stop_monitoring(self) -> None:
        """Stop monitoring (no-op for mock)."""
        pass

    # Event log retrieval

    def get_all_events(self) -> List[Dict[str, Any]]:
        """Get all emitted events."""
        with self._lock:
            return list(self._events)

    def get_all_events_log(self) -> List[Dict[str, Any]]:
        """Return all logged events for testing and assertion.

        Returns a consolidated view of all events that have been
        emitted or logged, suitable for assertion helpers.
        """
        with self._lock:
            return [
                event for event in self._events
                if isinstance(event, dict) and "type" in event
            ]

    def get_events_by_type(self, event_type: str) -> List[Dict[str, Any]]:
        """Return events of specific type."""
        with self._lock:
            return [
                event for event in self._events
                if isinstance(event, dict) and event.get("type") == event_type
            ]

    def get_handler_errors(self) -> List[Dict[str, Any]]:
        """Get all handler errors that occurred during review cycle."""
        with self._lock:
            return list(self._handler_errors)

    # Assertion helpers

    def assert_iteration_count(
        self,
        work_item_id: str,
        expected: int
    ) -> None:
        """Assert work item took expected iterations.

        Args:
            work_item_id: Work item ID to check
            expected: Expected number of iterations

        Raises:
            AssertionError: If iteration count doesn't match
        """
        state = self._cycle_states.get(work_item_id)
        if not state:
            raise AssertionError(
                f"No cycle state found for work item {work_item_id}"
            )
        if state.current_iteration != expected:
            raise AssertionError(
                f"Expected {expected} iterations for {work_item_id}, "
                f"got {state.current_iteration}"
            )

    def assert_final_status(
        self,
        work_item_id: str,
        expected_status: ReviewStatusLiteral
    ) -> None:
        """Assert work item has expected final status.

        Args:
            work_item_id: Work item ID to check
            expected_status: Expected final status

        Raises:
            AssertionError: If status doesn't match
        """
        events = self.get_all_events_log()
        completion_event = None

        for event in reversed(events):
            if (event.get("type") == "REVIEW_CYCLE_COMPLETED" and
                event.get("work_item_id") == work_item_id):
                completion_event = event
                break

        if not completion_event:
            raise AssertionError(
                f"No completion event found for work item {work_item_id}"
            )

        actual_status = completion_event.get("final_status")
        if actual_status != expected_status:
            raise AssertionError(
                f"Expected status {expected_status} for {work_item_id}, "
                f"got {actual_status}"
            )

    def assert_escalation_occurred(self, work_item_id: str) -> None:
        """Assert work item was escalated to human.

        Args:
            work_item_id: Work item ID to check

        Raises:
            AssertionError: If escalation didn't occur
        """
        events = self.get_all_events_log()
        for event in events:
            if (event.get("type") == "REVIEW_CYCLE_COMPLETED" and
                event.get("work_item_id") == work_item_id):
                if not event.get("human_escalation"):
                    raise AssertionError(
                        f"Expected escalation for {work_item_id}"
                    )
                return

        raise AssertionError(
            f"No completion event found for work item {work_item_id}"
        )

    def assert_no_escalation(self, work_item_id: str) -> None:
        """Assert work item was not escalated to human.

        Args:
            work_item_id: Work item ID to check

        Raises:
            AssertionError: If escalation occurred
        """
        events = self.get_all_events_log()
        for event in events:
            if (event.get("type") == "REVIEW_CYCLE_COMPLETED" and
                event.get("work_item_id") == work_item_id):
                if event.get("human_escalation"):
                    raise AssertionError(
                        f"Unexpected escalation for {work_item_id}"
                    )
                return

        raise AssertionError(
            f"No completion event found for work item {work_item_id}"
        )

    def assert_no_handler_errors(self) -> None:
        """Assert no event handler errors occurred.

        Raises:
            AssertionError: If any handler errors were recorded
        """
        errors = self.get_handler_errors()
        if errors:
            error_summary = "\n".join(
                f"  - {e['event_type']}: {e['error']}" for e in errors
            )
            raise AssertionError(
                f"Expected no handler errors, but found {len(errors)}:\n{error_summary}"
            )

    # Helper methods

    def _validate_request(self, request: ReviewCycleRequest) -> None:
        """Validate review cycle request."""
        if not request.work_item_id:
            raise ValueError("work_item_id is required")
        if not request.project_id:
            raise ValueError("project_id is required")
        if request.max_iterations <= 0:
            raise ValueError("max_iterations must be positive")

    def _log_event(self, event: Dict[str, Any]) -> None:
        """Log event to event tracking for testing purposes.

        This complements the regular event emission by storing a copy
        in a searchable format for assertion helpers.
        """
        event["timestamp"] = self.clock.now().isoformat()
        with self._lock:
            self._events.append(event)

    def clear(self) -> None:
        """Clear all state for testing."""
        with self._lock:
            self._review_cycles.clear()
            self._cycle_states.clear()
            self._review_sequences.clear()
            self._sequence_indices.clear()
            self._events.clear()
            self._event_handlers.clear()
            self._monitoring.clear()
            self._handler_errors.clear()
            self._human_feedback_queue.clear()
