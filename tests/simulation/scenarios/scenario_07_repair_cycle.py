"""
Scenario 7: Repair Cycle with Iterative Test-Driven Fixing

Work item goes through a repair cycle where AI agent iteratively executes tests,
identifies failures, and fixes issues until tests pass.

Tests repair cycle with two iterations:
- Iteration 1: Tests fail with specific failures
- Agent fixes the identified issues
- Iteration 2: Tests pass

Expected outcome:
- Repair cycle starts with UNIT test type
- Tests fail in iteration 1 (2 failures)
- Agent fixes 1 file with failures
- Tests pass in iteration 2
- Cycle completes successfully
"""

from datetime import timedelta

from codetoreum.domain.events import DomainEvent
from codetoreum.domain.repair_cycle_types import RepairTestType, RepairTestFailure
from codetoreum.infrastructure.simulation import (
    SimulationConfig,
    SimulationRunner,
)


def create_config() -> SimulationConfig:
    """Create configuration for repair cycle scenario."""
    config = SimulationConfig.create_fast_config(
        scenario_name="repair_cycle_iterative_fixing",
        speed_multiplier=50.0,
    )

    config.scenario_description = (
        "Repair cycle with iterative test-driven fixing. Tests fail, agent fixes issues, tests pass."
    )

    # Configure agent responses for repair agent
    config.add_agent_response_pattern(
        agent_id="senior_software_engineer",
        pattern=r".*fix.*",
        response="Fixed the identified test failures by correcting the implementation.",
    )

    return config


async def run_scenario(runner: SimulationRunner) -> None:
    """Execute repair cycle scenario."""
    pipeline_run_id = "pipeline-run-001"

    # Repair cycle starts
    event = DomainEvent(
        aggregate_id=pipeline_run_id,
        aggregate_type="RepairCycle",
        payload={
            "stage_name": "fix_failures",
            "test_types": ["UNIT"],
        },
    )
    event.event_type = "repair_cycle.started"
    runner.capture_event(event)

    # First iteration: Test execution started
    await runner.advance_time(timedelta(minutes=2))

    event = DomainEvent(
        aggregate_id=pipeline_run_id,
        aggregate_type="RepairCycle",
        payload={
            "test_type": "UNIT",
            "test_type_index": 1,
            "test_cycle_iteration": 1,
            "max_test_cycle_iterations": 5,
            "timeout": 900,
        },
    )
    event.event_type = "repair_cycle.test_execution_started"
    runner.capture_event(event)

    # First iteration: Test execution completed with failures
    await runner.advance_time(timedelta(minutes=3))

    event = DomainEvent(
        aggregate_id=pipeline_run_id,
        aggregate_type="RepairCycle",
        payload={
            "test_type": "UNIT",
            "test_type_index": 1,
            "test_cycle_iteration": 1,
            "passed": 5,
            "failed": 2,
            "warnings": 0,
            "has_failures": True,
            "failures": [
                {
                    "file": "test_auth.py",
                    "test": "test_login_validation",
                    "message": "AssertionError: Expected login to succeed with valid credentials",
                },
                {
                    "file": "test_auth.py",
                    "test": "test_password_strength",
                    "message": "AssertionError: Password must be at least 8 characters",
                },
            ],
        },
    )
    event.event_type = "repair_cycle.test_execution_completed"
    runner.capture_event(event)

    runner.assert_event_occurred(
        "repair_cycle.test_execution_completed", assertion_name="first_test_failed"
    )

    # Fix cycle starts
    await runner.advance_time(timedelta(minutes=1))

    event = DomainEvent(
        aggregate_id=pipeline_run_id,
        aggregate_type="RepairCycle",
        payload={
            "test_type": "UNIT",
            "test_type_index": 1,
            "test_cycle_iteration": 1,
            "file_count": 1,
            "total_failures": 2,
        },
    )
    event.event_type = "repair_cycle.fix_cycle_started"
    runner.capture_event(event)

    # File fix started
    await runner.advance_time(timedelta(minutes=1))

    event = DomainEvent(
        aggregate_id=pipeline_run_id,
        aggregate_type="RepairCycle",
        payload={
            "test_file": "src/auth.py",
            "failure_count": 2,
            "test_type": "UNIT",
        },
    )
    event.event_type = "repair_cycle.file_fix_started"
    runner.capture_event(event)

    # Agent fixes the file
    await runner.advance_time(timedelta(minutes=4))

    event = DomainEvent(
        aggregate_id=pipeline_run_id,
        aggregate_type="RepairCycle",
        payload={
            "test_file": "src/auth.py",
            "failure_count": 2,
            "test_type": "UNIT",
            "success": True,
        },
    )
    event.event_type = "repair_cycle.file_fix_completed"
    runner.capture_event(event)

    runner.assert_event_occurred(
        "repair_cycle.file_fix_completed", assertion_name="file_fix_completed"
    )

    # Second iteration: Test execution started (re-test after fix)
    await runner.advance_time(timedelta(minutes=2))

    event = DomainEvent(
        aggregate_id=pipeline_run_id,
        aggregate_type="RepairCycle",
        payload={
            "test_type": "UNIT",
            "test_type_index": 1,
            "test_cycle_iteration": 2,
            "max_test_cycle_iterations": 5,
            "timeout": 900,
        },
    )
    event.event_type = "repair_cycle.test_execution_started"
    runner.capture_event(event)

    # Second iteration: Test execution completed with all passing
    await runner.advance_time(timedelta(minutes=3))

    event = DomainEvent(
        aggregate_id=pipeline_run_id,
        aggregate_type="RepairCycle",
        payload={
            "test_type": "UNIT",
            "test_type_index": 1,
            "test_cycle_iteration": 2,
            "passed": 7,
            "failed": 0,
            "warnings": 0,
            "has_failures": False,
            "failures": [],
        },
    )
    event.event_type = "repair_cycle.test_execution_completed"
    runner.capture_event(event)

    runner.assert_event_occurred(
        "repair_cycle.test_execution_completed", assertion_name="second_test_passed"
    )

    # Test cycle completed (all tests for UNIT type passed)
    await runner.advance_time(timedelta(minutes=1))

    event = DomainEvent(
        aggregate_id=pipeline_run_id,
        aggregate_type="RepairCycle",
        payload={
            "test_type": "UNIT",
            "test_type_index": 1,
            "passed": True,
            "test_cycle_iterations": 2,
            "files_fixed": 1,
            "warnings_reviewed": 0,
            "error": None,
            "duration_seconds": 600.0,
        },
    )
    event.event_type = "repair_cycle.test_cycle_completed"
    runner.capture_event(event)

    # Entire repair cycle completed
    await runner.advance_time(timedelta(minutes=1))

    event = DomainEvent(
        aggregate_id=pipeline_run_id,
        aggregate_type="RepairCycle",
        payload={
            "overall_success": True,
            "test_results": [
                {
                    "test_type": "UNIT",
                    "passed": True,
                    "iterations": 2,
                    "files_fixed": 1,
                    "warnings_reviewed": 0,
                    "duration_seconds": 600.0,
                    "error": None,
                },
            ],
            "total_agent_calls": 1,
            "duration_seconds": 650.0,
        },
    )
    event.event_type = "repair_cycle.completed"
    runner.capture_event(event)

    runner.assert_event_occurred(
        "repair_cycle.completed", assertion_name="cycle_completed"
    )

    # Assertions for event sequence
    runner.assert_event_count(
        "repair_cycle.started", 1, "cycle_started_once"
    )
    runner.assert_event_count(
        "repair_cycle.test_execution_started", 2, "test_started_twice"
    )
    runner.assert_event_count(
        "repair_cycle.test_execution_completed", 2, "test_completed_twice"
    )
    runner.assert_event_count(
        "repair_cycle.fix_cycle_started", 1, "fix_cycle_started_once"
    )
    runner.assert_event_count(
        "repair_cycle.file_fix_started", 1, "file_fix_started_once"
    )
    runner.assert_event_count(
        "repair_cycle.file_fix_completed", 1, "file_fix_completed_once"
    )
    runner.assert_event_count(
        "repair_cycle.test_cycle_completed", 1, "test_cycle_completed_once"
    )


async def test_repair_cycle():
    """Test repair cycle scenario."""
    config = create_config()
    runner = SimulationRunner(config)

    result = await runner.run(run_scenario)
    runner.print_summary()

    assert result.success, f"Scenario failed: {result.errors}"
    assert result.events_captured == 10
    assert result.assertions_passed == 11


if __name__ == "__main__":
    import asyncio

    asyncio.run(test_repair_cycle())
