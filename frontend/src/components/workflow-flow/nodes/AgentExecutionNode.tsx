import { memo } from 'react'
import { Handle, Position } from '@xyflow/react'
import { Activity, CheckCircle, XCircle, Clock } from 'lucide-react'
import type { AgentExecutionNodeData, NodeStyleConfig } from '@/types/flow'

interface AgentExecutionNodeProps {
  data: AgentExecutionNodeData
}

const getNodeStyle = (status: string, isActive: boolean): NodeStyleConfig & { boxShadow: string } => {
  if (status === 'running' || isActive) {
    return {
      background: '#1f6feb',
      borderColor: '#58a6ff',
      textColor: '#fff',
      boxShadow: '0 0 10px rgba(88, 166, 255, 0.5)',
    }
  } else if (status === 'completed') {
    return {
      background: '#238636',
      borderColor: '#2ea043',
      textColor: '#fff',
      boxShadow: '0 2px 4px rgba(0,0,0,0.1)',
    }
  } else if (status === 'failed') {
    return {
      background: '#da3633',
      borderColor: '#f85149',
      textColor: '#fff',
      boxShadow: '0 2px 4px rgba(0,0,0,0.1)',
    }
  }
  return {
    background: '#6e7681',
    borderColor: '#30363d',
    textColor: '#fff',
    boxShadow: '0 2px 4px rgba(0,0,0,0.1)',
  }
}

export const AgentExecutionNode = memo(({ data }: AgentExecutionNodeProps) => {
  const { label, status, isActive, metadata } = data
  const style = getNodeStyle(status, isActive)

  const getIcon = () => {
    if (status === 'completed') return <CheckCircle className="w-4 h-4" />
    if (status === 'failed') return <XCircle className="w-4 h-4" />
    if (status === 'running' || isActive) return <Activity className="w-4 h-4" />
    return <Clock className="w-4 h-4" />
  }

  return (
    <div
      style={{
        padding: '12px 16px',
        borderRadius: '8px',
        border: `${isActive ? '3px' : '2px'} solid ${style.borderColor}`,
        background: style.background,
        color: style.textColor,
        minWidth: '200px',
        maxWidth: '300px',
        boxShadow: style.boxShadow,
      }}
      className="relative"
    >
      {/* Candy stripe animation for active agents */}
      {isActive && (
        <div
          className="absolute top-0 left-0 right-0 h-1 rounded-t-md overflow-hidden"
          style={{
            backgroundImage:
              'linear-gradient(45deg, rgba(255,255,255,.2) 25%, transparent 25%, transparent 50%, rgba(255,255,255,.2) 50%, rgba(255,255,255,.2) 75%, transparent 75%, transparent)',
            backgroundSize: '1rem 1rem',
            animation: 'pulse 2s cubic-bezier(0.4, 0, 0.6, 1) infinite, stripes 1s linear infinite',
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

      <style>{`
        @keyframes stripes {
          0% {
            background-position: 0 0;
          }
          100% {
            background-position: 1rem 1rem;
          }
        }
      `}</style>
    </div>
  )
})

AgentExecutionNode.displayName = 'AgentExecutionNode'
