import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Plus, Trash2, Edit2, Save, X, AlertCircle, Settings } from 'lucide-react'
import { Button } from '../components/ui/button'
import { Input } from '../components/ui/input'
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '../components/ui/card'
import { agentConfigApi } from '../api/client'
import type { AgentConfig } from '../types'

export default function AgentConfigPage() {
  const [selectedAgent, setSelectedAgent] = useState<string | null>(null)
  const queryClient = useQueryClient()

  const { data: agents, isLoading, error } = useQuery({
    queryKey: ['agents'],
    queryFn: () => agentConfigApi.getAll(),
  })

  const selectedAgentData = agents?.find((a) => a.agent_name === selectedAgent)

  if (isLoading) {
    return <div className="flex justify-center p-8">Loading agents...</div>
  }

  if (error) {
    return <div className="text-destructive p-8">Error loading agents: {error.message}</div>
  }

  return (
    <div className="space-y-6">
      <div className="flex justify-between items-center">
        <div>
          <h2 className="text-3xl font-bold">Agent Configuration</h2>
          <p className="text-muted-foreground mt-1">
            Edit agent prompts, capabilities, and constraints
          </p>
        </div>
        <CreateAgentButton queryClient={queryClient} />
      </div>

      <div className="grid grid-cols-3 gap-6">
        {/* Agent List */}
        <Card className="col-span-1">
          <CardHeader>
            <CardTitle>Agents</CardTitle>
            <CardDescription>Select an agent to configure</CardDescription>
          </CardHeader>
          <CardContent>
            <div className="space-y-2">
              {agents?.map((agent) => (
                <div
                  key={agent.agent_name}
                  className={`p-3 border rounded-md cursor-pointer transition-colors ${
                    selectedAgent === agent.agent_name
                      ? 'bg-primary/10 border-primary'
                      : 'hover:bg-muted'
                  }`}
                  onClick={() => setSelectedAgent(agent.agent_name)}
                >
                  <div className="font-medium">{agent.agent_name}</div>
                  {agent.metadata.description && (
                    <p className="text-sm text-muted-foreground mt-1">
                      {agent.metadata.description}
                    </p>
                  )}
                  <div className="flex items-center justify-between mt-2">
                    <span className="text-xs text-muted-foreground">{agent.model}</span>
                    {agent.makes_code_changes && (
                      <span className="text-xs bg-primary/20 text-primary px-2 py-0.5 rounded">
                        Maker
                      </span>
                    )}
                  </div>
                </div>
              ))}
              {agents?.length === 0 && (
                <p className="text-muted-foreground text-sm text-center py-4">
                  No agents configured
                </p>
              )}
            </div>
          </CardContent>
        </Card>

        {/* Agent Editor */}
        <div className="col-span-2 space-y-6">
          {selectedAgentData ? (
            <>
              <AgentDetailsCard agent={selectedAgentData} queryClient={queryClient} />
              <CapabilitiesCard agent={selectedAgentData} queryClient={queryClient} />
              <MCPServersCard agent={selectedAgentData} queryClient={queryClient} />
              <ConstraintsCard agent={selectedAgentData} queryClient={queryClient} />
            </>
          ) : (
            <Card>
              <CardContent className="flex flex-col items-center justify-center py-12">
                <AlertCircle className="h-12 w-12 text-muted-foreground mb-4" />
                <p className="text-muted-foreground">Select an agent to configure</p>
              </CardContent>
            </Card>
          )}
        </div>
      </div>
    </div>
  )
}

// Create Agent Button
function CreateAgentButton({ queryClient }: { queryClient: any }) {
  const [isCreating, setIsCreating] = useState(false)
  const [name, setName] = useState('')
  const [description, setDescription] = useState('')
  const [model, setModel] = useState('claude-sonnet-4-5-20250929')

  const createMutation = useMutation({
    mutationFn: (data: AgentConfig) => agentConfigApi.create(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['agents'] })
      setIsCreating(false)
      setName('')
      setDescription('')
      setModel('claude-sonnet-4-5-20250929')
    },
  })

  if (!isCreating) {
    return (
      <Button onClick={() => setIsCreating(true)}>
        <Plus className="h-4 w-4 mr-2" />
        New Agent
      </Button>
    )
  }

  return (
    <div className="flex items-center space-x-2">
      <Input
        placeholder="Agent name"
        value={name}
        onChange={(e) => setName(e.target.value)}
        className="w-48"
      />
      <Input
        placeholder="Description (optional)"
        value={description}
        onChange={(e) => setDescription(e.target.value)}
        className="w-64"
      />
      <Button
        onClick={() =>
          createMutation.mutate({
            project_id: 'codetoreum',
            agent_name: name,
            model,
            timeout_seconds: 300,
            max_retries: 3,
            requires_docker: false,
            requires_dev_container: false,
            makes_code_changes: false,
            filesystem_write_allowed: true,
            mcp_servers: [],
            capabilities: {},
            version: 1,
            created_at: new Date().toISOString(),
            updated_at: new Date().toISOString(),
            metadata: { description },
          })
        }
        disabled={!name || createMutation.isPending}
      >
        <Save className="h-4 w-4 mr-2" />
        Create
      </Button>
      <Button variant="ghost" onClick={() => setIsCreating(false)}>
        <X className="h-4 w-4" />
      </Button>
    </div>
  )
}

// Agent Details Card
function AgentDetailsCard({
  agent,
  queryClient,
}: {
  agent: AgentConfig
  queryClient: any
}) {
  const [isEditing, setIsEditing] = useState(false)
  const [model, setModel] = useState(agent.model)
  const [timeout, setTimeout] = useState(agent.timeout_seconds.toString())
  const [description, setDescription] = useState(agent.metadata.description || '')

  const updateMutation = useMutation({
    mutationFn: (updates: any) => agentConfigApi.update(agent.agent_name, { updates, user_id: 'admin' }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['agents'] })
      setIsEditing(false)
    },
  })

  const deleteMutation = useMutation({
    mutationFn: () => agentConfigApi.delete(agent.agent_name),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['agents'] })
    },
  })

  const handleSave = () => {
    updateMutation.mutate({
      model,
      timeout_seconds: parseInt(timeout),
      metadata: { ...agent.metadata, description },
    })
  }

  const models = [
    'claude-sonnet-4-5-20250929',
    'claude-3-5-sonnet-20241022',
    'claude-3-opus-20240229',
    'gpt-4-turbo',
    'gpt-4',
  ]

  return (
    <Card>
      <CardHeader>
        <div className="flex items-center justify-between">
          <div className="flex-1">
            <CardTitle className="flex items-center space-x-2">
              <Settings className="h-5 w-5" />
              <span>{agent.agent_name}</span>
            </CardTitle>
            {isEditing ? (
              <Input
                placeholder="Description"
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                className="mt-2"
              />
            ) : (
              <CardDescription>{agent.metadata.description}</CardDescription>
            )}
          </div>
          <div className="flex items-center space-x-2">
            {isEditing ? (
              <>
                <Button size="sm" onClick={handleSave} disabled={updateMutation.isPending}>
                  <Save className="h-4 w-4 mr-2" />
                  Save
                </Button>
                <Button size="sm" variant="ghost" onClick={() => setIsEditing(false)}>
                  <X className="h-4 w-4" />
                </Button>
              </>
            ) : (
              <>
                <Button size="sm" variant="outline" onClick={() => setIsEditing(true)}>
                  <Edit2 className="h-4 w-4 mr-2" />
                  Edit
                </Button>
                <Button
                  size="sm"
                  variant="destructive"
                  onClick={() => {
                    if (confirm('Are you sure you want to delete this agent?')) {
                      deleteMutation.mutate()
                    }
                  }}
                  disabled={deleteMutation.isPending}
                >
                  <Trash2 className="h-4 w-4" />
                </Button>
              </>
            )}
          </div>
        </div>
      </CardHeader>
      <CardContent>
        <div className="grid grid-cols-2 gap-4">
          <div>
            <label className="text-sm font-medium text-muted-foreground">Model</label>
            {isEditing ? (
              <select
                className="mt-1 flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
                value={model}
                onChange={(e) => setModel(e.target.value)}
              >
                {models.map((m) => (
                  <option key={m} value={m}>
                    {m}
                  </option>
                ))}
              </select>
            ) : (
              <p className="mt-1 font-medium">{agent.model}</p>
            )}
          </div>
          <div>
            <label className="text-sm font-medium text-muted-foreground">Timeout (seconds)</label>
            {isEditing ? (
              <Input
                type="number"
                value={timeout}
                onChange={(e) => setTimeout(e.target.value)}
                className="mt-1"
              />
            ) : (
              <p className="mt-1 font-medium">{agent.timeout_seconds}s</p>
            )}
          </div>
          <div>
            <label className="text-sm font-medium text-muted-foreground">Version</label>
            <p className="mt-1 font-medium">{agent.version}</p>
          </div>
          <div>
            <label className="text-sm font-medium text-muted-foreground">Updated</label>
            <p className="mt-1 font-medium">
              {new Date(agent.updated_at).toLocaleDateString()}
            </p>
          </div>
        </div>
      </CardContent>
    </Card>
  )
}

// Capabilities Card
function CapabilitiesCard({
  agent,
  queryClient,
}: {
  agent: AgentConfig
  queryClient: any
}) {
  const [isAdding, setIsAdding] = useState(false)
  const [newCapability, setNewCapability] = useState('')

  const updateMutation = useMutation({
    mutationFn: (updates: any) => agentConfigApi.update(agent.agent_name, { updates, user_id: 'admin' }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['agents'] })
      setIsAdding(false)
      setNewCapability('')
    },
  })

  const capabilitiesList: string[] = Array.isArray(agent.capabilities)
    ? agent.capabilities
    : Array.isArray(agent.capabilities?.capabilities)
      ? agent.capabilities.capabilities
      : []

  const addCapability = () => {
    if (!newCapability) return
    updateMutation.mutate({
      capabilities: [...capabilitiesList, newCapability],
    })
  }

  const removeCapability = (capability: string) => {
    updateMutation.mutate({
      capabilities: capabilitiesList.filter((c) => c !== capability),
    })
  }

  const predefinedCapabilities = [
    'code-generation',
    'code-review',
    'testing',
    'debugging',
    'documentation',
    'refactoring',
    'security-analysis',
    'performance-optimization',
  ]

  return (
    <Card>
      <CardHeader>
        <div className="flex items-center justify-between">
          <div>
            <CardTitle>Capabilities</CardTitle>
            <CardDescription>Configure what this agent can do</CardDescription>
          </div>
          <Button size="sm" onClick={() => setIsAdding(true)}>
            <Plus className="h-4 w-4 mr-2" />
            Add
          </Button>
        </div>
      </CardHeader>
      <CardContent>
        <div className="space-y-3">
          {/* Existing Capabilities */}
          <div className="flex flex-wrap gap-2">
            {capabilitiesList.map((capability) => (
              <div
                key={capability}
                className="flex items-center space-x-2 bg-primary/10 border border-primary px-3 py-1 rounded-md"
              >
                <span className="text-sm">{capability}</span>
                <button
                  onClick={() => removeCapability(capability)}
                  className="text-destructive hover:text-destructive/80"
                >
                  <X className="h-3 w-3" />
                </button>
              </div>
            ))}
            {capabilitiesList.length === 0 && (
              <p className="text-muted-foreground text-sm">No capabilities configured</p>
            )}
          </div>

          {/* Add New Capability */}
          {isAdding && (
            <div className="border-t pt-3 space-y-3">
              <h4 className="text-sm font-medium">Add Capability</h4>
              <div className="flex flex-wrap gap-2">
                {predefinedCapabilities
                  .filter((cap) => !capabilitiesList.includes(cap))
                  .map((cap) => (
                    <button
                      key={cap}
                      onClick={() => {
                        updateMutation.mutate({
                          capabilities: [...capabilitiesList, cap],
                        })
                      }}
                      className="text-sm bg-muted hover:bg-muted/80 px-3 py-1 rounded-md"
                    >
                      {cap}
                    </button>
                  ))}
              </div>
              <div className="flex items-center space-x-2">
                <Input
                  placeholder="Custom capability"
                  value={newCapability}
                  onChange={(e) => setNewCapability(e.target.value)}
                />
                <Button onClick={addCapability} disabled={updateMutation.isPending}>
                  Add
                </Button>
                <Button variant="ghost" onClick={() => setIsAdding(false)}>
                  Cancel
                </Button>
              </div>
            </div>
          )}
        </div>
      </CardContent>
    </Card>
  )
}

// MCP Servers Card
function MCPServersCard({
  agent,
  queryClient,
}: {
  agent: AgentConfig
  queryClient: any
}) {
  const [isAdding, setIsAdding] = useState(false)
  const [newServer, setNewServer] = useState('')

  const updateMutation = useMutation({
    mutationFn: (updates: any) => agentConfigApi.update(agent.agent_name, { updates, user_id: 'admin' }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['agents'] })
      setIsAdding(false)
      setNewServer('')
    },
  })

  const addServer = () => {
    if (!newServer) return
    updateMutation.mutate({
      mcp_servers: [...agent.mcp_servers, newServer],
    })
  }

  const removeServer = (server: string) => {
    updateMutation.mutate({
      mcp_servers: agent.mcp_servers.filter((s) => s !== server),
    })
  }

  const predefinedServers = [
    'filesystem',
    'github',
    'gitlab',
    'jira',
    'slack',
    'docker',
    'kubernetes',
    'aws',
  ]

  return (
    <Card>
      <CardHeader>
        <div className="flex items-center justify-between">
          <div>
            <CardTitle>MCP Servers</CardTitle>
            <CardDescription>Configure Model Context Protocol servers</CardDescription>
          </div>
          <Button size="sm" onClick={() => setIsAdding(true)}>
            <Plus className="h-4 w-4 mr-2" />
            Add
          </Button>
        </div>
      </CardHeader>
      <CardContent>
        <div className="space-y-3">
          {/* Existing Servers */}
          <div className="space-y-2">
            {agent.mcp_servers.map((server) => (
              <div
                key={server}
                className="flex items-center justify-between p-2 border rounded-md"
              >
                <span className="font-medium">{server}</span>
                <Button
                  size="sm"
                  variant="ghost"
                  onClick={() => removeServer(server)}
                  disabled={updateMutation.isPending}
                >
                  <Trash2 className="h-4 w-4" />
                </Button>
              </div>
            ))}
            {agent.mcp_servers.length === 0 && (
              <p className="text-muted-foreground text-sm">No MCP servers configured</p>
            )}
          </div>

          {/* Add New Server */}
          {isAdding && (
            <div className="border-t pt-3 space-y-3">
              <h4 className="text-sm font-medium">Add MCP Server</h4>
              <div className="flex flex-wrap gap-2">
                {predefinedServers
                  .filter((srv) => !agent.mcp_servers.includes(srv))
                  .map((srv) => (
                    <button
                      key={srv}
                      onClick={() => {
                        updateMutation.mutate({
                          mcp_servers: [...agent.mcp_servers, srv],
                        })
                      }}
                      className="text-sm bg-muted hover:bg-muted/80 px-3 py-1 rounded-md"
                    >
                      {srv}
                    </button>
                  ))}
              </div>
              <div className="flex items-center space-x-2">
                <Input
                  placeholder="Custom server name"
                  value={newServer}
                  onChange={(e) => setNewServer(e.target.value)}
                />
                <Button onClick={addServer} disabled={updateMutation.isPending}>
                  Add
                </Button>
                <Button variant="ghost" onClick={() => setIsAdding(false)}>
                  Cancel
                </Button>
              </div>
            </div>
          )}
        </div>
      </CardContent>
    </Card>
  )
}

// Constraints Card
function ConstraintsCard({
  agent,
  queryClient,
}: {
  agent: AgentConfig
  queryClient: any
}) {
  const constraints = (agent as any).constraints ?? {}
  const [isEditing, setIsEditing] = useState(false)
  const [requiresDocker, setRequiresDocker] = useState(agent.requires_docker)
  const [makesCodeChanges, setMakesCodeChanges] = useState(agent.makes_code_changes)
  const [maxTokens, setMaxTokens] = useState(
    constraints.max_tokens?.toString() || '100000'
  )
  const [rateLimit, setRateLimit] = useState(
    constraints.rate_limit?.toString() || '10'
  )

  const updateMutation = useMutation({
    mutationFn: (updates: any) => agentConfigApi.update(agent.agent_name, { updates, user_id: 'admin' }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['agents'] })
      setIsEditing(false)
    },
  })

  const handleSave = () => {
    updateMutation.mutate({
      requires_docker: requiresDocker,
      makes_code_changes: makesCodeChanges,
      constraints: {
        ...constraints,
        max_tokens: maxTokens ? parseInt(maxTokens) : undefined,
        rate_limit: rateLimit ? parseInt(rateLimit) : undefined,
      },
    })
  }

  return (
    <Card>
      <CardHeader>
        <div className="flex items-center justify-between">
          <div>
            <CardTitle>Constraints & Permissions</CardTitle>
            <CardDescription>Configure security and execution constraints</CardDescription>
          </div>
          {isEditing ? (
            <div className="flex items-center space-x-2">
              <Button size="sm" onClick={handleSave} disabled={updateMutation.isPending}>
                <Save className="h-4 w-4 mr-2" />
                Save
              </Button>
              <Button size="sm" variant="ghost" onClick={() => setIsEditing(false)}>
                <X className="h-4 w-4" />
              </Button>
            </div>
          ) : (
            <Button size="sm" variant="outline" onClick={() => setIsEditing(true)}>
              <Edit2 className="h-4 w-4 mr-2" />
              Edit
            </Button>
          )}
        </div>
      </CardHeader>
      <CardContent>
        <div className="space-y-4">
          <div className="grid grid-cols-2 gap-4">
            <label className="flex items-center space-x-2">
              <input
                type="checkbox"
                checked={isEditing ? requiresDocker : agent.requires_docker}
                onChange={(e) => setRequiresDocker(e.target.checked)}
                disabled={!isEditing}
                className="h-4 w-4"
              />
              <span className="text-sm">Requires Docker</span>
            </label>
            <label className="flex items-center space-x-2">
              <input
                type="checkbox"
                checked={isEditing ? makesCodeChanges : agent.makes_code_changes}
                onChange={(e) => setMakesCodeChanges(e.target.checked)}
                disabled={!isEditing}
                className="h-4 w-4"
              />
              <span className="text-sm">Makes Code Changes</span>
            </label>
          </div>
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="text-sm font-medium text-muted-foreground">
                Max Tokens
              </label>
              {isEditing ? (
                <Input
                  type="number"
                  value={maxTokens}
                  onChange={(e) => setMaxTokens(e.target.value)}
                  className="mt-1"
                />
              ) : (
                <p className="mt-1 font-medium">{constraints.max_tokens || 'N/A'}</p>
              )}
            </div>
            <div>
              <label className="text-sm font-medium text-muted-foreground">
                Rate Limit (req/min)
              </label>
              {isEditing ? (
                <Input
                  type="number"
                  value={rateLimit}
                  onChange={(e) => setRateLimit(e.target.value)}
                  className="mt-1"
                />
              ) : (
                <p className="mt-1 font-medium">{constraints.rate_limit || 'N/A'}</p>
              )}
            </div>
          </div>
        </div>
      </CardContent>
    </Card>
  )
}
