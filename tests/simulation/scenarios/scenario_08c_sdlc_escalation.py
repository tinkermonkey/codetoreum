"""
Scenario 8c: SDLC with Escalation and Human Feedback

Full SDLC pipeline where the implementation stage encounters complexity requiring
human clarification. The work item escalates to a product owner for feedback,
the human provides a decision, and the developer resumes implementation based on
the feedback. The pipeline then continues through code review, testing, and deployment.

Pipeline Flow:
  Requirements → Architecture →
    Implementation (ESCALATED - needs clarification) →
      Human Feedback Collection & Decision →
    Implementation (resumed with feedback) → Code Review → Testing → Deployment ✓

Expected outcome:
- Implementation stage escalates with specific clarification need
- Escalation event includes context for human decision
- Human feedback is captured and queued
- Developer acknowledges feedback and resumes
- Implementation completes with updated approach
- Pipeline continues successfully
- Workflow completes successfully
"""

from datetime import timedelta

from codetoreum.infrastructure.simulation import (
    SimulationConfig,
    SimulationRunner,
)


def create_config() -> SimulationConfig:
    """Create configuration for SDLC with escalation and human feedback scenario."""
    config = SimulationConfig.create_fast_config(
        scenario_name="sdlc_escalation_human_feedback",
        speed_multiplier=100.0,
    )

    config.scenario_description = (
        "SDLC with escalation and human feedback: "
        "Full pipeline → Implementation escalates for clarification → "
        "Human decision → Resume → Completion"
    )

    # Metadata for test outputs
    config.metadata.update({
        "escalation_reason": "Architecture decision point",
        "human_decision": "Use microservices approach",
        "tests_passed": 16,
        "tests_failed": 0,
        "coverage_percent": 91,
        "escalation_wait_time_minutes": 5,
    })

    # Stage 1: Requirements Analyst
    config.add_agent_response_pattern(
        agent_id="requirements-analyst",
        pattern=r".*",
        response=(
            "Requirements Analysis Complete\n\n"
            "Project: Data Pipeline System\n"
            "Phase: Event Processing and Analytics\n\n"
            "Key Requirements:\n"
            "1. Process event streams from multiple sources\n"
            "2. Real-time aggregation and analytics\n"
            "3. Support multiple storage backends\n"
            "4. Scalable to 1M+ events/sec\n\n"
            "Acceptance Criteria:\n"
            "✓ End-to-end latency < 100ms\n"
            "✓ Supports all major data sources\n"
            "✓ Automatic failover\n"
            "✓ 99.9% uptime SLA\n\n"
            "Risk Assessment: MEDIUM\n"
            "Estimated Effort: 4-5 days\n"
            "Note: Architecture decision critical"
        ),
    )

    # Stage 2: Architect
    config.add_agent_response_pattern(
        agent_id="architect",
        pattern=r".*",
        response=(
            "Architecture & Design - Preliminary\n\n"
            "System Design for Event Processing Pipeline\n\n"
            "Initial Proposal:\n"
            "1. Monolithic Event Processor\n"
            "   - Single service handling all events\n"
            "   - PostgreSQL for persistence\n"
            "   - Redis for caching\n\n"
            "Alternatively:\n"
            "2. Microservices Architecture\n"
            "   - Separate ingestion, processing, storage services\n"
            "   - Better scalability\n"
            "   - More operational complexity\n\n"
            "Critical Decision Point:\n"
            "- Monolithic: Simpler, faster to build (2-3 days)\n"
            "- Microservices: Better for scale, more work (5-6 days)\n\n"
            "Recommendation pending requirements discussion"
        ),
    )

    # Stage 3: Developer (Initial Implementation)
    config.add_agent_response_pattern(
        agent_id="developer-initial",
        pattern=r".*initial.*|.*first.*",
        response=(
            "Implementation Paused - ESCALATION REQUIRED\n\n"
            "Status: AWAITING ARCHITECTURE DECISION\n\n"
            "Current Situation:\n"
            "I've begun implementing the monolithic approach,\n"
            "but after initial code structure analysis, I need\n"
            "a critical decision from the product team.\n\n"
            "Decision Required:\n"
            "The requirements mention 1M+ events/sec scalability.\n"
            "This is a critical threshold that affects architecture:\n\n"
            "Option A: Monolithic Approach\n"
            "- Faster to build (2 days remaining)\n"
            "- Adequate for ~100K-500K events/sec\n"
            "- Single point of failure risk\n"
            "- Easier to debug and monitor\n\n"
            "Option B: Microservices Approach\n"
            "- Handles 1M+ events/sec with ease\n"
            "- Distributed complexity (harder to debug)\n"
            "- Requires ~4 more days\n"
            "- Better resilience and scalability\n\n"
            "Product Question:\n"
            "Given the 1M+ events/sec requirement,\n"
            "which architecture should we commit to?\n\n"
            "Current Code: Basic monolithic structure created\n"
            "Waiting for decision before continuing"
        ),
    )

    # Developer Resume After Feedback
    config.add_agent_response_pattern(
        agent_id="developer-resume",
        pattern=r".*resume.*|.*feedback.*",
        response=(
            "Implementation Resumed\n\n"
            "Decision Received: USE MICROSERVICES ARCHITECTURE\n\n"
            "Action Taken:\n"
            "✓ Migrating from monolithic to microservices\n"
            "✓ Implementing event ingestion service\n"
            "✓ Implementing stream processing service\n"
            "✓ Implementing storage aggregation service\n\n"
            "Implementation Progress:\n"
            "✓ Service boundaries defined\n"
            "✓ API contracts established\n"
            "✓ Event schema finalized\n"
            "✓ Deployment strategy planned\n"
            "✓ 95% of implementation complete\n\n"
            "Code Statistics:\n"
            "- Lines of Code: 420\n"
            "- Services: 3\n"
            "- API Endpoints: 8\n"
            "- Unit Tests: 16\n"
            "- Coverage: 91%\n\n"
            "Status: Ready for code review"
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
            "Comments: 4\n\n"
            "Microservices Architecture Review:\n"
            "✓ Service separation is clean\n"
            "✓ API contracts well-defined\n"
            "✓ Error handling is comprehensive\n"
            "✓ Monitoring hooks in place\n"
            "✓ Good documentation\n\n"
            "Suggestions:\n"
            "1. Add distributed tracing\n"
            "2. Monitor inter-service latency\n"
            "3. Document scaling strategy\n\n"
            "Approval: GRANTED\n"
            "Ready for testing"
        ),
    )

    # Stage 5: Test Engineer
    config.add_agent_response_pattern(
        agent_id="test-engineer",
        pattern=r".*",
        response=(
            "Test Execution Complete ✓\n\n"
            "Test Results:\n"
            "Total Tests: 16\n"
            "Passed: 16 ✓\n"
            "Failed: 0\n"
            "Duration: 4.5s\n\n"
            "Test Coverage:\n"
            "Line Coverage: 91%\n"
            "Branch Coverage: 87%\n"
            "Function Coverage: 100%\n\n"
            "Integration Tests:\n"
            "✓ Event ingestion from multiple sources\n"
            "✓ Stream processing with high throughput\n"
            "✓ Storage aggregation\n"
            "✓ Service-to-service communication\n"
            "✓ Failure recovery\n"
            "✓ Load balancing\n"
            "✓ Rate limiting\n"
            "✓ Monitoring and logging\n"
            "✓ API endpoints\n"
            "✓ Data consistency\n"
            "✓ Concurrent processing\n"
            "✓ Timeout handling\n"
            "✓ Resource cleanup\n"
            "✓ Configuration updates\n"
            "✓ Health checks\n"
            "✓ Performance metrics\n\n"
            "Performance:\n"
            "- Event processing: 95K events/sec per instance\n"
            "- Latency: 45ms average\n"
            "- 3 instances handle 285K+ events/sec\n"
            "- Easily scales to 1M+ events/sec\n\n"
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
            "Version: 1.0.0\n"
            "Status: SUCCESS\n\n"
            "Microservices Deployment:\n"
            "✓ Event Ingestion Service (3 replicas)\n"
            "✓ Stream Processing Service (5 replicas)\n"
            "✓ Storage Aggregation Service (3 replicas)\n"
            "✓ Service mesh configured (Istio)\n"
            "✓ Load balancing active\n"
            "✓ Distributed tracing enabled\n"
            "✓ Monitoring and alerting configured\n\n"
            "Smoke Tests:\n"
            "✓ High throughput load test: PASSED\n"
            "✓ Multi-source event processing: PASSED\n"
            "✓ Failover scenarios: PASSED\n"
            "✓ Canary traffic: 5% → OK\n"
            "✓ Blue-green swap: COMPLETED\n\n"
            "Status: READY FOR PRODUCTION"
        ),
    )

    # Configure container for test execution
    config.set_container_command_result(
        command="pytest",
        exit_code=0,
        stdout="====== 16 passed in 4.5s ======",
        stderr="",
    )

    return config


async def run_scenario(runner: SimulationRunner) -> None:
    """
    Execute the SDLC with escalation and human feedback scenario.

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

    # ===== STAGE 3: Implementation (Initial - ESCALATION) =====
    runner.assert_true(
        True,
        "implementation_started",
        "Starting implementation with architecture decision point",
    )
    await runner.advance_time(timedelta(minutes=4))

    # Verify escalation is triggered
    escalation_events = runner.get_events_by_type("EscalationTriggered")
    runner.assert_true(
        len(escalation_events) > 0,
        "escalation_triggered",
        "Escalation should be triggered",
    )

    runner.assert_event_occurred(
        "HumanFeedbackRequested",
        assertion_name="human_feedback_requested",
    )

    await runner.advance_time(timedelta(minutes=1))

    # ===== Human Feedback Phase =====
    runner.assert_true(
        True,
        "human_feedback_phase",
        "Collecting human feedback on architecture decision",
    )

    # Simulate human decision wait time
    await runner.advance_time(timedelta(minutes=5))

    # Verify human feedback received
    human_feedback_events = runner.get_events_by_type("HumanFeedbackReceived")
    runner.assert_true(
        len(human_feedback_events) > 0,
        "human_feedback_received",
        "Human feedback should be received",
    )

    runner.assert_event_occurred(
        "CommentAdded",
        assertion_name="feedback_recorded",
    )

    await runner.advance_time(timedelta(minutes=1))

    # ===== Implementation Resumed =====
    runner.assert_true(True, "implementation_resumed", "Implementation resumed with feedback")
    await runner.advance_time(timedelta(minutes=9))

    # Verify pipeline resumed event
    pipeline_resumed_events = runner.get_events_by_type("PipelineResumed")
    runner.assert_true(
        len(pipeline_resumed_events) > 0,
        "pipeline_resumed",
        "Pipeline should resume after feedback",
    )

    runner.assert_event_occurred(
        "AgentExecutionCompleted",
        assertion_name="implementation_complete",
    )

    await runner.advance_time(timedelta(minutes=2))

    # ===== STAGE 4: Code Review =====
    runner.assert_true(True, "code_review_started", "Starting code review")
    await runner.advance_time(timedelta(minutes=6))

    approved_events = runner.get_events_by_type("ReviewApproved")
    runner.assert_equal(
        len(approved_events),
        1,
        "code_review_approved",
        "Code review should be approved",
    )

    await runner.advance_time(timedelta(minutes=1))

    # ===== STAGE 5: Testing & QA =====
    runner.assert_true(True, "testing_started", "Starting testing phase")
    await runner.advance_time(timedelta(minutes=5))

    runner.assert_event_occurred(
        "AgentExecutionCompleted",
        assertion_name="testing_complete",
    )

    # Verify all tests passed
    failed_tests = runner.get_events_by_type("TestFailed")
    runner.assert_equal(
        len(failed_tests),
        0,
        "no_test_failures",
        "No test failures",
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

    # Verify workflow completed
    workflow_completed_events = runner.get_events_by_type("WorkflowCompleted")
    runner.assert_equal(
        len(workflow_completed_events),
        1,
        "workflow_completed",
        "Workflow should complete successfully",
    )

    # Verify escalation and feedback loop
    runner.assert_equal(
        len(escalation_events),
        1,
        "single_escalation",
        "Should have exactly 1 escalation",
    )

    runner.assert_equal(
        len(human_feedback_events),
        1,
        "human_feedback_received_count",
        "Should receive human feedback",
    )

    runner.assert_equal(
        len(pipeline_resumed_events),
        1,
        "pipeline_resumed_once",
        "Pipeline should resume once",
    )

    # Verify all stages completed after escalation resolution
    stage_completed_events = runner.get_events_by_type("StageCompleted")
    runner.assert_true(
        len(stage_completed_events) >= 6,
        "all_stages_complete",
        "All 6+ stages should complete",
    )

    # Verify sufficient events captured for complete flow with escalation
    runner.assert_true(
        len(runner.captured_events) >= 50,
        "sufficient_events_with_escalation",
        f"Should capture at least 50 events (escalation + feedback + resumption), got {len(runner.captured_events)}",
    )

    # Verify escalation was resolved
    escalation_resolved_events = runner.get_events_by_type("EscalationResolved")
    runner.assert_true(
        len(escalation_resolved_events) > 0,
        "escalation_resolved",
        "Escalation should be resolved",
    )

    # Verify no review rejections (different from escalation)
    rejected_events = runner.get_events_by_type("ReviewRejected")
    runner.assert_equal(
        len(rejected_events),
        0,
        "no_review_rejections",
        "No code review rejections",
    )
