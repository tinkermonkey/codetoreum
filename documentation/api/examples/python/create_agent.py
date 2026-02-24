"""
Example: Create a new agent in Codetoreum

This example demonstrates how to create a new agent with capabilities
and MCP server configuration.
"""
import logging
from typing import TYPE_CHECKING

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
    mcp_servers: list[dict] | None = None,
    configuration: dict | None = None,
) -> dict:
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
        "Content-Type": "application/json"
    }

    payload = {
        "name": name,
        "description": description,
        "agent_type": agent_type,
        "capabilities": capabilities or [],
        "configuration": configuration or {
            "model": "claude-sonnet-4",
            "temperature": 0.7,
            "max_tokens": 4000
        },
        "active": True
    }

    response = requests.post(url, json=payload, headers=headers, timeout=30)
    response.raise_for_status()

    agent_data = response.json()
    logger.info(f"✓ Created agent: {agent_data['id']}")

    # Add MCP servers if provided
    if mcp_servers:
        for mcp_server in mcp_servers:
            add_mcp_server(agent_data['id'], mcp_server)

    return agent_data


def add_mcp_server(agent_id: str, mcp_config: dict) -> dict:
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
        "Content-Type": "application/json"
    }

    response = requests.post(
        url, json=mcp_config, headers=headers, timeout=30
    )
    response.raise_for_status()

    result = response.json()
    logger.info(f"✓ Added MCP server: {mcp_config['name']}")
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

        logger.info(f"Agent ID: {backend_agent['id']}")
        logger.info(f"Name: {backend_agent['name']}")
        logger.info(
            f"Capabilities: {', '.join(backend_agent['capabilities'])}"
        )

        logger.info("✓ Created agent successfully")

    except requests.exceptions.HTTPError as e:
        logger.error(f"API Error: {e.response.status_code}")
        try:
            error_detail = e.response.json()
            logger.error(
                f"Detail: {error_detail.get('detail', 'No details provided')}"
            )
        except ValueError:
            logger.error(f"Detail: {e.response.text}")
    except requests.exceptions.ConnectionError as e:
        logger.error(f"Connection Error: Unable to connect to {BASE_URL}")
        logger.error("Ensure the API server is running")
    except requests.exceptions.Timeout as e:
        logger.error("Timeout Error: Request took too long")
    except requests.exceptions.RequestException as e:
        logger.error(f"Request Error: {str(e)}")
    except Exception as e:
        logger.error(
            f"Unexpected Error: {type(e).__name__}: {str(e)}"
        )


if __name__ == "__main__":
    main()
