"""
Simulation Data Seeding Utilities

Provides programmatic API and scenario loading for populating simulation environments
with test data. Supports both fluent API for custom scenarios and YAML-based
declarative configuration.
"""

import logging
import random
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

import yaml

from codetoreum.adapters.testing.in_memory_config_store import InMemoryConfigStore
from codetoreum.adapters.testing.in_memory_ticket_adapter import InMemoryTicketAdapter
from codetoreum.adapters.testing.mock_board_adapter import MockBoardAdapter
from codetoreum.domain.board_workflow_template import (
    BoardWorkflowTemplate,
    ColumnTemplate,
    ColumnType,
)
from codetoreum.domain.work_item import WorkItemPriority, WorkItemStatus
from codetoreum.infrastructure.simulation.bootstrap import (
    SimulationAdapters,
    SimulationApplicationBootstrap,
)
from codetoreum.infrastructure.simulation.scenario_models import ScenarioModel
from codetoreum.ports.exceptions import ValidationError
from codetoreum.ports.output.config_store import (
    AgentConfig,
    PipelineConfig,
    ProjectConfig,
)

logger = logging.getLogger(__name__)


@dataclass
class CreatedItems:
    """Tracks all items created during seeding for cleanup."""

    projects: list[str] = field(default_factory=list)
    workflows: list[str] = field(default_factory=list)
    agents: list[str] = field(default_factory=list)
    work_items: list[str] = field(default_factory=list)
    pipelines: list[str] = field(default_factory=list)
    boards: list[str] = field(default_factory=list)

    def clear(self) -> None:
        """Clear all tracking."""
        self.projects.clear()
        self.workflows.clear()
        self.agents.clear()
        self.work_items.clear()
        self.pipelines.clear()
        self.boards.clear()


class SimulationDataSeeder:
    """
    Data seeding utility for simulation testing.

    Provides:
    - Programmatic API for creating test data (projects, workflows, agents, work items)
    - Fluent/chainable interface for building scenarios
    - Pre-built scenarios for common use cases
    - Item tracking for cleanup

    Usage:
        seeder = SimulationDataSeeder(bootstrap)
        await seeder.seed_default_scenario()

        # Or custom:
        await seeder \
            .create_project("my-project") \
            .create_workflow("3-stage-workflow") \
            .create_agents(["coder", "reviewer"]) \
            .create_work_items(count=10)
    """

    def __init__(
        self,
        bootstrap: SimulationApplicationBootstrap,
        track_items: bool = True,
    ):
        """
        Initialize data seeder.

        Args:
            bootstrap: Simulation bootstrap with configured adapters
            track_items: Whether to track created items for cleanup
        """
        if not bootstrap._is_setup:
            message = "Bootstrap must be set up before seeding"
            raise ValidationError(message)

        self.bootstrap = bootstrap
        self.adapters: SimulationAdapters = bootstrap.adapters
        self.track_items = track_items
        self.created_items = CreatedItems()

        # Quick access to adapters
        self._ticket_adapter: InMemoryTicketAdapter = self.adapters.ticket_system
        self._config_store: InMemoryConfigStore = self.adapters.config_store
        self._board_adapter: MockBoardAdapter = self.adapters.board

        # Defaults
        self._current_project_id: str | None = None
        self._current_workflow_id: str | None = None

    # =========================================================================
    # Core Data Creation Methods
    # =========================================================================

    async def create_project(
        self,
        name: str,
        description: str = "",
        repository_url: str | None = None,
        default_branch: str = "main",
        metadata: dict[str, Any] | None = None,
    ) -> "SimulationDataSeeder":
        """
        Create a project configuration.

        Args:
            name: Project name (must be unique)
            description: Project description
            repository_url: Repository URL (optional, defaults to mock URL)
            default_branch: Default branch name (stored in metadata)
            metadata: Additional metadata

        Returns:
            Self for chaining
        """
        project_id = str(uuid4())

        if repository_url is None:
            repository_url = f"https://github.com/test-org/{name}.git"

        # Parse github_org and github_repo from repository URL
        github_org = "test-org"
        github_repo = name
        if "github.com/" in repository_url:
            parts = repository_url.replace(".git", "").split("github.com/")[1].split("/")
            if len(parts) >= 2:
                github_org = parts[0]
                github_repo = parts[1]

        meta = metadata or {}
        meta["default_branch"] = default_branch
        meta["description"] = description
        meta["repository_url"] = repository_url

        project_config = ProjectConfig(
            id=project_id,
            name=name,
            github_org=github_org,
            github_repo=github_repo,
            version=1,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
            metadata=meta,
        )

        await self._config_store.save_project_config(project_config)

        if self.track_items:
            self.created_items.projects.append(project_id)

        # Set as current project for chaining
        self._current_project_id = project_id

        logger.info(f"Created project: {name} ({project_id})")
        return self

    async def create_workflow(
        self,
        name: str,
        description: str = "",
        stages: list[dict[str, Any]] | None = None,
        project_id: str | None = None,
    ) -> "SimulationDataSeeder":
        """
        Create a workflow template.

        Args:
            name: Workflow name
            description: Workflow description
            stages: List of stage definitions (name, agent_type, etc.)
            project_id: Project ID (uses current if not specified)

        Returns:
            Self for chaining
        """
        workflow_id = str(uuid4())
        project_id = project_id or self._current_project_id

        if not project_id:
            message = "No project context. Create a project first or provide project_id."
            raise ValidationError(message)

        # Default 3-stage workflow if no stages provided
        if stages is None:
            stages = [
                {
                    "name": "design",
                    "agent_type": "architect",
                    "description": "Design the solution",
                    "order": 1,
                },
                {
                    "name": "implementation",
                    "agent_type": "coder",
                    "description": "Implement the solution",
                    "order": 2,
                },
                {
                    "name": "testing",
                    "agent_type": "tester",
                    "description": "Test the implementation",
                    "order": 3,
                },
            ]

        # Create stage configurations as dictionaries (not dataclass objects)
        stage_configs = []
        for stage_def in stages:
            stage_dict = {
                "name": stage_def["name"],
                "description": stage_def.get("description", ""),
                "agent_type": stage_def.get("agent_type", "generic"),
                "order": stage_def.get("order", len(stage_configs) + 1),
                "entry_conditions": stage_def.get("entry_conditions", {}),
                "exit_conditions": stage_def.get("exit_conditions", {}),
                "max_retries": stage_def.get("max_retries", 3),
                "timeout_seconds": stage_def.get("timeout_seconds", 3600),
            }
            stage_configs.append(stage_dict)

        # Create pipeline config
        pipeline_config = PipelineConfig(
            id=str(uuid4()),
            project_id=project_id,
            name=name,
            stages=stage_configs,
            version=1,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
            metadata={"description": description},
        )

        await self._config_store.save_pipeline_config(pipeline_config)

        if self.track_items:
            self.created_items.pipelines.append(pipeline_config.id)
            self.created_items.workflows.append(workflow_id)

        self._current_workflow_id = workflow_id

        logger.info(f"Created workflow: {name} with {len(stages)} stages")
        return self

    async def create_agents(
        self,
        agent_definitions: list[dict[str, Any]],
        project_id: str | None = None,
    ) -> "SimulationDataSeeder":
        """
        Create agent configurations.

        Args:
            agent_definitions: List of agent definitions with name, capabilities, etc.
            project_id: Project ID (uses current if not specified)

        Returns:
            Self for chaining
        """
        project_id = project_id or self._current_project_id

        if not project_id:
            message = "No project context. Create a project first or provide project_id."
            raise ValidationError(message)

        for agent_def in agent_definitions:
            agent_name = agent_def.get("name")
            if not agent_name:
                message = "Agent definition must include 'name'"
                raise ValidationError(message)

            # Capabilities are stored as list of strings
            capabilities = agent_def.get("capabilities", ["code_generation"])

            # Build metadata with agent-specific info
            metadata = agent_def.get("metadata", {})
            metadata.update(
                {
                    "agent_type": agent_def.get("agent_type", "generic"),
                    "description": agent_def.get("description", f"{agent_name} agent"),
                    "llm_model": agent_def.get("llm_model", "claude-3-5-sonnet-20241022"),
                    "temperature": agent_def.get("temperature", 0.7),
                    "max_tokens": agent_def.get("max_tokens", 4096),
                    "system_prompt": agent_def.get("system_prompt", ""),
                    "enabled": agent_def.get("enabled", True),
                }
            )

            agent_config = AgentConfig(
                project_id=project_id,
                agent_name=agent_name,
                model=agent_def.get("llm_model", "claude-3-5-sonnet-20241022"),
                timeout=agent_def.get("timeout", 3600),
                requires_docker=agent_def.get("requires_docker", True),
                makes_code_changes=agent_def.get("makes_code_changes", True),
                capabilities=capabilities,
                version=1,
                created_at=datetime.now(UTC),
                updated_at=datetime.now(UTC),
                metadata=metadata,
            )

            await self._config_store.save_agent_config(agent_config)

            if self.track_items:
                self.created_items.agents.append(agent_name)

            logger.debug(f"Created agent: {agent_name}")

        logger.info(f"Created {len(agent_definitions)} agents")
        return self

    async def create_work_items(
        self,
        count: int = 1,
        title_prefix: str = "Test Issue",
        project_id: str | None = None,
        labels: list[str] | None = None,
        priority: WorkItemPriority = WorkItemPriority.MEDIUM,
        status: WorkItemStatus = WorkItemStatus.NEW,
        metadata: dict[str, Any] | None = None,
    ) -> "SimulationDataSeeder":
        """
        Create work items.

        Args:
            count: Number of work items to create
            title_prefix: Prefix for work item titles
            project_id: Project ID (uses current if not specified)
            labels: Labels to apply
            priority: Work item priority
            status: Initial status
            metadata: Additional metadata

        Returns:
            Self for chaining
        """
        project_id = project_id or self._current_project_id

        if not project_id:
            message = "No project context. Create a project first or provide project_id."
            raise ValidationError(message)

        for i in range(count):
            title = f"{title_prefix} #{i + 1}"
            description = f"Description for {title}"

            work_item = await self._ticket_adapter.create_work_item(
                title=title,
                description=description,
                project_id=project_id,
                labels=labels or [],
                priority=priority,
                metadata=metadata or {},
            )

            # Update status if not NEW
            if status != WorkItemStatus.NEW:
                work_item.status = status

            if self.track_items:
                self.created_items.work_items.append(work_item.id)

        logger.info(f"Created {count} work items")
        return self

    # =========================================================================
    # Board Operations
    # =========================================================================

    async def create_board(
        self,
        board_id: str,
        board_name: str,
        column_names: list[str],
        project_id: str | None = None,
    ) -> "SimulationDataSeeder":
        """
        Create a board with specified columns.

        Args:
            board_id: Board identifier
            board_name: Display name for the board
            column_names: List of column names in order
            project_id: Project ID (uses current if not specified)

        Returns:
            Self for chaining
        """
        project_id = project_id or self._current_project_id

        if not project_id:
            message = "No project context. Create a project first or provide project_id."
            raise ValidationError(message)

        self._board_adapter.create_board(project_id, board_id, board_name, column_names)
        self._board_adapter.current_project = project_id
        self._board_adapter.current_board = board_id

        if self.track_items:
            self.created_items.boards.append(board_id)

        logger.info(f"Created board: {board_name} ({board_id}) with columns {column_names}")
        return self

    async def place_item_on_board(
        self,
        board_id: str,
        column_name: str,
        work_item_id: str,
        project_id: str | None = None,
    ) -> "SimulationDataSeeder":
        """
        Place a work item on a board column.

        Args:
            board_id: Board identifier
            column_name: Target column name
            work_item_id: Work item to place
            project_id: Project ID (uses current if not specified)

        Returns:
            Self for chaining
        """
        project_id = project_id or self._current_project_id

        if not project_id:
            message = "No project context. Create a project first or provide project_id."
            raise ValidationError(message)

        self._board_adapter.current_project = project_id
        self._board_adapter.add_item_to_column(board_id, column_name, work_item_id)

        logger.info(f"Placed work item {work_item_id} in column '{column_name}' on board {board_id}")
        return self

    def register_workflow_template(
        self,
        board_id: str,
        column_names: list[str],
        agent_types: list[str],
    ) -> "SimulationDataSeeder":
        """Build and register a BoardWorkflowTemplate for board automation.

        Maps board columns to workflow agents:
        - First column -> MANUAL (no agent)
        - Last column -> MANUAL, exit column (no agent)
        - Middle columns -> AUTOMATED, mapped to agent_types in order
        - First automated column -> pipeline trigger

        Args:
            board_id: Board to register template for
            column_names: Ordered column names from the board
            agent_types: Agent type IDs from workflow stages (ordered)

        Returns:
            Self for chaining
        """
        columns: list[ColumnTemplate] = []
        agent_index = 0

        for pos, col_name in enumerate(column_names):
            is_first = pos == 0
            is_last = pos == len(column_names) - 1
            is_middle = not is_first and not is_last

            if is_middle and agent_index < len(agent_types):
                agent_id = agent_types[agent_index]
                is_trigger = agent_index == 0  # First automated column
                columns.append(
                    ColumnTemplate(
                        name=col_name,
                        type=ColumnType.AUTOMATED,
                        agent_id=agent_id,
                        is_pipeline_trigger=is_trigger,
                        is_exit_column=False,
                        position=pos,
                        auto_progress_on_completion=True,
                    )
                )
                agent_index += 1
            else:
                columns.append(
                    ColumnTemplate(
                        name=col_name,
                        type=ColumnType.MANUAL,
                        agent_id=None,
                        is_pipeline_trigger=False,
                        is_exit_column=is_last,
                        position=pos,
                        auto_progress_on_completion=False,
                    )
                )

        # Derive trigger/exit column names
        trigger_cols = tuple(c.name for c in columns if c.is_pipeline_trigger)
        exit_cols = tuple(c.name for c in columns if c.is_exit_column)

        template = BoardWorkflowTemplate(
            id=f"template-{board_id}",
            name=f"Workflow for {board_id}",
            pipeline_trigger_columns=trigger_cols,
            exit_columns=exit_cols,
            columns=tuple(columns),
        )

        self.bootstrap.adapters.workflow_config.register_template(board_id, template)
        logger.info(
            f"Registered workflow template for board {board_id}: "
            f"{[c.name + ('*' if c.agent_id else '') for c in columns]}"
        )
        return self

    # =========================================================================
    # Pre-built Scenarios
    # =========================================================================

    async def seed_default_scenario(self) -> "SimulationDataSeeder":
        """
        Seed default scenario: Basic scenario with 3 work items, 1 workflow, 3 agents.

        This is a minimal scenario for smoke testing.

        Returns:
            Self for chaining
        """
        logger.info("Seeding default scenario...")

        await self.create_project(
            name="default-project",
            description="Default test project",
        )

        await self.create_workflow(
            name="default-workflow",
            description="Default 3-stage workflow",
        )

        await self.create_agents(
            [
                {
                    "name": "architect",
                    "agent_type": "architect",
                    "description": "Software architect agent",
                    "capabilities": ["code_generation", "code_review"],
                },
                {
                    "name": "coder",
                    "agent_type": "coder",
                    "description": "Software developer agent",
                    "capabilities": ["code_generation"],
                },
                {
                    "name": "tester",
                    "agent_type": "tester",
                    "description": "QA tester agent",
                    "capabilities": ["code_review", "testing"],
                },
            ]
        )

        await self.create_work_items(
            count=3,
            title_prefix="Default Issue",
            labels=["test", "default"],
        )

        await self.create_board(
            board_id="board-1",
            board_name="Default Board",
            column_names=["Backlog", "Ready", "In Progress", "Review", "Done"],
        )

        # Register workflow template for board automation
        self.register_workflow_template(
            board_id="board-1",
            column_names=["Backlog", "Ready", "In Progress", "Review", "Done"],
            agent_types=["architect", "coder", "tester"],
        )

        # Place created work items in Backlog
        for work_item_id in self.created_items.work_items:
            await self.place_item_on_board("board-1", "Backlog", work_item_id)

        logger.info("Default scenario seeded successfully")
        return self

    async def seed_simple_workflow(self) -> "SimulationDataSeeder":
        """
        Seed simple workflow scenario: Single work item through 3-stage workflow.

        This scenario is useful for testing basic workflow execution end-to-end.

        Returns:
            Self for chaining
        """
        logger.info("Seeding simple workflow scenario...")

        await self.create_project(
            name="simple-workflow-project",
            description="Project for simple workflow testing",
        )

        await self.create_workflow(
            name="simple-workflow",
            description="Simple linear workflow",
            stages=[
                {
                    "name": "design",
                    "agent_type": "architect",
                    "description": "Design phase",
                    "order": 1,
                },
                {
                    "name": "implement",
                    "agent_type": "coder",
                    "description": "Implementation phase",
                    "order": 2,
                },
                {
                    "name": "test",
                    "agent_type": "tester",
                    "description": "Testing phase",
                    "order": 3,
                },
            ],
        )

        await self.create_agents(
            [
                {
                    "name": "architect",
                    "agent_type": "architect",
                    "capabilities": ["code_generation"],
                },
                {
                    "name": "coder",
                    "agent_type": "coder",
                    "capabilities": ["code_generation"],
                },
                {
                    "name": "tester",
                    "agent_type": "tester",
                    "capabilities": ["testing"],
                },
            ]
        )

        await self.create_work_items(
            count=1,
            title_prefix="Simple Workflow Task",
            labels=["workflow-test"],
        )

        await self.create_board(
            board_id="board-1",
            board_name="Simple Workflow Board",
            column_names=["Backlog", "Ready", "In Progress", "Review", "Done"],
        )

        for work_item_id in self.created_items.work_items:
            await self.place_item_on_board("board-1", "Backlog", work_item_id)

        logger.info("Simple workflow scenario seeded successfully")
        return self

    async def seed_parallel_workflow(self) -> "SimulationDataSeeder":
        """
        Seed parallel workflow scenario: 10 work items executing in parallel.

        This scenario tests concurrent execution and resource management.

        Returns:
            Self for chaining
        """
        logger.info("Seeding parallel workflow scenario...")

        await self.create_project(
            name="parallel-workflow-project",
            description="Project for parallel workflow testing",
        )

        await self.create_workflow(
            name="parallel-workflow",
            description="Workflow for parallel execution",
        )

        await self.create_agents(
            [
                {
                    "name": "coder-1",
                    "agent_type": "coder",
                    "capabilities": ["code_generation"],
                },
                {
                    "name": "coder-2",
                    "agent_type": "coder",
                    "capabilities": ["code_generation"],
                },
                {
                    "name": "reviewer",
                    "agent_type": "reviewer",
                    "capabilities": ["code_review"],
                },
            ]
        )

        await self.create_work_items(
            count=10,
            title_prefix="Parallel Task",
            labels=["parallel", "concurrent"],
        )

        await self.create_board(
            board_id="board-1",
            board_name="Parallel Workflow Board",
            column_names=["Backlog", "Ready", "In Progress", "Review", "Done"],
        )

        for work_item_id in self.created_items.work_items:
            await self.place_item_on_board("board-1", "Backlog", work_item_id)

        logger.info("Parallel workflow scenario seeded successfully")
        return self

    async def seed_review_cycle(self) -> "SimulationDataSeeder":
        """
        Seed review cycle scenario: Work items with review feedback loops.

        This scenario tests the review and feedback mechanism.

        Returns:
            Self for chaining
        """
        logger.info("Seeding review cycle scenario...")

        await self.create_project(
            name="review-cycle-project",
            description="Project for review cycle testing",
        )

        await self.create_workflow(
            name="review-workflow",
            description="Workflow with review stages",
            stages=[
                {
                    "name": "implement",
                    "agent_type": "coder",
                    "description": "Implementation",
                    "order": 1,
                },
                {
                    "name": "review",
                    "agent_type": "reviewer",
                    "description": "Code review",
                    "order": 2,
                },
                {
                    "name": "revise",
                    "agent_type": "coder",
                    "description": "Address feedback",
                    "order": 3,
                },
            ],
        )

        await self.create_agents(
            [
                {
                    "name": "coder",
                    "agent_type": "coder",
                    "capabilities": ["code_generation"],
                    "metadata": {"review_mode": False},
                },
                {
                    "name": "reviewer",
                    "agent_type": "reviewer",
                    "capabilities": ["code_review"],
                    "metadata": {"strict_mode": True},
                },
            ]
        )

        await self.create_work_items(
            count=5,
            title_prefix="Review Cycle Task",
            labels=["review", "feedback"],
        )

        await self.create_board(
            board_id="board-1",
            board_name="Review Cycle Board",
            column_names=["Backlog", "Ready", "In Progress", "Review", "Done"],
        )

        for work_item_id in self.created_items.work_items:
            await self.place_item_on_board("board-1", "Backlog", work_item_id)

        logger.info("Review cycle scenario seeded successfully")
        return self

    async def seed_failure_scenario(self) -> "SimulationDataSeeder":
        """
        Seed failure scenario: Includes execution failures and retries.

        This scenario tests error handling and retry mechanisms.

        Returns:
            Self for chaining
        """
        logger.info("Seeding failure scenario...")

        await self.create_project(
            name="failure-scenario-project",
            description="Project for failure testing",
        )

        await self.create_workflow(
            name="failure-workflow",
            description="Workflow with potential failures",
            stages=[
                {
                    "name": "flaky-stage",
                    "agent_type": "flaky-agent",
                    "description": "Stage with intermittent failures",
                    "order": 1,
                    "max_retries": 5,
                },
                {
                    "name": "recovery-stage",
                    "agent_type": "recovery-agent",
                    "description": "Recovery stage",
                    "order": 2,
                },
            ],
        )

        await self.create_agents(
            [
                {
                    "name": "flaky-agent",
                    "agent_type": "flaky",
                    "capabilities": ["code_generation"],
                    "metadata": {"failure_rate": 0.5},
                },
                {
                    "name": "recovery-agent",
                    "agent_type": "recovery",
                    "capabilities": ["code_generation"],
                    "metadata": {"failure_rate": 0.0},
                },
            ]
        )

        await self.create_work_items(
            count=3,
            title_prefix="Failure Test Task",
            labels=["failure", "retry"],
        )

        await self.create_board(
            board_id="board-1",
            board_name="Failure Recovery Board",
            column_names=["Backlog", "Ready", "In Progress", "Review", "Done"],
        )

        for work_item_id in self.created_items.work_items:
            await self.place_item_on_board("board-1", "Backlog", work_item_id)

        logger.info("Failure scenario seeded successfully")
        return self

    # =========================================================================
    # YAML Scenario Loading
    # =========================================================================

    async def seed_from_yaml(self, file_path: str | Path) -> "SimulationDataSeeder":
        """
        Seed data from YAML scenario file.

        Args:
            file_path: Path to YAML scenario file

        Returns:
            Self for chaining

        Raises:
            FileNotFoundError: If file doesn't exist
            yaml.YAMLError: If YAML is malformed
            ValidationError: If scenario validation fails
        """
        file_path = Path(file_path)

        if not file_path.exists():
            message = f"Scenario file not found: {file_path}"
            raise FileNotFoundError(message)

        logger.info(f"Loading scenario from {file_path}...")

        with open(file_path) as f:
            yaml_data = yaml.safe_load(f)

        if not yaml_data:
            message = f"Empty YAML file: {file_path}"
            raise ValidationError(message)

        # Validate with Pydantic model
        try:
            scenario = ScenarioModel(**yaml_data)
        except Exception as e:
            message = f"Scenario validation failed: {e}"
            raise ValidationError(message)

        logger.info(f"Loaded scenario: {scenario.name} (version {scenario.version})")

        # Seed projects
        for project_model in scenario.projects:
            await self.create_project(
                name=project_model.name,
                description=project_model.description,
                repository_url=project_model.repository_url,
                default_branch=project_model.default_branch,
                metadata=project_model.metadata,
            )

        # Seed workflows
        for workflow_model in scenario.workflows:
            stages = [
                {
                    "name": stage.name,
                    "agent_type": stage.agent_type,
                    "description": stage.description,
                    "order": stage.order,
                    "entry_conditions": stage.entry_conditions,
                    "exit_conditions": stage.exit_conditions,
                    "max_retries": stage.max_retries,
                    "timeout_seconds": stage.timeout_seconds,
                }
                for stage in workflow_model.stages
            ]

            await self.create_workflow(
                name=workflow_model.name,
                description=workflow_model.description,
                stages=stages,
            )

        # Seed agents
        agent_defs = [
            {
                "name": agent.name,
                "agent_type": agent.agent_type,
                "description": agent.description,
                "capabilities": agent.capabilities,
                "llm_model": agent.llm_model,
                "temperature": agent.temperature,
                "max_tokens": agent.max_tokens,
                "system_prompt": agent.system_prompt,
                "enabled": agent.enabled,
                "metadata": agent.metadata,
            }
            for agent in scenario.agents
        ]

        if agent_defs:
            await self.create_agents(agent_defs)

        # Seed work items
        for work_item_model in scenario.work_items:
            # Convert string priority/status to enum
            priority_map = {
                "low": WorkItemPriority.LOW,
                "medium": WorkItemPriority.MEDIUM,
                "high": WorkItemPriority.HIGH,
                "critical": WorkItemPriority.CRITICAL,
            }

            status_map = {
                "new": WorkItemStatus.NEW,
                "assigned": WorkItemStatus.ASSIGNED,
                "in_progress": WorkItemStatus.IN_PROGRESS,
                "under_review": WorkItemStatus.UNDER_REVIEW,
                "completed": WorkItemStatus.COMPLETED,
                "failed": WorkItemStatus.FAILED,
                "blocked": WorkItemStatus.BLOCKED,
            }

            priority = priority_map.get(work_item_model.priority, WorkItemPriority.MEDIUM)
            status = status_map.get(work_item_model.status, WorkItemStatus.NEW)

            await self.create_work_items(
                count=1,
                title_prefix=work_item_model.title,
                labels=work_item_model.labels,
                priority=priority,
                status=status,
                metadata=work_item_model.metadata,
            )

        # Seed boards and register workflow templates for board automation
        # Extract agent types from workflow stages (ordered by stage order)
        agent_types: list[str] = []
        for workflow_model in scenario.workflows:
            sorted_stages = sorted(workflow_model.stages, key=lambda s: s.order)
            agent_types = [stage.agent_type for stage in sorted_stages]
            break  # Use first workflow's agents

        for board_model in scenario.boards:
            await self.create_board(
                board_id=board_model.board_id,
                board_name=board_model.board_name,
                column_names=board_model.columns,
            )
            if agent_types:
                self.register_workflow_template(
                    board_id=board_model.board_id,
                    column_names=board_model.columns,
                    agent_types=agent_types,
                )

        # Seed board placements (match work items by title prefix)
        if scenario.board_placements:
            # Build a map of work item title -> id from the ticket adapter
            all_items = {}
            for item_id in self.created_items.work_items:
                try:
                    item = await self._ticket_adapter.get_work_item(item_id)
                    all_items[item.title] = item.id
                except Exception:
                    logger.error(
                        f"Failed to retrieve work item {item_id} during board placement seeding",
                        exc_info=True,
                    )
                    # Continue processing remaining items
                    continue

            board_id = scenario.boards[0].board_id if scenario.boards else "board-1"

            for placement in scenario.board_placements:
                # Match by title prefix (work items created from YAML get " #1" appended)
                matched_id = None
                for title, item_id in all_items.items():
                    if title.startswith(placement.work_item_title):
                        matched_id = item_id
                        break

                if matched_id:
                    await self.place_item_on_board(
                        board_id=board_id,
                        column_name=placement.column,
                        work_item_id=matched_id,
                    )
                else:
                    logger.warning(f"Board placement: no work item found matching title '{placement.work_item_title}'")

        logger.info(f"Scenario seeded successfully from {file_path}")
        return self

    # =========================================================================
    # Mock Adapter Configuration Methods
    # =========================================================================

    def configure_agent_behavior(
        self,
        agent_name: str,
        response: str | None = None,
        delay_seconds: float = 0.0,
        exit_code: int = 0,
    ) -> "SimulationDataSeeder":
        """
        Configure mock adapter behavior for a specific agent.

        Args:
            agent_name: Agent name to configure
            response: Mock LLM response (default: success message)
            delay_seconds: Simulated delay before response
            exit_code: Container exit code (0 = success)

        Returns:
            Self for chaining
        """
        from codetoreum.adapters.testing.mock_llm_adapter import MockLLMAdapter

        mock_llm: MockLLMAdapter = self.adapters.llm_provider

        if response is None:
            response = f"Mock response from {agent_name}: Task completed successfully"

        # Set response for this agent
        mock_llm.set_agent_response(agent_name, response)
        mock_llm.set_delay(delay_seconds)

        logger.debug(f"Configured agent behavior: {agent_name}, exit_code={exit_code}")
        return self

    def configure_agent_failure(
        self,
        agent_name: str,
        failure_mode: str = "timeout",
        failure_count: int = 1,
        error_message: str | None = None,
    ) -> "SimulationDataSeeder":
        """
        Configure agent to fail in specific ways.

        Args:
            agent_name: Agent name to configure
            failure_mode: Type of failure ("timeout", "error", "intermittent")
            failure_count: Number of failures before success (0 = always fail)
            error_message: Custom error message

        Returns:
            Self for chaining
        """
        from codetoreum.adapters.testing.mock_llm_adapter import MockLLMAdapter

        mock_llm: MockLLMAdapter = self.adapters.llm_provider

        if error_message is None:
            error_message = f"Mock failure from {agent_name}: {failure_mode}"

        # Configure failure behavior
        mock_llm.set_agent_failure(
            agent_name=agent_name,
            failure_mode=failure_mode,
            failure_count=failure_count,
            error_message=error_message,
        )

        logger.debug(f"Configured agent failure: {agent_name}, mode={failure_mode}, count={failure_count}")
        return self

    def configure_review_behavior(
        self,
        reviewer_name: str,
        approval_rate: float = 0.8,
        feedback_template: str | None = None,
    ) -> "SimulationDataSeeder":
        """
        Configure mock review behavior for reviewer agents.

        Args:
            reviewer_name: Reviewer agent name
            approval_rate: Probability of approval (0.0 - 1.0)
            feedback_template: Template for review feedback

        Returns:
            Self for chaining
        """
        from codetoreum.adapters.testing.mock_llm_adapter import MockLLMAdapter

        mock_llm: MockLLMAdapter = self.adapters.llm_provider

        if feedback_template is None:
            feedback_template = (
                "Code review feedback from {reviewer}: "
                "Please address the following issues:\n"
                "1. Add more error handling\n"
                "2. Improve code documentation\n"
                "3. Add unit tests"
            )

        # Set review responses based on approval rate
        random.seed(42)  # Deterministic for testing

        def review_response_fn():
            if random.random() < approval_rate:
                return f"APPROVED: Code review passed by {reviewer_name}"
            return feedback_template.format(reviewer=reviewer_name)

        mock_llm.set_agent_response_fn(reviewer_name, review_response_fn)

        logger.debug(f"Configured review behavior: {reviewer_name}, approval_rate={approval_rate}")
        return self

    def configure_container_output(
        self,
        exit_code: int = 0,
        stdout: str | None = None,
        stderr: str | None = None,
    ) -> "SimulationDataSeeder":
        """
        Configure mock container execution output.

        Args:
            exit_code: Container exit code
            stdout: Standard output
            stderr: Standard error output

        Returns:
            Self for chaining
        """
        from codetoreum.adapters.testing.fake_container_adapter import (
            FakeContainerAdapter,
        )

        fake_container: FakeContainerAdapter = self.adapters.container_runtime

        fake_container.set_default_exit_code(exit_code)

        if stdout:
            fake_container.set_default_stdout(stdout)

        if stderr:
            fake_container.set_default_stderr(stderr)

        logger.debug(f"Configured container output: exit_code={exit_code}")
        return self

    # =========================================================================
    # Cleanup Methods
    # =========================================================================

    async def cleanup(self) -> None:
        """
        Clean up all created items.

        This removes all tracked items from adapters. Only works if track_items=True.
        """
        if not self.track_items:
            logger.warning("Item tracking is disabled, cannot cleanup")
            return

        logger.info("Cleaning up seeded data...")

        # Note: In-memory adapters don't need explicit cleanup as they're destroyed
        # with the bootstrap. This method is here for completeness and future
        # extensibility if we need to support persistent adapters in simulation.

        self.created_items.clear()
        logger.info("Cleanup completed")

    def get_created_items(self) -> CreatedItems:
        """
        Get all created items for inspection or testing.

        Returns:
            CreatedItems object with all tracked items
        """
        return self.created_items
