"""
Scenario 6: Happy Path Full SDLC

Complete SDLC pipeline from requirements through deployment with all stages
succeeding. A single work item progresses through 6 sequential stages with all
agents completing successfully, demonstrating the deterministic happy path execution.

Pipeline Flow:
  Requirements Analysis → Architecture/Design → Implementation → Code Review →
  Testing & QA → Deployment (All succeed)

Expected outcome:
- Work item moves through all 6 SDLC stages
- 6 agent executions complete successfully in sequence
- No rejections, failures, or escalations
- All artifacts are generated
- Workflow completes successfully with COMPLETED status
"""

from datetime import timedelta

from codetoreum.infrastructure.simulation import (
    SimulationConfig,
    SimulationRunner,
)


def create_config() -> SimulationConfig:
    """Create configuration for happy path full SDLC scenario."""
    config = SimulationConfig.create_fast_config(
        scenario_name="happy_path_full_sdlc",
        speed_multiplier=100.0,
    )

    config.scenario_description = (
        "Full SDLC pipeline: Requirements → Architecture → Implementation → "
        "Code Review → Testing → Deployment (All succeed)"
    )

    # Metadata for test outputs
    config.metadata.update({
        "tests_passed": 15,
        "tests_failed": 0,
        "coverage_percent": 92,
        "lines_of_code": 350,
        "functions_implemented": 8,
        "issues_fixed": 0,
    })

    # Stage 1: Requirements Analyst
    config.add_agent_response_pattern(
        agent_id="requirements-analyst",
        pattern=r".*",
        response=(
            "Requirements Analysis Complete\n\n"
            "Project: User Authentication System\n"
            "Phase: OAuth2 Integration with MFA\n\n"
            "Key Requirements:\n"
            "1. Implement OAuth2 authorization flow\n"
            "2. Add multi-factor authentication (MFA)\n"
            "3. Support session management\n"
            "4. Implement rate limiting\n\n"
            "Acceptance Criteria:\n"
            "✓ Users can login with OAuth2\n"
            "✓ MFA is enforced for sensitive operations\n"
            "✓ Sessions expire after 30 minutes\n"
            "✓ Rate limiting prevents brute force\n\n"
            "Risk Assessment: LOW\n"
            "Estimated Effort: 3-4 days\n"
            "Priority: HIGH"
        ),
    )

    # Stage 2: Architect
    config.add_agent_response_pattern(
        agent_id="architect",
        pattern=r".*",
        response=(
            "Architecture & Design Complete\n\n"
            "System Design for OAuth2 + MFA\n\n"
            "Components:\n"
            "1. OAuth2 Authorization Server\n"
            "   - Token generation and validation\n"
            "   - Token refresh mechanism\n"
            "   - Scope management\n\n"
            "2. MFA Service\n"
            "   - TOTP/SMS support\n"
            "   - Backup codes\n"
            "   - Recovery flows\n\n"
            "3. Session Manager\n"
            "   - Redis-based session store\n"
            "   - Automatic expiration\n"
            "   - Concurrent session limits\n\n"
            "4. Rate Limiter\n"
            "   - Token bucket algorithm\n"
            "   - Per-user rate limits\n"
            "   - IP-based restrictions\n\n"
            "Database Schema: 3 new tables\n"
            "API Endpoints: 12 new endpoints\n"
            "Dependencies: oauth2lib, pyotp, redis\n"
            "Technology Stack: Python FastAPI, Redis, PostgreSQL"
        ),
    )

    # Stage 3: Developer
    config.add_agent_response_pattern(
        agent_id="developer",
        pattern=r".*",
        response=(
            "Implementation Complete\n\n"
            "Code Statistics:\n"
            "- Lines of Code: 350\n"
            "- Functions Implemented: 8\n"
            "- Classes Created: 5\n"
            "- Modules: 4\n\n"
            "Implementation Details:\n"
            "1. OAuth2 Provider Integration\n"
            "   - Implemented GoogleOAuth2Provider\n"
            "   - Implemented GitHubOAuth2Provider\n"
            "   - Token exchange and validation\n\n"
            "2. MFA Service\n"
            "   - TOTP implementation with pyotp\n"
            "   - SMS delivery via Twilio\n"
            "   - Backup code generation\n\n"
            "3. Session Management\n"
            "   - Redis session store\n"
            "   - Automatic cleanup\n"
            "   - Concurrent session handling\n\n"
            "4. Rate Limiting\n"
            "   - Token bucket implementation\n"
            "   - Distributed rate limiting\n"
            "   - Configurable limits\n\n"
            "All unit tests passing: 45/45\n"
            "Code documentation: 100% coverage\n"
            "Ready for code review"
        ),
    )

    # Stage 4: Code Reviewer
    config.add_agent_response_pattern(
        agent_id="code-reviewer",
        pattern=r".*",
        response=(
            "Code Review Complete - APPROVED ✓\n\n"
            "Review Summary:\n"
            "Status: APPROVED\n"
            "Issues Found: 0\n"
            "Comments: 5\n\n"
            "Strengths:\n"
            "✓ Clean, readable code\n"
            "✓ Excellent error handling\n"
            "✓ Good test coverage\n"
            "✓ Follows PEP 8 standards\n"
            "✓ Security best practices implemented\n\n"
            "Review Comments:\n"
            "1. [INFO] Consider adding rate limit headers to responses\n"
            "2. [INFO] Add telemetry for OAuth provider failures\n"
            "3. [INFO] Document the backup code recovery flow\n"
            "4. [SUGGESTION] Add cache invalidation strategy\n"
            "5. [MINOR] Typo in MFA service docstring\n\n"
            "Approval: GRANTED\n"
            "Reviewer: architect-001\n"
            "Ready to merge"
        ),
    )

    # Stage 5: Test Engineer
    config.add_agent_response_pattern(
        agent_id="test-engineer",
        pattern=r".*",
        response=(
            "Test Execution Complete ✓\n\n"
            "Test Results:\n"
            "Total Tests: 15\n"
            "Passed: 15 ✓\n"
            "Failed: 0\n"
            "Skipped: 0\n"
            "Duration: 2.5s\n\n"
            "Test Coverage:\n"
            "Line Coverage: 92%\n"
            "Branch Coverage: 88%\n"
            "Function Coverage: 100%\n\n"
            "Integration Tests:\n"
            "✓ OAuth2 flow (Google provider)\n"
            "✓ OAuth2 flow (GitHub provider)\n"
            "✓ TOTP MFA\n"
            "✓ SMS MFA\n"
            "✓ Backup code recovery\n"
            "✓ Session expiration\n"
            "✓ Rate limiting\n"
            "✓ Concurrent session handling\n"
            "✓ Token refresh\n"
            "✓ Error handling\n"
            "✓ Performance under load\n"
            "✓ Security validations\n"
            "✓ Database migrations\n"
            "✓ Redis connectivity\n"
            "✓ Rate limit accuracy\n\n"
            "Performance Metrics:\n"
            "- Avg OAuth2 response time: 45ms\n"
            "- Avg MFA validation time: 15ms\n"
            "- Session creation: 10ms\n"
            "- Rate limit check: 5ms\n\n"
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
            "Version: 2.1.0\n"
            "Status: SUCCESS\n\n"
            "Deployment Steps:\n"
            "1. Database Migrations\n"
            "   - Applied 3 new schema migrations\n"
            "   - Created indices for performance\n"
            "   - Verified data integrity\n\n"
            "2. Service Deployment\n"
            "   - Deployed to 3 production instances\n"
            "   - Load balancer configured\n"
            "   - Health checks passing: 3/3\n\n"
            "3. Cache Initialization\n"
            "   - Redis cluster initialized\n"
            "   - Replication verified\n"
            "   - Sentinel monitoring enabled\n\n"
            "4. Configuration\n"
            "   - Environment variables deployed\n"
            "   - OAuth2 secrets configured\n"
            "   - SSL certificates verified\n\n"
            "5. Smoke Tests\n"
            "   - Login flow: PASSED ✓\n"
            "   - MFA validation: PASSED ✓\n"
            "   - Rate limiting: PASSED ✓\n"
            "   - Canary traffic: 5% → OK\n"
            "   - Blue-green swap: COMPLETED\n\n"
            "Rollback Plan: Prepared\n"
            "Monitoring: Active\n"
            "Alerts: Configured\n"
            "Status: READY FOR PRODUCTION"
        ),
    )

    # Configure container for test execution
    config.set_container_command_result(
        command="pytest",
        exit_code=0,
        stdout="====== 15 passed in 2.5s ======",
        stderr="",
    )

    config.set_container_command_result(
        command="coverage",
        exit_code=0,
        stdout="Name                    Stmts   Miss  Cover\n"
                "───────────────────────────────────────\n"
                "oauth2_service.py         125     10    92%\n"
                "mfa_service.py             95      8    92%\n"
                "session_manager.py         75      6    92%\n"
                "rate_limiter.py            55      4    93%\n"
                "───────────────────────────────────────\n"
                "TOTAL                     350     28    92%",
        stderr="",
    )

    config.set_container_command_result(
        command="pylint",
        exit_code=0,
        stdout="Your code has been rated at 9.8/10",
        stderr="",
    )

    return config


async def run_scenario(runner: SimulationRunner) -> None:
    """
    Execute the happy path full SDLC scenario.

    Args:
        runner: Simulation runner instance
    """
    # Verify initial state
    runner.assert_equal(
        len(runner.captured_events),
        0,
        "initial_state",
        "Should start with no events",
    )

    # ===== STAGE 1: Requirements Analysis =====
    runner.assert_true(True, "stage_1_start", "Starting Requirements Analysis")
    await runner.advance_time(timedelta(minutes=5))

    runner.assert_event_occurred(
        "AgentExecutionStarted",
        assertion_name="stage_1_agent_started",
    )
    runner.assert_event_occurred(
        "AgentExecutionCompleted",
        assertion_name="stage_1_agent_completed",
    )

    # Advance for artifact generation
    await runner.advance_time(timedelta(minutes=1))
    runner.assert_event_occurred(
        "StageCompleted",
        assertion_name="stage_1_complete",
    )

    # ===== STAGE 2: Architecture/Design =====
    runner.assert_true(True, "stage_2_start", "Starting Architecture Design")
    await runner.advance_time(timedelta(minutes=5))

    runner.assert_event_occurred(
        "AgentExecutionStarted",
        assertion_name="stage_2_agent_started",
    )
    runner.assert_event_occurred(
        "AgentExecutionCompleted",
        assertion_name="stage_2_agent_completed",
    )

    await runner.advance_time(timedelta(minutes=1))
    runner.assert_event_occurred(
        "StageCompleted",
        assertion_name="stage_2_complete",
    )

    # ===== STAGE 3: Implementation =====
    runner.assert_true(True, "stage_3_start", "Starting Implementation")
    await runner.advance_time(timedelta(minutes=8))

    runner.assert_event_occurred(
        "AgentExecutionStarted",
        assertion_name="stage_3_agent_started",
    )
    runner.assert_event_occurred(
        "AgentExecutionCompleted",
        assertion_name="stage_3_agent_completed",
    )

    await runner.advance_time(timedelta(minutes=2))
    runner.assert_event_occurred(
        "StageCompleted",
        assertion_name="stage_3_complete",
    )

    # ===== STAGE 4: Code Review =====
    runner.assert_true(True, "stage_4_start", "Starting Code Review")
    await runner.advance_time(timedelta(minutes=6))

    runner.assert_event_occurred(
        "AgentExecutionStarted",
        assertion_name="stage_4_agent_started",
    )
    runner.assert_event_occurred(
        "AgentExecutionCompleted",
        assertion_name="stage_4_agent_completed",
    )

    # Should be approved in happy path
    approved_events = runner.get_events_by_type("ReviewApproved")
    runner.assert_equal(
        len(approved_events),
        1,
        "code_review_approved",
        "Code review should be approved",
    )

    await runner.advance_time(timedelta(minutes=1))
    runner.assert_event_occurred(
        "StageCompleted",
        assertion_name="stage_4_complete",
    )

    # ===== STAGE 5: Testing & QA =====
    runner.assert_true(True, "stage_5_start", "Starting Testing & QA")
    await runner.advance_time(timedelta(minutes=5))

    runner.assert_event_occurred(
        "AgentExecutionStarted",
        assertion_name="stage_5_agent_started",
    )
    runner.assert_event_occurred(
        "AgentExecutionCompleted",
        assertion_name="stage_5_agent_completed",
    )

    # Should have no test failures in happy path
    failed_tests = runner.get_events_by_type("TestFailed")
    runner.assert_equal(
        len(failed_tests),
        0,
        "no_test_failures",
        "No test failures in happy path",
    )

    await runner.advance_time(timedelta(minutes=1))
    runner.assert_event_occurred(
        "StageCompleted",
        assertion_name="stage_5_complete",
    )

    # ===== STAGE 6: Deployment =====
    runner.assert_true(True, "stage_6_start", "Starting Deployment")
    await runner.advance_time(timedelta(minutes=4))

    runner.assert_event_occurred(
        "AgentExecutionStarted",
        assertion_name="stage_6_agent_started",
    )
    runner.assert_event_occurred(
        "AgentExecutionCompleted",
        assertion_name="stage_6_agent_completed",
    )

    await runner.advance_time(timedelta(minutes=1))
    runner.assert_event_occurred(
        "StageCompleted",
        assertion_name="stage_6_complete",
    )

    # ===== Final Assertions =====
    runner.assert_true(True, "workflow_completion", "Verifying workflow completion")

    # Verify all stages completed
    stage_completed_events = runner.get_events_by_type("StageCompleted")
    runner.assert_equal(
        len(stage_completed_events),
        6,
        "all_stages_complete",
        "All 6 stages should complete",
    )

    # Verify workflow completed
    workflow_completed_events = runner.get_events_by_type("WorkflowCompleted")
    runner.assert_equal(
        len(workflow_completed_events),
        1,
        "workflow_completed",
        "Workflow should have one completion event",
    )

    # Verify no rejections or failures in happy path
    rejected_events = runner.get_events_by_type("ReviewRejected")
    runner.assert_equal(
        len(rejected_events),
        0,
        "no_rejections",
        "No code review rejections in happy path",
    )

    escalation_events = runner.get_events_by_type("EscalationTriggered")
    runner.assert_equal(
        len(escalation_events),
        0,
        "no_escalations",
        "No escalations in happy path",
    )

    # Verify metrics recording
    runner.assert_event_occurred(
        "MetricsRecorded",
        assertion_name="metrics_recorded",
    )

    # Verify proper event count (approximately 30+ events for full pipeline)
    runner.assert_true(
        len(runner.captured_events) >= 30,
        "sufficient_events_captured",
        f"Should capture at least 30 events, got {len(runner.captured_events)}",
    )
