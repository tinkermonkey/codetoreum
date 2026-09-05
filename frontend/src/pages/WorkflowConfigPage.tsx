import { useState, useEffect } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Plus, Trash2, Edit2, Save, X, AlertCircle } from 'lucide-react'
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
import { StageCard } from '../components/workflow-editor/StageCard'
import { StageEditor } from '../components/workflow-editor/StageEditor'
import type { PipelineConfig, Stage } from '../types'
import { useToast } from '../components/ui/use-toast'

export default function WorkflowConfigPage() {
  const [selectedPipeline, setSelectedPipeline] = useState<string | null>(null)
  const [hasUnsavedChanges, setHasUnsavedChanges] = useState(false)
  const queryClient = useQueryClient()
  const { toast } = useToast()

  const { data: pipelines, isLoading, error } = useQuery({
    queryKey: ['pipelines'],
    queryFn: () => pipelineConfigApi.getAll(),
  })

  const { data: agents } = useQuery({
    queryKey: ['agents'],
    queryFn: () => agentConfigApi.getAll(),
  })

  const selectedPipelineData = pipelines?.find((p) => p.id === selectedPipeline)

  // Warning for unsaved changes
  useEffect(() => {
    const handleBeforeUnload = (e: BeforeUnloadEvent) => {
      if (hasUnsavedChanges) {
        e.preventDefault()
        e.returnValue = ''
      }
    }

    window.addEventListener('beforeunload', handleBeforeUnload)
    return () => window.removeEventListener('beforeunload', handleBeforeUnload)
  }, [hasUnsavedChanges])

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
        <CreatePipelineButton
          queryClient={queryClient}
          onSuccess={() => toast({ title: 'Pipeline created successfully' })}
          onError={(error) => toast({
            title: 'Failed to create pipeline',
            description: error.message,
            variant: 'destructive'
          })}
        />
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
                  onClick={() => {
                    if (hasUnsavedChanges && !confirm('You have unsaved changes. Continue?')) {
                      return
                    }
                    setSelectedPipeline(pipeline.id)
                    setHasUnsavedChanges(false)
                  }}
                >
                  <div className="font-medium">{pipeline.name}</div>
                  {pipeline.metadata?.description && (
                    <p className="text-sm text-muted-foreground mt-1">
                      {pipeline.metadata.description}
                    </p>
                  )}
                  <div className="flex items-center justify-between mt-2">
                    <span className="text-xs text-muted-foreground">
                      {pipeline.stages.length} stages
                    </span>
                    {pipeline.metadata?.is_default && (
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
                onUnsavedChanges={setHasUnsavedChanges}
              />
              <div className="mt-6">
                <StagesEditor
                  pipeline={selectedPipelineData}
                  agents={agents || []}
                  queryClient={queryClient}
                  onUnsavedChanges={setHasUnsavedChanges}
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
function CreatePipelineButton({
  queryClient,
  onSuccess,
  onError,
}: {
  queryClient: any
  onSuccess: () => void
  onError: (error: Error) => void
}) {
  const [isCreating, setIsCreating] = useState(false)
  const [name, setName] = useState('')
  const [description, setDescription] = useState('')
  const [error, setError] = useState('')

  const createMutation = useMutation({
    mutationFn: (data: Partial<PipelineConfig>) => pipelineConfigApi.create(data as PipelineConfig),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['pipelines'] })
      setIsCreating(false)
      setName('')
      setDescription('')
      setError('')
      onSuccess()
    },
    onError: (err: Error) => {
      setError(err.message)
      onError(err)
    },
  })

  const handleCreate = () => {
    if (!name.trim()) {
      setError('Pipeline name is required')
      return
    }

    createMutation.mutate({
      id: `pipeline-${Date.now()}`,
      name: name.trim(),
      project_id: 'codetoreum',
      stages: [],
      triggers: [],
      version: 1,
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString(),
      metadata: { description: description.trim() },
    })
  }

  if (!isCreating) {
    return (
      <Button onClick={() => setIsCreating(true)}>
        <Plus className="h-4 w-4 mr-2" />
        New Pipeline
      </Button>
    )
  }

  return (
    <div className="flex flex-col space-y-2">
      <div className="flex items-center space-x-2">
        <Input
          placeholder="Pipeline name *"
          value={name}
          onChange={(e) => {
            setName(e.target.value)
            setError('')
          }}
          className="w-48"
        />
        <Input
          placeholder="Description (optional)"
          value={description}
          onChange={(e) => setDescription(e.target.value)}
          className="w-64"
        />
        <Button
          onClick={handleCreate}
          disabled={!name.trim() || createMutation.isPending}
        >
          {createMutation.isPending ? (
            <>Saving...</>
          ) : (
            <>
              <Save className="h-4 w-4 mr-2" />
              Create
            </>
          )}
        </Button>
        <Button
          variant="ghost"
          onClick={() => {
            setIsCreating(false)
            setName('')
            setDescription('')
            setError('')
          }}
          disabled={createMutation.isPending}
        >
          <X className="h-4 w-4" />
        </Button>
      </div>
      {error && <p className="text-sm text-destructive">{error}</p>}
    </div>
  )
}

// Pipeline Details Card
function PipelineDetailsCard({
  pipeline,
  queryClient,
  onUnsavedChanges,
}: {
  pipeline: PipelineConfig
  queryClient: any
  onUnsavedChanges: (hasChanges: boolean) => void
}) {
  const [isEditing, setIsEditing] = useState(false)
  const [name, setName] = useState(pipeline.name)
  const [description, setDescription] = useState(pipeline.metadata?.description || '')
  const [isDefault, setIsDefault] = useState(pipeline.metadata?.is_default || false)
  const { toast } = useToast()

  useEffect(() => {
    const hasChanges = isEditing && (
      name !== pipeline.name ||
      description !== (pipeline.metadata?.description || '') ||
      isDefault !== (pipeline.metadata?.is_default || false)
    )
    onUnsavedChanges(hasChanges)
  }, [isEditing, name, description, isDefault, pipeline, onUnsavedChanges])

  const updateMutation = useMutation({
    mutationFn: (data: Partial<PipelineConfig>) =>
      pipelineConfigApi.update(pipeline.name, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['pipelines'] })
      setIsEditing(false)
      onUnsavedChanges(false)
      toast({ title: 'Pipeline updated successfully' })
    },
    onError: (error: Error) => {
      toast({
        title: 'Failed to update pipeline',
        description: error.message,
        variant: 'destructive'
      })
    },
  })

  const deleteMutation = useMutation({
    mutationFn: () => pipelineConfigApi.delete(pipeline.name),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['pipelines'] })
      toast({ title: 'Pipeline deleted successfully' })
    },
    onError: (error: Error) => {
      toast({
        title: 'Failed to delete pipeline',
        description: error.message,
        variant: 'destructive'
      })
    },
  })

  const handleSave = () => {
    if (!name.trim()) {
      toast({
        title: 'Validation error',
        description: 'Pipeline name is required',
        variant: 'destructive'
      })
      return
    }

    updateMutation.mutate({
      ...pipeline,
      name: name.trim(),
      metadata: {
        ...pipeline.metadata,
        description: description.trim(),
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
                placeholder="Pipeline name *"
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
              <CardDescription>{pipeline.metadata?.description}</CardDescription>
            )}
          </div>
          <div className="flex items-center space-x-2">
            {isEditing ? (
              <>
                <Button
                  size="sm"
                  onClick={handleSave}
                  disabled={updateMutation.isPending || !name.trim()}
                >
                  {updateMutation.isPending ? (
                    'Saving...'
                  ) : (
                    <>
                      <Save className="h-4 w-4 mr-2" />
                      Save
                    </>
                  )}
                </Button>
                <Button
                  size="sm"
                  variant="ghost"
                  onClick={() => {
                    setIsEditing(false)
                    setName(pipeline.name)
                    setDescription(pipeline.metadata?.description || '')
                    setIsDefault(pipeline.metadata?.is_default || false)
                    onUnsavedChanges(false)
                  }}
                  disabled={updateMutation.isPending}
                >
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
                  {deleteMutation.isPending ? (
                    'Deleting...'
                  ) : (
                    <Trash2 className="h-4 w-4" />
                  )}
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
                  {pipeline.metadata?.is_default ? 'Yes' : 'No'}
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
  onUnsavedChanges,
}: {
  pipeline: PipelineConfig
  agents: any[]
  queryClient: any
  onUnsavedChanges: (hasChanges: boolean) => void
}) {
  const [isAddingStage, setIsAddingStage] = useState(false)
  const [editingStageIndex, setEditingStageIndex] = useState<number | null>(null)
  const { toast } = useToast()

  const updateStagesMutation = useMutation({
    mutationFn: (stages: Stage[]) =>
      pipelineConfigApi.update(pipeline.name, { ...pipeline, stages }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['pipelines'] })
      setIsAddingStage(false)
      setEditingStageIndex(null)
      onUnsavedChanges(false)
      toast({ title: 'Stages updated successfully' })
    },
    onError: (error: Error) => {
      toast({
        title: 'Failed to update stages',
        description: error.message,
        variant: 'destructive'
      })
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
    if (!confirm('Are you sure you want to delete this stage?')) return
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
          <Button
            size="sm"
            onClick={() => setIsAddingStage(true)}
            disabled={updateStagesMutation.isPending}
          >
            <Plus className="h-4 w-4 mr-2" />
            Add Stage
          </Button>
        </div>
      </CardHeader>
      <CardContent>
        <div className="space-y-3">
          {/* Stage List */}
          {pipeline.stages.map((stage, index) => (
            <div key={index}>
              {editingStageIndex === index ? (
                <StageEditor
                  stage={stage}
                  agents={agents}
                  onSave={(updatedStage) => updateStage(index, updatedStage)}
                  onCancel={() => {
                    setEditingStageIndex(null)
                    onUnsavedChanges(false)
                  }}
                  isLoading={updateStagesMutation.isPending}
                />
              ) : (
                <StageCard
                  stage={stage}
                  index={index}
                  totalStages={pipeline.stages.length}
                  onEdit={() => {
                    setEditingStageIndex(index)
                    onUnsavedChanges(true)
                  }}
                  onDelete={() => deleteStage(index)}
                  onMove={(direction) => moveStage(index, direction)}
                  isLoading={updateStagesMutation.isPending}
                />
              )}
            </div>
          ))}

          {/* Add New Stage */}
          {isAddingStage && (
            <StageEditor
              agents={agents}
              onSave={addStage}
              onCancel={() => {
                setIsAddingStage(false)
                onUnsavedChanges(false)
              }}
              isLoading={updateStagesMutation.isPending}
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
