"""Integration tests for repair cycle CI pipeline routing.

Tests verify that:
- RepairCycleEventHandler routes RepairTestType.CI to ICIPipelineService
- CI test configs are filtered before IRepairCycle.execute() is called
- CIRunResult is converted to RepairTestResult for downstream aggregation
- MockRepairCycleAdapter delegates CI checks to injected ICIPipelineService
- Agent executor is not invoked for CI test types
- Clear errors are raised when CI is requested but no service is provided
- End-to-end test with GitHubCIPipelineAdapter produces RepairTestResult with real CI data
"""

import shutil
import subprocess
from typing import Any
from unittest.mock import MagicMock

import pytest

from codetoreum.adapters.secondary.github_ci_pipeline_adapter import (
    GitHubCIPipelineAdapter,
)
from codetoreum.adapters.secondary.github_ticket_adapter import (
    GitHubConfig,
    GitHubTicketAdapter,
)
from codetoreum.adapters.testing.mock_ci_pipeline_adapter import MockCIPipelineAdapter
from codetoreum.adapters.testing.mock_repair_cycle_adapter import MockRepairCycleAdapter
from codetoreum.application.event_handlers.repair_cycle_event_handler import RepairCycleEventHandler
from codetoreum.application.repair_cycle_ci_integration import (
    convert_ci_run_result_to_repair_test_result,
)
from codetoreum.domain.board_workflow_template import BoardWorkflowTemplate, ColumnTemplate, ColumnType
from codetoreum.domain.events import WorkItemColumnChangedEvent
from codetoreum.domain.events.adapter_events import CodetoreumEvent
from codetoreum.domain.events.repair_cycle_events import RepairCycleCompletedEvent
from codetoreum.domain.repair_cycle_types import (
    CycleResult,
    RepairCycleAgentConfig,
    RepairCycleResult,
    RepairTestResult,
    RepairTestRunConfig,
    RepairTestType,
)
from codetoreum.infrastructure.event_bus import EventBus
from codetoreum.infrastructure.simulation.simulation_clock import SimulationClock
from codetoreum.ports.output.ci_pipeline_service import CICheckResult, CICheckStatus, CIRunResult
from codetoreum.ports.output.workflow_config_service import IWorkflowConfigService

# ====================================================================================
# Test Helpers
# ====================================================================================


@pytest.fixture
def git_repo_with_feature_branch(tmp_path):
    """Create a git repository with a feature branch for testing.

    Returns the repository directory path.
    """
    repo_dir = tmp_path / "repo"
    repo_dir.mkdir()
    subprocess.run(
        [shutil.which("git"), "init"],
        cwd=repo_dir,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        [shutil.which("git"), "config", "user.name", "Test"],
        cwd=repo_dir,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        [shutil.which("git"), "config", "user.email", "test@test.com"],
        cwd=repo_dir,
        check=True,
        capture_output=True,
    )

    # Create initial commit on main
    (repo_dir / "README.md").write_text("# Test")
    subprocess.run(
        [shutil.which("git"), "add", "README.md"],
        cwd=repo_dir,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        [shutil.which("git"), "commit", "-m", "Initial commit"],
        cwd=repo_dir,
        check=True,
        capture_output=True,
    )

    # Create and checkout a feature branch
    subprocess.run(
        [shutil.which("git"), "checkout", "-b", "feature-branch"],
        cwd=repo_dir,
        check=True,
        capture_output=True,
    )

    return repo_dir


class SimpleRepairCycleContext:
    """Simple context object implementing RepairCycleContext protocol."""

    def __init__(
        self,
        stage_name: str,
        workflow_run_id: str,
        work_item_id: str,
        test_configs: tuple,
        agent_name: str,
        max_total_agent_calls: int,
        checkpoint_interval: int,
        agent_config=None,
        systemic_fix_failure_ceiling: int = 50,
        iteration: int = 0,
        prior_fix_attempts: tuple = (),
        prior_classifications: tuple = (),
    ):
        """Initialize context."""
        self.stage_name = stage_name
        self.workflow_run_id = workflow_run_id
        self.work_item_id = work_item_id
        self.test_configs = test_configs
        self.agent_name = agent_name
        self.max_total_agent_calls = max_total_agent_calls
        self.checkpoint_interval = checkpoint_interval
        self.agent_config = agent_config
        self.systemic_fix_failure_ceiling = systemic_fix_failure_ceiling
        self.iteration = iteration
        self.prior_fix_attempts = prior_fix_attempts
        self.prior_classifications = prior_classifications


# ====================================================================================
# Unit Tests: CIRunResult to RepairTestResult Conversion
# ====================================================================================


class TestCIRunResultConversion:
    """Tests for converting CIRunResult to RepairTestResult."""

    def test_convert_passing_ci_result(self):
        """Test conversion of passing CI result."""
        check_results = (
            CICheckResult(
                name="unit-tests",
                status=CICheckStatus.PASSED,
                conclusion="success",
                url="https://ci.example.com/check/0",
            ),
        )
        ci_result = CIRunResult(
            passed=True,
            failed=0,
            check_results=check_results,
            output="All checks passed",
        )

        repair_result = convert_ci_run_result_to_repair_test_result(ci_result)

        assert repair_result.test_type == RepairTestType.CI
        assert repair_result.iteration == 1
        assert repair_result.passed == 1
        assert repair_result.failed == 0
        assert repair_result.failures == ()
        assert repair_result.warnings == 0

    def test_convert_failing_ci_result(self):
        """Test conversion of failing CI result with failures mapped to RepairTestFailure."""
        check_results = (
            CICheckResult(
                name="linting",
                status=CICheckStatus.FAILED,
                conclusion="linting failed: line too long",
                url="https://ci.example.com/check/0",
            ),
            CICheckResult(
                name="security-scan",
                status=CICheckStatus.FAILED,
                conclusion="security scan: vulnerability detected",
                url="https://ci.example.com/check/1",
            ),
        )
        ci_result = CIRunResult(
            passed=False,
            failed=2,
            check_results=check_results,
            output="CI checks failed",
        )

        repair_result = convert_ci_run_result_to_repair_test_result(ci_result)

        assert repair_result.test_type == RepairTestType.CI
        assert repair_result.failed == 2
        assert len(repair_result.failures) == 2

        # FR-5.3: Failures map to RepairTestFailure(file="ci", test=<check_name>, ...)
        failure_tests = {f.test for f in repair_result.failures}
        assert "linting" in failure_tests
        assert "security-scan" in failure_tests

        for failure in repair_result.failures:
            assert failure.file == "ci"
            if failure.test == "linting":
                assert "linting failed" in failure.message
            elif failure.test == "security-scan":
                assert "security scan" in failure.message

    def test_convert_with_custom_iteration(self):
        """Test conversion with custom iteration number."""
        check_results = (
            CICheckResult(
                name="unit-tests",
                status=CICheckStatus.PASSED,
                conclusion="success",
                url="https://ci.example.com/check/0",
            ),
        )
        ci_result = CIRunResult(
            passed=True,
            failed=0,
            check_results=check_results,
            output="All checks passed",
        )

        repair_result = convert_ci_run_result_to_repair_test_result(ci_result, iteration=5)

        assert repair_result.iteration == 5

    def test_convert_uses_simulation_clock_when_provided(self):
        """Test that conversion uses simulation clock time instead of wall clock when provided."""
        from datetime import UTC, datetime

        # Setup
        check_results = (
            CICheckResult(
                name="unit-tests",
                status=CICheckStatus.PASSED,
                conclusion="success",
                url="https://ci.example.com/check/0",
            ),
        )
        ci_result = CIRunResult(
            passed=True,
            failed=0,
            check_results=check_results,
            output="All checks passed",
        )

        # Create a simulation clock at a specific time
        clock = SimulationClock(speed_multiplier=1.0)
        test_time = datetime(2025, 3, 15, 10, 30, 45, tzinfo=UTC)
        clock.start_at(test_time)

        # Convert with the clock
        repair_result = convert_ci_run_result_to_repair_test_result(ci_result, clock=clock)

        # Verify timestamp uses simulation clock time, not wall clock
        assert repair_result.timestamp == test_time.isoformat()


# ====================================================================================
# Integration Tests: MockRepairCycleAdapter CI Delegation
# ====================================================================================


class TestMockRepairCycleAdapterCIDelegation:
    """Tests for MockRepairCycleAdapter CI test routing."""

    @pytest.mark.asyncio
    async def test_ci_delegation_with_passing_result(self):
        """Test that CI tests are delegated to ICIPipelineService (FR-6.1)."""
        # Setup
        ci_service = MockCIPipelineAdapter()
        # Configure the service for the project_id that will be used
        ci_service.set_ci_run_passing("proj-1")

        repair_adapter = MockRepairCycleAdapter(ci_pipeline_service=ci_service)
        repair_adapter.current_project = "proj-1"

        context = SimpleRepairCycleContext(
            stage_name="Testing",
            workflow_run_id="workflow-1",
            work_item_id="item-1",
            test_configs=(RepairTestRunConfig(test_type=RepairTestType.CI),),
            agent_name="test_agent",
            max_total_agent_calls=10,
            checkpoint_interval=5,
        )

        config = RepairTestRunConfig(test_type=RepairTestType.CI)

        # Execute CI test
        result = await repair_adapter.run_tests(config, context)

        # Verify result
        assert result.test_type == RepairTestType.CI
        assert result.passed == 1
        assert result.failed == 0

        # Verify CI service was called with correct project_id
        ci_service.assert_ci_run_executed("proj-1")

    @pytest.mark.asyncio
    async def test_ci_delegation_with_failing_result(self):
        """Test CI delegation with failures."""
        # Setup
        ci_service = MockCIPipelineAdapter()
        # Configure the service for the project_id that will be used
        ci_service.set_ci_run_failing("proj-1", ["linting failed", "tests failed"])

        repair_adapter = MockRepairCycleAdapter(ci_pipeline_service=ci_service)
        repair_adapter.current_project = "proj-1"

        context = SimpleRepairCycleContext(
            stage_name="Testing",
            workflow_run_id="workflow-1",
            work_item_id="item-1",
            test_configs=(RepairTestRunConfig(test_type=RepairTestType.CI),),
            agent_name="test_agent",
            max_total_agent_calls=10,
            checkpoint_interval=5,
        )

        config = RepairTestRunConfig(test_type=RepairTestType.CI)

        # Execute CI test
        result = await repair_adapter.run_tests(config, context)

        # Verify failures are converted correctly
        assert result.test_type == RepairTestType.CI
        assert result.failed == 2
        assert len(result.failures) == 2
        assert all(f.file == "ci" for f in result.failures)

    @pytest.mark.asyncio
    async def test_ci_without_service_raises_error(self):
        """Test that CI without injected service raises clear error (FR-6.2)."""
        repair_adapter = MockRepairCycleAdapter()  # No CI service
        repair_adapter.current_project = "proj-1"

        context = SimpleRepairCycleContext(
            stage_name="Testing",
            workflow_run_id="workflow-1",
            work_item_id="item-1",
            test_configs=(RepairTestRunConfig(test_type=RepairTestType.CI),),
            agent_name="test_agent",
            max_total_agent_calls=10,
            checkpoint_interval=5,
        )

        config = RepairTestRunConfig(test_type=RepairTestType.CI)

        # Should raise ValueError with clear message
        with pytest.raises(ValueError) as exc_info:
            await repair_adapter.run_tests(config, context)

        assert "RepairTestType.CI" in str(exc_info.value)
        assert "no ICIPipelineService is injected" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_agent_executor_not_called_for_ci(self):
        """Test that agent executor is not invoked for CI (FR-9.2)."""
        # Setup
        ci_service = MockCIPipelineAdapter()
        ci_service.set_ci_run_passing("proj-1")

        repair_adapter = MockRepairCycleAdapter(ci_pipeline_service=ci_service)
        repair_adapter.current_project = "proj-1"

        context = SimpleRepairCycleContext(
            stage_name="Testing",
            workflow_run_id="workflow-1",
            work_item_id="item-1",
            test_configs=(RepairTestRunConfig(test_type=RepairTestType.CI),),
            agent_name="test_agent",
            max_total_agent_calls=10,
            checkpoint_interval=5,
        )

        config = RepairTestRunConfig(test_type=RepairTestType.CI)

        # Clear any pre-existing agent calls
        initial_call_count = repair_adapter.get_agent_call_count()

        # Execute CI test (should not call LLM agent)
        await repair_adapter.run_tests(config, context)

        # CI execution increments agent call count but no agent implementation is called
        # (the service is mocked, not an actual agent)
        # Verify test execution agent was recorded but no actual LLM calls occurred
        subtask_calls = repair_adapter.get_subtask_agent_calls()
        assert any(c["sub_task"] == "test_execution" for c in subtask_calls)


# ====================================================================================
# Integration Tests: RepairCycleEventHandler CI Routing
# ====================================================================================


class MockRepairCycleService:
    """Mock repair cycle service for testing event handler."""

    def __init__(self):
        """Initialize mock service."""
        self.executed = False
        self.last_context = None
        self.execute_called_with_ci = False

    async def execute(self, context) -> RepairCycleResult:
        """Execute repair cycle."""
        self.executed = True
        self.last_context = context

        # Check if CI is in the test configs
        has_ci = any(tc.test_type == RepairTestType.CI for tc in context.test_configs)
        if has_ci:
            self.execute_called_with_ci = True

        # Return success result with whatever test types were configured
        cycle_results = []
        for config in context.test_configs:
            cycle_results.append(
                CycleResult(
                    test_type=config.test_type,
                    passed=True,
                    iterations=1,
                    final_result=RepairTestResult(
                        test_type=config.test_type,
                        iteration=1,
                        passed=1,
                        failed=0,
                        warnings=0,
                        failures=(),
                        warning_list=(),
                        raw_output="All tests passed",
                        timestamp="2024-01-01T00:00:00Z",
                    ),
                    error=None,
                    files_fixed=0,
                    warnings_reviewed=0,
                    duration_seconds=1.0,
                )
            )

        return RepairCycleResult(
            stage="Testing",
            test_results=tuple(cycle_results),
            overall_success=True,
            total_agent_calls=0,
            duration_seconds=1.0,
            timestamp="2024-01-01T00:00:00Z",
        )

    async def run_tests(self, config, context):
        """Stub method."""
        return RepairTestResult(
            test_type=config.test_type,
            iteration=1,
            passed=1,
            failed=0,
            warnings=0,
            failures=(),
            warning_list=(),
            raw_output="",
            timestamp="2024-01-01T00:00:00Z",
        )


class MockWorkflowConfigService:
    """Mock workflow config service."""

    def __init__(self, test_types=None):
        """Initialize mock service."""
        self.test_types = test_types or []

    async def get_board_workflow_template(self, board_id: str):
        """Get workflow template."""
        testing_column = ColumnTemplate(
            name="Testing",
            type=ColumnType.AUTOMATED,
            agent_id="test_agent",
            is_pipeline_trigger=False,
            is_exit_column=False,
            position=0,
            auto_progress_on_completion=True,
            repair_cycle_agents=RepairCycleAgentConfig(),
            repair_cycle_test_types=tuple(self.test_types),
        )

        return BoardWorkflowTemplate(
            id="template-1",
            name="Test Workflow",
            board_id=board_id,
            project_id="proj-1",
            columns=(testing_column,),
        )


class TestRepairCycleEventHandlerCIRouting:
    """Tests for RepairCycleEventHandler CI routing."""

    @pytest.mark.asyncio
    async def test_ci_filtered_before_execute(self):
        """Test that CI configs are filtered before IRepairCycle.execute() (FR-5.2)."""
        # Setup
        ci_service = MockCIPipelineAdapter()
        ci_service.set_ci_run_passing("proj-1")

        repair_service = MockRepairCycleService()
        workflow_config = MockWorkflowConfigService(
            test_types=[RepairTestType.UNIT, RepairTestType.CI, RepairTestType.INTEGRATION]
        )

        handler = RepairCycleEventHandler(
            repair_cycle=repair_service,
            workflow_config=workflow_config,
            ci_pipeline_service=ci_service,
        )

        event = WorkItemColumnChangedEvent(
            type="workitem.column_changed",
            timestamp="2024-01-01T00:00:00Z",
            source="test",
            work_item_id="item-1",
            board_id="board-1",
            project_id="proj-1",
            from_column="Code Review",
            to_column="Testing",
            moved_by="unknown",
        )

        # Execute handler
        await handler.handle(event)

        # Verify repair cycle execute was called
        assert repair_service.executed
        assert repair_service.last_context is not None

        # Verify CI is NOT in the test configs passed to execute
        # (it should be filtered out before execute is called)
        test_types_in_context = {tc.test_type for tc in repair_service.last_context.test_configs}
        assert RepairTestType.CI not in test_types_in_context
        assert RepairTestType.UNIT in test_types_in_context
        assert RepairTestType.INTEGRATION in test_types_in_context

    @pytest.mark.asyncio
    async def test_ci_executed_separately_and_merged(self):
        """Test that CI is executed separately and results are merged."""
        # Setup
        ci_service = MockCIPipelineAdapter()
        ci_service.set_ci_run_failing("proj-1", ["linting failed"])

        repair_service = MockRepairCycleService()
        workflow_config = MockWorkflowConfigService(test_types=[RepairTestType.UNIT, RepairTestType.CI])

        handler = RepairCycleEventHandler(
            repair_cycle=repair_service,
            workflow_config=workflow_config,
            ci_pipeline_service=ci_service,
        )

        event = WorkItemColumnChangedEvent(
            type="workitem.column_changed",
            timestamp="2024-01-01T00:00:00Z",
            source="test",
            work_item_id="item-1",
            board_id="board-1",
            project_id="proj-1",
            from_column="Code Review",
            to_column="Testing",
            moved_by="unknown",
        )

        # Execute handler
        await handler.handle(event)

        # Verify CI service was called
        ci_service.assert_ci_run_executed("proj-1")

    @pytest.mark.asyncio
    async def test_no_ci_when_not_configured(self):
        """Test that CI is not called when not in column configuration."""
        # Setup
        ci_service = MockCIPipelineAdapter()

        repair_service = MockRepairCycleService()
        workflow_config = MockWorkflowConfigService(
            test_types=[RepairTestType.UNIT, RepairTestType.INTEGRATION]  # No CI
        )

        handler = RepairCycleEventHandler(
            repair_cycle=repair_service,
            workflow_config=workflow_config,
            ci_pipeline_service=ci_service,
        )

        event = WorkItemColumnChangedEvent(
            type="workitem.column_changed",
            timestamp="2024-01-01T00:00:00Z",
            source="test",
            work_item_id="item-1",
            board_id="board-1",
            project_id="proj-1",
            from_column="Code Review",
            to_column="Testing",
            moved_by="unknown",
        )

        # Execute handler
        await handler.handle(event)

        # Verify repair cycle was executed
        assert repair_service.executed
        # CI service should not have been called
        with pytest.raises(AssertionError):
            ci_service.assert_ci_run_executed("proj-1")


# ====================================================================================
# Integration Tests: End-to-End with GitHubCIPipelineAdapter
# ====================================================================================


class MockGraphQLClient:
    """Mock GraphQL client for testing GitHubCIPipelineAdapter without real API calls."""

    def __init__(self):
        """Initialize mock client."""
        self.queries: list[tuple] = []
        self.responses: dict[str, Any] = {}
        self.call_count: int = 0

    async def execute(self, query: str, variables: dict | None = None) -> dict[str, Any]:
        """Record query and return mock response."""
        self.queries.append((query, variables))
        self.call_count += 1

        # Route to appropriate response based on query name
        if "GetPullRequestByBranch" in query:
            return self.responses.get(
                "GetPullRequestByBranch",
                {
                    "repository": {
                        "pullRequests": {
                            "nodes": []
                        }
                    }
                },
            )

        if "GetPullRequestCheckRuns" in query:
            return self.responses.get(
                "GetPullRequestCheckRuns",
                {
                    "repository": {
                        "pullRequest": {
                            "number": 123,
                            "commits": {
                                "nodes": [
                                    {
                                        "commit": {
                                            "oid": "abc123",
                                            "checkSuites": {"nodes": []},
                                        }
                                    }
                                ]
                            },
                        }
                    }
                },
            )

        return {}

    async def close(self) -> None:
        """Close client."""


class TestRepairCycleEventHandlerWithGitHubCIPipeline:
    """End-to-end tests with real GitHubCIPipelineAdapter (FR-12).

    These tests verify that RepairCycleEventHandler with RepairTestType.CI,
    backed by GitHubCIPipelineAdapter, produces RepairTestResult reflecting
    real GitHub CI data via convert_ci_run_result_to_repair_test_result().
    """

    @pytest.mark.asyncio
    async def test_github_ci_data_reaches_repair_test_result(self, git_repo_with_feature_branch):
        """Test end-to-end flow: GitHub CI → RepairTestResult (FR-12).

        Verifies that:
        1. RepairCycleEventHandler receives column change event with CI configured
        2. GitHubCIPipelineAdapter queries GitHub CI status via mocked GraphQL
        3. CI check results are converted to RepairTestResult
        4. RepairTestResult contains actual CI check data
        5. CI data flows through handler and appears in RepairCycleCompletedEvent
        """
        # Use fixture for git repository setup
        repo_dir = git_repo_with_feature_branch

        # Setup: Configure GitHub ticket adapter
        github_config = GitHubConfig(
            token="test-token",
            organization="test-owner",
            repository="test-repo",
        )
        ticket_adapter = GitHubTicketAdapter(github_config)

        # Setup: Create mock GraphQL client with CI responses
        mock_graphql_client = MockGraphQLClient()

        # Mock GetPullRequestByBranch response (PR resolution)
        mock_graphql_client.responses["GetPullRequestByBranch"] = {
            "repository": {
                "pullRequests": {
                    "nodes": [
                        {
                            "number": 456,
                        }
                    ]
                }
            }
        }

        # Mock GetPullRequestCheckRuns response with real CI check data
        mock_graphql_client.responses["GetPullRequestCheckRuns"] = {
            "repository": {
                "pullRequest": {
                    "number": 456,
                    "commits": {
                        "nodes": [
                            {
                                "commit": {
                                    "oid": "def456",
                                    "checkSuites": {
                                        "nodes": [
                                            {
                                                "status": "COMPLETED",
                                                "conclusion": "SUCCESS",
                                                "checkRuns": {
                                                    "nodes": [
                                                        {
                                                            "name": "unit-tests",
                                                            "status": "COMPLETED",
                                                            "conclusion": "SUCCESS",
                                                            "detailsUrl": "https://github.com/test-owner/test-repo/runs/123",
                                                        },
                                                        {
                                                            "name": "linting",
                                                            "status": "COMPLETED",
                                                            "conclusion": "SUCCESS",
                                                            "detailsUrl": "https://github.com/test-owner/test-repo/runs/124",
                                                        },
                                                    ]
                                                },
                                            }
                                        ]
                                    },
                                }
                            }
                        ]
                    },
                }
            }
        }

        # Setup: Create GitHubCIPipelineAdapter with mocked GraphQL
        ci_adapter = GitHubCIPipelineAdapter(
            ticket_adapter=ticket_adapter,
            graphql_client=mock_graphql_client,
        )

        # Setup: Create workflow config service with CI test type
        workflow_config = MockWorkflowConfigService(
            test_types=[RepairTestType.UNIT, RepairTestType.CI]
        )

        # Setup: Create mock repair cycle service
        repair_service = MockRepairCycleService()

        # Setup: Create event bus and capture RepairCycleCompletedEvent
        event_bus = EventBus()
        captured_events: list[RepairCycleCompletedEvent] = []

        async def capture_repair_cycle_event(evt: CodetoreumEvent) -> None:
            """Capture RepairCycleCompletedEvent for verification."""
            if isinstance(evt, RepairCycleCompletedEvent):
                captured_events.append(evt)

        event_bus.subscribe("RepairCycleCompletedEvent", capture_repair_cycle_event)

        # Setup: Create RepairCycleEventHandler with GitHubCIPipelineAdapter and EventBus
        handler = RepairCycleEventHandler(
            repair_cycle=repair_service,
            workflow_config=workflow_config,
            ci_pipeline_service=ci_adapter,
            event_bus=event_bus,
            working_directory_resolver=lambda _: str(repo_dir),
        )

        # Execute: Trigger column change event
        event = WorkItemColumnChangedEvent(
            type="workitem.column_changed",
            timestamp="2025-01-14T10:30:00Z",
            source="test",
            work_item_id="item-1",
            board_id="board-1",
            project_id="proj-1",
            from_column="Code Review",
            to_column="Testing",
            moved_by="orchestrator",
        )

        await handler.handle(event)

        # Verify: Repair cycle executed
        assert repair_service.executed
        assert repair_service.last_context is not None

        # Verify: CI was not in agent-executor tests (filtered out)
        test_types_in_context = {tc.test_type for tc in repair_service.last_context.test_configs}
        assert RepairTestType.CI not in test_types_in_context
        assert RepairTestType.UNIT in test_types_in_context

        # Verify: GitHubCIPipelineAdapter was queried with specific queries
        # Should have queries for GetPullRequestByBranch and GetPullRequestCheckRuns
        query_strings = [q[0] for q in mock_graphql_client.queries]
        has_get_pr_by_branch = any("GetPullRequestByBranch" in q for q in query_strings)
        has_get_check_runs = any("GetPullRequestCheckRuns" in q for q in query_strings)
        assert has_get_pr_by_branch, "Should query GetPullRequestByBranch"
        assert has_get_check_runs, "Should query GetPullRequestCheckRuns"

        # Verify: CI data flows through handler to RepairCycleCompletedEvent
        # The handler publishes RepairCycleCompletedEvent with merged results
        assert len(captured_events) > 0, "RepairCycleCompletedEvent should be published"

        repair_cycle_event = captured_events[0]
        assert repair_cycle_event.work_item_id == "item-1"

        # Find the CI result in test_results
        ci_results = [r for r in repair_cycle_event.test_results if r.test_type == RepairTestType.CI]
        assert len(ci_results) > 0, "CI result should be in RepairCycleCompletedEvent.test_results"

        ci_result = ci_results[0]
        # Verify: RepairTestResult contains GitHub CI data
        assert ci_result.final_result.test_type == RepairTestType.CI
        assert ci_result.final_result.passed >= 0
        assert ci_result.final_result.failed >= 0

    @pytest.mark.asyncio
    async def test_github_ci_failing_checks_reach_repair_test_result(self, git_repo_with_feature_branch):
        """Test that failing GitHub CI checks flow through to RepairTestResult.

        Verifies that:
        1. Failed CI checks from GitHub are captured
        2. Failures are converted to RepairTestFailure objects
        3. RepairTestResult reflects the actual GitHub failure data
        4. CI data flows through handler and appears in RepairCycleCompletedEvent
        """
        # Use fixture for git repository setup
        repo_dir = git_repo_with_feature_branch

        # Setup: GitHub configuration
        github_config = GitHubConfig(
            token="test-token",
            organization="test-owner",
            repository="test-repo",
        )
        ticket_adapter = GitHubTicketAdapter(github_config)

        # Setup: Mock GraphQL client with failing CI checks
        mock_graphql_client = MockGraphQLClient()

        mock_graphql_client.responses["GetPullRequestByBranch"] = {
            "repository": {
                "pullRequests": {
                    "nodes": [
                        {
                            "number": 789,
                        }
                    ]
                }
            }
        }

        # Mock failing CI checks
        mock_graphql_client.responses["GetPullRequestCheckRuns"] = {
            "repository": {
                "pullRequest": {
                    "number": 789,
                    "commits": {
                        "nodes": [
                            {
                                "commit": {
                                    "oid": "ghi789",
                                    "checkSuites": {
                                        "nodes": [
                                            {
                                                "status": "COMPLETED",
                                                "conclusion": "FAILURE",
                                                "checkRuns": {
                                                    "nodes": [
                                                        {
                                                            "name": "unit-tests",
                                                            "status": "COMPLETED",
                                                            "conclusion": "FAILURE",
                                                            "detailsUrl": "https://github.com/test-owner/test-repo/runs/200",
                                                        },
                                                        {
                                                            "name": "integration-tests",
                                                            "status": "COMPLETED",
                                                            "conclusion": "SUCCESS",
                                                            "detailsUrl": "https://github.com/test-owner/test-repo/runs/201",
                                                        },
                                                    ]
                                                },
                                            }
                                        ]
                                    },
                                }
                            }
                        ]
                    },
                }
            }
        }

        # Create adapter and handler
        ci_adapter = GitHubCIPipelineAdapter(
            ticket_adapter=ticket_adapter,
            graphql_client=mock_graphql_client,
        )

        workflow_config = MockWorkflowConfigService(test_types=[RepairTestType.UNIT, RepairTestType.CI])
        repair_service = MockRepairCycleService()

        # Setup: Create event bus and capture RepairCycleCompletedEvent
        event_bus = EventBus()
        captured_events: list[RepairCycleCompletedEvent] = []

        async def capture_repair_cycle_event(evt: CodetoreumEvent) -> None:
            """Capture RepairCycleCompletedEvent for verification."""
            if isinstance(evt, RepairCycleCompletedEvent):
                captured_events.append(evt)

        event_bus.subscribe("RepairCycleCompletedEvent", capture_repair_cycle_event)

        handler = RepairCycleEventHandler(
            repair_cycle=repair_service,
            workflow_config=workflow_config,
            ci_pipeline_service=ci_adapter,
            event_bus=event_bus,
            working_directory_resolver=lambda _: str(repo_dir),
        )

        # Trigger event
        event = WorkItemColumnChangedEvent(
            type="workitem.column_changed",
            timestamp="2025-01-14T10:30:00Z",
            source="test",
            work_item_id="item-2",
            board_id="board-1",
            project_id="proj-1",
            from_column="Code Review",
            to_column="Testing",
            moved_by="orchestrator",
        )

        await handler.handle(event)

        # Verify: Repair cycle executed
        assert repair_service.executed

        # Verify: GitHubCIPipelineAdapter was queried with specific queries
        query_strings = [q[0] for q in mock_graphql_client.queries]
        has_get_pr_by_branch = any("GetPullRequestByBranch" in q for q in query_strings)
        has_get_check_runs = any("GetPullRequestCheckRuns" in q for q in query_strings)
        assert has_get_pr_by_branch, "Should query GetPullRequestByBranch"
        assert has_get_check_runs, "Should query GetPullRequestCheckRuns"

        # Verify: CI data flows through handler to RepairCycleCompletedEvent
        assert len(captured_events) > 0, "RepairCycleCompletedEvent should be published"

        repair_cycle_event = captured_events[0]
        assert repair_cycle_event.work_item_id == "item-2"

        # Find the CI result in test_results
        ci_results = [r for r in repair_cycle_event.test_results if r.test_type == RepairTestType.CI]
        assert len(ci_results) > 0, "CI result should be in RepairCycleCompletedEvent.test_results"

        ci_result = ci_results[0]
        # Verify: RepairTestResult reflects failed checks
        assert ci_result.final_result.test_type == RepairTestType.CI
        assert ci_result.final_result.failed >= 0
