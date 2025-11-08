import { memo } from 'react'
import { Handle, Position } from '@xyflow/react'
import { GitBranch } from 'lucide-react'
import type { DecisionNodeData } from '@/types/flow'

interface DecisionNodeProps {
  data: DecisionNodeData
}

const DECISION_COLORS: Record<string, { bg: string; border: string }> = {
  routing: { bg: '#3b82f6', border: '#2563eb' },
  progression: { bg: '#10b981', border: '#059669' },
  review_cycle: { bg: '#8b5cf6', border: '#7c3aed' },
  feedback: { bg: '#f59e0b', border: '#d97706' },
  error_handling: { bg: '#ef4444', border: '#dc2626' },
  task_management: { bg: '#06b6d4', border: '#0891b2' },
  branch_management: { bg: '#84cc16', border: '#65a30d' },
  conversational_loop: { bg: '#ec4899', border: '#db2777' },
  default: { bg: '#f59e0b', border: '#d97706' },
}

export const DecisionNode = memo(({ data }: DecisionNodeProps) => {
  const { label, category, metadata } = data
  const colors = DECISION_COLORS[category || 'default'] || DECISION_COLORS.default

  return (
    <div
      style={{
        padding: '12px 16px',
        borderRadius: '8px',
        border: `2px solid ${colors.border}`,
        background: colors.bg,
        color: '#fff',
        minWidth: '200px',
        maxWidth: '300px',
        boxShadow: '0 2px 4px rgba(0,0,0,0.1)',
      }}
    >
      <Handle type="target" position={Position.Top} style={{ opacity: 0 }} />

      <div className="flex items-start gap-2">
        <div className="mt-0.5">
          <GitBranch className="w-4 h-4" />
        </div>
        <div className="flex-1">
          <div className="font-semibold text-sm">{label}</div>
          {metadata && Object.keys(metadata).length > 0 && (
            <div className="text-xs mt-1 opacity-90">
              {typeof metadata === 'string' ? metadata : JSON.stringify(metadata)}
            </div>
          )}
        </div>
      </div>

      <Handle type="source" position={Position.Bottom} style={{ opacity: 0 }} />
    </div>
  )
})

DecisionNode.displayName = 'DecisionNode'
