"""
Scenario 8b: SDLC with Test Failures and Repair Cycle

Full SDLC pipeline where the testing stage discovers failures that require
developer fixes. The developer repairs the code and testing validates all tests pass.
The pipeline then continues to deployment.

Pipeline Flow:
  Requirements → Architecture → Implementation → Code Review (✓) →
    Testing (FAILED: 3 failures) → Developer Repair →
    Testing (PASSED: all tests) → Deployment ✓

Expected outcome:
- Initial test run discovers 3 failed tests
- Repair cycle triggered with failure details
- Developer fixes the issues
- Testing re-runs with all tests passing
- Pipeline continues to deployment
- Workflow completes successfully
"""

from datetime import timedelta

from codetoreum.infrastructure.simulation import (
    SimulationConfig,
    SimulationRunner,
)


def create_config() -> SimulationConfig:
    """Create configuration for SDLC with test failures and repair scenario."""
    config = SimulationConfig.create_fast_config(
        scenario_name="sdlc_test_failures_repair",
        speed_multiplier=100.0,
    )

    config.scenario_description = (
        "SDLC with test failures and repair: "
        "Full pipeline → Testing discovers 3 failures → "
        "Developer repairs → Testing passes → Deployment"
    )

    # Metadata for test outputs
    config.metadata.update({
        "initial_tests_total": 18,
        "initial_tests_passed": 15,
        "initial_tests_failed": 3,
        "initial_coverage": 88,
        "repaired_tests_total": 18,
        "repaired_tests_passed": 18,
        "repaired_tests_failed": 0,
        "repaired_coverage": 94,
        "issues_fixed": 3,
    })

    # Stage 1: Requirements Analyst
    config.add_agent_response_pattern(
        agent_id="requirements-analyst",
        pattern=r".*",
        response=(
            "Requirements Analysis Complete\n\n"
            "Project: Real-time Notification System\n"
            "Phase: WebSocket Push Notifications\n\n"
            "Key Requirements:\n"
            "1. Implement WebSocket server for real-time notifications\n"
            "2. Support multiple client connections\n"
            "3. Handle message queuing and delivery\n"
            "4. Implement reconnection and recovery\n\n"
            "Acceptance Criteria:\n"
            "✓ Messages delivered within 100ms\n"
            "✓ Handle 1000+ concurrent connections\n"
            "✓ Queue persisted during outages\n"
            "✓ Automatic reconnection on failure\n\n"
            "Risk Assessment: MEDIUM-HIGH\n"
            "Estimated Effort: 3 days"
        ),
    )

    # Stage 2: Architect
    config.add_agent_response_pattern(
        agent_id="architect",
        pattern=r".*",
        response=(
            "Architecture & Design Complete\n\n"
            "System Design for Real-time Notifications\n\n"
            "Components:\n"
            "1. WebSocket Server\n"
            "   - Connection management\n"
            "   - Message broadcast\n"
            "   - Connection pooling\n\n"
            "2. Message Queue\n"
            "   - Redis pub/sub\n"
            "   - Persistent queue for offline\n"
            "   - Dead letter queue\n\n"
            "3. Connection Manager\n"
            "   - Automatic reconnection\n"
            "   - Session tracking\n"
            "   - Graceful shutdown\n\n"
            "Technology: Python asyncio, Redis, FastAPI WebSocket"
        ),
    )

    # Stage 3: Developer
    config.add_agent_response_pattern(
        agent_id="developer",
        pattern=r".*",
        response=(
            "Implementation Complete\n\n"
            "Code Statistics:\n"
            "- Lines of Code: 320\n"
            "- Functions Implemented: 7\n"
            "- Classes Created: 4\n\n"
            "Implementation Summary:\n"
            "✓ WebSocket server with 1000+ connection support\n"
            "✓ Redis-backed message queue\n"
            "✓ Connection pooling and management\n"
            "✓ Basic error handling\n"
            "✓ Logging infrastructure\n\n"
            "Unit tests: 18 created\n"
            "Code coverage: 88%\n"
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
            "Issues Found: 0 CRITICAL\n"
            "Comments: 3\n\n"
            "Code Quality:\n"
            "✓ Clean architecture\n"
            "✓ Good error handling patterns\n"
            "✓ Readable implementation\n"
            "✓ Appropriate logging\n\n"
            "Suggestions for enhancement:\n"
            "1. Monitor connection timeout edge cases\n"
            "2. Add metrics collection\n"
            "3. Performance tuning notes\n\n"
            "Approval: GRANTED\n"
            "Ready for testing"
        ),
    )

    # Stage 5: Test Engineer (Initial Run - FAILURES)
    config.add_agent_response_pattern(
        agent_id="test-engineer-initial",
        pattern=r".*initial.*|.*first.*",
        response=(
            "Test Execution Complete (Initial) ✗\n\n"
            "Test Results:\n"
            "Total Tests: 18\n"
            "Passed: 15 ✓\n"
            "Failed: 3 ✗\n"
            "Skipped: 0\n"
            "Duration: 4.2s\n\n"
            "Test Coverage:\n"
            "Line Coverage: 88%\n"
            "Branch Coverage: 82%\n\n"
            "Failed Tests:\n"
            "✗ test_connection_timeout_handling\n"
            "   Error: AssertionError - Expected timeout after 30s, got 35s\n"
            "   Issue: Race condition in timeout logic\n\n"
            "✗ test_queue_persistence_on_crash\n"
            "   Error: KeyError: 'message_queue'\n"
            "   Issue: Redis connection lost during test\n\n"
            "✗ test_concurrent_connections_limit\n"
            "   Error: AssertionError - Max connections: expected 1000, got 998\n"
            "   Issue: Off-by-two error in connection pooling\n\n"
            "Action: REPAIR REQUIRED\n"
            "All failures are fixable"
        ),
    )

    # Developer Repair Response
    config.add_agent_response_pattern(
        agent_id="developer-repair",
        pattern=r".*repair.*|.*fix.*",
        response=(
            "Code Repair Complete\n\n"
            "Failures Fixed:\n"
            "1. Connection Timeout Handling\n"
            "   ✓ Fixed race condition in timeout logic\n"
            "   ✓ Used proper asyncio.wait_for wrapper\n"
            "   ✓ Added timeout buffer validation\n"
            "   ✓ Test now passes consistently\n\n"
            "2. Queue Persistence\n"
            "   ✓ Added connection pool retry logic\n"
            "   ✓ Implemented connection health checks\n"
            "   ✓ Added queue recovery mechanism\n"
            "   ✓ Test passes with persistence verified\n\n"
            "3. Connection Pooling\n"
            "   ✓ Fixed off-by-two error in limit check\n"
            "   ✓ Proper counting of active connections\n"
            "   ✓ Added unit test for edge case\n"
            "   ✓ Test now validates exactly 1000 limit\n\n"
            "Additional Improvements:\n"
            "✓ Added defensive connection validation\n"
            "✓ Improved test reliability\n"
            "✓ Better error messages\n\n"
            "Coverage improved: 88% → 94%"
        ),
    )

    # Stage 5: Test Engineer (Rerun - ALL PASSED)
    config.add_agent_response_pattern(
        agent_id="test-engineer-rerun",
        pattern=r".*rerun.*|.*re-run.*|.*validation.*",
        response=(
            "Test Execution Complete (Validation Run) ✓\n\n"
            "Test Results:\n"
            "Total Tests: 18\n"
            "Passed: 18 ✓✓✓\n"
            "Failed: 0\n"
            "Skipped: 0\n"
            "Duration: 3.8s\n\n"
            "Test Coverage:\n"
            "Line Coverage: 94%\n"
            "Branch Coverage: 91%\n"
            "Function Coverage: 100%\n\n"
            "All Tests Passing:\n"
            "✓ test_connection_timeout_handling\n"
            "✓ test_queue_persistence_on_crash\n"
            "✓ test_concurrent_connections_limit\n"
            "✓ 15 other tests (all passing)\n\n"
            "Test Improvements:\n"
            "- Timeout tests now reliable\n"
            "- Persistence validation comprehensive\n"
            "- Connection limit tests robust\n"
            "- Overall test suite stability: EXCELLENT\n\n"
            "Quality Gates: ALL PASSED ✓\n"
            "Ready for deployment"
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
            "Version: 1.0.0\n"
            "Status: SUCCESS\n\n"
            "Deployment Steps:\n"
            "✓ All smoke tests passed\n"
            "✓ Performance baseline established\n"
            "✓ Monitoring alerts configured\n"
            "✓ Canary traffic: 5% → OK\n"
            "✓ Blue-green swap: COMPLETED\n"
            "✓ Post-deployment validation: PASSED\n\n"
            "Status: READY FOR PRODUCTION"
        ),
    )

    # Configure container for test execution
    config.set_container_command_result(
        command="pytest-initial",
        exit_code=1,
        stdout="====== 15 passed, 3 failed in 4.2s ======",
        stderr="FAILED test_connection_timeout_handling\nFAILED test_queue_persistence_on_crash\nFAILED test_concurrent_connections_limit",
    )

    config.set_container_command_result(
        command="pytest-rerun",
        exit_code=0,
        stdout="====== 18 passed in 3.8s ======",
        stderr="",
    )

    return config


async def run_scenario(runner: SimulationRunner) -> None:
    """
    Execute the SDLC with test failures and repair scenario.

    Args:
        runner: Simulation runner instance
    """
    # ===== STAGE 1: Requirements Analysis =====
    await runner.advance_time(timedelta(minutes=5))
    runner.assert_event_occurred(
        "AgentExecutionCompleted",
        assertion_name="requirements_analysis_complete",
    )
    await runner.advance_time(timedelta(minutes=1))

    # ===== STAGE 2: Architecture/Design =====
    await runner.advance_time(timedelta(minutes=5))
    runner.assert_event_occurred(
        "AgentExecutionCompleted",
        assertion_name="architecture_complete",
    )
    await runner.advance_time(timedelta(minutes=1))

    # ===== STAGE 3: Implementation =====
    await runner.advance_time(timedelta(minutes=8))
    runner.assert_event_occurred(
        "AgentExecutionCompleted",
        assertion_name="implementation_complete",
    )
    await runner.advance_time(timedelta(minutes=2))

    # ===== STAGE 4: Code Review (Approved) =====
    await runner.advance_time(timedelta(minutes=6))
    approved_events = runner.get_events_by_type("ReviewApproved")
    runner.assert_equal(
        len(approved_events),
        1,
        "code_review_approved",
        "Code review should be approved",
    )
    await runner.advance_time(timedelta(minutes=1))

    # ===== STAGE 5: Testing (Initial Run - FAILURES) =====
    runner.assert_true(True, "testing_started", "Starting initial test run")
    await runner.advance_time(timedelta(minutes=6))

    # Verify test failures
    test_failed_events = runner.get_events_by_type("TestFailed")
    runner.assert_equal(
        len(test_failed_events),
        3,
        "test_failures_detected",
        "Should detect exactly 3 test failures",
    )

    runner.assert_event_occurred(
        "TestExecutionFailed",
        assertion_name="test_execution_failed_event",
    )

    await runner.advance_time(timedelta(minutes=2))

    # ===== REPAIR CYCLE TRIGGERED =====
    runner.assert_true(True, "repair_cycle_started", "Repair cycle initiated")

    # Verify repair cycle event
    repair_events = runner.get_events_by_type("RepairCycleStarted")
    runner.assert_true(
        len(repair_events) > 0,
        "repair_cycle_event",
        "Repair cycle should be recorded",
    )

    # ===== Developer Repair Phase =====
    await runner.advance_time(timedelta(minutes=8))

    repair_complete_events = runner.get_events_by_type("DeveloperRepairCompleted")
    runner.assert_true(
        len(repair_complete_events) > 0,
        "developer_repair_complete",
        "Developer repair should be recorded",
    )

    await runner.advance_time(timedelta(minutes=2))

    # ===== STAGE 5: Testing (Rerun - ALL PASSED) =====
    runner.assert_true(True, "testing_rerun_started", "Testing rerun after repair")
    await runner.advance_time(timedelta(minutes=5))

    # Verify all tests now pass
    test_passed_events = runner.get_events_by_type("TestPassed")
    runner.assert_true(
        len(test_passed_events) >= 18,
        "all_tests_passed",
        "All tests should pass after repair",
    )

    # Verify test execution succeeded
    runner.assert_event_occurred(
        "TestExecutionSucceeded",
        assertion_name="test_execution_succeeded_event",
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

    # Verify workflow completed successfully
    workflow_completed_events = runner.get_events_by_type("WorkflowCompleted")
    runner.assert_equal(
        len(workflow_completed_events),
        1,
        "workflow_completed",
        "Workflow should complete successfully",
    )

    # Verify all stages completed
    stage_completed_events = runner.get_events_by_type("StageCompleted")
    runner.assert_true(
        len(stage_completed_events) >= 6,
        "all_stages_complete",
        "All stages should complete",
    )

    # Verify repair cycle completed
    runner.assert_equal(
        len(test_failed_events),
        3,
        "initial_failures_recorded",
        "Should record 3 initial failures",
    )

    runner.assert_true(
        len(test_passed_events) >= 18,
        "final_tests_passed",
        "All tests should pass after repair",
    )

    # Verify sufficient events for complete flow
    runner.assert_true(
        len(runner.captured_events) >= 45,
        "sufficient_events_captured",
        f"Should capture at least 45 events, got {len(runner.captured_events)}",
    )

    # Verify no escalations or rejections
    escalation_events = runner.get_events_by_type("EscalationTriggered")
    runner.assert_equal(
        len(escalation_events),
        0,
        "no_escalations",
        "No escalations in test failure scenario",
    )

    rejected_events = runner.get_events_by_type("ReviewRejected")
    runner.assert_equal(
        len(rejected_events),
        0,
        "no_review_rejections",
        "No code review rejections",
    )
