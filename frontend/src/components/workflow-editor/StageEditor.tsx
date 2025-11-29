import { useState } from 'react'
import { Save, X } from 'lucide-react'
import { Button } from '../ui/button'
import { Input } from '../ui/input'
import type { Stage } from '../../types'

interface StageEditorProps {
  stage?: Stage
  agents: any[]
  onSave: (stage: Stage) => void
  onCancel: () => void
  isLoading?: boolean
}

export function StageEditor({
  stage,
  agents,
  onSave,
  onCancel,
  isLoading = false,
}: StageEditorProps) {
  const [name, setName] = useState(stage?.name || '')
  const [agent, setAgent] = useState(stage?.agent || '')
  const [timeoutMinutes, setTimeoutMinutes] = useState(stage?.timeout_minutes?.toString() || '')
  const [maxRetries, setMaxRetries] = useState(stage?.max_retries?.toString() || '')
  const [retryOnFailure, setRetryOnFailure] = useState(stage?.retry_on_failure || false)
  const [conditionType, setConditionType] = useState<string>(
    stage?.entry_conditions?.[0]?.type || 'success'
  )
  const [errors, setErrors] = useState<{
    name?: string
    agent?: string
    timeout?: string
    retries?: string
  }>({})

  const validate = (): boolean => {
    const newErrors: typeof errors = {}

    if (!name.trim()) {
      newErrors.name = 'Stage name is required'
    }

    if (!agent.trim()) {
      newErrors.agent = 'Agent selection is required'
    }

    if (timeoutMinutes) {
      const timeout = parseFloat(timeoutMinutes)
      if (isNaN(timeout) || timeout <= 0) {
        newErrors.timeout = 'Timeout must be a positive number'
      }
    }

    if (maxRetries) {
      const retries = parseInt(maxRetries)
      if (isNaN(retries) || retries < 0 || !Number.isInteger(parseFloat(maxRetries))) {
        newErrors.retries = 'Max retries must be a non-negative integer'
      }
    }

    setErrors(newErrors)
    return Object.keys(newErrors).length === 0
  }

  const handleSave = () => {
    if (!validate()) return

    const newStage: Stage = {
      name: name.trim(),
      agent: agent.trim(),
      timeout_minutes: timeoutMinutes ? parseFloat(timeoutMinutes) : undefined,
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
        <div className="flex flex-col space-y-1">
          <Input
            placeholder="Stage name *"
            value={name}
            onChange={(e) => {
              setName(e.target.value)
              setErrors((prev) => ({ ...prev, name: undefined }))
            }}
            className={errors.name ? 'border-destructive' : ''}
          />
          {errors.name && <p className="text-xs text-destructive">{errors.name}</p>}
        </div>
        <div className="flex flex-col space-y-1">
          <select
            className={`flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm ${
              errors.agent ? 'border-destructive' : ''
            }`}
            value={agent}
            onChange={(e) => {
              setAgent(e.target.value)
              setErrors((prev) => ({ ...prev, agent: undefined }))
            }}
          >
            <option value="">Select agent... *</option>
            {agents.map((a) => (
              <option key={a.agent_name} value={a.agent_name}>
                {a.agent_name}
              </option>
            ))}
          </select>
          {errors.agent && <p className="text-xs text-destructive">{errors.agent}</p>}
        </div>
        <div className="flex flex-col space-y-1">
          <Input
            type="number"
            placeholder="Timeout (minutes)"
            value={timeoutMinutes}
            onChange={(e) => {
              setTimeoutMinutes(e.target.value)
              setErrors((prev) => ({ ...prev, timeout: undefined }))
            }}
            className={errors.timeout ? 'border-destructive' : ''}
          />
          {errors.timeout && <p className="text-xs text-destructive">{errors.timeout}</p>}
        </div>
        <div className="flex flex-col space-y-1">
          <Input
            type="number"
            placeholder="Max retries"
            value={maxRetries}
            onChange={(e) => {
              setMaxRetries(e.target.value)
              setErrors((prev) => ({ ...prev, retries: undefined }))
            }}
            className={errors.retries ? 'border-destructive' : ''}
          />
          {errors.retries && <p className="text-xs text-destructive">{errors.retries}</p>}
        </div>
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
        <Button
          onClick={handleSave}
          disabled={isLoading || (!name.trim() && !agent.trim())}
        >
          {isLoading ? (
            'Saving...'
          ) : (
            <>
              <Save className="h-4 w-4 mr-2" />
              {stage ? 'Update' : 'Add'} Stage
            </>
          )}
        </Button>
        <Button variant="ghost" onClick={onCancel} disabled={isLoading}>
          <X className="h-4 w-4 mr-2" />
          Cancel
        </Button>
      </div>
    </div>
  )
}
