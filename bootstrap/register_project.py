#!/usr/bin/env python3
"""Register a project in Codetoreum's configuration store.

Usage:
    .venv/bin/python bootstrap/register_project.py [path/to/project.json]

Reads a project JSON file (default: bootstrap/project.json) and persists
the project config and agent configs to Elasticsearch. The server loads these
at startup — restart it to activate new registrations.

JSON format:
    {
      "project": { "id", "name", "github_org", "github_repo", "description", "default_branch" },
      "agents": [{ "name", "model", "timeout", "requires_docker", "makes_code_changes",
                   "capabilities", "description", "commit_policy" }],
      "board": { "id", "name", "columns": [{ "name", "type", "agent_id",
                 "is_pipeline_trigger", "is_exit_column", "auto_progress_on_completion",
                 "sla_seconds", "on_failure_column" }] }
    }
"""

import asyncio
import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root / "src"))

from elasticsearch import AsyncElasticsearch

from codetoreum.adapters.secondary.elasticsearch_config_storage import (
    ElasticsearchConfigStorage,
)
from codetoreum.ports.output.config_store import AgentConfig, ProjectConfig


def _load_config(config_path: Path) -> dict:
    with open(config_path) as f:
        return json.load(f)


async def _register(config: dict, es_url: str) -> None:
    es_client = AsyncElasticsearch([es_url])
    try:
        store = ElasticsearchConfigStorage(es_client)
        await store.initialize()

        now = datetime.now(UTC)
        project = config["project"]

        project_config = ProjectConfig(
            id=project["id"],
            name=project["name"],
            github_org=project["github_org"],
            github_repo=project["github_repo"],
            version=1,
            created_at=now,
            updated_at=now,
            metadata={
                "description": project.get("description", ""),
                "default_branch": project.get("default_branch", "main"),
                "repository_url": (f"https://github.com/{project['github_org']}/{project['github_repo']}.git"),
            },
        )
        await store.save_project_config(project_config)
        print(f"  [OK] project '{project_config.id}'  ({project_config.github_org}/{project_config.github_repo})")

        for agent_def in config.get("agents", []):
            agent_config = AgentConfig(
                project_id=project["id"],
                agent_name=agent_def["name"],
                model=agent_def.get("model", "claude-sonnet-4-6"),
                timeout=agent_def.get("timeout", 3600),
                requires_docker=agent_def.get("requires_docker", True),
                makes_code_changes=agent_def.get("makes_code_changes", True),
                capabilities=agent_def.get("capabilities", ["code_generation"]),
                version=1,
                created_at=now,
                updated_at=now,
                metadata={
                    "description": agent_def.get("description", ""),
                    "commit_policy": agent_def.get("commit_policy", "on_success"),
                },
            )
            await store.save_agent_config(agent_config)
            print(f"  [OK] agent   '{agent_config.agent_name}'  (model: {agent_config.model})")

    finally:
        await es_client.close()


def _print_next_steps(config: dict) -> None:
    project_id = config["project"]["id"]
    board_id = config.get("board", {}).get("id", "board-1")

    print()
    print("Restart the server to activate agents and board workflow, then:")
    print()
    print("  Extract the auth token printed on startup:")
    print(
        "     AUTH_TOKEN=$(grep 'Authentication token:' /tmp/codetoreum.log | sed 's/.*Authentication token: //' | tr -d '[:space:]')"
    )
    print()
    print("  1. Create a work item (or link a GitHub issue):")
    print("     curl -s -X POST http://localhost:8000/api/v2/work-items \\")
    print("       -H 'Content-Type: application/json' \\")
    print("       -H 'Authorization: Bearer $AUTH_TOKEN' \\")
    print("       -d '{")
    print(f'         "project_id": "{project_id}",')
    print('         "title": "My task title",')
    print('         "description": "Detailed description of what Claude should do",')
    print('         "external_id": "42",')
    print(
        f'         "external_url": "https://github.com/{config["project"]["github_org"]}/{config["project"]["github_repo"]}/issues/42"'
    )
    print("       }'")
    print()
    print("     The external_id/external_url fields link to a GitHub issue (optional).")
    print()
    print("  2. Trigger execution (move to 'In Progress'):")
    print("     curl -s -X POST http://localhost:8000/api/v2/trigger/column-change \\")
    print("       -H 'Content-Type: application/json' \\")
    print("       -H 'Authorization: Bearer $AUTH_TOKEN' \\")
    print("       -d '{")
    print('         "work_item_id": "<id-from-step-1>",')
    print('         "to_column": "In Progress",')
    print(f'         "project_id": "{project_id}",')
    print(f'         "board_id": "{board_id}"')
    print("       }'")


def main() -> None:
    config_path = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).parent / "project.json"
    if not config_path.exists():
        print(f"Error: config file not found: {config_path}", file=sys.stderr)
        sys.exit(1)

    es_url = os.environ.get("ELASTICSEARCH_URL", "http://localhost:9200")
    config = _load_config(config_path)

    print(f"Registering '{config['project']['id']}' → {es_url}")
    asyncio.run(_register(config, es_url))
    _print_next_steps(config)


if __name__ == "__main__":
    main()
