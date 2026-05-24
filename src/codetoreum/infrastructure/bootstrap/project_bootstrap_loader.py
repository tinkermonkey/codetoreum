"""Load project registrations from bootstrap/ JSON files at server startup.

Scans the project root's bootstrap/ directory for *.json files and populates
the in-memory services that are not ES-backed:
- IAgentRepository  — Agent domain objects built from bootstrap agent definitions
- IWorkflowConfigService — BoardWorkflowTemplate built from bootstrap board configs

Called by ProductionApplicationBootstrap during Phase 5c so that any project
registered via `bootstrap/register_project.py` is active without code changes.
"""

import json
import logging
from datetime import UTC, datetime
from pathlib import Path

from codetoreum.domain.agent import Agent, AgentCapability, AgentType, CommitPolicy
from codetoreum.domain.board_workflow_template import (
    BoardWorkflowTemplate,
    ColumnTemplate,
    ColumnType,
)
from codetoreum.ports.output.agent_repository import IAgentRepository
from codetoreum.ports.output.config_store import IConfigStore, ProjectConfig
from codetoreum.ports.output.workflow_config_service import IWorkflowConfigService

logger = logging.getLogger(__name__)


def _column_type(type_str: str) -> ColumnType:
    return ColumnType.AUTOMATED if type_str == "automated" else ColumnType.MANUAL


def _build_board_template(board_config: dict, project_id: str) -> BoardWorkflowTemplate:
    board_id = board_config["id"]
    columns = tuple(
        ColumnTemplate(
            name=col["name"],
            type=_column_type(col.get("type", "manual")),
            agent_id=col.get("agent_id"),
            is_pipeline_trigger=col.get("is_pipeline_trigger", False),
            is_exit_column=col.get("is_exit_column", False),
            position=pos,
            auto_progress_on_completion=col.get("auto_progress_on_completion", False),
            sla_seconds=col.get("sla_seconds"),
            on_failure_column=col.get("on_failure_column"),
        )
        for pos, col in enumerate(board_config["columns"])
    )
    return BoardWorkflowTemplate(
        id=f"template-{board_id}",
        name=board_config.get("name", f"Workflow for {board_id}"),
        board_id=board_id,
        project_id=project_id,
        columns=columns,
    )


def _build_agent(agent_def: dict, project_id: str) -> Agent:
    now = datetime.now(UTC)
    caps = agent_def.get("capabilities", ["code_generation"])
    try:
        commit_policy = CommitPolicy(agent_def.get("commit_policy", "on_success"))
    except ValueError:
        commit_policy = CommitPolicy.ON_SUCCESS

    return Agent(
        id=agent_def["name"],
        name=agent_def["name"],
        display_name=agent_def.get("description", agent_def["name"]),
        agent_type=AgentType.MAKER,
        capabilities={c: AgentCapability(skill=c, proficiency=1.0, description=c) for c in caps},
        role_description=agent_def.get("description", ""),
        model=agent_def.get("model", "claude-sonnet-4-6"),
        timeout_seconds=agent_def.get("timeout", 3600),
        max_retries=3,
        requires_docker=agent_def.get("requires_docker", False),
        requires_dev_container=False,
        makes_code_changes=agent_def.get("makes_code_changes", True),
        filesystem_write_allowed=True,
        mcp_servers=[],
        metadata={},
        created_at=now,
        updated_at=now,
        commit_policy=commit_policy,
    )


async def load_bootstrap_dir(
    bootstrap_dir: Path,
    agent_repository: IAgentRepository,
    workflow_config: IWorkflowConfigService,
    config_store: IConfigStore | None = None,
) -> int:
    """Load all *.json bootstrap files into in-memory services.

    Returns the number of project files successfully loaded.
    """
    if not bootstrap_dir.exists():
        logger.debug(f"Bootstrap directory not found, skipping: {bootstrap_dir}")
        return 0

    loaded = 0
    for json_path in sorted(bootstrap_dir.glob("*.json")):
        try:
            config = json.loads(json_path.read_text())
        except Exception as e:
            logger.error(
                f"Failed to read bootstrap file {json_path.name}: {e}",
                exc_info=True,
                extra={"error_id": "ERR_BOOTSTRAP_FILE_READ_FAILURE"},
            )
            continue

        project_id = config.get("project", {}).get("id")
        if not project_id:
            logger.warning(f"Skipping {json_path.name}: missing project.id")
            continue

        for agent_def in config.get("agents", []):
            try:
                agent = _build_agent(agent_def, project_id)
                await agent_repository.save(agent, project_id)
                logger.info(f"Loaded agent '{agent.id}' for project '{project_id}'")
            except Exception as e:
                logger.error(
                    f"Failed to load agent '{agent_def.get('name')}' from {json_path.name}: {e}",
                    exc_info=True,
                    extra={"error_id": "ERR_BOOTSTRAP_AGENT_LOAD_FAILURE"},
                )

        board_config = config.get("board")
        if board_config:
            try:
                template = _build_board_template(board_config, project_id)
                await workflow_config.save_board_workflow_template(template)
                logger.info(
                    f"Loaded board template '{template.board_id}' for project '{project_id}' "
                    f"({len(template.columns)} columns)",
                )
            except Exception as e:
                logger.error(
                    f"Failed to load board template from {json_path.name}: {e}",
                    exc_info=True,
                    extra={"error_id": "ERR_BOOTSTRAP_BOARD_TEMPLATE_LOAD_FAILURE"},
                )

        if config_store is not None:
            try:
                project_def = config.get("project", {})
                project_cfg = ProjectConfig(
                    id=project_id,
                    name=project_def.get("name", project_id),
                    github_org=project_def.get("github_org", ""),
                    github_repo=project_def.get("github_repo", ""),
                    created_at=datetime.now(UTC),
                    updated_at=datetime.now(UTC),
                )
                await config_store.save_project_config(project_cfg)
                logger.info(f"Loaded project config '{project_id}' into config_store")
            except Exception as e:
                logger.error(
                    f"Failed to load project config for '{project_id}' from {json_path.name}: {e}",
                    exc_info=True,
                    extra={"error_id": "ERR_BOOTSTRAP_PROJECT_CONFIG_LOAD_FAILURE"},
                )

        logger.info(f"Loaded bootstrap config: project='{project_id}' from {json_path.name}")
        loaded += 1

    return loaded
