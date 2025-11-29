import { Edit2, Trash2 } from 'lucide-react'
import { Button } from '../ui/button'
import type { Stage } from '../../types'

interface StageCardProps {
  stage: Stage
  index: number
  totalStages: number
  onEdit: () => void
  onDelete: () => void
  onMove: (direction: 'up' | 'down') => void
  isLoading?: boolean
}

export function StageCard({
  stage,
  index,
  totalStages,
  onEdit,
  onDelete,
  onMove,
  isLoading = false,
}: StageCardProps) {
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
          disabled={index === 0 || isLoading}
          title="Move up"
        >
          ↑
        </Button>
        <Button
          size="sm"
          variant="ghost"
          onClick={() => onMove('down')}
          disabled={index === totalStages - 1 || isLoading}
          title="Move down"
        >
          ↓
        </Button>
        <Button
          size="sm"
          variant="outline"
          onClick={onEdit}
          disabled={isLoading}
        >
          <Edit2 className="h-4 w-4" />
        </Button>
        <Button
          size="sm"
          variant="destructive"
          onClick={() => {
            if (confirm('Are you sure you want to delete this stage?')) {
              onDelete()
            }
          }}
          disabled={isLoading}
        >
          <Trash2 className="h-4 w-4" />
        </Button>
      </div>
    </div>
  )
}
