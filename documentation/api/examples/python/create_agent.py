"""
Example: Create a new agent in Codetoreum

This example demonstrates how to create a new agent with capabilities
and MCP server configuration.
"""

import logging
from typing import Any, cast

import requests

logger = logging.getLogger(__name__)


# Configuration
BASE_URL = "http://localhost:8000"
API_TOKEN = "your_token_here"  # Get from server startup logs


def create_agent(
    name: str,
    description: str,
    agent_type: str = "claude_code",
    capabilities: list[str] | None = None,
    mcp_servers: list[dict[str, Any]] | None = None,
    configuration: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Create a new agent.

    Args:
        name: Unique agent identifier
        description: Human-readable description
        agent_type: Type of agent (claude_code, aider, custom)
        capabilities: List of skills/capabilities
        mcp_servers: MCP server configurations
        configuration: Agent-specific configuration

    Returns:
        Created agent data including ID

    Raises:
        requests.HTTPError: If request fails
    """
    url = f"{BASE_URL}/api/v2/agents/"

    headers = {
        "Authorization": f"Bearer {API_TOKEN}",
        "Content-Type": "application/json",
    }

    payload = {
        "name": name,
        "description": description,
        "agent_type": agent_type,
        "capabilities": capabilities or [],
        "configuration": configuration
        or {
            "model": "claude-sonnet-4",
            "temperature": 0.7,
            "max_tokens": 4000,
        },
        "active": True,
    }

    response = requests.post(url, json=payload, headers=headers, timeout=30)
    response.raise_for_status()

    agent_data: dict[str, Any] = cast("dict[str, Any]", response.json())
    logger.info("✓ Created agent: %s", agent_data["id"])

    # Add MCP servers if provided
    if mcp_servers:
        for mcp_server in mcp_servers:
            add_mcp_server(agent_data["id"], mcp_server)

    return agent_data


def add_mcp_server(agent_id: str, mcp_config: dict[str, Any]) -> dict[str, Any]:
    """
    Add MCP server to an agent.

    Args:
        agent_id: Agent ID
        mcp_config: MCP server configuration

    Returns:
        Updated MCP server configuration
    """
    url = f"{BASE_URL}/api/v2/agents/{agent_id}/mcp-servers"

    headers = {
        "Authorization": f"Bearer {API_TOKEN}",
        "Content-Type": "application/json",
    }

    response = requests.post(url, json=mcp_config, headers=headers, timeout=30)
    response.raise_for_status()

    result: dict[str, Any] = cast("dict[str, Any]", response.json())
    logger.info("✓ Added MCP server: %s", mcp_config["name"])
    return result


def main() -> None:
    """Example usage."""
    try:
        # Example 1: Create a backend development agent
        logger.info("Creating backend specialist agent...")
        backend_agent = create_agent(
            name="backend-specialist",
            description="Python backend development specialist",
            agent_type="claude_code",
            capabilities=[
                "python",
                "fastapi",
                "sqlalchemy",
                "postgresql",
                "docker",
            ],
            configuration={
                "model": "claude-sonnet-4",
                "temperature": 0.7,
                "max_tokens": 8000,
                "timeout_minutes": 120,
            },
            mcp_servers=[
                {
                    "name": "filesystem",
                    "command": "npx",
                    "args": [
                        "-y",
                        "@modelcontextprotocol/server-filesystem",
                        "/workspace",
                    ],
                    "env": {},
                },
                {
                    "name": "git",
                    "command": "npx",
                    "args": ["-y", "@modelcontextprotocol/server-git"],
                    "env": {},
                },
            ],
        )

        logger.info("Agent ID: %s", backend_agent["id"])
        logger.info("Name: %s", backend_agent["name"])
        logger.info("Capabilities: %s", ", ".join(backend_agent["capabilities"]))

        logger.info("✓ Created agent successfully")

    except requests.exceptions.HTTPError as e:
        logger.exception("API Error: %s", e.response.status_code)
        try:
            error_detail = e.response.json()
            logger.error("Detail: %s", error_detail.get("detail", "No details provided"))
        except ValueError:
            logger.error("Detail: %s", e.response.text)
    except requests.exceptions.ConnectionError:
        logger.exception("Connection Error: Unable to connect to %s", BASE_URL)
    except requests.exceptions.Timeout:
        logger.exception("Timeout Error: Request took too long")
    except requests.exceptions.RequestException as e:
        logger.exception("Request Error: %s", str(e))
    except Exception as e:
        logger.exception("Unexpected Error: %s: %s", type(e).__name__, str(e))


if __name__ == "__main__":
    main()
