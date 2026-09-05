import { memo } from 'react'
import { Handle, Position } from '@xyflow/react'
import { Activity, CheckCircle, PlayCircle, XCircle } from 'lucide-react'
import type { WorkflowEventNodeData, NodeStyleConfig } from '@/types/flow'

interface WorkflowEventNodeProps {
  data: WorkflowEventNodeData
}

const NODE_STYLES: Record<string, NodeStyleConfig> = {
  WorkflowStarted: {
    background: '#10b981',
    borderColor: '#059669',
    textColor: '#fff',
  },
  WorkflowCompleted: {
    background: '#6366f1',
    borderColor: '#4f46e5',
    textColor: '#fff',
  },
  ExecutionRunning: {
    background: '#1f6feb',
    borderColor: '#58a6ff',
    textColor: '#fff',
  },
  ExecutionCompleted: {
    background: '#238636',
    borderColor: '#2ea043',
    textColor: '#fff',
  },
  ExecutionFailed: {
    background: '#da3633',
    borderColor: '#f85149',
    textColor: '#fff',
  },
  default: {
    background: '#374151',
    borderColor: '#4b5563',
    textColor: '#fff',
  },
}

export const WorkflowEventNode = memo(({ data }: WorkflowEventNodeProps) => {
  const { label, eventType, status, isActive, metadata } = data

  const getNodeStyle = (): React.CSSProperties => {
    const styleKey = eventType || 'default'
    const style = NODE_STYLES[styleKey] || NODE_STYLES.default

    return {
      padding: '12px 16px',
      borderRadius: '8px',
      border: `2px solid ${style.borderColor}`,
      background: style.background,
      color: style.textColor,
      minWidth: '200px',
      maxWidth: '300px',
      boxShadow: isActive
        ? '0 0 10px rgba(88, 166, 255, 0.5)'
        : '0 2px 4px rgba(0,0,0,0.1)',
    }
  }

  const getIcon = () => {
    if (eventType === 'WorkflowStarted') return <PlayCircle className="w-4 h-4" />
    if (eventType === 'WorkflowCompleted') return <CheckCircle className="w-4 h-4" />
    if (status === 'completed') return <CheckCircle className="w-4 h-4" />
    if (status === 'failed') return <XCircle className="w-4 h-4" />
    return <Activity className="w-4 h-4" />
  }

  return (
    <div style={getNodeStyle()} className="relative">
      {/* Candy stripe animation for active nodes */}
      {isActive && (
        <div
          className="absolute top-0 left-0 right-0 h-1 rounded-t-md overflow-hidden animate-pulse"
          style={{
            backgroundImage:
              'linear-gradient(45deg, rgba(255,255,255,.2) 25%, transparent 25%, transparent 50%, rgba(255,255,255,.2) 50%, rgba(255,255,255,.2) 75%, transparent 75%, transparent)',
            backgroundSize: '1rem 1rem',
            animation: 'pulse 2s cubic-bezier(0.4, 0, 0.6, 1) infinite',
          }}
        />
      )}

      <Handle type="target" position={Position.Top} style={{ opacity: 0 }} />

      <div className="flex items-start gap-2">
        <div className="mt-0.5">{getIcon()}</div>
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

WorkflowEventNode.displayName = 'WorkflowEventNode'
