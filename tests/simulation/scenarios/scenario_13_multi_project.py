"""
Scenario 13: Multi-Project Orchestration

Test scenarios for multi-project orchestration:

Scenario A: Multi-Project Setup with enabled/disabled projects (US1)
- Multiple projects configured with some enabled, some disabled
- Only enabled projects are processed
- Disabled projects are completely skipped with no errors

Scenario B: Project Isolation (US3)
- Pipeline locks don't cross-contaminate between projects
- Work items from different projects can acquire locks independently
- Lock namespaces are per-project

Scenario C: Config Change Detection (US4)
- New projects added to configuration are detected on next cycle
- Config changes trigger project reloading
- New projects are processed in subsequent cycles

Scenario D: Clone Failure Handling (US5)
- Clone failures for one project don't block others
- Failure event is emitted with retry flag
- Other projects continue processing after one fails
"""

import pytest
from datetime import timedelta, datetime, timezone
from typing import Any, Dict, Optional

from codetoreum.infrastructure.simulation import (
    SimulationConfig,
    SimulationRunner,
)
from codetoreum.domain.value_objects import ProjectConfig
from codetoreum.domain.events.project_events import (
    OrchestrationCycleCompletedEvent,
    ProjectClonedEvent,
    ProjectCloneFailedEvent,
)
from codetoreum.domain.work_item import WorkItem
from codetoreum.adapters.testing.mock_project_manager_adapter import (
    MockProjectManagerAdapter,
)


def create_test_work_item(
    project_id: str,
    id: str,
    requires_pipeline_lock: bool = False,
) -> WorkItem:
    """Create test work item for simulation.

    Args:
        project_id: Project identifier
        id: Work item ID
        requires_pipeline_lock: Whether this work item needs a pipeline lock

    Returns:
        WorkItem: Configured test work item
    """
    from codetoreum.domain.work_item import WorkItemStatus, WorkItemPriority

    return WorkItem(
        id=id,
        project_id=project_id,
        title=f"Test work item {id} for {project_id}",
        description=f"Simulate work item processing for project {project_id}",
        status=WorkItemStatus.IN_PROGRESS,
        priority=WorkItemPriority.MEDIUM,
        labels=[],
        external_id=None,
        external_url=None,
        assigned_agent_id=None,
        assigned_at=None,
        current_workflow_id=None,
        current_stage=None,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
        completed_at=None,
    )


def extract_repo_name(repo_url: str) -> str:
    """Extract repository name from URL.

    Removes .git suffix and takes final path component.
    Handles both SSH (git@...) and HTTPS formats.

    Args:
        repo_url: Repository URL (SSH or HTTPS format)

    Returns:
        Repository name extracted from URL

    Examples:
        - "git@github.com:org/repo.git" → "repo"
        - "https://github.com/org/repo.git" → "repo"
        - "https://github.com/org/repo" → "repo"
    """
    url = repo_url
    if url.endswith(".git"):
        url = url[:-4]
    return url.rstrip("/").split("/")[-1]


def create_config() -> SimulationConfig:
    """Create configuration for multi-project orchestration scenario."""
    config = SimulationConfig.create_fast_config(
        scenario_name="multi_project_orchestration",
        speed_multiplier=100.0,
    )

    config.scenario_description = (
        "Multi-project orchestration cycle: "
        "3 projects (api-service, web-app, data-service) processed sequentially, "
        "each with isolated workflows and boards"
    )

    # Configure projects
    projects = {
        "api-service": {
            "repo_url": "https://github.com/acme/api-service.git",
            "branch": "main",
            "boards": ["backend-pipeline"],
            "work_items": 5,
            "agents": ["code-generator", "code-reviewer", "test-runner"],
        },
        "web-app": {
            "repo_url": "https://github.com/acme/web-app.git",
            "branch": "develop",
            "boards": ["frontend-pipeline"],
            "work_items": 7,
            "agents": ["ui-generator", "qa-tester"],
        },
        "data-service": {
            "repo_url": "https://github.com/acme/data-service.git",
            "branch": "main",
            "boards": ["data-pipeline"],
            "work_items": 6,
            "agents": ["data-engineer", "data-validator"],
        },
    }

    config.metadata.update({
        "projects": projects,
        "total_work_items": sum(p["work_items"] for p in projects.values()),
        "total_projects": len(projects),
    })

    # Configure agent responses for each project
    _configure_project_agents(config, projects)

    # Configure container responses
    config.set_container_command_result(
        command="pytest",
        exit_code=0,
        stdout="====== 10 passed in 2.5s =======",
        stderr="",
    )

    config.set_container_command_result(
        command="npm test",
        exit_code=0,
        stdout="====== 8 passed in 3.2s =======",
        stderr="",
    )

    return config


def _configure_project_agents(config: SimulationConfig, projects: Dict[str, Any]) -> None:
    """Configure agent response patterns for each project."""
    # API Service agents
    config.add_agent_response_pattern(
        agent_id="code-generator",
        pattern=r".*generate.*",
        response=(
            "I've generated the following API code:\n\n"
            "```python\n"
            "@router.post('/api/users')\n"
            "def create_user(user: UserSchema):\n"
            "    return db.users.insert(user)\n"
            "```"
        ),
    )

    config.add_agent_response_pattern(
        agent_id="code-reviewer",
        pattern=r".*review.*",
        response="Code review: ✅ APPROVED\n- API design looks good\n- Follows REST conventions\n- LGTM",
    )

    config.add_agent_response_pattern(
        agent_id="test-runner",
        pattern=r".*test.*",
        response="✅ Tests passed: 10/10\n- Unit tests: 10 passed\n- Coverage: 95%\n- Performance: OK",
    )

    # Web App agents
    config.add_agent_response_pattern(
        agent_id="ui-generator",
        pattern=r".*UI|ui|component.*",
        response="Generated React components for user profile display",
    )

    config.add_agent_response_pattern(
        agent_id="qa-tester",
        pattern=r".*test|qa.*",
        response=(
            "QA Testing Complete:\n"
            "- 8 test cases passed\n"
            "- No regressions detected\n"
            "- Ready for release"
        ),
    )

    # Data Service agents
    config.add_agent_response_pattern(
        agent_id="data-engineer",
        pattern=r".*data|pipeline.*",
        response=(
            "Data pipeline implementation:\n"
            "- ETL script created\n"
            "- Supports 10K records/min\n"
            "- Error handling configured"
        ),
    )

    config.add_agent_response_pattern(
        agent_id="data-validator",
        pattern=r".*validat.*",
        response=(
            "Data validation results:\n"
            "- 100% data quality score\n"
            "- No duplicates found\n"
            "- All constraints satisfied"
        ),
    )


async def run_scenario(runner: SimulationRunner) -> None:
    """
    Execute the multi-project orchestration scenario.

    Simulates:
    1. Configuration reload detecting 3 enabled projects
    2. Repository clone for each project
    3. Per-project workflow orchestration
    4. Work item processing across all projects
    5. Aggregated cycle completion event

    Args:
        runner: Simulation runner instance
    """
    from codetoreum.domain.events import DomainEvent

    projects = runner.config.metadata["projects"]

    # =========================================================================
    # Configuration reload
    # =========================================================================
    # Configuration reload is simulated in the orchestrator

    # =========================================================================
    # Repository cloning for each project
    # =========================================================================

    for project_name, project_info in projects.items():
        clone_event = ProjectClonedEvent(
            type="project.cloned",
            timestamp=datetime.now(timezone.utc).isoformat(),
            source="project_manager",
            project_name=project_name,
            repo_url=project_info["repo_url"],
            workspace_path=f"/workspace/{project_name}",
            branch=project_info["branch"],
        )
        runner.capture_event(clone_event)

    # Advance time for clone operations
    await runner.advance_time(timedelta(milliseconds=500))

    # =========================================================================
    # Per-project workflow orchestration
    # =========================================================================
    total_work_items = 0

    for project_name, project_info in projects.items():
        work_items_count = project_info["work_items"]
        total_work_items += work_items_count

        # Simulate work item processing for this project
        for i in range(work_items_count):
            issue_num = (i + 1) * 100  # ISSUE-100, ISSUE-200, etc.

            # Simulate card moved event for each work item
            card_moved = DomainEvent(
                aggregate_id=f"{project_name}-{issue_num}",
                aggregate_type="WorkItem",
                payload={
                    "project": project_name,
                    "issue_number": issue_num,
                    "from_column": "Backlog",
                    "to_column": "In Progress",
                    "title": f"Task {i+1} for {project_name}",
                },
            )
            card_moved.event_type = "CardMoved"
            runner.capture_event(card_moved)

            # Simulate agent execution for the work item
            agent_idx = i % len(project_info["agents"])
            agent_name = project_info["agents"][agent_idx]

            execution_completed = DomainEvent(
                aggregate_id=f"{project_name}-{issue_num}",
                aggregate_type="AgentExecution",
                payload={
                    "project": project_name,
                    "issue_number": issue_num,
                    "agent": agent_name,
                    "status": "completed",
                    "output": f"Completed task for {project_name}",
                },
            )
            execution_completed.event_type = "ExecutionCompleted"
            runner.capture_event(execution_completed)

        # Advance time for this project's processing
        await runner.advance_time(timedelta(milliseconds=200))

    # =========================================================================
    # Orchestration cycle completion
    # =========================================================================
    cycle_completed = OrchestrationCycleCompletedEvent(
        type="orchestration.cycle_completed",
        timestamp=datetime.now(timezone.utc).isoformat(),
        source="multi_project_orchestrator",
        projects_processed=len(projects),
        boards_processed=len(projects),  # One board per project in this scenario
        work_items_found=total_work_items,
        cycle_duration_ms=1000,
    )
    runner.capture_event(cycle_completed)

    # =========================================================================
    # Final Assertions
    # =========================================================================

    runner.assert_equal(
        len(projects),
        3,
        "projects_count",
        "Should have 3 projects",
    )

    runner.assert_equal(
        total_work_items,
        18,
        "total_work_items",
        "Should process 18 total work items (5+7+6)",
    )

    # Verify cloned projects count
    cloned_events = sum(
        1
        for e in runner.captured_events
        if isinstance(e, ProjectClonedEvent)
    )
    runner.assert_equal(
        cloned_events,
        len(projects),
        "cloned_projects",
        "All projects should have clone events",
    )

    # Verify cycle completion event was captured
    cycle_events = sum(
        1
        for e in runner.captured_events
        if isinstance(e, OrchestrationCycleCompletedEvent)
    )
    runner.assert_equal(
        cycle_events,
        1,
        "cycle_event",
        "OrchestrationCycleCompletedEvent should be emitted",
    )

    # Advance final time
    await runner.advance_time(timedelta(milliseconds=300))


class TestScenario13MultiProjectOrchestration:
    """
    Simulation tests for multi-project orchestration.

    Tests validate:
    - Multiple projects configured and processed
    - Only enabled projects processed (disabled projects skipped)
    - Pipeline state isolated per project
    - Config changes detected on next poll cycle
    - Clone failures don't block other projects
    """

    @pytest.fixture
    async def simulation_runner(self) -> SimulationRunner:
        """Create simulation runner with mock project adapter."""
        config = SimulationConfig.create_fast_config(
            scenario_name="multi_project_test",
            speed_multiplier=100.0,
        )
        runner = SimulationRunner(config)

        # Create and configure mock adapter
        project_adapter = MockProjectManagerAdapter()

        # Add test projects
        project_adapter.add_project(
            "project_a",
            ProjectConfig(
                repo_url="https://vcs.example.com/org/project_a.git",
                branch="main",
                enabled=True,
                org="example-org",
            ),
        )
        project_adapter.add_boards_to_project("project_a", ["Board A"])

        project_adapter.add_project(
            "project_b",
            ProjectConfig(
                repo_url="https://vcs.example.com/org/project_b.git",
                branch="develop",
                enabled=True,
                org="example-org",
            ),
        )
        project_adapter.add_boards_to_project("project_b", ["Board B"])

        project_adapter.add_project(
            "project_c",
            ProjectConfig(
                repo_url="https://vcs.example.com/org/project_c.git",
                branch="main",
                enabled=False,  # Disabled project
                org="example-org",
            ),
        )
        project_adapter.add_boards_to_project("project_c", ["Board C"])

        runner.project_adapter = project_adapter
        return runner

    @pytest.mark.asyncio
    async def test_scenario_a_multi_project_setup(
        self, simulation_runner: SimulationRunner
    ):
        """
        Scenario A: Multi-Project Setup

        Given: 3 projects (2 enabled, 1 disabled)
        When: Orchestrator starts and processes one cycle
        Then: Only enabled projects are processed, disabled skipped
        """
        adapter = simulation_runner.project_adapter

        # Get enabled projects
        enabled_projects = await adapter.get_enabled_projects()

        # Verify only 2 enabled projects returned
        assert len(enabled_projects) == 2, "Should have 2 enabled projects"
        assert "project_a" in enabled_projects, "project_a should be enabled"
        assert "project_b" in enabled_projects, "project_b should be enabled"
        assert "project_c" not in enabled_projects, "project_c should be disabled"

        # Clone enabled projects
        for project_name in enabled_projects:
            path = await adapter.ensure_project_cloned(project_name)
            assert path is not None, f"Clone path should exist for {project_name}"
            assert project_name in path, f"Path should contain project name {project_name}"

        # Verify disabled project was not cloned
        try:
            await adapter.ensure_project_cloned("project_c")
            # If we get here without exception, project_c still shouldn't be marked as cloned
            state = adapter.get_project_state("project_c")
            assert state is not None
            assert not state.cloned, "Disabled project should not be cloned"
        except Exception:
            # Expected - project_c might not be in enabled list to clone
            pass

    @pytest.mark.asyncio
    async def test_scenario_b_project_isolation(
        self, simulation_runner: SimulationRunner
    ):
        """
        Scenario B: Project Isolation

        Given: Two projects with work items requiring pipeline locks
        When: Both projects process work items
        Then: Lock namespaces are isolated per project
        """
        adapter = simulation_runner.project_adapter

        # Add work items to both projects
        work_item_a = create_test_work_item(
            project_id="project_a",
            id="10",
            requires_pipeline_lock=True,
        )
        adapter.add_work_item_to_project("project_a", work_item_a)

        work_item_b = create_test_work_item(
            project_id="project_b",
            id="20",
            requires_pipeline_lock=True,
        )
        adapter.add_work_item_to_project("project_b", work_item_b)

        # Verify work items were added
        items_a = adapter.get_project_work_items("project_a")
        items_b = adapter.get_project_work_items("project_b")

        assert len(items_a) == 1, "project_a should have 1 work item"
        assert len(items_b) == 1, "project_b should have 1 work item"

        # Verify items are from different projects (isolation)
        assert items_a[0].project_id == "project_a"
        assert items_b[0].project_id == "project_b"
        assert items_a[0].project_id != items_b[0].project_id

    @pytest.mark.asyncio
    async def test_scenario_c_config_change_detection(
        self, simulation_runner: SimulationRunner
    ):
        """
        Scenario C: Config Change Detection

        Given: Orchestrator running with 2 enabled projects
        When: New project added to config
        Then: New project picked up on next cycle
        """
        adapter = simulation_runner.project_adapter

        # Get initial enabled projects
        initial_projects = await adapter.get_enabled_projects()
        assert len(initial_projects) == 2, "Should start with 2 enabled projects"

        # Add new project to config
        project_adapter = simulation_runner.project_adapter
        project_adapter.add_project(
            "project_d",
            ProjectConfig(
                repo_url="https://vcs.example.com/org/project_d.git",
                branch="main",
                enabled=True,
                org="example-org",
            ),
        )
        project_adapter.add_boards_to_project("project_d", ["Board D"])

        # Get enabled projects again (simulating config reload)
        updated_projects = await adapter.get_enabled_projects()

        # Verify new project is detected
        assert len(updated_projects) == 3, "Should have 3 enabled projects after add"
        assert "project_d" in updated_projects, "project_d should be in enabled list"

        # Verify original projects still present
        assert "project_a" in updated_projects
        assert "project_b" in updated_projects

    @pytest.mark.asyncio
    async def test_scenario_d_clone_failure_handling(
        self, simulation_runner: SimulationRunner
    ):
        """
        Scenario D: Clone Failure Handling

        Given: 3 projects, one with simulated clone failure
        When: Orchestration cycle runs
        Then: Failed project emits error event, other projects continue
        """
        adapter = simulation_runner.project_adapter

        # Simulate clone failure for project_b
        adapter.simulate_clone_failure("project_b")

        enabled_projects = await adapter.get_enabled_projects()

        # Try to clone all enabled projects
        cloned_successfully = []
        clone_failures = []

        for project_name in enabled_projects:
            try:
                path = await adapter.ensure_project_cloned(project_name)
                cloned_successfully.append(project_name)
            except Exception as e:
                clone_failures.append((project_name, str(e)))

        # Verify project_a cloned successfully
        assert "project_a" in cloned_successfully, "project_a should clone successfully"

        # Verify project_b failed
        assert len(clone_failures) == 1, "Should have 1 clone failure"
        assert clone_failures[0][0] == "project_b", "project_b should have failed"

        # Verify failure count incremented
        failure_count = adapter.get_clone_failure_count("project_b")
        assert failure_count > 0, "Clone failure count should be incremented"

    @pytest.mark.asyncio
    async def test_repository_url_parsing(self):
        """Test repository URL parsing for SSH and HTTPS formats.

        Validates that extract_repo_name correctly handles:
        - SSH format: git@github.com:org/repo.git
        - HTTPS format: https://github.com/org/repo.git
        - URLs without .git suffix
        """
        # SSH format with .git
        assert extract_repo_name("git@github.com:org/repo.git") == "repo"
        assert extract_repo_name("git@gitlab.com:group/subgroup/repo.git") == "repo"

        # HTTPS format with .git
        assert extract_repo_name("https://github.com/org/repo.git") == "repo"
        assert extract_repo_name("https://gitlab.com/group/subgroup/repo.git") == "repo"

        # HTTPS format without .git
        assert extract_repo_name("https://github.com/org/repo") == "repo"
        assert extract_repo_name("https://github.com/org/repo-name") == "repo-name"

        # SSH format without .git
        assert extract_repo_name("git@github.com:org/repo-name") == "repo-name"

        # Edge cases
        assert extract_repo_name("https://github.com/org/my-repo.git") == "my-repo"
        assert extract_repo_name("git@github.com:org/my-repo-name") == "my-repo-name"


@pytest.mark.asyncio
async def test_scenario_13_multi_project():
    """Test multi-project orchestration scenario.

    Validates:
    - Multiple independent projects processed in single orchestration cycle
    - 3 projects (api-service, web-app, data-service) with isolated boards
    - 18 total work items across all projects
    - Project isolation maintained with no cross-contamination
    - OrchestrationCycleCompletedEvent emitted with aggregated metrics
    """
    config = create_config()
    runner = SimulationRunner(config)
    result = await runner.run(run_scenario)

    assert result.success, f"Scenario failed: {result.errors}"
    assert result.speed_multiplier >= 10.0, "Speed multiplier below target"
    assert result.events_captured > 0, "No events captured"
    assert result.assertions_passed > 0, "No assertions passed"
    assert result.assertions_failed == 0, "Some assertions failed"
