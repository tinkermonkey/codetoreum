"""Mock PR Review Cycle adapter for simulation and unit testing.

This module provides a mock implementation of IPRReviewCycle that simulates PR review
cycles without actual agent calls. It supports deterministic test results and
configurable review sequences for comprehensive simulation testing.

The mock adapter:
1. Implements all five IPRReviewCycle methods with in-memory state storage
2. Emits all nine domain events in correct sequential order
3. Delegates sub-issue creation to injected ITicketSystem and IBoardService
4. Provides configuration API for test authors (set_outcome, set_findings, etc.)
5. Provides assertion helpers for test verification
6. Supports deterministic time manipulation via SimulationClock
7. Uses threading.RLock() for thread-safe state management
"""

import logging
import threading
from dataclasses import dataclass, field
from datetime import timedelta
from typing import Any

from codetoreum.adapters.secondary.mock_event_emitter import MockEventEmitter
from codetoreum.domain.events.pr_review_cycle_events import (
    PRReviewCycleApprovedEvent,
    PRReviewCycleCICheckCompletedEvent,
    PRReviewCycleCodeReviewStartedEvent,
    PRReviewCycleConsolidationCompletedEvent,
    PRReviewCycleConsolidationStartedEvent,
    PRReviewCycleEscalatedEvent,
    PRReviewCycleIssuesFoundEvent,
    PRReviewCycleMaxCyclesReachedEvent,
    PRReviewCyclePhaseCompletedEvent,
    PRReviewCycleStartedEvent,
    PRReviewCycleSubIssuesCreatedEvent,
    PRReviewCycleVerificationStartedEvent,
)
from codetoreum.domain.pr_review_cycle_types import (
    PRReviewCycleResult,
    PRReviewCycleState,
    PRReviewFinding,
    PRReviewOutcome,
    PRReviewPhaseOutput,
    PRReviewStatus,
)
from codetoreum.infrastructure.simulation.simulation_clock import SimulationClock
from codetoreum.ports.output.board_service import IBoardService, MovedByType
from codetoreum.ports.output.event_emitter import IEventEmitter
from codetoreum.ports.output.pr_review_cycle_service import (
    IPRReviewCycle,
    PRReviewCycleRequest,
    PRReviewCycleStateData,
)
from codetoreum.ports.output.ticket_system import ITicketSystem

logger = logging.getLogger(__name__)


@dataclass
class _CycleConfiguration:
    """Internal configuration for cycle behavior."""

    outcome: PRReviewOutcome = PRReviewOutcome.ISSUES_FOUND
    findings: list[PRReviewFinding] = field(default_factory=list)
    approved_immediately: bool = False
    ci_failing: bool = False
    ci_failures_count: int = 0
    max_cycles_reached: bool = False


class MockPRReviewCycleAdapter(MockEventEmitter, IPRReviewCycle):
    """Mock adapter for PR review cycle simulation testing.

    Provides:
    - All five IPRReviewCycle method implementations with in-memory state
    - Configurable cycle behavior via shorthand methods
    - SimulationClock integration for deterministic time advancement
    - Event emission with correct sequencing
    - Service delegation for sub-issue creation
    - Assertion helpers for test verification
    - Thread-safe state management

    Example:
        # Setup with required dependencies
        clock = SimulationClock()
        adapter = MockPRReviewCycleAdapter(
            ticket_system=mock_ticket_system,
            board_service=mock_board_service,
            clock=clock,
            event_emitter=mock_emitter
        )

        # Configure behavior
        adapter.set_approved_immediately()
        # Or: adapter.set_outcome(PRReviewOutcome.ISSUES_FOUND, findings=[...])

        # Execute cycle
        result = await adapter.start_pr_review_cycle(request)

        # Assert results
        adapter.assert_outcome(work_item_id, PRReviewOutcome.APPROVED)
        adapter.assert_sub_issues_created(work_item_id, 6)
    """

    def __init__(
        self,
        ticket_system: ITicketSystem | None = None,
        board_service: IBoardService | None = None,
        clock: SimulationClock | None = None,
        event_emitter: IEventEmitter | None = None,
    ) -> None:
        """Initialize the PR review cycle adapter.

        All parameters are optional and can be injected after construction via public properties.
        The clock is required at construction time to support time-aware behavior.

        Args:
            ticket_system: Optional ticket system adapter for creating work items.
                          Can be injected via public property after construction.
            board_service: Optional board service adapter for moving items between columns.
                          Can be injected via public property after construction.
            clock: Optional SimulationClock for deterministic time advancement.
                  Can be injected via public property after construction.
            event_emitter: Optional event emitter for domain event publication.
                          Can be injected via public property after construction.

        Note:
            Dependencies can be set after construction using the public properties:
            adapter.ticket_system = ticket_system
            adapter.board_service = board_service
            adapter.clock = clock
            adapter.event_emitter = event_emitter
        """
        super().__init__()
        self._ticket_system = ticket_system
        self._board_service = board_service
        self._clock = clock
        self._event_emitter = event_emitter

        # State storage
        self._cycles: dict[str, PRReviewCycleStateData] = {}
        self._project_cycles: dict[str, list[PRReviewCycleStateData]] = {}
        self._cycle_configs: dict[str, _CycleConfiguration] = {}
        self._sub_issues_created: dict[str, list[str]] = {}
        self._ci_checked: set[str] = set()

        # Event system
        self._events: list[dict[str, Any]] = []
        self._lock = threading.RLock()

    @property
    def clock(self) -> SimulationClock:
        """Get simulation clock for time advancement."""
        return self._clock

    @clock.setter
    def clock(self, clock: SimulationClock) -> None:
        """Set simulation clock for time advancement.

        Args:
            clock: SimulationClock instance for deterministic time advancement
        """
        self._clock = clock

    @property
    def ticket_system(self) -> ITicketSystem | None:
        """Get the ticket system adapter."""
        return self._ticket_system

    @ticket_system.setter
    def ticket_system(self, ticket_system: ITicketSystem | None) -> None:
        """Set the ticket system adapter.

        Args:
            ticket_system: ITicketSystem instance for creating sub-issues
        """
        self._ticket_system = ticket_system

    @property
    def board_service(self) -> IBoardService | None:
        """Get the board service adapter."""
        return self._board_service

    @board_service.setter
    def board_service(self, board_service: IBoardService | None) -> None:
        """Set the board service adapter.

        Args:
            board_service: IBoardService instance for moving items between columns
        """
        self._board_service = board_service

    @property
    def event_emitter(self) -> IEventEmitter | None:
        """Get the event emitter."""
        return self._event_emitter

    @event_emitter.setter
    def event_emitter(self, event_emitter: IEventEmitter | None) -> None:
        """Set the event emitter.

        Args:
            event_emitter: IEventEmitter instance for domain event publication
        """
        self._event_emitter = event_emitter

    # ==================== Configuration Methods ====================

    def set_outcome(self, outcome: PRReviewOutcome, findings: list[PRReviewFinding] | None = None) -> None:
        """Configure the cycle outcome.

        Args:
            outcome: The desired outcome (ISSUES_FOUND, APPROVED, MAX_CYCLES_REACHED)
            findings: List of findings if outcome is ISSUES_FOUND
        """
        config = _CycleConfiguration(
            outcome=outcome,
            findings=findings or [],
            approved_immediately=outcome == PRReviewOutcome.APPROVED,
            max_cycles_reached=outcome == PRReviewOutcome.MAX_CYCLES_REACHED,
        )
        with self._lock:
            self._cycle_configs["default"] = config

    def set_findings(self, findings: list[PRReviewFinding]) -> None:
        """Configure findings for ISSUES_FOUND outcome.

        Args:
            findings: List of findings discovered in review
        """
        with self._lock:
            config = self._cycle_configs.get("default", _CycleConfiguration())
            config.findings = findings
            config.outcome = PRReviewOutcome.ISSUES_FOUND
            self._cycle_configs["default"] = config

    def set_approved_immediately(self) -> None:
        """Configure cycle to approve immediately."""
        with self._lock:
            self._cycle_configs["default"] = _CycleConfiguration(
                outcome=PRReviewOutcome.APPROVED,
                approved_immediately=True,
            )

    def set_ci_failing(self, work_item_id: str, failure_count: int = 2) -> None:
        """Configure CI to fail with specified failure count.

        Args:
            work_item_id: Work item ID (for tracking)
            failure_count: Number of CI failures
        """
        with self._lock:
            config = self._cycle_configs.get("default", _CycleConfiguration())
            config.ci_failing = True
            config.ci_failures_count = failure_count
            self._cycle_configs["default"] = config

    def set_max_cycles_reached(self) -> None:
        """Configure cycle to report max cycles reached."""
        with self._lock:
            self._cycle_configs["default"] = _CycleConfiguration(
                outcome=PRReviewOutcome.MAX_CYCLES_REACHED,
                max_cycles_reached=True,
            )

    # ==================== IPRReviewCycle Implementation ====================

    async def start_pr_review_cycle(self, request: PRReviewCycleRequest) -> PRReviewCycleResult:
        """Start a new PR review cycle.

        Executes all phases in sequence based on configuration:
        - Phase 1: Code review (emits CodeReviewStartedEvent)
        - Phase 2.x: Verification per context source (emits VerificationStartedEvent)
        - Phase 3: CI check (emits CICheckCompletedEvent)
        - Phase 4: Consolidation (emits ConsolidationStartedEvent)

        If max_cycles is reached, short-circuits before phase events.
        If CI fails, skips Phase 4.

        Args:
            request: PR review cycle request with configuration

        Returns:
            PRReviewCycleResult with complete cycle execution result

        Raises:
            ValueError: If request validation fails
            ExternalServiceError: If service calls fail
        """
        # Validate request
        if not request.work_item_id:
            raise ValueError("work_item_id is required")
        if not request.project_id:
            raise ValueError("project_id is required")
        if not request.board_id:
            raise ValueError("board_id is required")

        work_item_id = request.work_item_id
        project_id = request.project_id
        cycle_number = request.cycle_number

        # Get configuration
        with self._lock:
            config = self._cycle_configs.get("default", _CycleConfiguration())

        # Provide default findings if outcome is ISSUES_FOUND but no findings configured
        if config.outcome == PRReviewOutcome.ISSUES_FOUND and not config.findings:
            config.findings = [
                PRReviewFinding(
                    title="Code quality issue",
                    description="Code review findings detected",
                    severity="medium",
                    phase="code_review",
                )
            ]

        # Create cycle state
        cycle_id = f"cycle-{work_item_id}-{cycle_number}"
        started_at = self._clock.now().isoformat()

        # Calculate phases_planned dynamically based on config
        phases_planned = 1 + len(request.config.verifier_context_sources) + (1 if request.config.ci_check_enabled else 0) + 1

        # Emit PRReviewCycleStartedEvent
        started_event = PRReviewCycleStartedEvent(
            type="pr_review_cycle.started",
            timestamp=started_at,
            source="mock_pr_review_cycle",
            pr_id=request.pr_id or f"pr-{work_item_id}",
            work_item_id=work_item_id,
            cycle_number=cycle_number,
            max_outer_cycles=request.config.max_outer_cycles,
            verifier_context_sources=request.config.verifier_context_sources,
            phases_planned=phases_planned,
            workflow_run_id=request.workflow_run_id,
        )
        self._event_emitter.emit(started_event)
        self._log_event({"type": "pr_review_cycle.started", "cycle_id": cycle_id})

        # Check max cycles before emitting phase events
        if config.max_cycles_reached:
            max_cycles_event = PRReviewCycleMaxCyclesReachedEvent(
                type="pr_review_cycle.max_cycles_reached",
                timestamp=self._clock.now().isoformat(),
                source="mock_pr_review_cycle",
                pr_id=request.pr_id or f"pr-{work_item_id}",
                cycle_number=cycle_number,
                max_outer_cycles=request.config.max_outer_cycles,
                next_column="Human Review",
                workflow_run_id=request.workflow_run_id,
            )
            self._event_emitter.emit(max_cycles_event)
            self._log_event({"type": "pr_review_cycle.max_cycles_reached", "cycle_id": cycle_id})

            escalated_event = PRReviewCycleEscalatedEvent(
                type="pr_review_cycle.escalated",
                timestamp=self._clock.now().isoformat(),
                source="mock_pr_review_cycle",
                pr_id=request.pr_id or f"pr-{work_item_id}",
                reason="max_cycles_reached",
                cycle_number=cycle_number,
                workflow_run_id=request.workflow_run_id,
            )
            self._event_emitter.emit(escalated_event)
            self._log_event({"type": "pr_review_cycle.escalated", "cycle_id": cycle_id})

            # Create placeholder phase output to satisfy non-empty phase_outputs requirement
            escalation_phase = PRReviewPhaseOutput(
                phase_name="escalation",
                phase_index=1,
                success=False,
                findings=(),
                summary="Max cycles reached - escalating to human review",
                duration_seconds=0.0,
                error="Max outer cycles reached, escalating for human review",
            )

            result = PRReviewCycleResult(
                cycle_number=cycle_number,
                workflow_run_id=request.workflow_run_id,
                outcome=PRReviewOutcome.MAX_CYCLES_REACHED,
                phase_outputs=(escalation_phase,),
                all_findings=(),
                sub_issue_ids=(),
                ci_passed=None,
                total_findings=0,
                critical_count=0,
                high_count=0,
                medium_count=0,
                low_count=0,
                total_duration_seconds=0.0,
                timestamp=started_at,
                next_column="Human Review",
            )

            # Still store state for recovery purposes
            cycle_state = PRReviewCycleState(
                cycle_id=cycle_id,
                pr_id=request.pr_id or f"pr-{work_item_id}",
                work_item_id=work_item_id,
                project_id=project_id,
                board_id=request.board_id,
                status=PRReviewStatus.ESCALATED,
                cycle_number=cycle_number,
                current_phase="completed",
                findings=[],
                phase_outputs=[],
                config=request.config,
                started_at=started_at,
                updated_at=self._clock.now().isoformat(),
            )
            state_data = PRReviewCycleStateData(
                work_item_id=work_item_id,
                project_id=project_id,
                board_id=request.board_id,
                cycle_number=cycle_number,
                cycle_state=cycle_state,
                created_at=started_at,
                updated_at=self._clock.now().isoformat(),
            )
            with self._lock:
                self._cycles[work_item_id] = state_data
                if project_id not in self._project_cycles:
                    self._project_cycles[project_id] = []
                self._project_cycles[project_id].append(state_data)
            return result

        # ===== PHASE 1: Code Review =====
        phase1_start = self._clock.now()
        code_review_event = PRReviewCycleCodeReviewStartedEvent(
            type="pr_review_cycle.code_review_started",
            timestamp=phase1_start.isoformat(),
            source="mock_pr_review_cycle",
            pr_id=request.pr_id or f"pr-{work_item_id}",
            workflow_run_id=request.workflow_run_id,
            timeout_seconds=request.config.code_review_timeout_seconds,
        )
        self._event_emitter.emit(code_review_event)
        self._log_event({"type": "pr_review_cycle.code_review_started", "cycle_id": cycle_id})

        # Advance clock for Phase 1 (~10 minutes)
        await self._clock.advance(timedelta(minutes=10))

        # Emit phase completed event for Phase 1
        phase1_completed = PRReviewCyclePhaseCompletedEvent(
            type="pr_review_cycle.phase_completed",
            timestamp=self._clock.now().isoformat(),
            source="mock_pr_review_cycle",
            pr_id=request.pr_id or f"pr-{work_item_id}",
            phase_name="code_review",
            phase_index=1,
            findings_count=len(config.findings),
            comment_id="",
            workflow_run_id=request.workflow_run_id,
        )
        self._event_emitter.emit(phase1_completed)
        self._log_event({"type": "pr_review_cycle.phase_completed", "cycle_id": cycle_id, "phase_index": 1})

        # ===== PHASE 2.x: Verification =====
        for idx, source in enumerate(request.config.verifier_context_sources):
            verification_event = PRReviewCycleVerificationStartedEvent(
                type="pr_review_cycle.verification_started",
                timestamp=self._clock.now().isoformat(),
                source="mock_pr_review_cycle",
                pr_id=request.pr_id or f"pr-{work_item_id}",
                context_source=source,
                source_index=idx + 1,
                total_sources=len(request.config.verifier_context_sources),
                workflow_run_id=request.workflow_run_id,
            )
            self._event_emitter.emit(verification_event)
            self._log_event(
                {
                    "type": "pr_review_cycle.verification_started",
                    "cycle_id": cycle_id,
                    "context_source": source,
                }
            )

            # Advance clock for each verification (~5 minutes)
            await self._clock.advance(timedelta(minutes=5))

        # Emit phase completed event for Phase 2 (all verifications)
        phase2_completed = PRReviewCyclePhaseCompletedEvent(
            type="pr_review_cycle.phase_completed",
            timestamp=self._clock.now().isoformat(),
            source="mock_pr_review_cycle",
            pr_id=request.pr_id or f"pr-{work_item_id}",
            phase_name="verification",
            phase_index=2,
            findings_count=0,
            comment_id="",
            workflow_run_id=request.workflow_run_id,
        )
        self._event_emitter.emit(phase2_completed)
        self._log_event({"type": "pr_review_cycle.phase_completed", "cycle_id": cycle_id, "phase_index": 2})

        # ===== PHASE 3: CI Check =====
        ci_passed = not config.ci_failing
        ci_event = PRReviewCycleCICheckCompletedEvent(
            type="pr_review_cycle.ci_check_completed",
            timestamp=self._clock.now().isoformat(),
            source="mock_pr_review_cycle",
            pr_id=request.pr_id or f"pr-{work_item_id}",
            ci_passed=ci_passed,
            failures_count=config.ci_failures_count if config.ci_failing else 0,
            pending_count=0,
            duration_seconds=0.5,
            workflow_run_id=request.workflow_run_id,
        )
        self._event_emitter.emit(ci_event)
        self._log_event(
            {
                "type": "pr_review_cycle.ci_check_completed",
                "cycle_id": cycle_id,
                "ci_passed": ci_passed,
            }
        )
        with self._lock:
            self._ci_checked.add(work_item_id)

        # Advance clock for Phase 3 (~0.5 seconds - already advanced above)
        await self._clock.advance(timedelta(milliseconds=500))

        # Emit phase completed event for Phase 3
        phase3_completed = PRReviewCyclePhaseCompletedEvent(
            type="pr_review_cycle.phase_completed",
            timestamp=self._clock.now().isoformat(),
            source="mock_pr_review_cycle",
            pr_id=request.pr_id or f"pr-{work_item_id}",
            phase_name="ci_check",
            phase_index=3,
            findings_count=len(config.findings) if not ci_passed else 0,
            comment_id="",
            workflow_run_id=request.workflow_run_id,
        )
        self._event_emitter.emit(phase3_completed)
        self._log_event({"type": "pr_review_cycle.phase_completed", "cycle_id": cycle_id, "phase_index": 3})

        # If CI failed, skip Phase 4 and route to failure column
        if not ci_passed:
            phase_outputs = [
                PRReviewPhaseOutput(
                    phase_name="code_review",
                    phase_index=1,
                    success=True,
                    findings=tuple(config.findings),
                    summary="Code review completed",
                    duration_seconds=600.0,
                )
            ]
            for idx, source in enumerate(request.config.verifier_context_sources, start=2):
                phase_outputs.append(
                    PRReviewPhaseOutput(
                        phase_name=f"verification_{source}",
                        phase_index=idx,
                        success=True,
                        findings=(),
                        summary=f"Verified against {source}",
                        duration_seconds=300.0,
                        context_source=source,
                    )
                )
            phase_outputs.append(
                PRReviewPhaseOutput(
                    phase_name="ci_check",
                    phase_index=len(request.config.verifier_context_sources) + 2,
                    success=False,
                    findings=tuple(config.findings),
                    summary=f"CI check failed with {config.ci_failures_count} failures",
                    duration_seconds=0.5,
                    error=f"CI pipeline failed with {config.ci_failures_count} failures",
                )
            )

            # Create sub-issues for CI failures to satisfy domain invariant
            # (ISSUES_FOUND requires non-empty sub_issue_ids)
            sub_issue_ids: list[str] = []
            for finding in config.findings:
                try:
                    work_item = await self._ticket_system.create_work_item(
                        title=finding.title,
                        description=f"CI Finding: {finding.title}\nPhase: {finding.phase}\nSeverity: {finding.severity}\nContext Source: {finding.context_source or 'N/A'}\n\nDescription:\n{finding.description}",
                        project_id=project_id,
                        labels=["pr-review-finding", "ci-failure", finding.phase, finding.severity],
                        parent_issue_id=work_item_id,
                    )
                    sub_issue_ids.append(work_item.id)

                    # Add to the appropriate column on the board
                    target_column = request.config.sub_issue_initial_column or "Backlog"
                    await self._board_service.add_item_to_column(
                        work_item.id,
                        target_column,
                        MovedByType.ORCHESTRATOR,
                    )
                except Exception as e:
                    logger.error(
                        f"Error creating sub-issue for CI finding: {e}",
                        exc_info=True,
                        extra={"error_id": "ERR_SUB_ISSUE_CREATION"},
                    )

            with self._lock:
                self._sub_issues_created[work_item_id] = sub_issue_ids

            result = PRReviewCycleResult(
                cycle_number=cycle_number,
                workflow_run_id=request.workflow_run_id,
                outcome=PRReviewOutcome.ISSUES_FOUND,
                phase_outputs=tuple(phase_outputs),
                all_findings=tuple(config.findings),
                sub_issue_ids=tuple(sub_issue_ids),
                ci_passed=False,
                total_findings=len(config.findings),
                critical_count=sum(1 for f in config.findings if f.severity == "critical"),
                high_count=sum(1 for f in config.findings if f.severity == "high"),
                medium_count=sum(1 for f in config.findings if f.severity == "medium"),
                low_count=sum(1 for f in config.findings if f.severity == "low"),
                total_duration_seconds=(self._clock.now() - phase1_start).total_seconds(),
                timestamp=started_at,
                next_column=request.config.on_issues_found_column or "In Development",
            )

            # Still store state for recovery purposes
            cycle_state = PRReviewCycleState(
                cycle_id=cycle_id,
                pr_id=request.pr_id or f"pr-{work_item_id}",
                work_item_id=work_item_id,
                project_id=project_id,
                board_id=request.board_id,
                status=PRReviewStatus.COMPLETED,
                cycle_number=cycle_number,
                current_phase="ci_check",
                findings=config.findings.copy(),
                phase_outputs=phase_outputs,
                config=request.config,
                started_at=started_at,
                updated_at=self._clock.now().isoformat(),
            )
            state_data = PRReviewCycleStateData(
                work_item_id=work_item_id,
                project_id=project_id,
                board_id=request.board_id,
                cycle_number=cycle_number,
                cycle_state=cycle_state,
                created_at=started_at,
                updated_at=self._clock.now().isoformat(),
            )
            with self._lock:
                self._cycles[work_item_id] = state_data
                if project_id not in self._project_cycles:
                    self._project_cycles[project_id] = []
                self._project_cycles[project_id].append(state_data)
            return result

        # ===== PHASE 4: Consolidation =====
        consolidation_event = PRReviewCycleConsolidationStartedEvent(
            type="pr_review_cycle.consolidation_started",
            timestamp=self._clock.now().isoformat(),
            source="mock_pr_review_cycle",
            pr_id=request.pr_id or f"pr-{work_item_id}",
            finding_count=len(config.findings),
            workflow_run_id=request.workflow_run_id,
        )
        self._event_emitter.emit(consolidation_event)
        self._log_event(
            {
                "type": "pr_review_cycle.consolidation_started",
                "cycle_id": cycle_id,
                "finding_count": len(config.findings),
            }
        )

        # Advance clock for Phase 4 (~10 minutes)
        await self._clock.advance(timedelta(minutes=10))

        # Emit outcome event and create sub-issues if needed
        outcome = config.outcome
        next_column = request.config.on_approved_column or "Done"  # Use config or default to Done
        sub_issue_ids: list[str] = []

        if config.approved_immediately or outcome == PRReviewOutcome.APPROVED:
            outcome_event = PRReviewCycleApprovedEvent(
                type="pr_review_cycle.approved",
                timestamp=self._clock.now().isoformat(),
                source="mock_pr_review_cycle",
                pr_id=request.pr_id or f"pr-{work_item_id}",
                cycle_number=cycle_number,
                cycle_duration_seconds=(self._clock.now() - phase1_start).total_seconds(),
                next_column=next_column,
                workflow_run_id=request.workflow_run_id,
            )
            self._event_emitter.emit(outcome_event)
            self._log_event({"type": "pr_review_cycle.approved", "cycle_id": cycle_id})

        else:  # ISSUES_FOUND
            # Create sub-issues for each finding
            for finding in config.findings:
                try:
                    work_item = await self._ticket_system.create_work_item(
                        title=finding.title,
                        description=f"Finding: {finding.title}\nPhase: {finding.phase}\nSeverity: {finding.severity}\nContext Source: {finding.context_source or 'N/A'}\n\nDescription:\n{finding.description}",
                        project_id=project_id,
                        labels=["pr-review-finding", finding.phase, finding.severity],
                        parent_issue_id=work_item_id,
                    )
                    sub_issue_ids.append(work_item.id)

                    # Add to the appropriate column on the board
                    target_column = request.config.sub_issue_initial_column or "Backlog"
                    await self._board_service.add_item_to_column(
                        work_item.id,
                        target_column,
                        MovedByType.ORCHESTRATOR,
                    )
                except Exception as e:
                    logger.error(
                        f"Error creating sub-issue for finding: {e}",
                        exc_info=True,
                        extra={"error_id": "ERR_SUB_ISSUE_CREATION"},
                    )

            with self._lock:
                self._sub_issues_created[work_item_id] = sub_issue_ids

            # Emit sub-issues created event
            if sub_issue_ids:
                sub_issues_event = PRReviewCycleSubIssuesCreatedEvent(
                    type="pr_review_cycle.sub_issues_created",
                    timestamp=self._clock.now().isoformat(),
                    source="mock_pr_review_cycle",
                    pr_id=request.pr_id or f"pr-{work_item_id}",
                    cycle_number=cycle_number,
                    count=len(sub_issue_ids),
                    sub_issue_ids=tuple(sub_issue_ids),
                    target_board=request.board_id,
                    workflow_run_id=request.workflow_run_id,
                )
                self._event_emitter.emit(sub_issues_event)
                self._log_event(
                    {
                        "type": "pr_review_cycle.sub_issues_created",
                        "cycle_id": cycle_id,
                        "count": len(sub_issue_ids),
                    }
                )

            # Calculate severity counts from findings
            critical_count = sum(1 for f in config.findings if f.severity == "critical")
            high_count = sum(1 for f in config.findings if f.severity == "high")
            medium_count = sum(1 for f in config.findings if f.severity == "medium")
            low_count = sum(1 for f in config.findings if f.severity == "low")

            outcome_event = PRReviewCycleIssuesFoundEvent(
                type="pr_review_cycle.issues_found",
                timestamp=self._clock.now().isoformat(),
                source="mock_pr_review_cycle",
                pr_id=request.pr_id or f"pr-{work_item_id}",
                cycle_number=cycle_number,
                finding_count=len(config.findings),
                critical_count=critical_count,
                high_count=high_count,
                medium_count=medium_count,
                low_count=low_count,
                sub_issue_count=len(sub_issue_ids),
                cycle_duration_seconds=(self._clock.now() - phase1_start).total_seconds(),
                next_column=request.config.on_issues_found_column or "In Development",
                workflow_run_id=request.workflow_run_id,
            )
            self._event_emitter.emit(outcome_event)
            self._log_event(
                {
                    "type": "pr_review_cycle.issues_found",
                    "cycle_id": cycle_id,
                    "finding_count": len(config.findings),
                    "sub_issue_count": len(sub_issue_ids),
                }
            )
            next_column = request.config.on_issues_found_column or "In Development"

        # Emit Phase 4 consolidation completed event
        # Calculate severity counts from findings
        consolidation_critical = sum(1 for f in config.findings if f.severity == "critical")
        consolidation_high = sum(1 for f in config.findings if f.severity == "high")
        consolidation_medium = sum(1 for f in config.findings if f.severity == "medium")
        consolidation_low = sum(1 for f in config.findings if f.severity == "low")
        consolidation_duration = (self._clock.now() - phase1_start).total_seconds()

        consolidation_completed = PRReviewCycleConsolidationCompletedEvent(
            type="pr_review_cycle.consolidation_completed",
            timestamp=self._clock.now().isoformat(),
            source="mock_pr_review_cycle",
            pr_id=request.pr_id or f"pr-{work_item_id}",
            total_findings=len(config.findings),
            critical_count=consolidation_critical,
            high_count=consolidation_high,
            medium_count=consolidation_medium,
            low_count=consolidation_low,
            consolidation_duration_seconds=consolidation_duration,
            workflow_run_id=request.workflow_run_id,
        )
        self._event_emitter.emit(consolidation_completed)
        self._log_event(
            {
                "type": "pr_review_cycle.consolidation_completed",
                "cycle_id": cycle_id,
                "total_findings": len(config.findings),
            }
        )

        # Build phase outputs
        phase_outputs = [
            PRReviewPhaseOutput(
                phase_name="code_review",
                phase_index=1,
                success=True,
                findings=tuple(config.findings),
                summary="Code review completed",
                duration_seconds=600.0,
            )
        ]
        for idx, source in enumerate(request.config.verifier_context_sources, start=2):
            phase_outputs.append(
                PRReviewPhaseOutput(
                    phase_name=f"verification_{source}",
                    phase_index=idx,
                    success=True,
                    findings=(),
                    summary=f"Verified against {source}",
                    duration_seconds=300.0,
                    context_source=source,
                )
            )
        phase_outputs.append(
            PRReviewPhaseOutput(
                phase_name="ci_check",
                phase_index=len(request.config.verifier_context_sources) + 2,
                success=True,
                findings=(),
                summary="CI check passed",
                duration_seconds=0.5,
            )
        )
        phase_outputs.append(
            PRReviewPhaseOutput(
                phase_name="consolidation",
                phase_index=len(request.config.verifier_context_sources) + 3,
                success=True,
                findings=tuple(config.findings),
                summary=f"Consolidation completed, outcome: {outcome.value}",
                duration_seconds=600.0,
            )
        )

        # Create final result
        result = PRReviewCycleResult(
            cycle_number=cycle_number,
            workflow_run_id=request.workflow_run_id,
            outcome=outcome,
            phase_outputs=tuple(phase_outputs),
            all_findings=tuple(config.findings),
            sub_issue_ids=tuple(sub_issue_ids),
            ci_passed=ci_passed,
            total_findings=len(config.findings),
            critical_count=sum(1 for f in config.findings if f.severity == "critical"),
            high_count=sum(1 for f in config.findings if f.severity == "high"),
            medium_count=sum(1 for f in config.findings if f.severity == "medium"),
            low_count=sum(1 for f in config.findings if f.severity == "low"),
            total_duration_seconds=(self._clock.now() - phase1_start).total_seconds(),
            timestamp=started_at,
            next_column=next_column,
        )

        # Still store state for recovery purposes
        cycle_state = PRReviewCycleState(
            cycle_id=cycle_id,
            pr_id=request.pr_id or f"pr-{work_item_id}",
            work_item_id=work_item_id,
            project_id=project_id,
            board_id=request.board_id,
            status=PRReviewStatus.COMPLETED,
            cycle_number=cycle_number,
            current_phase="consolidation",
            findings=config.findings.copy(),
            phase_outputs=phase_outputs,
            config=request.config,
            started_at=started_at,
            updated_at=self._clock.now().isoformat(),
        )
        state_data = PRReviewCycleStateData(
            work_item_id=work_item_id,
            project_id=project_id,
            board_id=request.board_id,
            cycle_number=cycle_number,
            cycle_state=cycle_state,
            created_at=started_at,
            updated_at=self._clock.now().isoformat(),
        )

        with self._lock:
            self._cycles[work_item_id] = state_data
            if project_id not in self._project_cycles:
                self._project_cycles[project_id] = []
            self._project_cycles[project_id].append(state_data)

        return result

    async def get_cycle_state(self, work_item_id: str, project_id: str) -> PRReviewCycleStateData | None:
        """Retrieve current state of a PR review cycle.

        Args:
            work_item_id: Work item ID to get cycle state for
            project_id: Project ID containing the work item

        Returns:
            PRReviewCycleStateData if cycle exists, None otherwise
        """
        with self._lock:
            return self._cycles.get(work_item_id)

    async def save_cycle_state(self, state: PRReviewCycleStateData) -> None:
        """Persist PR review cycle state.

        Args:
            state: PR review cycle state to persist
        """
        with self._lock:
            self._cycles[state.work_item_id] = state

    async def remove_cycle_state(self, work_item_id: str, project_id: str) -> None:
        """Remove completed cycle state.

        Args:
            work_item_id: Work item ID of the cycle to remove
            project_id: Project ID containing the work item
        """
        with self._lock:
            self._cycles.pop(work_item_id, None)

    async def load_active_cycles(self, project_id: str) -> list[PRReviewCycleStateData]:
        """Load all in-progress cycles for a project.

        Args:
            project_id: Project ID to load cycles for

        Returns:
            List of PRReviewCycleStateData objects for active cycles
        """
        with self._lock:
            return list(self._project_cycles.get(project_id, []))

    # ==================== Assertion Helpers ====================

    def assert_cycle_completed(self, work_item_id: str) -> None:
        """Assert that a cycle was completed.

        Args:
            work_item_id: Work item ID to check

        Raises:
            AssertionError: If cycle not completed
        """
        with self._lock:
            state = self._cycles.get(work_item_id)
        if not state:
            msg = f"No cycle found for work item {work_item_id}"
            raise AssertionError(msg)
        if state.cycle_state.status != PRReviewStatus.COMPLETED:
            msg = f"Expected cycle to be completed for {work_item_id}, got status {state.cycle_state.status.value}"
            raise AssertionError(msg)

    def assert_outcome(self, work_item_id: str, expected_outcome: PRReviewOutcome) -> None:
        """Assert cycle has expected outcome.

        Args:
            work_item_id: Work item ID to check
            expected_outcome: Expected outcome

        Raises:
            AssertionError: If outcome doesn't match
        """
        with self._lock:
            events = list(self._events)

        # Find the last outcome event for this work item
        for event in reversed(events):
            event_type = event.get("type")
            if event_type == "pr_review_cycle.approved":
                if expected_outcome == PRReviewOutcome.APPROVED:
                    return
                msg = f"Expected outcome {expected_outcome.value} for {work_item_id}, got APPROVED"
                raise AssertionError(msg)
            if event_type == "pr_review_cycle.issues_found":
                if expected_outcome == PRReviewOutcome.ISSUES_FOUND:
                    return
                msg = f"Expected outcome {expected_outcome.value} for {work_item_id}, got ISSUES_FOUND"
                raise AssertionError(msg)
            if event_type == "pr_review_cycle.max_cycles_reached":
                if expected_outcome == PRReviewOutcome.MAX_CYCLES_REACHED:
                    return
                msg = f"Expected outcome {expected_outcome.value} for {work_item_id}, got MAX_CYCLES_REACHED"
                raise AssertionError(msg)

        msg = f"No outcome event found for {work_item_id}"
        raise AssertionError(msg)

    def assert_sub_issues_created(self, work_item_id: str, expected_count: int) -> None:
        """Assert expected number of sub-issues were created.

        Args:
            work_item_id: Work item ID to check
            expected_count: Expected number of sub-issues

        Raises:
            AssertionError: If count doesn't match
        """
        with self._lock:
            actual_count = len(self._sub_issues_created.get(work_item_id, []))
        if actual_count != expected_count:
            msg = f"Expected {expected_count} sub-issues for {work_item_id}, got {actual_count}"
            raise AssertionError(msg)

    def assert_ci_checked(self, work_item_id: str) -> None:
        """Assert that CI check was performed.

        Args:
            work_item_id: Work item ID to check

        Raises:
            AssertionError: If CI was not checked
        """
        with self._lock:
            if work_item_id not in self._ci_checked:
                msg = f"Expected CI check to be performed for {work_item_id}"
                raise AssertionError(msg)

    def assert_cycle_number(self, work_item_id: str, expected_cycle_number: int) -> None:
        """Assert cycle has expected cycle number.

        Args:
            work_item_id: Work item ID to check
            expected_cycle_number: Expected cycle number

        Raises:
            AssertionError: If cycle number doesn't match
        """
        with self._lock:
            state = self._cycles.get(work_item_id)
        if not state:
            msg = f"No cycle found for work item {work_item_id}"
            raise AssertionError(msg)
        if state.cycle_number != expected_cycle_number:
            msg = f"Expected cycle number {expected_cycle_number} for {work_item_id}, got {state.cycle_number}"
            raise AssertionError(msg)

    # ==================== Helper Methods ====================

    def _log_event(self, event: dict[str, Any]) -> None:
        """Log event for testing purposes.

        Args:
            event: Event data to log
        """
        event["timestamp"] = self._clock.now().isoformat()
        with self._lock:
            self._events.append(event)

    def get_all_events(self) -> list[dict[str, Any]]:
        """Get all logged events.

        Returns:
            List of all events logged during this session
        """
        with self._lock:
            return list(self._events)

    def clear(self) -> None:
        """Clear all internal state for testing."""
        with self._lock:
            self._cycles.clear()
            self._project_cycles.clear()
            self._cycle_configs.clear()
            self._sub_issues_created.clear()
            self._ci_checked.clear()
            self._events.clear()
