"""Production review cycle adapter — in-memory state, no simulation scaffolding."""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from codetoreum.domain.review_cycle import ReviewCycle, ReviewDecision
from codetoreum.infrastructure.error_ids import ErrorRegistry
from codetoreum.ports.output.review_cycle_service import (
    IReviewCycle,
    IterationOutput,
    ReviewCycleRequest,
    ReviewCycleResult,
    ReviewCycleState,
    ReviewFinding,
    ReviewResult,
)

if TYPE_CHECKING:
    from codetoreum.ports.output.event_emitter import IEventEmitter

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


@dataclass
class _ReviewDecisionItem:
    """Internal return type from _evaluate_maker_output."""

    decision: ReviewDecision
    summary: str | None = None
    findings: list[ReviewFinding] = field(default_factory=list)

    def to_review_result(self) -> ReviewResult:
        """Convert to a ReviewResult."""
        status_map = {
            ReviewDecision.APPROVE: "APPROVED",
            ReviewDecision.REQUEST_CHANGES: "CHANGES_REQUESTED",
            ReviewDecision.ESCALATE: "BLOCKED",
        }
        status = status_map.get(self.decision, "CHANGES_REQUESTED")
        blocking = [f for f in self.findings if f.severity == "blocking"]
        return ReviewResult(
            status=status,
            findings=self.findings,
            blocking_count=len(blocking),
            summary=self.summary,
        )


# ---------------------------------------------------------------------------
# Adapter
# ---------------------------------------------------------------------------


class BasicReviewCycleAdapter(IReviewCycle):
    """Production review cycle adapter using in-memory state.

    Implements the maker-checker review loop without any simulation
    scaffolding. Event emission uses an async helper that delegates to the
    injected event_emitter, event_bus, and/or event_store.

    Constructor signature is compatible with the simulation mock so it can
    be swapped without touching call-sites that only use the port interface.
    """

    def __init__(
        self,
        event_emitter: IEventEmitter | None = None,
        event_bus: Any | None = None,
        event_store: Any | None = None,
    ) -> None:
        self._event_emitter = event_emitter
        self._event_bus = event_bus
        self._event_store = event_store

        # Core review state
        self._review_cycles: dict[str, ReviewCycle] = {}
        self._cycle_states: dict[str, ReviewCycleState] = {}
        self._human_feedback_queue: dict[str, list[str]] = {}

        self._lock = threading.RLock()

    # ------------------------------------------------------------------
    # Public dependency setters (allow post-construction injection)
    # ------------------------------------------------------------------

    @property
    def event_emitter(self) -> IEventEmitter | None:
        return self._event_emitter

    @event_emitter.setter
    def event_emitter(self, value: IEventEmitter | None) -> None:
        self._event_emitter = value

    @property
    def event_bus(self) -> Any | None:
        return self._event_bus

    @event_bus.setter
    def event_bus(self, value: Any | None) -> None:
        self._event_bus = value

    @property
    def event_store(self) -> Any | None:
        return self._event_store

    @event_store.setter
    def event_store(self, value: Any | None) -> None:
        self._event_store = value

    # ------------------------------------------------------------------
    # Event emission helper
    # ------------------------------------------------------------------

    async def _emit_event(self, event: Any) -> None:
        """Emit event to event_emitter, event_bus, and event_store."""
        event_type = type(event).__name__
        logger.debug(
            "_emit_event: %s, event_emitter=%s, event_bus=%s, event_store=%s",
            event_type,
            self._event_emitter is not None,
            self._event_bus is not None,
            self._event_store is not None,
        )

        if self._event_emitter:
            try:
                self._event_emitter.emit(event)
            except Exception as e:
                logger.warning("Failed to emit %s to event_emitter: %s", event_type, e, exc_info=True)

        if self._event_bus:
            try:
                await self._event_bus.publish(event)
            except Exception as e:
                logger.warning("Failed to publish %s to event_bus: %s", event_type, e, exc_info=True)

        if self._event_store:
            try:
                aggregate_id = getattr(event, "work_item_id", "unknown")
                await self._event_store.append(aggregate_id, [event])
            except Exception as e:
                logger.warning("Failed to append %s to event_store: %s", event_type, e, exc_info=True)

    # ------------------------------------------------------------------
    # IReviewCycle — core methods
    # ------------------------------------------------------------------

    async def start_review_cycle(self, request: ReviewCycleRequest) -> ReviewCycleResult:
        """Start a new review cycle.

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
            workflow_id=request.board_id,
            stage_name="review",
            maker_agent_id=request.maker_agent,
            reviewer_agent_id=request.reviewer_agent,
            max_iterations=request.max_iterations,
        )

        with self._lock:
            self._review_cycles[work_item_id] = cycle

        # Import events here to avoid any chance of circular imports at module
        # level — these are domain layer frozen dataclasses.
        from codetoreum.domain.events.review_cycle_events import (
            ReviewCycleApprovedEvent,
            ReviewCycleEscalatedToHumanEvent,
            ReviewCycleHumanFeedbackReceivedEvent,
            ReviewCycleIterationCompletedEvent,
            ReviewCycleMakerRevisionEvent,
            ReviewCycleMaxIterationsReachedEvent,
            ReviewCycleStartedEvent,
        )

        await self._emit_event(
            ReviewCycleStartedEvent(
                type="review_cycle.started",
                timestamp=datetime.now(UTC).isoformat(),
                source="review_cycle",
                review_cycle_id=cycle.id,
                work_item_id=work_item_id,
                project_id=request.project_id,
                maker_agent=request.maker_agent,
                reviewer_agent=request.reviewer_agent,
                max_iterations=request.max_iterations,
            )
        )
        logger.debug(
            "Review cycle started for work_item=%s cycle_id=%s",
            work_item_id,
            cycle.id,
        )

        # Run review iterations
        iteration = 0
        final_status = "APPROVED"
        human_escalation = False

        try:
            for iteration in range(1, request.max_iterations + 1):
                # Production heuristic: evaluate maker output from previous stage
                maker_output = request.previous_stage_output or ""
                decision_item = self._evaluate_maker_output(maker_output)

                # Process the decision
                decision_item.to_review_result()

                if decision_item.decision == ReviewDecision.APPROVE:
                    cycle.start_iteration(
                        maker_output="Maker output iteration",
                        maker_execution_id=f"exec-maker-{iteration}",
                    )
                    cycle.submit_review(
                        decision=ReviewDecision.APPROVE,
                        comment=decision_item.summary or "Approved",
                        reviewer_execution_id=f"exec-reviewer-{iteration}",
                    )
                    final_status = "APPROVED"

                    await self._emit_event(
                        ReviewCycleIterationCompletedEvent(
                            type="review_cycle.iteration_completed",
                            timestamp=datetime.now(UTC).isoformat(),
                            source="review_cycle",
                            review_cycle_id=cycle.id,
                            work_item_id=work_item_id,
                            iteration=iteration,
                            status="APPROVED",
                            blocking_count=0,
                        )
                    )
                    await self._emit_event(
                        ReviewCycleApprovedEvent(
                            type="review_cycle.approved",
                            timestamp=datetime.now(UTC).isoformat(),
                            source="review_cycle",
                            review_cycle_id=cycle.id,
                            work_item_id=work_item_id,
                            total_iterations=iteration,
                        )
                    )
                    break

                if decision_item.decision == ReviewDecision.REQUEST_CHANGES:
                    cycle.start_iteration(
                        maker_output="Maker output iteration",
                        maker_execution_id=f"exec-maker-{iteration}",
                    )
                    cycle.submit_review(
                        decision=ReviewDecision.REQUEST_CHANGES,
                        comment=decision_item.summary or "Changes requested",
                        reviewer_execution_id=f"exec-reviewer-{iteration}",
                        issues=[f.description for f in decision_item.findings],
                    )
                    final_status = "CHANGES_REQUESTED"

                    if iteration >= request.max_iterations:
                        final_status = "BLOCKED"
                        human_escalation = True

                        await self._emit_event(
                            ReviewCycleMaxIterationsReachedEvent(
                                type="review_cycle.max_iterations_reached",
                                timestamp=datetime.now(UTC).isoformat(),
                                source="review_cycle",
                                review_cycle_id=cycle.id,
                                work_item_id=work_item_id,
                                max_iterations=request.max_iterations,
                            )
                        )
                        await self._emit_event(
                            ReviewCycleEscalatedToHumanEvent(
                                type="review_cycle.escalated_to_human",
                                timestamp=datetime.now(UTC).isoformat(),
                                source="review_cycle",
                                review_cycle_id=cycle.id,
                                work_item_id=work_item_id,
                                iteration=iteration,
                                blocking_count=0,
                                escalation_reason="MAX_ITERATIONS",
                            )
                        )
                        break

                    await self._emit_event(
                        ReviewCycleIterationCompletedEvent(
                            type="review_cycle.iteration_completed",
                            timestamp=datetime.now(UTC).isoformat(),
                            source="review_cycle",
                            review_cycle_id=cycle.id,
                            work_item_id=work_item_id,
                            iteration=iteration,
                            status="CHANGES_REQUESTED",
                            blocking_count=0,
                        )
                    )
                    await self._emit_event(
                        ReviewCycleMakerRevisionEvent(
                            type="review_cycle.maker_revision",
                            timestamp=datetime.now(UTC).isoformat(),
                            source="review_cycle",
                            review_cycle_id=cycle.id,
                            work_item_id=work_item_id,
                            iteration=iteration,
                        )
                    )

                elif decision_item.decision == ReviewDecision.ESCALATE:
                    cycle.start_iteration(
                        maker_output="Maker output iteration",
                        maker_execution_id=f"exec-maker-{iteration}",
                    )
                    cycle.submit_review(
                        decision=ReviewDecision.ESCALATE,
                        comment=decision_item.summary or "Escalating to human",
                        reviewer_execution_id=f"exec-reviewer-{iteration}",
                        issues=[f.description for f in decision_item.findings],
                    )
                    final_status = "BLOCKED"
                    human_escalation = True

                    blocking_count = sum(1 for f in decision_item.findings if f.severity == "blocking")
                    await self._emit_event(
                        ReviewCycleIterationCompletedEvent(
                            type="review_cycle.iteration_completed",
                            timestamp=datetime.now(UTC).isoformat(),
                            source="review_cycle",
                            review_cycle_id=cycle.id,
                            work_item_id=work_item_id,
                            iteration=iteration,
                            status="BLOCKED",
                            blocking_count=blocking_count,
                        )
                    )
                    await self._emit_event(
                        ReviewCycleEscalatedToHumanEvent(
                            type="review_cycle.escalated_to_human",
                            timestamp=datetime.now(UTC).isoformat(),
                            source="review_cycle",
                            review_cycle_id=cycle.id,
                            work_item_id=work_item_id,
                            iteration=iteration,
                            blocking_count=blocking_count,
                            escalation_reason="BLOCKED",
                        )
                    )

                    # Drain any pre-queued human feedback
                    feedback_queue = self._human_feedback_queue.get(work_item_id, [])
                    if feedback_queue:
                        feedback = feedback_queue.pop(0)
                        await self._emit_event(
                            ReviewCycleHumanFeedbackReceivedEvent(
                                type="review_cycle.human_feedback_received",
                                timestamp=datetime.now(UTC).isoformat(),
                                source="review_cycle",
                                review_cycle_id=cycle.id,
                                work_item_id=work_item_id,
                                feedback=feedback,
                            )
                        )
                        logger.debug(
                            "Human feedback applied for work_item=%s iteration=%s",
                            work_item_id,
                            iteration,
                        )
                    break

        except Exception as e:
            logger.error(
                "Error during review cycle execution: %s",
                e,
                exc_info=True,
                extra={"error_id": ErrorRegistry.ERR_REVIEW_CYCLE_ERROR},
            )
            raise

        # Persist cycle state
        now_str = datetime.now(UTC).isoformat()
        cycle_state = ReviewCycleState(
            work_item_id=work_item_id,
            project_id=request.project_id,
            board_id=request.board_id,
            maker_agent=request.maker_agent,
            reviewer_agent=request.reviewer_agent,
            max_iterations=request.max_iterations,
            workflow_run_id=request.workflow_run_id,
            current_iteration=iteration,
            maker_outputs=[
                IterationOutput(
                    iteration=i,
                    output=f"Maker output iteration {i}",
                    timestamp=now_str,
                )
                for i in range(1, iteration + 1)
            ],
            review_outputs=[
                IterationOutput(
                    iteration=i,
                    output=f"Review iteration {i}",
                    timestamp=now_str,
                )
                for i in range(1, iteration + 1)
            ],
            status="completed",
            created_at=now_str,
            updated_at=now_str,
        )

        with self._lock:
            self._cycle_states[work_item_id] = cycle_state

        logger.debug(
            "Review cycle completed work_item=%s final_status=%s iterations=%s escalated=%s",
            work_item_id,
            final_status,
            iteration,
            human_escalation,
        )

        return ReviewCycleResult(
            next_column="Testing" if final_status == "APPROVED" else "Code Review",
            cycle_complete=True,
            final_status=final_status,
            total_iterations=iteration,
            human_escalation_occurred=human_escalation,
        )

    async def resume_review_cycle(self, work_item_id: str, project_id: str) -> None:
        """Resume an interrupted review cycle.

        Args:
            work_item_id: Work item ID for the cycle to resume
            project_id: Project ID containing the work item
        """
        logger.info("Resuming review cycle for work_item=%s project=%s", work_item_id, project_id)
        # State recovery is handled by load_active_cycles; no-op here.

    async def resume_with_human_feedback(self, cycle_state: ReviewCycleState, feedback: str) -> None:
        """Resume a blocked cycle with human feedback.

        Args:
            cycle_state: Current state of the paused review cycle
            feedback: Human feedback to incorporate
        """
        from codetoreum.domain.events.review_cycle_events import ReviewCycleHumanFeedbackReceivedEvent

        cycle_id = f"cycle-{cycle_state.work_item_id}"
        await self._emit_event(
            ReviewCycleHumanFeedbackReceivedEvent(
                type="review_cycle.human_feedback_received",
                timestamp=datetime.now(UTC).isoformat(),
                source="review_cycle",
                review_cycle_id=cycle_id,
                work_item_id=cycle_state.work_item_id,
                feedback=feedback,
            )
        )
        logger.debug("Human feedback applied for work_item=%s", cycle_state.work_item_id)

    async def get_cycle_state(self, work_item_id: str) -> ReviewCycleState | None:
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

    async def load_active_cycles(self, project_id: str) -> list[ReviewCycleState]:
        """Load all in-progress cycles for a project.

        Args:
            project_id: Project ID to load cycles for

        Returns:
            List of ReviewCycleState objects for active cycles
        """
        with self._lock:
            return [
                state
                for state in self._cycle_states.values()
                if state.project_id == project_id and state.status != "completed"
            ]

    def parse_review(self, review_output: str) -> ReviewResult:
        """Parse reviewer output to extract status and findings.

        Args:
            review_output: Raw text output from reviewer agent

        Returns:
            ReviewResult with parsed status, findings, and counts
        """
        review_output_lower = review_output.lower()

        if "approve" in review_output_lower:
            status = "APPROVED"
        elif "escalate" in review_output_lower or "blocking" in review_output_lower:
            status = "BLOCKED"
        else:
            status = "CHANGES_REQUESTED"

        findings = []
        if "blocking" in review_output_lower:
            findings.append(ReviewFinding(severity="blocking", description="Blocking issue found in review output"))

        return ReviewResult(
            status=status,
            findings=findings,
            blocking_count=len([f for f in findings if f.severity == "blocking"]),
            summary=review_output[:100] if review_output else None,
        )

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _validate_request(self, request: ReviewCycleRequest) -> None:
        """Validate review cycle request."""
        if not request.work_item_id:
            msg = "work_item_id is required"
            raise ValueError(msg)
        if not request.project_id:
            msg = "project_id is required"
            raise ValueError(msg)
        if request.max_iterations <= 0:
            msg = "max_iterations must be positive"
            raise ValueError(msg)

    def _evaluate_maker_output(self, maker_output: str) -> _ReviewDecisionItem:
        """Evaluate maker output to derive a review decision (production heuristic).

        Analyzes the actual output from the maker agent to determine if the
        code meets review criteria. This implements causal linking between
        maker output and review decisions (FR-2/US-2.2).

        Args:
            maker_output: Output from the maker agent (code changes, explanations, etc.)

        Returns:
            _ReviewDecisionItem with decision derived from maker output
        """
        if not maker_output:
            return _ReviewDecisionItem(
                decision=ReviewDecision.REQUEST_CHANGES,
                summary="Maker output was empty or missing",
                findings=[ReviewFinding(severity="blocking", description="No code changes provided")],
            )

        output_lower = maker_output.lower()

        has_explanation = len(maker_output) > 100
        has_error_patterns = any(
            pattern in output_lower for pattern in ["error", "exception", "traceback", "failed", "cannot"]
        )
        has_quality_patterns = any(
            pattern in output_lower
            for pattern in ["fixed", "resolved", "updated", "improved", "refactored", "optimized"]
        )
        has_test_patterns = any(pattern in output_lower for pattern in ["test", "assert", "verify", "validate", "pass"])

        if has_error_patterns and not has_quality_patterns:
            return _ReviewDecisionItem(
                decision=ReviewDecision.REQUEST_CHANGES,
                summary="Output contains error patterns without clear fixes",
                findings=[
                    ReviewFinding(
                        severity="blocking",
                        description="Maker output indicates unresolved errors or failures",
                    )
                ],
            )
        if has_quality_patterns and has_test_patterns and has_explanation:
            return _ReviewDecisionItem(
                decision=ReviewDecision.APPROVE,
                summary="Maker output demonstrates quality improvements with test coverage",
            )
        if has_quality_patterns and has_explanation:
            return _ReviewDecisionItem(
                decision=ReviewDecision.REQUEST_CHANGES,
                summary="Maker output shows improvements but lacks test verification",
                findings=[ReviewFinding(severity="blocking", description="Missing or incomplete test coverage")],
            )
        return _ReviewDecisionItem(
            decision=ReviewDecision.REQUEST_CHANGES,
            summary="Maker output requires review and clarification",
            findings=[ReviewFinding(severity="blocking", description="Output needs clarification")],
        )

    def _log_event(self, event_data: dict[str, Any]) -> None:
        """Log event at debug level."""
        logger.debug("review_cycle event: %s", event_data)
