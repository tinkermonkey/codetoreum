import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Plus, Trash2, Edit2, Save, X, ChevronRight, AlertCircle } from 'lucide-react'
import { Button } from '../components/ui/button'
import { Input } from '../components/ui/input'
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '../components/ui/card'
import { pipelineConfigApi, agentConfigApi } from '../api/client'
import type { PipelineConfig, Stage, StageCondition } from '../types'

export default function WorkflowConfigPage() {
  const [selectedPipeline, setSelectedPipeline] = useState<string | null>(null)
  const queryClient = useQueryClient()

  const { data: pipelines, isLoading, error } = useQuery({
    queryKey: ['pipelines'],
    queryFn: () => pipelineConfigApi.getAll(),
  })

  const { data: agents } = useQuery({
    queryKey: ['agents'],
    queryFn: () => agentConfigApi.getAll(),
  })

  const selectedPipelineData = pipelines?.find((p) => p.id === selectedPipeline)

  if (isLoading) {
    return <div className="flex justify-center p-8">Loading pipelines...</div>
  }

  if (error) {
    return (
      <div className="text-destructive p-8">Error loading pipelines: {error.message}</div>
    )
  }

  return (
    <div className="space-y-6">
      <div className="flex justify-between items-center">
        <div>
          <h2 className="text-3xl font-bold">Workflow Configuration</h2>
          <p className="text-muted-foreground mt-1">
            Configure workflow pipelines, stages, and transitions
          </p>
        </div>
        <CreatePipelineButton queryClient={queryClient} />
      </div>

      <div className="grid grid-cols-3 gap-6">
        {/* Pipeline List */}
        <Card className="col-span-1">
          <CardHeader>
            <CardTitle>Pipelines</CardTitle>
            <CardDescription>Select a pipeline to configure</CardDescription>
          </CardHeader>
          <CardContent>
            <div className="space-y-2">
              {pipelines?.map((pipeline) => (
                <div
                  key={pipeline.id}
                  className={`p-3 border rounded-md cursor-pointer transition-colors ${
                    selectedPipeline === pipeline.id
                      ? 'bg-primary/10 border-primary'
                      : 'hover:bg-muted'
                  }`}
                  onClick={() => setSelectedPipeline(pipeline.id)}
                >
                  <div className="font-medium">{pipeline.name}</div>
                  {pipeline.metadata.description && (
                    <p className="text-sm text-muted-foreground mt-1">
                      {pipeline.metadata.description}
                    </p>
                  )}
                  <div className="flex items-center justify-between mt-2">
                    <span className="text-xs text-muted-foreground">
                      {pipeline.stages.length} stages
                    </span>
                    {pipeline.metadata.is_default && (
                      <span className="text-xs bg-primary/20 text-primary px-2 py-0.5 rounded">
                        Default
                      </span>
                    )}
                  </div>
                </div>
              ))}
              {pipelines?.length === 0 && (
                <p className="text-muted-foreground text-sm text-center py-4">
                  No pipelines configured
                </p>
              )}
            </div>
          </CardContent>
        </Card>

        {/* Pipeline Editor */}
        <div className="col-span-2">
          {selectedPipelineData ? (
            <>
              <PipelineDetailsCard
                pipeline={selectedPipelineData}
                queryClient={queryClient}
              />
              <div className="mt-6">
                <StagesEditor
                  pipeline={selectedPipelineData}
                  agents={agents || []}
                  queryClient={queryClient}
                />
              </div>
            </>
          ) : (
            <Card>
              <CardContent className="flex flex-col items-center justify-center py-12">
                <AlertCircle className="h-12 w-12 text-muted-foreground mb-4" />
                <p className="text-muted-foreground">Select a pipeline to configure</p>
              </CardContent>
            </Card>
          )}
        </div>
      </div>
    </div>
  )
}

// Create Pipeline Button
function CreatePipelineButton({ queryClient }: { queryClient: any }) {
  const [isCreating, setIsCreating] = useState(false)
  const [name, setName] = useState('')
  const [description, setDescription] = useState('')

  const createMutation = useMutation({
    mutationFn: (data: Partial<PipelineConfig>) => pipelineConfigApi.create(data as PipelineConfig),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['pipelines'] })
      setIsCreating(false)
      setName('')
      setDescription('')
    },
  })

  if (!isCreating) {
    return (
      <Button onClick={() => setIsCreating(true)}>
        <Plus className="h-4 w-4 mr-2" />
        New Pipeline
      </Button>
    )
  }

  return (
    <div className="flex items-center space-x-2">
      <Input
        placeholder="Pipeline name"
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
            id: `pipeline-${Date.now()}`,
            name,
            project_id: 'codetoreum',
            stages: [],
            triggers: [],
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

// Pipeline Details Card
function PipelineDetailsCard({
  pipeline,
  queryClient,
}: {
  pipeline: PipelineConfig
  queryClient: any
}) {
  const [isEditing, setIsEditing] = useState(false)
  const [name, setName] = useState(pipeline.name)
  const [description, setDescription] = useState(pipeline.metadata.description || '')
  const [isDefault, setIsDefault] = useState(pipeline.metadata.is_default || false)

  const updateMutation = useMutation({
    mutationFn: (data: Partial<PipelineConfig>) =>
      pipelineConfigApi.update(pipeline.name, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['pipelines'] })
      setIsEditing(false)
    },
  })

  const deleteMutation = useMutation({
    mutationFn: () => pipelineConfigApi.delete(pipeline.name),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['pipelines'] })
    },
  })

  const handleSave = () => {
    updateMutation.mutate({
      ...pipeline,
      name,
      metadata: {
        ...pipeline.metadata,
        description,
        is_default: isDefault,
      },
    })
  }

  return (
    <Card>
      <CardHeader>
        <div className="flex items-center justify-between">
          <div className="flex-1">
            {isEditing ? (
              <Input
                value={name}
                onChange={(e) => setName(e.target.value)}
                className="mb-2"
              />
            ) : (
              <CardTitle>{pipeline.name}</CardTitle>
            )}
            {isEditing ? (
              <Input
                placeholder="Description"
                value={description}
                onChange={(e) => setDescription(e.target.value)}
              />
            ) : (
              <CardDescription>{pipeline.metadata.description}</CardDescription>
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
                    if (confirm('Are you sure you want to delete this pipeline?')) {
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
        <div className="grid grid-cols-2 gap-4 text-sm">
          <div>
            <span className="text-muted-foreground">Version:</span>
            <span className="ml-2 font-medium">{pipeline.version}</span>
          </div>
          <div>
            <span className="text-muted-foreground">Stages:</span>
            <span className="ml-2 font-medium">{pipeline.stages.length}</span>
          </div>
          <div>
            <span className="text-muted-foreground">Updated:</span>
            <span className="ml-2 font-medium">
              {new Date(pipeline.updated_at).toLocaleDateString()}
            </span>
          </div>
          <div className="flex items-center">
            {isEditing ? (
              <label className="flex items-center space-x-2">
                <input
                  type="checkbox"
                  checked={isDefault}
                  onChange={(e) => setIsDefault(e.target.checked)}
                  className="h-4 w-4"
                />
                <span className="text-sm">Set as default</span>
              </label>
            ) : (
              <>
                <span className="text-muted-foreground">Default:</span>
                <span className="ml-2 font-medium">
                  {pipeline.metadata.is_default ? 'Yes' : 'No'}
                </span>
              </>
            )}
          </div>
        </div>
      </CardContent>
    </Card>
  )
}

// Stages Editor
function StagesEditor({
  pipeline,
  agents,
  queryClient,
}: {
  pipeline: PipelineConfig
  agents: any[]
  queryClient: any
}) {
  const [isAddingStage, setIsAddingStage] = useState(false)
  const [editingStageIndex, setEditingStageIndex] = useState<number | null>(null)

  const updateStagesMutation = useMutation({
    mutationFn: (stages: Stage[]) =>
      pipelineConfigApi.update(pipeline.name, { ...pipeline, stages }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['pipelines'] })
      setIsAddingStage(false)
      setEditingStageIndex(null)
    },
  })

  const addStage = (stage: Stage) => {
    const newStages = [...pipeline.stages, stage]
    updateStagesMutation.mutate(newStages)
  }

  const updateStage = (index: number, stage: Stage) => {
    const newStages = [...pipeline.stages]
    newStages[index] = stage
    updateStagesMutation.mutate(newStages)
  }

  const deleteStage = (index: number) => {
    const newStages = pipeline.stages.filter((_, i) => i !== index)
    updateStagesMutation.mutate(newStages)
  }

  const moveStage = (index: number, direction: 'up' | 'down') => {
    const newStages = [...pipeline.stages]
    const targetIndex = direction === 'up' ? index - 1 : index + 1
    if (targetIndex < 0 || targetIndex >= newStages.length) return
    ;[newStages[index], newStages[targetIndex]] = [newStages[targetIndex], newStages[index]]
    updateStagesMutation.mutate(newStages)
  }

  return (
    <Card>
      <CardHeader>
        <div className="flex items-center justify-between">
          <div>
            <CardTitle>Pipeline Stages</CardTitle>
            <CardDescription>Configure stages and their execution order</CardDescription>
          </div>
          <Button size="sm" onClick={() => setIsAddingStage(true)}>
            <Plus className="h-4 w-4 mr-2" />
            Add Stage
          </Button>
        </div>
      </CardHeader>
      <CardContent>
        <div className="space-y-3">
          {/* Pipeline Visualization */}
          {pipeline.stages.length > 0 && (
            <div className="flex items-center space-x-2 overflow-x-auto pb-4 mb-4 border-b">
              {pipeline.stages.map((stage, index) => (
                <div key={index} className="flex items-center">
                  <div className="bg-primary/10 border border-primary px-3 py-2 rounded-md whitespace-nowrap">
                    <div className="text-sm font-medium">{stage.name}</div>
                    <div className="text-xs text-muted-foreground">{stage.agent}</div>
                  </div>
                  {index < pipeline.stages.length - 1 && (
                    <ChevronRight className="h-5 w-5 mx-2 text-muted-foreground" />
                  )}
                </div>
              ))}
            </div>
          )}

          {/* Stage List */}
          {pipeline.stages.map((stage, index) => (
            <div key={index}>
              {editingStageIndex === index ? (
                <StageEditor
                  stage={stage}
                  agents={agents}
                  onSave={(updatedStage) => updateStage(index, updatedStage)}
                  onCancel={() => setEditingStageIndex(null)}
                />
              ) : (
                <StageCard
                  stage={stage}
                  index={index}
                  totalStages={pipeline.stages.length}
                  onEdit={() => setEditingStageIndex(index)}
                  onDelete={() => deleteStage(index)}
                  onMove={(direction) => moveStage(index, direction)}
                />
              )}
            </div>
          ))}

          {/* Add New Stage */}
          {isAddingStage && (
            <StageEditor
              agents={agents}
              onSave={addStage}
              onCancel={() => setIsAddingStage(false)}
            />
          )}

          {pipeline.stages.length === 0 && !isAddingStage && (
            <p className="text-muted-foreground text-sm text-center py-8">
              No stages configured. Add a stage to get started.
            </p>
          )}
        </div>
      </CardContent>
    </Card>
  )
}

// Stage Card
function StageCard({
  stage,
  index,
  totalStages,
  onEdit,
  onDelete,
  onMove,
}: {
  stage: Stage
  index: number
  totalStages: number
  onEdit: () => void
  onDelete: () => void
  onMove: (direction: 'up' | 'down') => void
}) {
  return (
    <div className="flex items-center justify-between p-3 border rounded-md">
      <div className="flex-1">
        <div className="flex items-center space-x-2">
          <span className="text-xs bg-muted px-2 py-1 rounded font-mono">
            Stage {index + 1}
          </span>
          <span className="font-medium">{stage.name}</span>
        </div>
        <div className="text-sm text-muted-foreground mt-1">
          Agent: <span className="font-medium">{stage.agent}</span>
          {stage.timeout_minutes && ` • Timeout: ${stage.timeout_minutes}m`}
          {stage.max_retries && ` • Max retries: ${stage.max_retries}`}
        </div>
        {stage.entry_conditions && stage.entry_conditions.length > 0 && (
          <div className="text-xs text-muted-foreground mt-1">
            Entry conditions: {stage.entry_conditions.map((c) => c.type).join(', ')}
          </div>
        )}
      </div>
      <div className="flex items-center space-x-1">
        <Button
          size="sm"
          variant="ghost"
          onClick={() => onMove('up')}
          disabled={index === 0}
        >
          ↑
        </Button>
        <Button
          size="sm"
          variant="ghost"
          onClick={() => onMove('down')}
          disabled={index === totalStages - 1}
        >
          ↓
        </Button>
        <Button size="sm" variant="outline" onClick={onEdit}>
          <Edit2 className="h-4 w-4" />
        </Button>
        <Button size="sm" variant="destructive" onClick={onDelete}>
          <Trash2 className="h-4 w-4" />
        </Button>
      </div>
    </div>
  )
}

// Stage Editor
function StageEditor({
  stage,
  agents,
  onSave,
  onCancel,
}: {
  stage?: Stage
  agents: any[]
  onSave: (stage: Stage) => void
  onCancel: () => void
}) {
  const [name, setName] = useState(stage?.name || '')
  const [agent, setAgent] = useState(stage?.agent || '')
  const [timeoutMinutes, setTimeoutMinutes] = useState(stage?.timeout_minutes?.toString() || '')
  const [maxRetries, setMaxRetries] = useState(stage?.max_retries?.toString() || '')
  const [retryOnFailure, setRetryOnFailure] = useState(stage?.retry_on_failure || false)
  const [conditionType, setConditionType] = useState<string>(
    stage?.entry_conditions?.[0]?.type || 'success'
  )

  const handleSave = () => {
    if (!name || !agent) return

    const newStage: Stage = {
      name,
      agent,
      timeout_minutes: timeoutMinutes ? parseInt(timeoutMinutes) : undefined,
      max_retries: maxRetries ? parseInt(maxRetries) : undefined,
      retry_on_failure: retryOnFailure,
      entry_conditions: [{ type: conditionType as any }],
    }

    onSave(newStage)
  }

  return (
    <div className="p-4 border rounded-md bg-muted/30 space-y-3">
      <h4 className="font-medium">{stage ? 'Edit Stage' : 'New Stage'}</h4>
      <div className="grid grid-cols-2 gap-3">
        <Input
          placeholder="Stage name"
          value={name}
          onChange={(e) => setName(e.target.value)}
        />
        <select
          className="flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
          value={agent}
          onChange={(e) => setAgent(e.target.value)}
        >
          <option value="">Select agent...</option>
          {agents.map((a) => (
            <option key={a.agent_name} value={a.agent_name}>
              {a.agent_name}
            </option>
          ))}
        </select>
        <Input
          type="number"
          placeholder="Timeout (minutes)"
          value={timeoutMinutes}
          onChange={(e) => setTimeoutMinutes(e.target.value)}
        />
        <Input
          type="number"
          placeholder="Max retries"
          value={maxRetries}
          onChange={(e) => setMaxRetries(e.target.value)}
        />
        <select
          className="flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
          value={conditionType}
          onChange={(e) => setConditionType(e.target.value)}
        >
          <option value="success">On Success</option>
          <option value="failure">On Failure</option>
          <option value="always">Always</option>
          <option value="manual">Manual</option>
          <option value="conditional">Conditional</option>
        </select>
        <label className="flex items-center space-x-2">
          <input
            type="checkbox"
            checked={retryOnFailure}
            onChange={(e) => setRetryOnFailure(e.target.checked)}
            className="h-4 w-4"
          />
          <span className="text-sm">Retry on failure</span>
        </label>
      </div>
      <div className="flex items-center space-x-2">
        <Button onClick={handleSave} disabled={!name || !agent}>
          <Save className="h-4 w-4 mr-2" />
          {stage ? 'Update' : 'Add'} Stage
        </Button>
        <Button variant="ghost" onClick={onCancel}>
          <X className="h-4 w-4 mr-2" />
          Cancel
        </Button>
      </div>
    </div>
  )
}
