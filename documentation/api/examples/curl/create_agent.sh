#!/bin/bash
#
# Example: Create a new agent in Codetoreum
#
# This example demonstrates how to create a new agent with capabilities
# and MCP server configuration using cURL.

# Configuration
BASE_URL="http://localhost:8000"
API_TOKEN="your_token_here"  # Get from server startup logs

# Colors for output
GREEN='\033[0;32m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}=== Creating Backend Development Agent ===${NC}\n"

# Create agent
RESPONSE=$(curl -s -X POST "${BASE_URL}/api/v2/agents/" \
  -H "Authorization: Bearer ${API_TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "backend-specialist",
    "description": "Python backend development specialist",
    "agent_type": "claude_code",
    "capabilities": [
      "python",
      "fastapi",
      "sqlalchemy",
      "postgresql",
      "docker"
    ],
    "configuration": {
      "model": "claude-sonnet-4",
      "temperature": 0.7,
      "max_tokens": 8000,
      "timeout_minutes": 120
    },
    "active": true
  }')

# Check if request was successful
if [ $? -eq 0 ]; then
  AGENT_ID=$(echo "$RESPONSE" | jq -r '.id')
  AGENT_NAME=$(echo "$RESPONSE" | jq -r '.name')

  echo -e "${GREEN}✓ Created agent: ${AGENT_ID}${NC}"
  echo "Name: ${AGENT_NAME}"
  echo ""

  # Pretty print the response
  echo "Full response:"
  echo "$RESPONSE" | jq '.'
  echo ""

  # Add MCP servers to the agent
  echo -e "${BLUE}=== Adding MCP Servers ===${NC}\n"

  # Add filesystem MCP server
  echo "Adding filesystem MCP server..."
  curl -s -X POST "${BASE_URL}/api/v2/agents/${AGENT_ID}/mcp-servers" \
    -H "Authorization: Bearer ${API_TOKEN}" \
    -H "Content-Type: application/json" \
    -d '{
      "name": "filesystem",
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-filesystem", "/workspace"],
      "env": {}
    }' | jq '.'

  echo -e "${GREEN}✓ Added filesystem MCP server${NC}\n"

  # Add git MCP server
  echo "Adding git MCP server..."
  curl -s -X POST "${BASE_URL}/api/v2/agents/${AGENT_ID}/mcp-servers" \
    -H "Authorization: Bearer ${API_TOKEN}" \
    -H "Content-Type: application/json" \
    -d '{
      "name": "git",
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-git"],
      "env": {}
    }' | jq '.'

  echo -e "${GREEN}✓ Added git MCP server${NC}\n"

else
  echo "Error creating agent"
  echo "$RESPONSE"
  exit 1
fi

# Create another agent
echo -e "${BLUE}=== Creating Frontend Development Agent ===${NC}\n"

curl -s -X POST "${BASE_URL}/api/v2/agents/" \
  -H "Authorization: Bearer ${API_TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "frontend-specialist",
    "description": "React and TypeScript frontend specialist",
    "agent_type": "claude_code",
    "capabilities": [
      "typescript",
      "react",
      "tailwind",
      "vite"
    ],
    "configuration": {
      "model": "claude-sonnet-4",
      "temperature": 0.8,
      "max_tokens": 6000
    },
    "active": true
  }' | jq '.'

echo -e "\n${GREEN}✓ Created 2 agents successfully${NC}\n"

# List all agents
echo -e "${BLUE}=== Listing All Active Agents ===${NC}\n"

curl -s -X GET "${BASE_URL}/api/v2/agents/?active=true&limit=10" \
  -H "Authorization: Bearer ${API_TOKEN}" | jq '.'

echo -e "\n${GREEN}✓ Done${NC}"
