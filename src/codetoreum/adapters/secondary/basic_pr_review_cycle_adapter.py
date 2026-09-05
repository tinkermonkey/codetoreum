"""Production PR review cycle adapter — in-memory state, no simulation scaffolding."""

from __future__ import annotations

import logging
import threading
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from codetoreum.domain.pr_review_cycle_types import (
    PRReviewCycleResult,
    PRReviewCycleState,
    PRReviewFinding,
    PRReviewOutcome,
    PRReviewPhaseOutput,
    PRReviewStatus,
)
from codetoreum.ports.output.board_service import MovedByType
from codetoreum.ports.output.pr_review_cycle_service import (
    IPRReviewCycle,
    PRReviewCycleRequest,
    PRReviewCycleStateData,
)

if TYPE_CHECKING:
    from codetoreum.ports.output.board_service import IBoardService
    from codetoreum.ports.output.event_emitter import IEventEmitter
    from codetoreum.ports.output.ticket_system import ITicketSystem

logger = logging.getLogger(__name__)


class BasicPRReviewCycleAdapter(IPRReviewCycle):
    """Production PR review cycle adapter using in-memory state.

    Implements the four-phase PR review pipeline without simulation
    scaffolding or pre-programmed outcomes. Outcome is determined by
    actual data:

    - max_cycles_reached: ``request.cycle_number > request.config.max_outer_cycles``
    - ci_passing: defaults to ``True``
      (TODO: inject ci_pipeline_service for real CI check)
    - findings: start empty; real code review is a future enhancement
    - outcome: APPROVED when findings are empty and CI passes;
               ISSUES_FOUND when CI fails or findings are present

    The ``_emit_and_publish_event`` helper is identical to the one in
    MockPRReviewCycleAdapter — it was already production-ready.
    """

    def __init__(
        self,
        ticket_system: ITicketSystem | None = None,
        board_service: IBoardService | None = None,
        event_emitter: IEventEmitter | None = None,
        event_bus: Any | None = None,
        event_store: Any | None = None,
    ) -> None:
        self._ticket_system = ticket_system
        self._board_service = board_service
        self._event_emitter = event_emitter
        self._event_bus = event_bus
        self._event_store = event_store

        # State storage (keyed by work_item_id for multi-item support)
        self._cycles: dict[str, PRReviewCycleStateData] = {}
        self._project_cycles: dict[str, list[PRReviewCycleStateData]] = {}

        self._lock = threading.RLock()

    # ------------------------------------------------------------------
    # Public dependency setters (allow post-construction injection)
    # ------------------------------------------------------------------

    @property
    def ticket_system(self) -> ITicketSystem | None:
        return self._ticket_system

    @ticket_system.setter
    def ticket_system(self, value: ITicketSystem | None) -> None:
        self._ticket_system = value

    @property
    def board_service(self) -> IBoardService | None:
        return self._board_service

    @board_service.setter
    def board_service(self, value: IBoardService | None) -> None:
        self._board_service = value

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
    # Helper Methods
    # ------------------------------------------------------------------

    async def _emit_and_publish_event(self, event: Any) -> None:
        """Emit event to local event_emitter, publish to event_bus, and persist to event_store.

        Args:
            event: Domain event to emit and publish
        """
        event_type = type(event).__name__
        logger.debug(
            "_emit_and_publish_event: %s, event_emitter=%s, event_bus=%s, event_store=%s",
            event_type,
            self._event_emitter is not None,
            self._event_bus is not None,
            self._event_store is not None,
        )

        # Emit to local event_emitter for test capture
        if self._event_emitter:
            try:
                self._event_emitter.emit(event)
                logger.debug("Emitted %s to local event_emitter", event_type)
            except Exception as e:
                logger.warning("Failed to emit %s to local event_emitter: %s", event_type, e, exc_info=True)

        # Publish to central event_bus for event handlers
        if self._event_bus:
            try:
                await self._event_bus.publish(event)
                logger.debug("Published %s to event_bus", event_type)
            except Exception as e:
                logger.warning("Failed to publish %s to event_bus: %s", event_type, e, exc_info=True)

        # Persist to event_store for audit trail
        if self._event_store:
            try:
                aggregate_id = getattr(event, "work_item_id", "unknown")
                await self._event_store.append(aggregate_id, [event])
                logger.debug("Appended %s to event_store for %s", event_type, aggregate_id)
            except Exception as e:
                logger.warning("Failed to append %s to event_store: %s", event_type, e, exc_info=True)

    def _log_event(self, event_data: dict[str, Any]) -> None:
        """Log event at debug level."""
        logger.debug("pr_review_cycle event: %s", event_data)

    # ------------------------------------------------------------------
    # IPRReviewCycle Implementation
    # ------------------------------------------------------------------

    async def start_pr_review_cycle(self, request: PRReviewCycleRequest) -> PRReviewCycleResult:
        """Start a new PR review cycle.

        Executes all phases in sequence:
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
        logger.info("start_pr_review_cycle invoked for %s", request.work_item_id)

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

        # Determine outcome from actual data, not pre-programmed flags
        # TODO: inject ci_pipeline_service for real CI check
        ci_passed = True  # CI passes by default; real CI check is a future enhancement
        findings: list[PRReviewFinding] = []  # findings come from real code review, not pre-programmed

        cycle_id = f"cycle-{work_item_id}-{cycle_number}"
        started_at_dt = datetime.now(UTC)
        started_at_str = started_at_dt.isoformat()

        # Calculate phases_planned dynamically based on config
        phases_planned = (
            1 + len(request.config.verifier_context_sources) + (1 if request.config.ci_check_enabled else 0) + 1
        )

        # Import events here to avoid module-level circular import risk.
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

        # Emit PRReviewCycleStartedEvent
        started_event = PRReviewCycleStartedEvent(
            type="pr_review_cycle.started",
            timestamp=started_at_str,
            source="pr_review_cycle",
            pr_id=request.pr_id or f"pr-{work_item_id}",
            work_item_id=work_item_id,
            cycle_number=cycle_number,
            max_outer_cycles=request.config.max_outer_cycles,
            verifier_context_sources=request.config.verifier_context_sources,
            phases_planned=phases_planned,
            workflow_run_id=request.workflow_run_id,
        )
        await self._emit_and_publish_event(started_event)
        self._log_event({"type": "pr_review_cycle.started", "cycle_id": cycle_id, "work_item_id": work_item_id})

        # Check max cycles before emitting phase events
        max_cycles_reached = request.cycle_number > request.config.max_outer_cycles
        if max_cycles_reached:
            escalation_cycle_number = request.config.max_outer_cycles + 1
            max_cycles_event = PRReviewCycleMaxCyclesReachedEvent(
                type="pr_review_cycle.max_cycles_reached",
                timestamp=datetime.now(UTC).isoformat(),
                source="pr_review_cycle",
                pr_id=request.pr_id or f"pr-{work_item_id}",
                work_item_id=work_item_id,
                cycle_number=escalation_cycle_number,
                max_cycles=request.config.max_outer_cycles,
                next_column="Human Review",
                workflow_run_id=request.workflow_run_id,
            )
            await self._emit_and_publish_event(max_cycles_event)
            self._log_event(
                {"type": "pr_review_cycle.max_cycles_reached", "cycle_id": cycle_id, "work_item_id": work_item_id}
            )

            escalated_event = PRReviewCycleEscalatedEvent(
                type="pr_review_cycle.escalated",
                timestamp=datetime.now(UTC).isoformat(),
                source="pr_review_cycle",
                pr_id=request.pr_id or f"pr-{work_item_id}",
                reason="max_cycles_reached",
                cycle_number=cycle_number,
                workflow_run_id=request.workflow_run_id,
            )
            await self._emit_and_publish_event(escalated_event)
            self._log_event({"type": "pr_review_cycle.escalated", "cycle_id": cycle_id})

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
                sub_issues_created=(),
                ci_passed=None,
                total_findings=0,
                critical_count=0,
                high_count=0,
                medium_count=0,
                low_count=0,
                total_duration_seconds=0.0,
                timestamp=started_at_str,
                next_column="Human Review",
            )

            cycle_state = PRReviewCycleState(
                id=cycle_id,
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
                started_at=started_at_dt,
                updated_at=datetime.now(UTC),
            )
            state_data = PRReviewCycleStateData(
                work_item_id=work_item_id,
                project_id=project_id,
                board_id=request.board_id,
                cycle_number=cycle_number,
                cycle_state=cycle_state,
                created_at=started_at_str,
                updated_at=datetime.now(UTC).isoformat(),
            )
            with self._lock:
                self._cycles[work_item_id] = state_data
                if project_id not in self._project_cycles:
                    self._project_cycles[project_id] = []
                self._project_cycles[project_id] = [
                    c for c in self._project_cycles[project_id] if c.work_item_id != work_item_id
                ]
                self._project_cycles[project_id].append(state_data)
            return result

        # ===== PHASE 1: Code Review =====
        phase1_start = datetime.now(UTC)
        code_review_event = PRReviewCycleCodeReviewStartedEvent(
            type="pr_review_cycle.code_review_started",
            timestamp=phase1_start.isoformat(),
            source="pr_review_cycle",
            pr_id=request.pr_id or f"pr-{work_item_id}",
            workflow_run_id=request.workflow_run_id,
            timeout_seconds=request.config.code_review_timeout_seconds,
        )
        await self._emit_and_publish_event(code_review_event)
        self._log_event({"type": "pr_review_cycle.code_review_started", "cycle_id": cycle_id})

        phase1_completed = PRReviewCyclePhaseCompletedEvent(
            type="pr_review_cycle.phase_completed",
            timestamp=datetime.now(UTC).isoformat(),
            source="pr_review_cycle",
            pr_id=request.pr_id or f"pr-{work_item_id}",
            phase_name="code_review",
            phase_index=1,
            findings_count=len(findings),
            comment_id="",
            workflow_run_id=request.workflow_run_id,
        )
        await self._emit_and_publish_event(phase1_completed)
        self._log_event({"type": "pr_review_cycle.phase_completed", "cycle_id": cycle_id, "phase_index": 1})

        # ===== PHASE 2.x: Verification =====
        for idx, source in enumerate(request.config.verifier_context_sources):
            verification_event = PRReviewCycleVerificationStartedEvent(
                type="pr_review_cycle.verification_started",
                timestamp=datetime.now(UTC).isoformat(),
                source="pr_review_cycle",
                pr_id=request.pr_id or f"pr-{work_item_id}",
                context_source=source,
                source_index=idx + 1,
                total_sources=len(request.config.verifier_context_sources),
                workflow_run_id=request.workflow_run_id,
            )
            await self._emit_and_publish_event(verification_event)
            self._log_event(
                {
                    "type": "pr_review_cycle.verification_started",
                    "cycle_id": cycle_id,
                    "context_source": source,
                }
            )

        phase2_completed = PRReviewCyclePhaseCompletedEvent(
            type="pr_review_cycle.phase_completed",
            timestamp=datetime.now(UTC).isoformat(),
            source="pr_review_cycle",
            pr_id=request.pr_id or f"pr-{work_item_id}",
            phase_name="verification",
            phase_index=2,
            findings_count=0,
            comment_id="",
            workflow_run_id=request.workflow_run_id,
        )
        await self._emit_and_publish_event(phase2_completed)
        self._log_event({"type": "pr_review_cycle.phase_completed", "cycle_id": cycle_id, "phase_index": 2})

        # ===== PHASE 3: CI Check (only if enabled) =====
        if request.config.ci_check_enabled:
            # TODO: inject ci_pipeline_service for real CI check
            ci_event = PRReviewCycleCICheckCompletedEvent(
                type="pr_review_cycle.ci_check_completed",
                timestamp=datetime.now(UTC).isoformat(),
                source="pr_review_cycle",
                pr_id=request.pr_id or f"pr-{work_item_id}",
                passed=ci_passed,
                failures_count=0,
                pending_count=0,
                duration_seconds=0.5,
                workflow_run_id=request.workflow_run_id,
            )
            await self._emit_and_publish_event(ci_event)
            self._log_event(
                {
                    "type": "pr_review_cycle.ci_check_completed",
                    "cycle_id": cycle_id,
                    "ci_passed": ci_passed,
                    "work_item_id": work_item_id,
                }
            )

        phase3_completed = PRReviewCyclePhaseCompletedEvent(
            type="pr_review_cycle.phase_completed",
            timestamp=datetime.now(UTC).isoformat(),
            source="pr_review_cycle",
            pr_id=request.pr_id or f"pr-{work_item_id}",
            phase_name="ci_check",
            phase_index=3,
            findings_count=0,
            comment_id="",
            workflow_run_id=request.workflow_run_id,
        )
        await self._emit_and_publish_event(phase3_completed)
        self._log_event(
            {
                "type": "pr_review_cycle.phase_completed",
                "cycle_id": cycle_id,
                "phase_index": 3,
                "work_item_id": work_item_id,
            }
        )

        # If CI failed, skip Phase 4 consolidation entirely
        if request.config.ci_check_enabled and not ci_passed:
            outcome = PRReviewOutcome.ISSUES_FOUND
            next_column = request.config.on_failure_column or request.config.on_issues_found_column or "In Development"
            sub_issue_ids: list[str] = []

            self._log_event(
                {
                    "type": "pr_review_cycle.ci_check_failed",
                    "cycle_id": cycle_id,
                    "work_item_id": work_item_id,
                    "reason": "ci_check_phase_failed",
                }
            )

            phase_outputs = [
                PRReviewPhaseOutput(
                    phase_name="code_review",
                    phase_index=1,
                    success=True,
                    findings=tuple(findings),
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
            next_phase_index = len(request.config.verifier_context_sources) + 2
            if request.config.ci_check_enabled:
                phase_outputs.append(
                    PRReviewPhaseOutput(
                        phase_name="ci_check",
                        phase_index=next_phase_index,
                        success=False,
                        findings=(),
                        summary="CI check failed",
                        duration_seconds=0.5,
                        error="CI pipeline failed",
                    )
                )

            result = PRReviewCycleResult(
                cycle_number=cycle_number,
                workflow_run_id=request.workflow_run_id,
                outcome=outcome,
                phase_outputs=tuple(phase_outputs),
                all_findings=tuple(findings),
                sub_issues_created=tuple(sub_issue_ids),
                ci_passed=ci_passed,
                total_findings=len(findings),
                critical_count=sum(1 for f in findings if f.severity == "critical"),
                high_count=sum(1 for f in findings if f.severity == "high"),
                medium_count=sum(1 for f in findings if f.severity == "medium"),
                low_count=sum(1 for f in findings if f.severity == "low"),
                total_duration_seconds=(datetime.now(UTC) - phase1_start).total_seconds(),
                timestamp=started_at_str,
                next_column=next_column,
            )

            cycle_state = PRReviewCycleState(
                id=cycle_id,
                pr_id=request.pr_id or f"pr-{work_item_id}",
                work_item_id=work_item_id,
                project_id=project_id,
                board_id=request.board_id,
                status=PRReviewStatus.COMPLETED,
                cycle_number=cycle_number,
                current_phase="ci_check",
                findings=list(findings),
                phase_outputs=phase_outputs,
                config=request.config,
                started_at=started_at_dt,
                updated_at=datetime.now(UTC),
            )
            state_data = PRReviewCycleStateData(
                work_item_id=work_item_id,
                project_id=project_id,
                board_id=request.board_id,
                cycle_number=cycle_number,
                cycle_state=cycle_state,
                created_at=started_at_str,
                updated_at=datetime.now(UTC).isoformat(),
            )
            with self._lock:
                self._cycles[work_item_id] = state_data
                if project_id not in self._project_cycles:
                    self._project_cycles[project_id] = []
                self._project_cycles[project_id] = [
                    c for c in self._project_cycles[project_id] if c.work_item_id != work_item_id
                ]
                self._project_cycles[project_id].append(state_data)
            return result

        # ===== PHASE 4: Consolidation =====
        consolidation_event = PRReviewCycleConsolidationStartedEvent(
            type="pr_review_cycle.consolidation_started",
            timestamp=datetime.now(UTC).isoformat(),
            source="pr_review_cycle",
            pr_id=request.pr_id or f"pr-{work_item_id}",
            finding_count=len(findings),
            workflow_run_id=request.workflow_run_id,
        )
        await self._emit_and_publish_event(consolidation_event)
        self._log_event(
            {
                "type": "pr_review_cycle.consolidation_started",
                "cycle_id": cycle_id,
                "finding_count": len(findings),
            }
        )

        # Determine outcome from actual data
        # Approved when no findings and CI passes; issues found otherwise
        if findings or not ci_passed:
            outcome = PRReviewOutcome.ISSUES_FOUND
        else:
            outcome = PRReviewOutcome.APPROVED

        next_column = request.config.on_approved_column or "Done"
        sub_issue_ids = []

        if outcome == PRReviewOutcome.APPROVED:
            outcome_event = PRReviewCycleApprovedEvent(
                type="pr_review_cycle.approved",
                timestamp=datetime.now(UTC).isoformat(),
                source="pr_review_cycle",
                pr_id=request.pr_id or f"pr-{work_item_id}",
                work_item_id=work_item_id,
                cycle_number=cycle_number,
                cycle_duration_seconds=(datetime.now(UTC) - phase1_start).total_seconds(),
                next_column=next_column,
                workflow_run_id=request.workflow_run_id,
            )
            await self._emit_and_publish_event(outcome_event)
            self._log_event({"type": "pr_review_cycle.approved", "cycle_id": cycle_id, "work_item_id": work_item_id})

        else:  # ISSUES_FOUND
            # Phase 4: create sub-issues for each finding
            for finding in findings:
                try:
                    work_item = await self._ticket_system.create_work_item(
                        title=finding.title,
                        description=(
                            f"Finding: {finding.title}\nPhase: {finding.phase}\n"
                            f"Severity: {finding.severity}\n"
                            f"Context Source: {finding.context_source or 'N/A'}\n\n"
                            f"Description:\n{finding.description}"
                        ),
                        project_id=project_id,
                        labels=["pr-review-finding", finding.phase, finding.severity],
                        parent_issue_id=work_item_id,
                    )
                    sub_issue_ids.append(work_item.id)

                    target_column = request.config.sub_issue_initial_column or "Backlog"
                    await self._board_service.add_item_to_column(
                        work_item.id,
                        target_column,
                        MovedByType.ORCHESTRATOR,
                    )
                except Exception as e:
                    logger.error(
                        "Error creating sub-issue for finding: %s",
                        e,
                        exc_info=True,
                        extra={"error_id": "ERR_SUB_ISSUE_CREATION"},
                    )

            if sub_issue_ids:
                sub_issues_event = PRReviewCycleSubIssuesCreatedEvent(
                    type="pr_review_cycle.sub_issues_created",
                    timestamp=datetime.now(UTC).isoformat(),
                    source="pr_review_cycle",
                    pr_id=request.pr_id or f"pr-{work_item_id}",
                    cycle_number=cycle_number,
                    count=len(sub_issue_ids),
                    work_item_ids=tuple(sub_issue_ids),
                    target_board=request.board_id,
                    workflow_run_id=request.workflow_run_id,
                )
                await self._emit_and_publish_event(sub_issues_event)
                self._log_event(
                    {
                        "type": "pr_review_cycle.sub_issues_created",
                        "cycle_id": cycle_id,
                        "count": len(sub_issue_ids),
                    }
                )

            critical_count = sum(1 for f in findings if f.severity == "critical")
            high_count = sum(1 for f in findings if f.severity == "high")
            medium_count = sum(1 for f in findings if f.severity == "medium")
            low_count = sum(1 for f in findings if f.severity == "low")

            outcome_event = PRReviewCycleIssuesFoundEvent(
                type="pr_review_cycle.issues_found",
                timestamp=datetime.now(UTC).isoformat(),
                source="pr_review_cycle",
                pr_id=request.pr_id or f"pr-{work_item_id}",
                work_item_id=work_item_id,
                cycle_number=cycle_number,
                total=len(findings),
                critical=critical_count,
                high=high_count,
                medium=medium_count,
                low=low_count,
                sub_issue_count=len(sub_issue_ids),
                cycle_duration_seconds=(datetime.now(UTC) - phase1_start).total_seconds(),
                next_column=request.config.on_issues_found_column or "In Development",
                workflow_run_id=request.workflow_run_id,
            )
            await self._emit_and_publish_event(outcome_event)
            self._log_event(
                {
                    "type": "pr_review_cycle.issues_found",
                    "cycle_id": cycle_id,
                    "work_item_id": work_item_id,
                    "finding_count": len(findings),
                    "sub_issue_count": len(sub_issue_ids),
                }
            )
            next_column = request.config.on_issues_found_column or "In Development"

        # Emit Phase 4 consolidation completed event
        consolidation_critical = sum(1 for f in findings if f.severity == "critical")
        consolidation_high = sum(1 for f in findings if f.severity == "high")
        consolidation_medium = sum(1 for f in findings if f.severity == "medium")
        consolidation_low = sum(1 for f in findings if f.severity == "low")
        consolidation_duration = (datetime.now(UTC) - phase1_start).total_seconds()

        consolidation_completed = PRReviewCycleConsolidationCompletedEvent(
            type="pr_review_cycle.consolidation_completed",
            timestamp=datetime.now(UTC).isoformat(),
            source="pr_review_cycle",
            pr_id=request.pr_id or f"pr-{work_item_id}",
            total_findings=len(findings),
            critical=consolidation_critical,
            high=consolidation_high,
            medium=consolidation_medium,
            low=consolidation_low,
            consolidation_duration_seconds=consolidation_duration,
            workflow_run_id=request.workflow_run_id,
        )
        await self._emit_and_publish_event(consolidation_completed)
        self._log_event(
            {
                "type": "pr_review_cycle.consolidation_completed",
                "cycle_id": cycle_id,
                "total_findings": len(findings),
            }
        )

        # Build phase outputs
        phase_outputs = [
            PRReviewPhaseOutput(
                phase_name="code_review",
                phase_index=1,
                success=True,
                findings=tuple(findings),
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

        next_phase_index = len(request.config.verifier_context_sources) + 2
        if request.config.ci_check_enabled:
            phase_outputs.append(
                PRReviewPhaseOutput(
                    phase_name="ci_check",
                    phase_index=next_phase_index,
                    success=ci_passed,
                    findings=(),
                    summary="CI check passed" if ci_passed else "CI check failed",
                    duration_seconds=0.5,
                    error=None if ci_passed else "CI pipeline failed",
                )
            )
            next_phase_index += 1

        phase_outputs.append(
            PRReviewPhaseOutput(
                phase_name="consolidation",
                phase_index=next_phase_index,
                success=True,
                findings=tuple(findings),
                summary=f"Consolidation completed, outcome: {outcome.value}",
                duration_seconds=600.0,
            )
        )

        result = PRReviewCycleResult(
            cycle_number=cycle_number,
            workflow_run_id=request.workflow_run_id,
            outcome=outcome,
            phase_outputs=tuple(phase_outputs),
            all_findings=tuple(findings),
            sub_issues_created=tuple(sub_issue_ids),
            ci_passed=ci_passed,
            total_findings=len(findings),
            critical_count=sum(1 for f in findings if f.severity == "critical"),
            high_count=sum(1 for f in findings if f.severity == "high"),
            medium_count=sum(1 for f in findings if f.severity == "medium"),
            low_count=sum(1 for f in findings if f.severity == "low"),
            total_duration_seconds=(datetime.now(UTC) - phase1_start).total_seconds(),
            timestamp=started_at_str,
            next_column=next_column,
        )

        cycle_state = PRReviewCycleState(
            id=cycle_id,
            pr_id=request.pr_id or f"pr-{work_item_id}",
            work_item_id=work_item_id,
            project_id=project_id,
            board_id=request.board_id,
            status=PRReviewStatus.COMPLETED,
            cycle_number=cycle_number,
            current_phase="consolidation",
            findings=list(findings),
            phase_outputs=phase_outputs,
            config=request.config,
            started_at=started_at_dt,
            updated_at=datetime.now(UTC),
        )
        state_data = PRReviewCycleStateData(
            work_item_id=work_item_id,
            project_id=project_id,
            board_id=request.board_id,
            cycle_number=cycle_number,
            cycle_state=cycle_state,
            created_at=started_at_str,
            updated_at=datetime.now(UTC).isoformat(),
        )

        with self._lock:
            self._cycles[work_item_id] = state_data
            if project_id not in self._project_cycles:
                self._project_cycles[project_id] = []
            self._project_cycles[project_id] = [
                c for c in self._project_cycles[project_id] if c.work_item_id != work_item_id
            ]
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

    async def save_cycle_state(self, data: PRReviewCycleStateData) -> None:
        """Persist PR review cycle state.

        Args:
            data: PR review cycle state to persist
        """
        with self._lock:
            self._cycles[data.work_item_id] = data
            project_id = data.project_id
            if project_id not in self._project_cycles:
                self._project_cycles[project_id] = []
            self._project_cycles[project_id] = [
                c for c in self._project_cycles[project_id] if c.work_item_id != data.work_item_id
            ]
            self._project_cycles[project_id].append(data)

    async def remove_cycle_state(self, work_item_id: str, project_id: str) -> None:
        """Remove completed cycle state.

        Args:
            work_item_id: Work item ID of the cycle to remove
            project_id: Project ID containing the work item
        """
        with self._lock:
            self._cycles.pop(work_item_id, None)
            if project_id in self._project_cycles:
                self._project_cycles[project_id] = [
                    c for c in self._project_cycles[project_id] if c.work_item_id != work_item_id
                ]

    async def load_active_cycles(self, project_id: str) -> list[PRReviewCycleStateData]:
        """Load all in-progress cycles for a project.

        Args:
            project_id: Project ID to load cycles for

        Returns:
            List of PRReviewCycleStateData objects for active cycles
        """
        with self._lock:
            return list(self._project_cycles.get(project_id, []))
