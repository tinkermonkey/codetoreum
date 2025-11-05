/**
 * Example: Create a new agent in Codetoreum
 *
 * This example demonstrates how to create a new agent with capabilities
 * and MCP server configuration using TypeScript.
 */

// Configuration
const BASE_URL = "http://localhost:8000";
const API_TOKEN = "your_token_here"; // Get from server startup logs

// Type definitions
interface AgentConfiguration {
  model?: string;
  temperature?: number;
  max_tokens?: number;
  timeout_minutes?: number;
  [key: string]: any;
}

interface MCPServer {
  name: string;
  command: string;
  args: string[];
  env: Record<string, string>;
}

interface Agent {
  id: string;
  name: string;
  description: string;
  agent_type: string;
  capabilities: string[];
  configuration: AgentConfiguration;
  active: boolean;
  created_at: string;
  updated_at?: string;
}

interface CreateAgentRequest {
  name: string;
  description: string;
  agent_type: string;
  capabilities?: string[];
  configuration?: AgentConfiguration;
  active?: boolean;
}

/**
 * Create a new agent
 */
async function createAgent(
  request: CreateAgentRequest,
  mcpServers?: MCPServer[]
): Promise<Agent> {
  const url = `${BASE_URL}/api/v2/agents/`;

  const payload: CreateAgentRequest = {
    name: request.name,
    description: request.description,
    agent_type: request.agent_type,
    capabilities: request.capabilities || [],
    configuration: request.configuration || {
      model: "claude-sonnet-4",
      temperature: 0.7,
      max_tokens: 4000,
    },
    active: request.active !== undefined ? request.active : true,
  };

  const response = await fetch(url, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${API_TOKEN}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify(payload),
  });

  if (!response.ok) {
    const error = await response.json();
    throw new Error(`Failed to create agent: ${error.detail}`);
  }

  const agent: Agent = await response.json();
  console.log(`✓ Created agent: ${agent.id}`);

  // Add MCP servers if provided
  if (mcpServers && mcpServers.length > 0) {
    for (const mcpServer of mcpServers) {
      await addMCPServer(agent.id, mcpServer);
    }
  }

  return agent;
}

/**
 * Add MCP server to an agent
 */
async function addMCPServer(
  agentId: string,
  mcpConfig: MCPServer
): Promise<MCPServer> {
  const url = `${BASE_URL}/api/v2/agents/${agentId}/mcp-servers`;

  const response = await fetch(url, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${API_TOKEN}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify(mcpConfig),
  });

  if (!response.ok) {
    const error = await response.json();
    throw new Error(`Failed to add MCP server: ${error.detail}`);
  }

  console.log(`✓ Added MCP server: ${mcpConfig.name}`);
  return await response.json();
}

/**
 * Get agent details
 */
async function getAgent(agentId: string): Promise<Agent> {
  const url = `${BASE_URL}/api/v2/agents/${agentId}`;

  const response = await fetch(url, {
    method: "GET",
    headers: {
      Authorization: `Bearer ${API_TOKEN}`,
    },
  });

  if (!response.ok) {
    const error = await response.json();
    throw new Error(`Failed to get agent: ${error.detail}`);
  }

  return await response.json();
}

/**
 * List all agents with optional filtering
 */
async function listAgents(filters?: {
  agent_type?: string;
  active?: boolean;
  capability?: string;
  offset?: number;
  limit?: number;
}): Promise<{ items: Agent[]; total: number; offset: number; limit: number }> {
  const params = new URLSearchParams();

  if (filters) {
    if (filters.agent_type) params.append("agent_type", filters.agent_type);
    if (filters.active !== undefined)
      params.append("active", filters.active.toString());
    if (filters.capability) params.append("capability", filters.capability);
    if (filters.offset !== undefined)
      params.append("offset", filters.offset.toString());
    if (filters.limit !== undefined)
      params.append("limit", filters.limit.toString());
  }

  const url = `${BASE_URL}/api/v2/agents/?${params.toString()}`;

  const response = await fetch(url, {
    method: "GET",
    headers: {
      Authorization: `Bearer ${API_TOKEN}`,
    },
  });

  if (!response.ok) {
    const error = await response.json();
    throw new Error(`Failed to list agents: ${error.detail}`);
  }

  return await response.json();
}

// Example usage
async function main() {
  try {
    console.log("=== Creating Agents ===\n");

    // Example 1: Create a backend development agent
    const backendAgent = await createAgent(
      {
        name: "backend-specialist",
        description: "Python backend development specialist",
        agent_type: "claude_code",
        capabilities: [
          "python",
          "fastapi",
          "sqlalchemy",
          "postgresql",
          "docker",
        ],
        configuration: {
          model: "claude-sonnet-4",
          temperature: 0.7,
          max_tokens: 8000,
          timeout_minutes: 120,
        },
      },
      [
        {
          name: "filesystem",
          command: "npx",
          args: [
            "-y",
            "@modelcontextprotocol/server-filesystem",
            "/workspace",
          ],
          env: {},
        },
        {
          name: "git",
          command: "npx",
          args: ["-y", "@modelcontextprotocol/server-git"],
          env: {},
        },
      ]
    );

    console.log(`\nAgent ID: ${backendAgent.id}`);
    console.log(`Name: ${backendAgent.name}`);
    console.log(`Capabilities: ${backendAgent.capabilities.join(", ")}`);

    // Example 2: Create a frontend development agent
    const frontendAgent = await createAgent({
      name: "frontend-specialist",
      description: "React and TypeScript frontend specialist",
      agent_type: "claude_code",
      capabilities: ["typescript", "react", "tailwind", "vite"],
      configuration: {
        model: "claude-sonnet-4",
        temperature: 0.8,
        max_tokens: 6000,
      },
    });

    console.log(`\n✓ Created 2 agents successfully`);

    // Example 3: List all active agents
    console.log("\n=== Listing Agents ===\n");

    const agents = await listAgents({ active: true, limit: 10 });
    console.log(`Found ${agents.total} active agent(s)`);

    for (const agent of agents.items) {
      console.log(`  - ${agent.name} (${agent.agent_type})`);
      console.log(`    Capabilities: ${agent.capabilities.join(", ")}`);
    }
  } catch (error) {
    console.error("Error:", error);
    process.exit(1);
  }
}

// Run if executed directly
if (require.main === module) {
  main();
}

export { createAgent, addMCPServer, getAgent, listAgents };
export type { Agent, CreateAgentRequest, MCPServer, AgentConfiguration };
