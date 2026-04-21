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
from codetoreum.domain.agent import Agent, AgentCapability, AgentType, CommitPolicy
from codetoreum.domain.board_workflow_template import (
    BoardWorkflowTemplate,
    ColumnTemplate,
    ColumnType,
)
from codetoreum.domain.repair_cycle_types import RepairTestType
from codetoreum.domain.work_item import WorkItemPriority, WorkItemStatus
from codetoreum.infrastructure.simulation.bootstrap import (
    SimulationAdapters,
    SimulationApplicationBootstrap,
)
from codetoreum.infrastructure.simulation.scenario_models import (
    ExternalSeedModel,
    OrchestratorConfigModel,
    ScenarioColumnConfig,
    ScenarioModel,
)
from codetoreum.ports.exceptions import ValidationError
from codetoreum.ports.output.agent_repository import IAgentRepository
from codetoreum.ports.output.config_store import (
    AgentConfig,
    PipelineConfig,
    ProjectConfig,
)
from codetoreum.ports.output.work_item_service import IWorkItemService

logger = logging.getLogger(__name__)


def _merge_yaml_dir(dir_path: Path) -> dict:
    """Merge all ``*.yaml`` files in a directory into one dict.

    Files are processed in alphabetical order so names like ``01_simulation.yaml``
    can be used to control load order when key conflicts matter.  In practice,
    each per-adapter file owns distinct top-level keys so ordering is irrelevant
    for correctness.
    """
    yaml_files = sorted(dir_path.glob("*.yaml"))
    if not yaml_files:
        raise FileNotFoundError(f"No YAML files found in directory: {dir_path}")
    merged: dict = {}
    for yaml_file in yaml_files:
        data = yaml.safe_load(yaml_file.read_text())
        if data:
            merged.update(data)
    return merged


# Keep backward-compatible alias (used by some tests via direct module access)
_merge_scenario_dir = _merge_yaml_dir


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
        await seeder.create_project("my-project")
        await seeder.create_workflow("3-stage-workflow")
        await seeder.create_agents([{"name": "coder", "capabilities": ["code_generation"]},
                                    {"name": "reviewer", "capabilities": ["review"]}])
        await seeder.create_work_items(count=10)
    """

    def __init__(
        self,
        bootstrap: SimulationApplicationBootstrap,
        track_items: bool = True,
        agent_repository: IAgentRepository | None = None,
        work_item_service: IWorkItemService | None = None,
    ):
        """
        Initialize data seeder.

        Args:
            bootstrap: Simulation bootstrap with configured adapters
            track_items: Whether to track created items for cleanup
            agent_repository: Optional agent repository to populate with domain Agent objects
            work_item_service: Optional work item service to mirror work items into
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
        self._agent_repository: IAgentRepository | None = agent_repository
        self._work_item_service: IWorkItemService | None = work_item_service

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

            # Also save to agent repository if available (for ExecutionServiceAgentExecutor)
            if self._agent_repository is not None:
                # Build default capabilities from the agent's capability list
                # Each capability string becomes an AgentCapability with full proficiency
                cap_list = agent_def.get("capabilities", ["code_generation"])
                default_capabilities: dict[str, AgentCapability] = {
                    cap: AgentCapability(skill=cap, proficiency=1.0, description=cap)
                    for cap in (cap_list if cap_list else ["code_generation"])
                }
                commit_policy_str = agent_def.get("commit_policy", "on_success")
                try:
                    commit_policy = CommitPolicy(commit_policy_str)
                except ValueError:
                    commit_policy = CommitPolicy.ON_SUCCESS

                agent_domain = Agent(
                    id=agent_name,  # Use agent_name as ID so column_config.agent_id matches
                    name=agent_name,
                    display_name=agent_def.get("description", agent_name),
                    agent_type=AgentType.MAKER,
                    capabilities=default_capabilities,
                    role_description=agent_def.get("description", ""),
                    model=agent_def.get("llm_model", "claude-sonnet-4-6"),
                    timeout_seconds=agent_def.get("timeout", 3600),
                    max_retries=3,
                    requires_docker=agent_def.get("requires_docker", False),
                    requires_dev_container=False,
                    makes_code_changes=agent_def.get("makes_code_changes", True),
                    filesystem_write_allowed=True,
                    mcp_servers=[],
                    metadata={},
                    created_at=datetime.now(UTC),
                    updated_at=datetime.now(UTC),
                    commit_policy=commit_policy,
                )
                await self._agent_repository.save(agent_domain, project_id)

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

            # Mirror into work_item_service if available (for ExecutionServiceAgentExecutor)
            if self._work_item_service is not None and hasattr(self._work_item_service, "add_work_item"):
                self._work_item_service.add_work_item(work_item)  # type: ignore[union-attr]

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

    async def register_workflow_template(
        self,
        board_id: str,
        column_names: list[str],
        agent_types: list[str],
        sla_seconds_by_column: dict[str, int] | None = None,
        project_id: str | None = None,
    ) -> "SimulationDataSeeder":
        """Build and register a BoardWorkflowTemplate for board automation.

        Maps board columns to workflow agents using positional rules:
        - First column -> MANUAL (no agent)
        - Last column -> MANUAL, exit column (no agent)
        - Middle columns -> AUTOMATED, mapped to agent_types in order
        - First automated column -> pipeline trigger

        Args:
            board_id: Board to register template for
            column_names: Ordered column names from the board
            agent_types: Agent type IDs from workflow stages (ordered)
            sla_seconds_by_column: Optional dict mapping column names to SLA
                thresholds in seconds.  Automated columns default to 3600 s.
            project_id: Project that owns this board.  Defaults to the current
                project set on the seeder (``_current_project_id``).

        Returns:
            Self for chaining

        Raises:
            ValidationError: If no project_id is available.
        """
        project_id = project_id or self._current_project_id
        if not project_id:
            msg = "No project context. Create a project first or provide project_id."
            raise ValidationError(msg)
        columns: list[ColumnTemplate] = []
        agent_index = 0
        sla_config = sla_seconds_by_column or {}

        # Default SLA threshold for automated columns (1 hour)
        default_sla_seconds = 3600

        for pos, col_name in enumerate(column_names):
            is_first = pos == 0
            is_last = pos == len(column_names) - 1
            is_middle = not is_first and not is_last

            if is_middle and agent_index < len(agent_types):
                agent_id = agent_types[agent_index]
                is_trigger = agent_index == 0  # First automated column
                # Use provided SLA or default for automated columns
                sla_seconds = sla_config.get(col_name, default_sla_seconds)
                columns.append(
                    ColumnTemplate(
                        name=col_name,
                        type=ColumnType.AUTOMATED,
                        agent_id=agent_id,
                        is_pipeline_trigger=is_trigger,
                        is_exit_column=False,
                        position=pos,
                        auto_progress_on_completion=True,
                        sla_seconds=sla_seconds,
                    )
                )
                agent_index += 1
            else:
                # Manual columns use provided SLA if specified, otherwise None
                sla_seconds = sla_config.get(col_name)
                columns.append(
                    ColumnTemplate(
                        name=col_name,
                        type=ColumnType.MANUAL,
                        agent_id=None,
                        is_pipeline_trigger=False,
                        is_exit_column=is_last,
                        position=pos,
                        auto_progress_on_completion=False,
                        sla_seconds=sla_seconds,
                    )
                )

        template = BoardWorkflowTemplate(
            id=f"template-{board_id}",
            name=f"Workflow for {board_id}",
            board_id=board_id,
            project_id=project_id,
            columns=tuple(columns),
        )

        await self.adapters.workflow_config.save_board_workflow_template(template)
        logger.info(
            f"Registered workflow template for board {board_id}: "
            f"{[c.name + ('*' if c.agent_id else '') + (f'[SLA:{c.sla_seconds}s]' if c.sla_seconds else '') for c in columns]}"
        )
        return self

    async def register_workflow_template_from_column_configs(
        self,
        board_id: str,
        column_configs: list[ScenarioColumnConfig],
        project_id: str | None = None,
    ) -> "SimulationDataSeeder":
        """Build and register a BoardWorkflowTemplate from explicit column configurations.

        Unlike ``register_workflow_template`` (which infers routing from positional
        rules), this method uses the full ``ScenarioColumnConfig`` spec for each
        column so that agent assignments, trigger/exit flags, SLA thresholds, and
        auto-progression are all under explicit YAML control.

        Args:
            board_id: Board to register the template for
            column_configs: Ordered list of explicit column definitions (position
                is inferred from list order, 0-based)
            project_id: Project that owns this board.  Defaults to the current
                project set on the seeder (``_current_project_id``).

        Returns:
            Self for chaining

        Raises:
            ValidationError: If no project_id is available.
        """
        project_id = project_id or self._current_project_id
        if not project_id:
            msg = "No project context. Create a project first or provide project_id."
            raise ValidationError(msg)
        columns: list[ColumnTemplate] = []
        for pos, cfg in enumerate(column_configs):
            col_type = ColumnType.AUTOMATED if cfg.type == "automated" else ColumnType.MANUAL
            # Convert repair_cycle_agents to domain model if present
            repair_cycle_agents = None
            if cfg.repair_cycle_agents:
                repair_cycle_agents = cfg.repair_cycle_agents.to_domain()
            # Parse repair_cycle_test_types strings to RepairTestType enum values
            repair_cycle_test_types: tuple[RepairTestType, ...] | None = None
            if cfg.repair_cycle_test_types:
                repair_cycle_test_types = tuple(RepairTestType(t) for t in cfg.repair_cycle_test_types)
            # Convert pr_review_cycle_config to domain model if present
            pr_review_cycle_config = None
            if cfg.pr_review_cycle_config:
                pr_review_cycle_config = cfg.pr_review_cycle_config.to_domain()
            columns.append(
                ColumnTemplate(
                    name=cfg.name,
                    type=col_type,
                    agent_id=cfg.agent_id,
                    is_pipeline_trigger=cfg.is_pipeline_trigger,
                    is_exit_column=cfg.is_exit_column,
                    position=pos,
                    auto_progress_on_completion=cfg.auto_progress_on_completion,
                    sla_seconds=cfg.sla_seconds,
                    on_failure_column=cfg.on_failure_column,
                    sla_escalation_column=cfg.sla_escalation_column,
                    repair_cycle_agents=repair_cycle_agents,
                    repair_cycle_test_types=repair_cycle_test_types,
                    pr_review_cycle_config=pr_review_cycle_config,
                    execution_type=cfg.execution_type,
                )
            )

        template = BoardWorkflowTemplate(
            id=f"template-{board_id}",
            name=f"Workflow for {board_id}",
            board_id=board_id,
            project_id=project_id,
            columns=tuple(columns),
        )

        await self.adapters.workflow_config.save_board_workflow_template(template)
        logger.info(
            f"Registered explicit workflow template for board {board_id}: "
            f"{[c.name + ('*' if c.agent_id else '') + (f'[SLA:{c.sla_seconds}s]' if c.sla_seconds else '') for c in columns]}"
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
        await self.register_workflow_template(
            board_id="board-1",
            column_names=["Backlog", "Ready", "In Progress", "Review", "Done"],
            agent_types=["architect", "coder", "tester"],
        )

        # Place created work items in Backlog
        for work_item_id in self.created_items.work_items:
            await self.place_item_on_board("board-1", "Backlog", work_item_id)

        logger.info("Default scenario seeded successfully")
        return self

    async def seed_two_project_scenario(self) -> tuple[str, str]:
        """Seed two independent projects (Alpha and Beta) for multi-project testing.

        Creates two separate boards with independent agents and work items.
        Each project has the same workflow columns:
        Backlog -> Ready -> In Progress -> Review -> Done

        Project Alpha uses board-alpha with agents: alpha-architect, alpha-coder, alpha-tester
        Project Beta uses board-beta with agents: beta-architect, beta-coder, beta-tester

        Returns:
            Tuple of (alpha_work_item_id, beta_work_item_id)
        """
        logger.info("Seeding two-project scenario (Alpha + Beta)...")

        # ---- Project Alpha ----
        await self.create_project(
            name="alpha-project",
            description="Alpha test project",
        )
        alpha_project_id = self._current_project_id

        await self.create_workflow(
            name="alpha-workflow",
            description="Alpha 3-stage workflow",
        )

        await self.create_agents(
            [
                {
                    "name": "alpha-architect",
                    "agent_type": "architect",
                    "description": "Alpha architect agent",
                    "capabilities": ["code_generation", "code_review"],
                },
                {
                    "name": "alpha-coder",
                    "agent_type": "coder",
                    "description": "Alpha developer agent",
                    "capabilities": ["code_generation"],
                },
                {
                    "name": "alpha-tester",
                    "agent_type": "tester",
                    "description": "Alpha QA tester agent",
                    "capabilities": ["code_review", "testing"],
                },
            ]
        )

        await self.create_work_items(
            count=1,
            title_prefix="Alpha Issue",
            labels=["alpha", "test"],
        )
        alpha_work_item_id = self.created_items.work_items[-1]

        await self.create_board(
            board_id="board-alpha",
            board_name="Alpha Board",
            column_names=["Backlog", "Ready", "In Progress", "Review", "Done"],
            project_id=alpha_project_id,
        )

        await self.register_workflow_template(
            board_id="board-alpha",
            column_names=["Backlog", "Ready", "In Progress", "Review", "Done"],
            agent_types=["alpha-architect", "alpha-coder", "alpha-tester"],
        )

        await self.place_item_on_board("board-alpha", "Backlog", alpha_work_item_id, project_id=alpha_project_id)

        # ---- Project Beta ----
        await self.create_project(
            name="beta-project",
            description="Beta test project",
        )
        beta_project_id = self._current_project_id

        await self.create_workflow(
            name="beta-workflow",
            description="Beta 3-stage workflow",
        )

        await self.create_agents(
            [
                {
                    "name": "beta-architect",
                    "agent_type": "architect",
                    "description": "Beta architect agent",
                    "capabilities": ["code_generation", "code_review"],
                },
                {
                    "name": "beta-coder",
                    "agent_type": "coder",
                    "description": "Beta developer agent",
                    "capabilities": ["code_generation"],
                },
                {
                    "name": "beta-tester",
                    "agent_type": "tester",
                    "description": "Beta QA tester agent",
                    "capabilities": ["code_review", "testing"],
                },
            ]
        )

        await self.create_work_items(
            count=1,
            title_prefix="Beta Issue",
            labels=["beta", "test"],
        )
        beta_work_item_id = self.created_items.work_items[-1]

        await self.create_board(
            board_id="board-beta",
            board_name="Beta Board",
            column_names=["Backlog", "Ready", "In Progress", "Review", "Done"],
            project_id=beta_project_id,
        )

        await self.register_workflow_template(
            board_id="board-beta",
            column_names=["Backlog", "Ready", "In Progress", "Review", "Done"],
            agent_types=["beta-architect", "beta-coder", "beta-tester"],
        )

        await self.place_item_on_board("board-beta", "Backlog", beta_work_item_id, project_id=beta_project_id)

        logger.info(f"Two-project scenario seeded: alpha={alpha_work_item_id}, beta={beta_work_item_id}")
        return alpha_work_item_id, beta_work_item_id

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
        Seed data from a YAML scenario file or scenario directory.

        **New-style split directory** (``orchestrator/`` subdir present):
        Uses two-pass loading to honour the external/orchestrator boundary:

            smoke/
              orchestrator/
                simulation.yaml   # name, version, speed_multiplier, …
                agents.yaml       # agents: […]
                workflows.yaml    # workflows: […]
                board_policy.yaml # board_policies: [{board_id, column_configs}]
              external/
                projects.yaml     # projects: […]
                work_items.yaml   # work_items: […]
                board_structure.yaml  # boards: [{board_id, board_name, columns}]
                board_placements.yaml # board_placements: […]

        Pass 1 — always: apply ``orchestrator/`` config (agents, workflows, board policies).
        Pass 2 — simulation only: seed ``external/`` data when the subdir exists
        (projects, work items, board structure, item placements).

        **Legacy flat directory** (no ``orchestrator/`` subdir):
        All ``*.yaml`` files are merged into a single ``ScenarioModel`` and
        seeded in one pass (backward-compatible with pre-split scenarios).

        Args:
            file_path: Path to a YAML scenario file **or** a scenario directory

        Returns:
            Self for chaining

        Raises:
            FileNotFoundError: If path doesn't exist or directory contains no YAML
            yaml.YAMLError: If YAML is malformed
            ValidationError: If scenario validation fails
        """
        file_path = Path(file_path)

        if not file_path.exists():
            message = f"Scenario path not found: {file_path}"
            raise FileNotFoundError(message)

        logger.info(f"Loading scenario from {file_path}...")

        # ── New-style split directory ────────────────────────────────────────
        if file_path.is_dir() and (file_path / "orchestrator").is_dir():
            return await self._seed_from_split_dir(file_path)

        # ── Legacy: single file or flat directory ────────────────────────────
        if file_path.is_dir():
            yaml_data = _merge_yaml_dir(file_path)
        else:
            with open(file_path) as f:
                yaml_data = yaml.safe_load(f)

        if not yaml_data:
            message = f"Empty scenario (no YAML content): {file_path}"
            raise ValidationError(message)

        try:
            scenario = ScenarioModel(**yaml_data)
        except Exception as e:
            message = f"Scenario validation failed: {e}"
            raise ValidationError(message)

        logger.info(f"Loaded scenario: {scenario.name} (version {scenario.version})")
        await self._seed_legacy_scenario(scenario)
        logger.info(f"Scenario seeded successfully from {file_path}")
        return self

    async def _seed_from_split_dir(self, scenario_dir: Path) -> "SimulationDataSeeder":
        """Three-pass seeding from a split orchestrator/ + external/ directory.

        Pass 1: Seed external projects first (to establish project context)
        Pass 2: Apply orchestrator config (workflows, agents, board policies)
        Pass 3: Seed remaining external data (work items, boards, placements)
        """
        # Load orchestrator config (needed for validation and later passes)
        orch_data = _merge_yaml_dir(scenario_dir / "orchestrator")
        if not orch_data:
            message = f"Empty orchestrator config in {scenario_dir / 'orchestrator'}"
            raise ValidationError(message)
        try:
            orch = OrchestratorConfigModel(**orch_data)
        except Exception as e:
            message = f"Orchestrator config validation failed: {e}"
            raise ValidationError(message)

        logger.info(f"Loaded orchestrator config: {orch.name} (version {orch.version})")

        # Load external data (needed for all passes)
        ext = None
        external_dir = scenario_dir / "external"
        if external_dir.is_dir():
            ext_data = _merge_yaml_dir(external_dir)
            if ext_data:
                try:
                    ext = ExternalSeedModel(**ext_data)
                except Exception as e:
                    message = f"External seed data validation failed: {e}"
                    raise ValidationError(message)

        # Pass 1: Seed external projects first to establish project context
        if ext and ext.projects:
            for project_model in ext.projects:
                await self.create_project(
                    name=project_model.name,
                    description=project_model.description,
                    repository_url=project_model.repository_url,
                    default_branch=project_model.default_branch,
                    metadata=project_model.metadata,
                )

        # Pass 2: Apply orchestrator config (with project context now available)
        await self._apply_orchestrator_config(orch)

        # Pass 3: Seed remaining external data
        if ext:
            await self._seed_external_data(ext, orch)

        # If orchestrator config was seeded with placeholder project_id and we now have
        # a real project, migrate workflows/agents from placeholder to the real project
        if (
            "orchestrator-default" in self._config_store.pipelines
            and self._current_project_id is not None
            and self._current_project_id != "orchestrator-default"
        ):
            logger.info(
                f"Migrating orchestrator config from placeholder to actual project_id: {self._current_project_id}"
            )
            await self._migrate_orchestrator_config(self._current_project_id)

        logger.info(f"Scenario seeded successfully from {scenario_dir}")
        return self

    async def _apply_orchestrator_config(self, orch: OrchestratorConfigModel) -> None:
        """Apply orchestrator-owned config: workflows, agents, board policies.

        Workflows are registered even when no external project has been seeded
        yet (real-adapter mode). A synthetic project_id is used as a namespace
        when the seeder has no current project context.
        """
        # Ensure a project context exists so create_workflow doesn't fail.
        # In real-adapter mode there is no external/ dir, so no project is seeded
        # by this seeder — use a deterministic placeholder.
        effective_project_id = self._current_project_id or "orchestrator-default"

        # Seed workflows
        for workflow_model in orch.workflows:
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
                project_id=effective_project_id,
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
            for agent in orch.agents
        ]
        if agent_defs:
            await self.create_agents(agent_defs, project_id=effective_project_id)

        # Register board policies (workflow templates) — board structure is in external/
        # but policies can be registered before the board itself is created; the
        # board service wires them on first use.
        for policy in orch.board_policies:
            await self.register_workflow_template_from_column_configs(
                board_id=policy.board_id,
                column_configs=policy.column_configs,
                project_id=effective_project_id,
            )

    async def _seed_external_data(self, ext: ExternalSeedModel, orch: OrchestratorConfigModel) -> None:
        """Seed external-system data: work items, board structures, placements.

        Note: Projects are seeded separately in _seed_from_split_dir as Pass 1
        to establish the project context for orchestrator config in Pass 2.
        """
        # Seed work items
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
        for work_item_model in ext.work_items:
            priority = priority_map.get(work_item_model.priority, WorkItemPriority.MEDIUM)
            status = status_map.get(work_item_model.status, WorkItemStatus.NEW)
            item_metadata = dict(work_item_model.metadata)
            if work_item_model.parent_issue_id is not None:
                item_metadata.setdefault("parent_issue_id", work_item_model.parent_issue_id)
            await self.create_work_items(
                count=1,
                title_prefix=work_item_model.title,
                labels=work_item_model.labels,
                priority=priority,
                status=status,
                metadata=item_metadata,
            )

        # Seed board structures
        for board_struct in ext.boards:
            await self.create_board(
                board_id=board_struct.board_id,
                board_name=board_struct.board_name,
                column_names=board_struct.columns,
            )

        # Seed board placements (match work items by title prefix)
        if ext.board_placements:
            all_items: dict[str, str] = {}
            for item_id in self.created_items.work_items:
                try:
                    item = await self._ticket_adapter.get_work_item(item_id)
                    all_items[item.title] = item.id
                except Exception:
                    logger.error(
                        f"Failed to retrieve work item {item_id} during board placement seeding",
                        exc_info=True,
                    )
                    continue

            board_id = ext.boards[0].board_id if ext.boards else "board-1"
            for placement in ext.board_placements:
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

    async def _migrate_orchestrator_config(self, new_project_id: str) -> None:
        """Migrate workflows and agents from orchestrator-default placeholder to actual project_id.

        When split-directory scenarios are seeded, the orchestrator config (workflows, agents, board
        policies) is applied before external projects are created. This creates pipelines and agents
        under the "orchestrator-default" placeholder project_id. Once external projects are seeded,
        we need to migrate these orchestrator-owned entities to the real project.

        Args:
            new_project_id: The actual project UUID to migrate to
        """
        from dataclasses import replace

        placeholder_project_id = "orchestrator-default"

        # Migrate pipelines
        if placeholder_project_id in self._config_store.pipelines:
            placeholder_pipelines = self._config_store.pipelines[placeholder_project_id]
            if new_project_id not in self._config_store.pipelines:
                self._config_store.pipelines[new_project_id] = {}

            for pipeline_name, pipeline_config in placeholder_pipelines.items():
                # Create new pipeline config with updated project_id
                new_pipeline = replace(pipeline_config, project_id=new_project_id)
                self._config_store.pipelines[new_project_id][pipeline_name] = new_pipeline
                logger.info(f"Migrated pipeline '{pipeline_name}' to project {new_project_id}")

            # Delete the placeholder project's pipelines
            del self._config_store.pipelines[placeholder_project_id]

        # Migrate agents
        if placeholder_project_id in self._config_store.agents:
            placeholder_agents = self._config_store.agents[placeholder_project_id]
            if new_project_id not in self._config_store.agents:
                self._config_store.agents[new_project_id] = {}

            for agent_name, agent_config in placeholder_agents.items():
                # Create new agent config with updated project_id
                new_agent = replace(agent_config, project_id=new_project_id)
                self._config_store.agents[new_project_id][agent_name] = new_agent
                logger.info(f"Migrated agent '{agent_name}' to project {new_project_id}")

            # Delete the placeholder project's agents
            del self._config_store.agents[placeholder_project_id]

        # Migrate board templates
        # List all templates for the placeholder project
        placeholder_templates = await self.adapters.workflow_config.list_board_workflow_templates(
            placeholder_project_id
        )

        for template in placeholder_templates:
            # Create new template with updated project_id
            new_template = replace(template, project_id=new_project_id)
            # Save the new template (overwrites in place since board_id is unchanged)
            await self.adapters.workflow_config.save_board_workflow_template(new_template)
            logger.info(f"Migrated board template '{template.board_id}' to project {new_project_id}")

    async def _seed_legacy_scenario(self, scenario: ScenarioModel) -> None:
        """Seed a legacy (flat) ScenarioModel — all data in one pass."""
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
        for work_item_model in scenario.work_items:
            priority = priority_map.get(work_item_model.priority, WorkItemPriority.MEDIUM)
            status = status_map.get(work_item_model.status, WorkItemStatus.NEW)
            item_metadata = dict(work_item_model.metadata)
            if work_item_model.parent_issue_id is not None:
                item_metadata.setdefault("parent_issue_id", work_item_model.parent_issue_id)
            await self.create_work_items(
                count=1,
                title_prefix=work_item_model.title,
                labels=work_item_model.labels,
                priority=priority,
                status=status,
                metadata=item_metadata,
            )

        # Seed boards and register workflow templates
        agent_types: list[str] = []
        for workflow_model in scenario.workflows:
            sorted_stages = sorted(workflow_model.stages, key=lambda s: s.order)
            agent_types = [stage.agent_type for stage in sorted_stages]
            break

        for board_model in scenario.boards:
            await self.create_board(
                board_id=board_model.board_id,
                board_name=board_model.board_name,
                column_names=board_model.columns,
            )
            if board_model.column_configs:
                await self.register_workflow_template_from_column_configs(
                    board_id=board_model.board_id,
                    column_configs=board_model.column_configs,
                )
            elif agent_types:
                await self.register_workflow_template(
                    board_id=board_model.board_id,
                    column_names=board_model.columns,
                    agent_types=agent_types,
                    sla_seconds_by_column=board_model.sla_seconds_by_column,
                )

        # Seed board placements
        if scenario.board_placements:
            all_items: dict[str, str] = {}
            for item_id in self.created_items.work_items:
                try:
                    item = await self._ticket_adapter.get_work_item(item_id)
                    all_items[item.title] = item.id
                except Exception:
                    logger.error(
                        f"Failed to retrieve work item {item_id} during board placement seeding",
                        exc_info=True,
                    )
                    continue

            board_id = scenario.boards[0].board_id if scenario.boards else "board-1"
            for placement in scenario.board_placements:
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
