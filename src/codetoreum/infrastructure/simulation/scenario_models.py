"""
Pydantic models for YAML scenario validation.

These models define the schema for declarative scenario configuration files.
"""

from datetime import datetime
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

if TYPE_CHECKING:
    from codetoreum.domain.pr_review_cycle_types import PRReviewCycleConfig
    from codetoreum.domain.repair_cycle_types import RepairCycleAgentConfig


class ScenarioProjectModel(BaseModel):
    """Project configuration in scenario file."""

    name: str = Field(..., description="Project name (must be unique)")
    description: str = Field(default="", description="Project description")
    repository_url: str | None = Field(default=None, description="Repository URL (auto-generated if not provided)")
    default_branch: str = Field(default="main", description="Default branch name")
    metadata: dict[str, Any] = Field(default_factory=dict, description="Additional metadata")


class ScenarioStageModel(BaseModel):
    """Pipeline stage configuration in scenario file."""

    name: str = Field(..., description="Stage name")
    agent_type: str = Field(..., description="Agent type for this stage")
    description: str = Field(default="", description="Stage description")
    order: int = Field(..., description="Stage order (1-based)")
    entry_conditions: dict[str, Any] = Field(default_factory=dict, description="Entry conditions")
    exit_conditions: dict[str, Any] = Field(default_factory=dict, description="Exit conditions")
    max_retries: int = Field(default=3, description="Maximum retry attempts", ge=0)
    timeout_seconds: int = Field(default=3600, description="Stage timeout in seconds", ge=1)

    @field_validator("order")
    @classmethod
    def validate_order(cls, v: int) -> int:
        """Validate stage order is positive."""
        if v < 1:
            message = "Stage order must be >= 1"
            raise ValueError(message)
        return v


class ScenarioWorkflowModel(BaseModel):
    """Workflow configuration in scenario file."""

    name: str = Field(..., description="Workflow name")
    description: str = Field(default="", description="Workflow description")
    stages: list[ScenarioStageModel] = Field(default_factory=list, description="Pipeline stages")

    @field_validator("stages")
    @classmethod
    def validate_stages(cls, v: list[ScenarioStageModel]) -> list[ScenarioStageModel]:
        """Validate stages have unique names and sequential order."""
        if not v:
            return v

        stage_names = [s.name for s in v]
        if len(stage_names) != len(set(stage_names)):
            message = "Stage names must be unique"
            raise ValueError(message)

        stage_orders = [s.order for s in v]
        expected_orders = list(range(1, len(v) + 1))
        if sorted(stage_orders) != expected_orders:
            message = f"Stage orders must be sequential 1..{len(v)}"
            raise ValueError(message)

        return v


class ScenarioAgentModel(BaseModel):
    """Agent configuration in scenario file."""

    name: str = Field(..., description="Agent name")
    agent_type: str = Field(default="generic", description="Agent type")
    description: str = Field(default="", description="Agent description")
    capabilities: list[str] = Field(default_factory=lambda: ["code_generation"], description="Agent capabilities")
    llm_model: str = Field(default="claude-3-5-sonnet-20241022", description="LLM model to use")
    temperature: float = Field(default=0.7, description="LLM temperature", ge=0.0, le=2.0)
    max_tokens: int = Field(default=4096, description="Maximum tokens", ge=1)
    system_prompt: str = Field(default="", description="System prompt")
    enabled: bool = Field(default=True, description="Whether agent is enabled")
    metadata: dict[str, Any] = Field(default_factory=dict, description="Additional metadata")

    @field_validator("capabilities")
    @classmethod
    def validate_capabilities(cls, v: list[str]) -> list[str]:
        """Validate capabilities are valid."""
        valid_capabilities = {
            "code_generation",
            "code_review",
            "testing",
            "documentation",
            "security_analysis",
            "performance_analysis",
        }
        for cap in v:
            if cap not in valid_capabilities:
                message = f"Invalid capability: {cap}. Valid: {valid_capabilities}"
                raise ValueError(message)
        return v


class RepairCycleAgentConfigModel(BaseModel):
    """YAML representation of per-sub-task agent assignments for the repair cycle.

    Maps repair cycle sub-tasks to specific agents. All fields are optional;
    None means fall back to the stage's default agent.

    Sub-task names correspond to the operations performed by the repair cycle:
    - test_execution: Runs tests and parses results
    - code_fix: Fixes code-level test failures
    - systemic_analysis: Classifies failure root causes
    - systemic_fix: Applies cross-cutting fixes
    - env_rebuild: Rebuilds test environment
    - env_verification: Verifies rebuilt environment
    - ci_check: Remediation for CI pipeline check failures (e.g., lint violations)
    """

    test_execution: str | None = Field(
        default=None,
        description="Agent for test execution sub-task",
    )
    code_fix: str | None = Field(
        default=None,
        description="Agent for code-level fixing sub-task",
    )
    systemic_analysis: str | None = Field(
        default=None,
        description="Agent for systemic analysis sub-task",
    )
    systemic_fix: str | None = Field(
        default=None,
        description="Agent for systemic fix sub-task",
    )
    env_rebuild: str | None = Field(
        default=None,
        description="Agent for environment rebuild sub-task",
    )
    env_verification: str | None = Field(
        default=None,
        description="Agent for environment verification sub-task",
    )
    ci_check: str | None = Field(
        default=None,
        description="Agent for CI check remediation sub-task",
    )

    def to_domain(self) -> "RepairCycleAgentConfig":
        """Convert this Pydantic model to a domain RepairCycleAgentConfig instance.

        Returns:
            A RepairCycleAgentConfig domain instance with the same field values.
        """
        from codetoreum.domain.repair_cycle_types import RepairCycleAgentConfig

        return RepairCycleAgentConfig(
            test_execution=self.test_execution,
            code_fix=self.code_fix,
            systemic_analysis=self.systemic_analysis,
            systemic_fix=self.systemic_fix,
            env_rebuild=self.env_rebuild,
            env_verification=self.env_verification,
            ci_check=self.ci_check,
        )


class PRReviewCycleConfigModel(BaseModel):
    """YAML representation of PR review cycle configuration.

    Mirrors the PRReviewCycleConfig domain model with Pydantic validation.
    All fields are optional and default to the domain model defaults.

    Attributes:
        max_outer_cycles: Maximum number of complete cycles before escalation (>= 1, default 3)
        verifier_context_sources: Tuple of context sources for verification phase
        code_review_timeout_seconds: Timeout for Phase 1 code review
        verification_timeout_seconds: Timeout per verification context source
        ci_check_enabled: Whether to perform Phase 3 CI check
        ci_check_timeout_seconds: Timeout for CI check
        consolidation_timeout_seconds: Timeout for Phase 4 consolidation
        sub_issue_creation: Whether to create sub-issues when findings are found
        sub_issue_labels: Labels to apply to created sub-issues
        sub_issue_initial_column: Column to place created sub-issues in
    """

    max_outer_cycles: int = Field(
        default=3,
        description="Maximum number of complete cycles before escalation",
        ge=1,
    )
    verifier_context_sources: list[str] = Field(
        default_factory=lambda: ["parent_issue"],
        description="List of context sources to use during verification phase",
        min_length=1,
    )
    code_review_timeout_seconds: int = Field(
        default=600,
        description="Timeout for Phase 1 code review in seconds",
        gt=0,
    )
    verification_timeout_seconds: int = Field(
        default=300,
        description="Timeout per verification context source in seconds",
        gt=0,
    )
    ci_check_enabled: bool = Field(
        default=True,
        description="Whether to perform Phase 3 CI check validation",
    )
    ci_check_timeout_seconds: int = Field(
        default=300,
        description="Timeout for Phase 3 CI check in seconds (must be > 0 when enabled)",
        ge=0,
    )
    consolidation_timeout_seconds: int = Field(
        default=600,
        description="Timeout for Phase 4 consolidation in seconds",
        gt=0,
    )
    sub_issue_target_board: str | None = Field(
        default=None,
        description="Board ID where sub-issues will be created",
    )
    sub_issue_creation: bool = Field(
        default=True,
        description="Whether to create sub-issues when findings are found",
    )
    sub_issue_labels: list[str] = Field(
        default_factory=list,
        description="Labels to apply to created sub-issues",
    )
    sub_issue_initial_column: str | None = Field(
        default=None,
        description="Column to place created sub-issues in",
    )
    on_issues_found_column: str | None = Field(
        default=None,
        description="Column to move item to when issues are found",
    )
    on_approved_column: str | None = Field(
        default=None,
        description="Column to move item to when approved",
    )
    agents: dict[str, str] | None = Field(
        default=None,
        description="Mapping of phase names to agent IDs (e.g., {'code_review': 'pr_code_reviewer'})",
    )

    @field_validator("ci_check_timeout_seconds")
    @classmethod
    def validate_ci_check_timeout(cls, v: int, info) -> int:
        """Validate ci_check_timeout_seconds when ci_check_enabled is True."""
        # Get the ci_check_enabled value from the data
        ci_check_enabled = info.data.get("ci_check_enabled", True)
        if ci_check_enabled and v <= 0:
            msg = f"ci_check_timeout_seconds must be > 0 when ci_check_enabled=True, got {v}"
            raise ValueError(msg)
        return v

    def to_domain(self) -> "PRReviewCycleConfig":
        """Convert this Pydantic model to a domain PRReviewCycleConfig instance.

        Returns:
            A PRReviewCycleConfig domain instance with the same field values.
            verifier_context_sources is converted from list to tuple.
            agents dict is decomposed into individual code_review_agent, verifier_agent,
            and consolidation_agent fields.
        """
        from codetoreum.domain.pr_review_cycle_types import PRReviewCycleConfig

        # Build kwargs with only the non-None values for optional fields
        kwargs = {
            "max_outer_cycles": self.max_outer_cycles,
            "verifier_context_sources": tuple(self.verifier_context_sources),
            "code_review_timeout_seconds": self.code_review_timeout_seconds,
            "verification_timeout_seconds": self.verification_timeout_seconds,
            "ci_check_enabled": self.ci_check_enabled,
            "ci_check_timeout_seconds": self.ci_check_timeout_seconds,
            "consolidation_timeout_seconds": self.consolidation_timeout_seconds,
            "sub_issue_target_board": self.sub_issue_target_board,
            "sub_issue_creation": self.sub_issue_creation,
            "sub_issue_labels": tuple(self.sub_issue_labels),
        }

        # Only add optional column fields if not None, so domain defaults apply
        if self.sub_issue_initial_column is not None:
            kwargs["sub_issue_initial_column"] = self.sub_issue_initial_column
        if self.on_issues_found_column is not None:
            kwargs["on_issues_found_column"] = self.on_issues_found_column
        if self.on_approved_column is not None:
            kwargs["on_approved_column"] = self.on_approved_column

        # Decompose agents dict into individual agent fields
        if self.agents:
            if "code_review" in self.agents:
                kwargs["code_review_agent"] = self.agents["code_review"]
            if "verification" in self.agents:
                kwargs["verifier_agent"] = self.agents["verification"]
            if "consolidation" in self.agents:
                kwargs["consolidation_agent"] = self.agents["consolidation"]

        return PRReviewCycleConfig(**kwargs)


class ScenarioColumnConfig(BaseModel):
    """Explicit column configuration for a board workflow template.

    When ``column_configs`` is provided on a board, the seeder uses these
    definitions directly instead of auto-generating routing from positional
    rules.  This lets you express the full ``ColumnTemplate`` schema — agent
    assignments, pipeline-trigger flags, exit columns, SLA thresholds, and
    auto-progression — in the scenario YAML.

    The ``columns`` list on the parent ``ScenarioBoardModel`` still controls
    which columns the mock board adapter creates; ``column_configs`` controls
    the *workflow semantics* registered with ``IWorkflowConfigService``.
    """

    name: str = Field(..., description="Column name — must match an entry in the parent board's columns list")
    type: str = Field(default="manual", description="Column type: 'manual' or 'automated'")
    agent_id: str | None = Field(
        default=None, description="Agent ID to trigger on entry (required when type=automated)"
    )
    is_pipeline_trigger: bool = Field(default=False, description="If True, acquiring pipeline lock when item enters")
    is_exit_column: bool = Field(default=False, description="If True, releasing pipeline lock when item enters")
    auto_progress_on_completion: bool = Field(
        default=False, description="Automatically move item to next column after agent completion (automated only)"
    )
    sla_seconds: int | None = Field(
        default=None, description="SLA threshold in seconds; None disables SLA enforcement", ge=1
    )
    on_failure_column: str | None = Field(
        default=None, description="Column to move item to on agent failure; None keeps item in place"
    )
    sla_escalation_column: str | None = Field(
        default=None, description="Column to move item to when SLA expires; None emits event only"
    )
    repair_cycle_agents: RepairCycleAgentConfigModel | None = Field(
        default=None,
        description="Per-sub-task agent assignments for the repair cycle on this column",
    )
    repair_cycle_test_types: list[str] | None = Field(
        default=None,
        description=(
            "Ordered list of test type names to run when this column triggers a repair cycle. "
            "Valid values: COMPILATION, UNIT, INTEGRATION, CI, E2E. "
            "When omitted, the handler uses the default sequence (UNIT, INTEGRATION, E2E)."
        ),
    )
    pr_review_cycle_config: PRReviewCycleConfigModel | None = Field(
        default=None,
        description=(
            "Configuration for PR review cycle on this column. When set, triggers PR review cycle "
            "instead of agent execution. Mutually exclusive with repair_cycle_agents."
        ),
    )
    execution_type: str = Field(
        default="task_queue", description="Execution mode: 'task_queue' (default) or 'conversational'"
    )

    @field_validator("type")
    @classmethod
    def validate_type(cls, v: str) -> str:
        """Validate column type is manual or automated."""
        if v not in ("manual", "automated"):
            message = f"Invalid column type: {v!r}. Valid values: manual, automated"
            raise ValueError(message)
        return v

    @field_validator("execution_type")
    @classmethod
    def validate_execution_type(cls, v: str) -> str:
        """Validate execution type is task_queue or conversational."""
        if v not in ("task_queue", "conversational"):
            message = f"Invalid execution_type: {v!r}. Valid values: task_queue, conversational"
            raise ValueError(message)
        return v


class ScenarioBoardModel(BaseModel):
    """Board configuration in scenario file."""

    board_id: str = Field(..., description="Board ID")
    board_name: str = Field(..., description="Board display name")
    columns: list[str] = Field(..., description="Column names in order", min_length=1)
    sla_seconds_by_column: dict[str, int] = Field(
        default_factory=dict,
        description="Optional SLA thresholds in seconds for each column name. "
        "If not specified, automated columns default to 3600 seconds (1 hour). "
        "Ignored when column_configs is provided.",
    )
    column_configs: list[ScenarioColumnConfig] = Field(
        default_factory=list,
        description="Explicit per-column workflow semantics. "
        "When non-empty, overrides auto-generation from positional workflow stage order. "
        "Each entry must correspond to a name listed in columns.",
    )

    @model_validator(mode="after")
    def validate_column_configs_references(self) -> "ScenarioBoardModel":
        """Validate that column_configs names and cross-column references exist in columns."""
        if not self.column_configs:
            return self
        column_set = set(self.columns)
        for cfg in self.column_configs:
            if cfg.name not in column_set:
                msg = f"column_configs entry '{cfg.name}' is not listed in columns: {self.columns}"
                raise ValueError(msg)
            if cfg.on_failure_column and cfg.on_failure_column not in column_set:
                msg = (
                    f"column_configs '{cfg.name}': on_failure_column '{cfg.on_failure_column}' "
                    f"is not listed in columns: {self.columns}"
                )
                raise ValueError(msg)
            if cfg.sla_escalation_column and cfg.sla_escalation_column not in column_set:
                msg = (
                    f"column_configs '{cfg.name}': sla_escalation_column "
                    f"'{cfg.sla_escalation_column}' is not listed in columns: {self.columns}"
                )
                raise ValueError(msg)
        return self


class ScenarioBoardItemPlacementModel(BaseModel):
    """Board item placement in scenario file."""

    work_item_title: str = Field(..., description="Work item title prefix to match")
    column: str = Field(..., description="Column to place the item in")


class ScenarioWorkItemModel(BaseModel):
    """Work item configuration in scenario file."""

    title: str = Field(..., description="Work item title")
    description: str = Field(default="", description="Work item description")
    labels: list[str] = Field(default_factory=list, description="Labels")
    priority: str = Field(default="medium", description="Priority level")
    status: str = Field(default="new", description="Initial status")
    parent_issue_id: int | None = Field(default=None, description="Parent issue ID for child-issue relationships")
    metadata: dict[str, Any] = Field(default_factory=dict, description="Additional metadata")

    @field_validator("priority")
    @classmethod
    def validate_priority(cls, v: str) -> str:
        """Validate priority is valid."""
        valid_priorities = {"low", "medium", "high", "critical"}
        if v.lower() not in valid_priorities:
            message = f"Invalid priority: {v}. Valid: {valid_priorities}"
            raise ValueError(message)
        return v.lower()

    @field_validator("status")
    @classmethod
    def validate_status(cls, v: str) -> str:
        """Validate status is valid."""
        valid_statuses = {
            "new",
            "assigned",
            "in_progress",
            "under_review",
            "completed",
            "failed",
            "blocked",
        }
        if v.lower() not in valid_statuses:
            message = f"Invalid status: {v}. Valid: {valid_statuses}"
            raise ValueError(message)
        return v.lower()


class ScenarioBoardStructureModel(BaseModel):
    """External board structure — owned by the external ticket system.

    Contains only the board identity and column names; no orchestrator
    policy (triggers, SLAs, agents).  Seeded into ``IBoardService`` during
    simulation; skipped when using real adapters (the board already exists).
    """

    board_id: str = Field(..., description="Board ID")
    board_name: str = Field(..., description="Board display name")
    columns: list[str] = Field(..., description="Column names in order", min_length=1)


class ScenarioBoardPolicyModel(BaseModel):
    """Orchestrator board policy — always owned by Codetoreum.

    Contains the ``BoardWorkflowTemplate`` metadata for a board: column
    triggers, exit flags, agent assignments, SLAs, and failure routing.
    Registered with ``IWorkflowConfigService`` on every startup, regardless
    of whether real or simulation adapters are used.
    """

    board_id: str = Field(..., description="Board ID this policy applies to")
    column_configs: list[ScenarioColumnConfig] = Field(
        ...,
        description="Per-column workflow semantics (triggers, SLAs, agents, failure routing)",
        min_length=1,
    )


class ExternalSeedModel(BaseModel):
    """Root model for ``external/`` scenario files.

    Data in this model is owned by the external system (ticket tracker, board
    provider) in production.  During simulation it is seeded so the mock
    adapters have realistic state to work with.  When real adapters are
    connected this entire directory should be skipped.
    """

    projects: list[ScenarioProjectModel] = Field(default_factory=list, description="Projects to create")
    work_items: list[ScenarioWorkItemModel] = Field(default_factory=list, description="Work items to create")
    boards: list[ScenarioBoardStructureModel] = Field(default_factory=list, description="Board structures to create")
    board_placements: list[ScenarioBoardItemPlacementModel] = Field(
        default_factory=list, description="Initial work item placements on boards"
    )

    @field_validator("projects")
    @classmethod
    def validate_projects(cls, v: list[ScenarioProjectModel]) -> list[ScenarioProjectModel]:
        """Validate project names are unique."""
        if len(v) != len({p.name for p in v}):
            raise ValueError("Project names must be unique")
        return v


class OrchestratorConfigModel(BaseModel):
    """Root model for ``orchestrator/`` scenario files.

    Config in this model is always owned by Codetoreum.  It is applied on
    every simulation startup, and will carry across to real-adapter
    deployments where the same workflow and agent definitions are needed.
    """

    name: str = Field(..., description="Scenario name")
    description: str = Field(default="", description="Scenario description")
    version: str = Field(default="1.0", description="Scenario version")

    # Simulation clock settings
    speed_multiplier: float = Field(default=10.0, description="Time speed multiplier", gt=0)
    auto_advance: bool = Field(default=False, description="Auto-advance simulation clock")

    # Orchestrator-owned definitions
    agents: list[ScenarioAgentModel] = Field(default_factory=list, description="Agent configurations")
    workflows: list[ScenarioWorkflowModel] = Field(default_factory=list, description="Workflow definitions")
    board_policies: list[ScenarioBoardPolicyModel] = Field(
        default_factory=list, description="Per-board column policy (triggers, SLAs, agents)"
    )

    # Additional metadata
    metadata: dict[str, Any] = Field(default_factory=dict, description="Additional scenario metadata")

    @field_validator("agents")
    @classmethod
    def validate_agents(cls, v: list[ScenarioAgentModel]) -> list[ScenarioAgentModel]:
        """Validate agent names are unique."""
        if len(v) != len({a.name for a in v}):
            raise ValueError("Agent names must be unique")
        return v

    @field_validator("workflows")
    @classmethod
    def validate_workflows(cls, v: list[ScenarioWorkflowModel]) -> list[ScenarioWorkflowModel]:
        """Validate workflow names are unique."""
        if len(v) != len({w.name for w in v}):
            raise ValueError("Workflow names must be unique")
        return v

    @model_validator(mode="after")
    def validate_repair_cycle_agent_refs(self) -> "OrchestratorConfigModel":
        """Validate that all repair_cycle_agents references exist in the agents list.

        For each column_config with repair_cycle_agents set, verify that every
        non-None agent name exists in the scenario's agents list.

        Raises:
            ValueError: If any referenced agent is not defined in the agents list.
        """
        defined_agents = {a.name for a in self.agents}

        for policy in self.board_policies:
            for col in policy.column_configs:
                if col.repair_cycle_agents is None:
                    continue

                rc = col.repair_cycle_agents
                for field_name, agent_name in [
                    ("test_execution", rc.test_execution),
                    ("code_fix", rc.code_fix),
                    ("systemic_analysis", rc.systemic_analysis),
                    ("systemic_fix", rc.systemic_fix),
                    ("env_rebuild", rc.env_rebuild),
                    ("env_verification", rc.env_verification),
                ]:
                    if agent_name and agent_name not in defined_agents:
                        msg = (
                            f"In board policy '{policy.board_id}', column '{col.name}': "
                            f"repair_cycle_agents.{field_name} references agent '{agent_name}' "
                            f"which is not defined in agents list. Defined agents: {sorted(defined_agents)}"
                        )
                        raise ValueError(msg)

        return self


class ScenarioModel(BaseModel):
    """
    Complete scenario configuration model.

    This is the root model for YAML scenario files.
    """

    name: str = Field(..., description="Scenario name")
    description: str = Field(default="", description="Scenario description")
    version: str = Field(default="1.0", description="Scenario version")
    created_at: datetime | None = Field(default=None, description="Scenario creation timestamp")

    # Simulation config
    speed_multiplier: float = Field(default=10.0, description="Time speed multiplier", gt=0)
    auto_advance: bool = Field(default=False, description="Auto-advance time")

    # Data definitions
    projects: list[ScenarioProjectModel] = Field(default_factory=list, description="Projects to create")
    workflows: list[ScenarioWorkflowModel] = Field(default_factory=list, description="Workflows to create")
    agents: list[ScenarioAgentModel] = Field(default_factory=list, description="Agents to create")
    work_items: list[ScenarioWorkItemModel] = Field(default_factory=list, description="Work items to create")
    boards: list[ScenarioBoardModel] = Field(default_factory=list, description="Boards to create")
    board_placements: list[ScenarioBoardItemPlacementModel] = Field(
        default_factory=list, description="Work item placements on boards"
    )

    # Additional metadata
    metadata: dict[str, Any] = Field(default_factory=dict, description="Additional scenario metadata")

    @field_validator("projects")
    @classmethod
    def validate_projects(cls, v: list[ScenarioProjectModel]) -> list[ScenarioProjectModel]:
        """Validate project names are unique."""
        if not v:
            return v

        project_names = [p.name for p in v]
        if len(project_names) != len(set(project_names)):
            message = "Project names must be unique"
            raise ValueError(message)

        return v

    @field_validator("workflows")
    @classmethod
    def validate_workflows(cls, v: list[ScenarioWorkflowModel]) -> list[ScenarioWorkflowModel]:
        """Validate workflow names are unique."""
        if not v:
            return v

        workflow_names = [w.name for w in v]
        if len(workflow_names) != len(set(workflow_names)):
            message = "Workflow names must be unique"
            raise ValueError(message)

        return v

    @field_validator("agents")
    @classmethod
    def validate_agents(cls, v: list[ScenarioAgentModel]) -> list[ScenarioAgentModel]:
        """Validate agent names are unique."""
        if not v:
            return v

        agent_names = [a.name for a in v]
        if len(agent_names) != len(set(agent_names)):
            message = "Agent names must be unique"
            raise ValueError(message)

        return v

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "name": "Example Scenario",
                "description": "An example scenario for testing",
                "version": "1.0",
                "speed_multiplier": 10.0,
                "projects": [
                    {
                        "name": "test-project",
                        "description": "Test project",
                    }
                ],
                "workflows": [
                    {
                        "name": "simple-workflow",
                        "stages": [
                            {
                                "name": "design",
                                "agent_type": "architect",
                                "order": 1,
                            }
                        ],
                    }
                ],
                "agents": [
                    {
                        "name": "architect",
                        "agent_type": "architect",
                        "capabilities": ["code_generation"],
                    }
                ],
                "work_items": [
                    {
                        "title": "Test task",
                        "priority": "medium",
                    }
                ],
            }
        }
    )
