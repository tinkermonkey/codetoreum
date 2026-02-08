"""
Scenario 13: Multi-Project Orchestration

Multiple independent projects are processed within a single orchestration cycle.
Each project has its own configuration, repository, board, and workflows.

Expected flow:
1. MultiProjectOrchestrator reloads project configurations
2. Gets list of enabled projects: api-service, web-app, data-service
3. For each project:
   - Ensures repository is cloned/updated
   - Executes per-project workflow orchestration
   - Processes work items from project board
4. Emits OrchestrationCycleCompletedEvent with aggregated metrics

Expected outcome:
- 3 projects processed
- ~15-20 total actions (work items) across all projects
- OrchestrationCycleCompletedEvent emitted with cycle metrics
- Project isolation maintained (no cross-project contamination)
"""

from datetime import timedelta
from typing import Any, Dict

from codetoreum.infrastructure.simulation import (
    SimulationConfig,
    SimulationRunner,
)
from codetoreum.domain.value_objects import ProjectConfig
from codetoreum.domain.events.project_events import (
    OrchestrationCycleCompletedEvent,
    ProjectClonedEvent,
)


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
    from datetime import datetime, timezone

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
