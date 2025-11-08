import { memo } from 'react'
import { Handle, Position } from '@xyflow/react'
import { ChevronDown, ChevronRight, RotateCcw } from 'lucide-react'
import type { CycleBoundingNodeData, CycleType } from '@/types/flow'

interface CycleBoundingNodeProps {
  data: CycleBoundingNodeData
}

const CYCLE_STYLES: Record<
  CycleType,
  { borderColor: string; bgColor: string; badgeColor: string; badgeBg: string }
> = {
  review: {
    borderColor: '#9333ea',
    bgColor: 'rgba(147, 51, 234, 0.05)',
    badgeColor: '#9333ea',
    badgeBg: 'rgba(147, 51, 234, 0.1)',
  },
  repair: {
    borderColor: '#dc2626',
    bgColor: 'rgba(220, 38, 38, 0.05)',
    badgeColor: '#dc2626',
    badgeBg: 'rgba(220, 38, 38, 0.1)',
  },
  conversation: {
    borderColor: '#2563eb',
    bgColor: 'rgba(37, 99, 235, 0.05)',
    badgeColor: '#2563eb',
    badgeBg: 'rgba(37, 99, 235, 0.1)',
  },
  unknown: {
    borderColor: '#6b7280',
    bgColor: 'rgba(107, 114, 128, 0.05)',
    badgeColor: '#6b7280',
    badgeBg: 'rgba(107, 114, 128, 0.1)',
  },
}

export const CycleBoundingNode = memo(({ data }: CycleBoundingNodeProps) => {
  const {
    cycleId,
    cycleType = 'unknown',
    label,
    iterationCount,
    isCollapsed,
    onToggleCollapse,
    width,
    height,
    cyclePadding = 40,
  } = data

  const style = CYCLE_STYLES[cycleType] || CYCLE_STYLES.unknown

  const handleToggle = (e: React.MouseEvent) => {
    e.stopPropagation()
    if (onToggleCollapse) {
      onToggleCollapse(cycleId)
    }
  }

  return (
    <div
      style={{
        width: isCollapsed ? 280 : width,
        height: isCollapsed ? 100 : height,
        border: '3px dashed',
        borderColor: style.borderColor,
        borderRadius: '12px',
        background: style.bgColor,
        position: 'relative',
        transition: 'all 0.3s ease',
        pointerEvents: 'all',
      }}
      className="cycle-bounding-node"
    >
      {/* Handles for connections when collapsed */}
      {isCollapsed && (
        <>
          <Handle
            type="target"
            position={Position.Top}
            id={`${cycleId}-target`}
            style={{
              background: style.borderColor,
              width: '10px',
              height: '10px',
              border: '2px solid white',
            }}
          />
          <Handle
            type="source"
            position={Position.Bottom}
            id={`${cycleId}-source`}
            style={{
              background: style.borderColor,
              width: '10px',
              height: '10px',
              border: '2px solid white',
            }}
          />
        </>
      )}

      {/* Header bar */}
      <div
        style={{
          position: 'absolute',
          top: -30,
          left: 0,
          right: 0,
          display: 'flex',
          alignItems: 'center',
          gap: '8px',
          padding: '6px 12px',
          background: `${style.borderColor}e6`,
          color: 'white',
          borderRadius: '6px 6px 0 0',
          fontSize: '13px',
          fontWeight: 600,
          cursor: 'pointer',
          userSelect: 'none',
          transition: 'background 0.2s ease',
        }}
        onClick={handleToggle}
        onMouseEnter={(e) => {
          e.currentTarget.style.background = style.borderColor
        }}
        onMouseLeave={(e) => {
          e.currentTarget.style.background = `${style.borderColor}e6`
        }}
      >
        <RotateCcw className="w-4 h-4" />
        <span className="flex-1">{label}</span>
        <span className="text-xs opacity-90">
          {iterationCount} iteration{iterationCount !== 1 ? 's' : ''}
        </span>
        {isCollapsed ? (
          <ChevronRight className="w-4 h-4" />
        ) : (
          <ChevronDown className="w-4 h-4" />
        )}
      </div>

      {/* Collapsed state content */}
      {isCollapsed && (
        <div
          style={{
            padding: '20px',
            display: 'flex',
            flexDirection: 'column',
            alignItems: 'center',
            justifyContent: 'center',
            height: '100%',
            gap: '8px',
          }}
        >
          <div
            style={{
              fontSize: '11px',
              color: style.badgeColor,
              fontWeight: 600,
              textTransform: 'uppercase',
              letterSpacing: '0.5px',
            }}
          >
            {label}
          </div>
          <div
            style={{
              fontSize: '24px',
              fontWeight: 700,
              color: style.badgeColor,
            }}
          >
            {iterationCount}×
          </div>
          <div
            style={{
              fontSize: '11px',
              color: '#6b7280',
              textAlign: 'center',
            }}
          >
            Click to expand
          </div>
        </div>
      )}

      {/* Expanded state - shows iteration markers */}
      {!isCollapsed && (
        <div
          style={{
            position: 'absolute',
            bottom: 8,
            left: cyclePadding,
            right: cyclePadding,
            display: 'flex',
            justifyContent: 'space-evenly',
            alignItems: 'center',
            padding: '4px',
          }}
        >
          {Array.from({ length: iterationCount }, (_, i) => (
            <div
              key={i}
              style={{
                fontSize: '10px',
                fontWeight: 600,
                color: style.badgeColor,
                background: style.badgeBg,
                padding: '4px 8px',
                borderRadius: '4px',
                border: `1px solid ${style.borderColor}50`,
              }}
            >
              #{i + 1}
            </div>
          ))}
        </div>
      )}

      {/* Corner decorations */}
      <div
        style={{
          position: 'absolute',
          top: 8,
          left: 8,
          width: '16px',
          height: '16px',
          borderTop: `3px solid ${style.borderColor}66`,
          borderLeft: `3px solid ${style.borderColor}66`,
          borderRadius: '4px 0 0 0',
        }}
      />
      <div
        style={{
          position: 'absolute',
          top: 8,
          right: 8,
          width: '16px',
          height: '16px',
          borderTop: `3px solid ${style.borderColor}66`,
          borderRight: `3px solid ${style.borderColor}66`,
          borderRadius: '0 4px 0 0',
        }}
      />
      <div
        style={{
          position: 'absolute',
          bottom: 8,
          left: 8,
          width: '16px',
          height: '16px',
          borderBottom: `3px solid ${style.borderColor}66`,
          borderLeft: `3px solid ${style.borderColor}66`,
          borderRadius: '0 0 0 4px',
        }}
      />
      <div
        style={{
          position: 'absolute',
          bottom: 8,
          right: 8,
          width: '16px',
          height: '16px',
          borderBottom: `3px solid ${style.borderColor}66`,
          borderRight: `3px solid ${style.borderColor}66`,
          borderRadius: '0 0 4px 0',
        }}
      />
    </div>
  )
})

CycleBoundingNode.displayName = 'CycleBoundingNode'
