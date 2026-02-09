import React, { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Plus, Trash2, Eye, EyeOff, Save } from 'lucide-react'
import { Button } from '../components/ui/button'
import { Input } from '../components/ui/input'
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '../components/ui/card'
import { projectConfigApi } from '../api/client'
import type { ProjectConfig } from '../types'

export default function ProjectConfigPage() {
  const [selectedProjectIndex, setSelectedProjectIndex] = useState(0)
  const queryClient = useQueryClient()

  // Fetch project list (each item already contains full config)
  const { data: projects = [], isLoading, error } = useQuery({
    queryKey: ['projectList'],
    queryFn: () => projectConfigApi.getAll(),
  })

  const config = projects[selectedProjectIndex] as ProjectConfig | undefined

  if (isLoading) {
    return <div className="flex justify-center p-8">Loading configuration...</div>
  }

  if (projects.length === 0) {
    return (
      <div className="text-muted-foreground p-8 text-center">
        No projects configured. Create a project to get started.
      </div>
    )
  }

  if (error) {
    return (
      <div className="text-destructive p-8">
        Error loading configuration: {error.message}
      </div>
    )
  }

  return (
    <div className="space-y-6">
      <div className="flex justify-between items-center">
        <div>
          <h2 className="text-3xl font-bold">Project Configuration</h2>
          <p className="text-muted-foreground mt-1">
            Manage environment variables, commands, and sub-agents
          </p>
        </div>
        <div className="flex items-center space-x-2">
          <span className="text-sm text-muted-foreground">
            Version: {config?.version || 'N/A'}
          </span>
        </div>
      </div>

      {config && (
        <>
          <EnvironmentVariablesSection config={config} queryClient={queryClient} />
          <MountedCommandsSection config={config} queryClient={queryClient} />
          <MountedSubAgentsSection config={config} queryClient={queryClient} />
          <RepositorySettingsSection config={config} queryClient={queryClient} />
        </>
      )}
    </div>
  )
}

// Environment Variables Section
function EnvironmentVariablesSection({
  config,
  queryClient,
}: {
  config: ProjectConfig
  queryClient: any
}) {
  const [newVarName, setNewVarName] = useState('')
  const [newVarValue, setNewVarValue] = useState('')
  const [newVarDescription, setNewVarDescription] = useState('')
  const [isSecret, setIsSecret] = useState(false)
  const [showSecrets, setShowSecrets] = useState<Record<string, boolean>>({})

  const addVarMutation = useMutation({
    mutationFn: (data: any) => projectConfigApi.addEnvironmentVariable(config.name, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['projectConfig', config.name] })
      setNewVarName('')
      setNewVarValue('')
      setNewVarDescription('')
      setIsSecret(false)
    },
  })

  const removeVarMutation = useMutation({
    mutationFn: (varName: string) =>
      projectConfigApi.removeEnvironmentVariable(config.name, varName),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['projectConfig', config.name] })
    },
  })

  const handleAddVariable = () => {
    if (!newVarName || !newVarValue) return

    addVarMutation.mutate({
      variable_name: newVarName,
      variable_value: newVarValue,
      user_id: 'admin',
      is_secret: isSecret,
      description: newVarDescription || undefined,
    })
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>Environment Variables</CardTitle>
        <CardDescription>
          Manage project-level environment variables available to all agents
        </CardDescription>
      </CardHeader>
      <CardContent>
        <div className="space-y-4">
          {/* Existing Variables */}
          <div className="space-y-2">
            {Object.entries(config.environment_variables || {}).map(([name, variable]) => (
              <div
                key={name}
                className="flex items-center justify-between p-3 border rounded-md"
              >
                <div className="flex-1">
                  <div className="font-medium flex items-center space-x-2">
                    <span>{name}</span>
                    {variable.is_secret && (
                      <span className="text-xs bg-destructive/10 text-destructive px-2 py-0.5 rounded">
                        Secret
                      </span>
                    )}
                  </div>
                  {variable.description && (
                    <p className="text-sm text-muted-foreground mt-1">
                      {variable.description}
                    </p>
                  )}
                  <div className="text-sm text-muted-foreground mt-1 flex items-center space-x-2">
                    <span>
                      Value:{' '}
                      {variable.is_secret && !showSecrets[name]
                        ? '••••••••'
                        : variable.value}
                    </span>
                    {variable.is_secret && (
                      <button
                        onClick={() =>
                          setShowSecrets((prev) => ({ ...prev, [name]: !prev[name] }))
                        }
                        className="text-primary hover:text-primary/80"
                      >
                        {showSecrets[name] ? (
                          <EyeOff className="h-4 w-4" />
                        ) : (
                          <Eye className="h-4 w-4" />
                        )}
                      </button>
                    )}
                  </div>
                </div>
                <Button
                  variant="destructive"
                  size="sm"
                  onClick={() => removeVarMutation.mutate(name)}
                  disabled={removeVarMutation.isPending}
                >
                  <Trash2 className="h-4 w-4" />
                </Button>
              </div>
            ))}
          </div>

          {/* Add New Variable */}
          <div className="border-t pt-4 space-y-3">
            <h4 className="font-medium">Add New Variable</h4>
            <div className="grid grid-cols-2 gap-3">
              <Input
                placeholder="Variable name (e.g., API_KEY)"
                value={newVarName}
                onChange={(e) => setNewVarName(e.target.value.toUpperCase())}
              />
              <Input
                placeholder="Variable value"
                type={isSecret ? 'password' : 'text'}
                value={newVarValue}
                onChange={(e) => setNewVarValue(e.target.value)}
              />
              <Input
                placeholder="Description (optional)"
                value={newVarDescription}
                onChange={(e) => setNewVarDescription(e.target.value)}
                className="col-span-2"
              />
            </div>
            <div className="flex items-center space-x-3">
              <label className="flex items-center space-x-2">
                <input
                  type="checkbox"
                  checked={isSecret}
                  onChange={(e) => setIsSecret(e.target.checked)}
                  className="h-4 w-4"
                />
                <span className="text-sm">Secret (will be encrypted)</span>
              </label>
              <Button onClick={handleAddVariable} disabled={addVarMutation.isPending}>
                <Plus className="h-4 w-4 mr-2" />
                Add Variable
              </Button>
            </div>
          </div>
        </div>
      </CardContent>
    </Card>
  )
}

// Mounted Commands Section
function MountedCommandsSection({
  config,
  queryClient,
}: {
  config: ProjectConfig
  queryClient: any
}) {
  const [newCommandName, setNewCommandName] = useState('')
  const [newCommandPath, setNewCommandPath] = useState('')
  const [newCommandDescription, setNewCommandDescription] = useState('')

  const mountCommandMutation = useMutation({
    mutationFn: (data: any) => projectConfigApi.addMountCommand(config.name, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['projectConfig', config.name] })
      setNewCommandName('')
      setNewCommandPath('')
      setNewCommandDescription('')
    },
  })

  const unmountCommandMutation = useMutation({
    mutationFn: (commandName: string) =>
      projectConfigApi.removeMountCommand(config.name, commandName),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['projectConfig', config.name] })
    },
  })

  return (
    <Card>
      <CardHeader>
        <CardTitle>Mounted Commands</CardTitle>
        <CardDescription>
          Mount custom commands available to agents in this project
        </CardDescription>
      </CardHeader>
      <CardContent>
        <div className="space-y-4">
          {/* Existing Commands */}
          <div className="space-y-2">
            {Object.entries(config.mounted_commands || {}).map(([name, command]) => (
              <div
                key={name}
                className="flex items-center justify-between p-3 border rounded-md"
              >
                <div className="flex-1">
                  <div className="font-medium">{name}</div>
                  <p className="text-sm text-muted-foreground">Path: {command.path}</p>
                  {command.description && (
                    <p className="text-sm text-muted-foreground">{command.description}</p>
                  )}
                </div>
                <Button
                  variant="destructive"
                  size="sm"
                  onClick={() => unmountCommandMutation.mutate(name)}
                  disabled={unmountCommandMutation.isPending}
                >
                  <Trash2 className="h-4 w-4" />
                </Button>
              </div>
            ))}
          </div>

          {/* Mount New Command */}
          <div className="border-t pt-4 space-y-3">
            <h4 className="font-medium">Mount New Command</h4>
            <div className="space-y-3">
              <Input
                placeholder="Command name (e.g., review-code)"
                value={newCommandName}
                onChange={(e) => setNewCommandName(e.target.value)}
              />
              <Input
                placeholder="Command file path (e.g., /commands/review.md)"
                value={newCommandPath}
                onChange={(e) => setNewCommandPath(e.target.value)}
              />
              <Input
                placeholder="Description (optional)"
                value={newCommandDescription}
                onChange={(e) => setNewCommandDescription(e.target.value)}
              />
              <Button
                onClick={() =>
                  mountCommandMutation.mutate({
                    command_name: newCommandName,
                    command_path: newCommandPath,
                    user_id: 'admin',
                    description: newCommandDescription || undefined,
                  })
                }
                disabled={mountCommandMutation.isPending}
              >
                <Plus className="h-4 w-4 mr-2" />
                Mount Command
              </Button>
            </div>
          </div>
        </div>
      </CardContent>
    </Card>
  )
}

// Mounted Sub-Agents Section
function MountedSubAgentsSection({
  config,
  queryClient,
}: {
  config: ProjectConfig
  queryClient: any
}) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>Mounted Sub-Agents</CardTitle>
        <CardDescription>
          Configure sub-agents available to agents in this project
        </CardDescription>
      </CardHeader>
      <CardContent>
        <div className="space-y-2">
          {Object.entries(config.mounted_subagents || {}).map(([name, subagent]) => (
            <div key={name} className="p-3 border rounded-md">
              <div className="font-medium">{name}</div>
              {subagent.description && (
                <p className="text-sm text-muted-foreground">{subagent.description}</p>
              )}
              <pre className="mt-2 text-xs bg-muted p-2 rounded overflow-x-auto">
                {JSON.stringify(subagent.config, null, 2)}
              </pre>
            </div>
          ))}
          {Object.keys(config.mounted_subagents || {}).length === 0 && (
            <p className="text-muted-foreground text-sm">No sub-agents mounted</p>
          )}
        </div>
      </CardContent>
    </Card>
  )
}

// Repository Settings Section
function RepositorySettingsSection({
  config,
  queryClient,
}: {
  config: ProjectConfig
  queryClient: any
}) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>Repository Settings</CardTitle>
        <CardDescription>Configure Git repository settings</CardDescription>
      </CardHeader>
      <CardContent>
        <div className="space-y-3">
          <div>
            <label className="text-sm font-medium">Tech Stacks</label>
            <pre className="mt-2 text-xs bg-muted p-3 rounded overflow-x-auto">
              {JSON.stringify(config.tech_stacks, null, 2)}
            </pre>
          </div>
          <div>
            <label className="text-sm font-medium">Testing Configuration</label>
            <pre className="mt-2 text-xs bg-muted p-3 rounded overflow-x-auto">
              {JSON.stringify(config.testing, null, 2)}
            </pre>
          </div>
        </div>
      </CardContent>
    </Card>
  )
}
