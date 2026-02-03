"""
Scenario 8a: SDLC with Code Review Feedback and Revisions

Full SDLC pipeline where the code review stage rejects the initial implementation,
requiring the developer to revise the code and resubmit. After the revision is
approved, the pipeline continues through testing and deployment.

Pipeline Flow:
  Requirements → Architecture → Implementation → Code Review (REJECTED) →
    Developer Revision → Code Review (APPROVED) → Testing → Deployment ✓

Expected outcome:
- Initial code review rejection with specific feedback
- Developer receives feedback and creates revision
- Revised code submitted for re-review
- Code review approval after revision
- Pipeline continues successfully
- Workflow completes with COMPLETED status
"""

from datetime import timedelta

from codetoreum.infrastructure.simulation import (
    SimulationConfig,
    SimulationRunner,
)


def create_config() -> SimulationConfig:
    """Create configuration for SDLC with code review feedback scenario."""
    config = SimulationConfig.create_fast_config(
        scenario_name="sdlc_review_feedback",
        speed_multiplier=100.0,
    )

    config.scenario_description = (
        "SDLC with code review rejection and revision: "
        "Requirements → Architecture → Implementation → Code Review (REJECTED) → "
        "Revision → Code Review (APPROVED) → Testing → Deployment"
    )

    # Metadata for test outputs
    config.metadata.update({
        "initial_tests_passed": 14,
        "initial_tests_failed": 1,
        "revised_tests_passed": 15,
        "revised_tests_failed": 0,
        "coverage_percent_initial": 85,
        "coverage_percent_revised": 92,
        "review_comments": 3,
        "issues_found": 3,
    })

    # Stage 1: Requirements Analyst
    config.add_agent_response_pattern(
        agent_id="requirements-analyst",
        pattern=r".*",
        response=(
            "Requirements Analysis Complete\n\n"
            "Project: Payment Processing System\n"
            "Phase: Stripe Integration with Retry Logic\n\n"
            "Key Requirements:\n"
            "1. Implement Stripe payment processing\n"
            "2. Add exponential backoff retry logic\n"
            "3. Support multiple payment methods\n"
            "4. Implement webhook handling for payment updates\n\n"
            "Acceptance Criteria:\n"
            "✓ Payments processed successfully\n"
            "✓ Transient failures retried with backoff\n"
            "✓ All payment methods supported\n"
            "✓ Webhooks delivered reliably\n\n"
            "Risk Assessment: MEDIUM\n"
            "Estimated Effort: 2-3 days"
        ),
    )

    # Stage 2: Architect
    config.add_agent_response_pattern(
        agent_id="architect",
        pattern=r".*",
        response=(
            "Architecture & Design Complete\n\n"
            "System Design for Stripe Integration\n\n"
            "Components:\n"
            "1. Payment Service\n"
            "   - Stripe API wrapper\n"
            "   - Payment processing logic\n"
            "   - Error handling\n\n"
            "2. Retry Service\n"
            "   - Exponential backoff strategy\n"
            "   - Circuit breaker pattern\n"
            "   - Dead letter queue for failures\n\n"
            "3. Webhook Handler\n"
            "   - Signature verification\n"
            "   - Event processing\n"
            "   - Duplicate detection\n\n"
            "Database: 2 new tables\n"
            "API Endpoints: 4 new endpoints\n"
            "Dependencies: stripe, httpx"
        ),
    )

    # Stage 3: Developer (Initial Implementation)
    config.add_agent_response_pattern(
        agent_id="developer",
        pattern=r".*",
        response=(
            "Implementation Complete\n\n"
            "Code Statistics:\n"
            "- Lines of Code: 280\n"
            "- Functions Implemented: 6\n"
            "- Classes Created: 4\n\n"
            "Initial Implementation Issues:\n"
            "1. Incomplete error handling in retry logic\n"
            "2. Missing webhook signature verification\n"
            "3. Insufficient logging for debugging\n"
            "4. Payment method type validation too strict\n\n"
            "Unit tests: 14/15 passing\n"
            "Coverage: 85% (below target of 90%)\n"
            "Ready for code review"
        ),
    )

    # Stage 4: Code Reviewer (Initial Review - REJECTED)
    config.add_agent_response_pattern(
        agent_id="code-reviewer-initial",
        pattern=r".*initial.*|.*first.*",
        response=(
            "Code Review Complete - REJECTED ✗\n\n"
            "Review Summary:\n"
            "Status: REQUEST CHANGES\n"
            "Issues Found: 3 CRITICAL, 1 MINOR\n"
            "Comments: 5\n\n"
            "Critical Issues:\n"
            "✗ ISSUE 1: Incomplete error handling\n"
            "  - Retry logic doesn't handle all Stripe error types\n"
            "  - Missing exponential backoff cap\n"
            "  - Action: Implement comprehensive error handling\n\n"
            "✗ ISSUE 2: Security concern - Webhook validation\n"
            "  - Webhook signature not verified\n"
            "  - Vulnerable to replay attacks\n"
            "  - Action: Implement HMAC signature verification\n\n"
            "✗ ISSUE 3: Insufficient observability\n"
            "  - Only 2 log statements in entire module\n"
            "  - Cannot debug payment failures\n"
            "  - Action: Add comprehensive logging\n\n"
            "Minor Issues:\n"
            "1. Payment method type validation too strict\n\n"
            "Test Coverage: 85% (target: 90%)\n\n"
            "Approval: REJECTED\n"
            "Action Required: Please address critical issues and resubmit"
        ),
    )

    # Developer Revision Response
    config.add_agent_response_pattern(
        agent_id="developer",
        pattern=r".*revision.*|.*fix.*",
        response=(
            "Code Revision Complete\n\n"
            "Changes Made:\n"
            "1. Error Handling\n"
            "   ✓ Added comprehensive Stripe error handling\n"
            "   ✓ Implemented exponential backoff with cap (max 60s)\n"
            "   ✓ Added rate limit handling\n\n"
            "2. Security Improvements\n"
            "   ✓ Implemented HMAC-SHA256 webhook signature verification\n"
            "   ✓ Added timestamp validation (5-minute window)\n"
            "   ✓ Implemented replay attack protection\n\n"
            "3. Observability\n"
            "   ✓ Added 15 structured log statements\n"
            "   ✓ Logs include correlation IDs\n"
            "   ✓ Payment flow fully traceable\n\n"
            "4. Additional Improvements\n"
            "   ✓ Relaxed payment method validation\n"
            "   ✓ Added metrics collection\n"
            "   ✓ Improved code documentation\n\n"
            "Revised Tests: 15/15 passing ✓\n"
            "Coverage: 92% (target: 90%) ✓\n"
            "Code quality improved significantly\n"
            "Ready for re-review"
        ),
    )

    # Stage 4: Code Reviewer (Revised Review - APPROVED)
    config.add_agent_response_pattern(
        agent_id="code-reviewer-revised",
        pattern=r".*revised.*|.*re.*",
        response=(
            "Code Review Complete - APPROVED ✓\n\n"
            "Review Summary:\n"
            "Status: APPROVED\n"
            "Issues Found: 0 CRITICAL, 1 SUGGESTION\n"
            "Comments: 3\n\n"
            "Strengths of Revision:\n"
            "✓ All critical issues resolved\n"
            "✓ Security improvements comprehensive\n"
            "✓ Excellent logging and observability\n"
            "✓ Error handling is robust\n"
            "✓ Test coverage improved to 92%\n"
            "✓ Code is well-documented\n\n"
            "Suggestions:\n"
            "1. Consider caching Stripe metadata\n"
            "2. Add metrics for success rates\n"
            "3. Monitor backoff timing\n\n"
            "Approval: GRANTED\n"
            "Ready to merge\n"
            "No blocking issues"
        ),
    )

    # Stage 5: Test Engineer
    config.add_agent_response_pattern(
        agent_id="test-engineer",
        pattern=r".*",
        response=(
            "Test Execution Complete ✓\n\n"
            "Test Results:\n"
            "Total Tests: 18\n"
            "Passed: 18 ✓\n"
            "Failed: 0\n"
            "Duration: 3.2s\n\n"
            "Test Coverage:\n"
            "Line Coverage: 92%\n"
            "Branch Coverage: 89%\n"
            "Function Coverage: 100%\n\n"
            "Integration Tests:\n"
            "✓ Stripe payment processing\n"
            "✓ Exponential backoff retry\n"
            "✓ Error handling and recovery\n"
            "✓ Webhook signature validation\n"
            "✓ Replay attack protection\n"
            "✓ Multiple payment methods\n"
            "✓ Rate limit handling\n\n"
            "Quality Gates: ALL PASSED ✓"
        ),
    )

    # Stage 6: DevOps Engineer (Deployment)
    config.add_agent_response_pattern(
        agent_id="devops-engineer",
        pattern=r".*",
        response=(
            "Deployment Complete ✓\n\n"
            "Deployment Summary:\n"
            "Environment: Production\n"
            "Version: 1.5.0\n"
            "Status: SUCCESS\n\n"
            "Deployment Checklist:\n"
            "✓ Database migrations applied\n"
            "✓ Configuration deployed\n"
            "✓ Service health checks passed\n"
            "✓ Canary traffic: 5% → OK\n"
            "✓ Blue-green swap: COMPLETED\n"
            "✓ Post-deployment tests: PASSED\n\n"
            "Status: READY FOR PRODUCTION"
        ),
    )

    # Configure container for test execution
    config.set_container_command_result(
        command="pytest",
        exit_code=0,
        stdout="====== 18 passed in 3.2s ======",
        stderr="",
    )

    return config


async def run_scenario(runner: SimulationRunner) -> None:
    """
    Execute the SDLC with code review feedback scenario.

    Args:
        runner: Simulation runner instance
    """
    # ===== STAGE 1: Requirements Analysis =====
    await runner.advance_time(timedelta(minutes=5))
    runner.assert_event_occurred(
        "AgentExecutionCompleted",
        assertion_name="req_analysis_complete",
    )
    await runner.advance_time(timedelta(minutes=1))

    # ===== STAGE 2: Architecture/Design =====
    await runner.advance_time(timedelta(minutes=5))
    runner.assert_event_occurred(
        "AgentExecutionCompleted",
        assertion_name="architecture_complete",
    )
    await runner.advance_time(timedelta(minutes=1))

    # ===== STAGE 3: Implementation (Initial) =====
    await runner.advance_time(timedelta(minutes=8))
    runner.assert_event_occurred(
        "AgentExecutionCompleted",
        assertion_name="initial_implementation_complete",
    )
    await runner.advance_time(timedelta(minutes=2))

    # ===== STAGE 4: Code Review (Initial - REJECTED) =====
    runner.assert_true(True, "code_review_started", "Starting initial code review")
    await runner.advance_time(timedelta(minutes=6))

    # Verify rejection event
    rejected_events = runner.get_events_by_type("ReviewRejected")
    runner.assert_equal(
        len(rejected_events),
        1,
        "initial_review_rejected",
        "Initial code review should be rejected",
    )

    runner.assert_event_occurred(
        "CommentAdded",
        assertion_name="review_feedback_added",
    )

    await runner.advance_time(timedelta(minutes=1))

    # ===== DEVELOPER REVISION =====
    runner.assert_true(True, "revision_triggered", "Developer revision started")
    await runner.advance_time(timedelta(minutes=7))

    revision_events = runner.get_events_by_type("WorkItemRevisionStarted")
    runner.assert_true(
        len(revision_events) > 0,
        "revision_event_emitted",
        "Revision event should be emitted",
    )

    runner.assert_event_occurred(
        "AgentExecutionCompleted",
        assertion_name="revision_complete",
    )

    await runner.advance_time(timedelta(minutes=2))

    # ===== STAGE 4: Code Review (Revised - APPROVED) =====
    runner.assert_true(True, "re_review_started", "Starting re-review of revised code")
    await runner.advance_time(timedelta(minutes=5))

    # Verify approval event
    approved_events = runner.get_events_by_type("ReviewApproved")
    runner.assert_equal(
        len(approved_events),
        1,
        "revised_review_approved",
        "Revised code review should be approved",
    )

    # Verify total review count (1 rejection + 1 approval)
    all_review_events = runner.get_events_by_type("ReviewStatusChanged")
    runner.assert_true(
        len(all_review_events) >= 2,
        "multiple_review_cycles",
        "Should have at least 2 review cycles",
    )

    await runner.advance_time(timedelta(minutes=1))

    # ===== STAGE 5: Testing & QA =====
    runner.assert_true(True, "testing_started", "Starting testing phase")
    await runner.advance_time(timedelta(minutes=5))

    runner.assert_event_occurred(
        "AgentExecutionCompleted",
        assertion_name="testing_complete",
    )

    # Verify no test failures in this scenario
    failed_tests = runner.get_events_by_type("TestFailed")
    runner.assert_equal(
        len(failed_tests),
        0,
        "no_test_failures",
        "No test failures after revision",
    )

    await runner.advance_time(timedelta(minutes=1))

    # ===== STAGE 6: Deployment =====
    runner.assert_true(True, "deployment_started", "Starting deployment")
    await runner.advance_time(timedelta(minutes=4))

    runner.assert_event_occurred(
        "AgentExecutionCompleted",
        assertion_name="deployment_complete",
    )

    await runner.advance_time(timedelta(minutes=1))

    # ===== Final Assertions =====
    runner.assert_true(True, "workflow_complete", "Verifying workflow completion")

    # Verify all stages completed
    stage_completed_events = runner.get_events_by_type("StageCompleted")
    runner.assert_true(
        len(stage_completed_events) >= 6,
        "all_stages_complete",
        "All stages should complete after revision",
    )

    # Verify workflow completed
    workflow_completed_events = runner.get_events_by_type("WorkflowCompleted")
    runner.assert_equal(
        len(workflow_completed_events),
        1,
        "workflow_completed",
        "Workflow should complete successfully",
    )

    # Verify review feedback loop
    runner.assert_equal(
        len(rejected_events),
        1,
        "review_rejected_count",
        "Should have exactly 1 rejection",
    )
    runner.assert_equal(
        len(approved_events),
        1,
        "review_approved_count",
        "Should have exactly 1 approval",
    )

    # Verify sufficient events captured for complete flow
    runner.assert_true(
        len(runner.captured_events) >= 40,
        "sufficient_events_for_feedback_loop",
        f"Should capture at least 40 events (rejection + revision), got {len(runner.captured_events)}",
    )
