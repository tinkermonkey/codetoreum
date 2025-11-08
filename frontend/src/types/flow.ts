import type { Node, Edge, MarkerType } from '@xyflow/react'
import type { WorkflowEvent } from './workflow-event'

/**
 * Flow node types supported by the pipeline visualization
 */
export type FlowNodeType =
  | 'workflow-event'
  | 'agent-execution'
  | 'decision'
  | 'review'
  | 'cycle'

/**
 * Node status states
 */
export type NodeStatus = 'pending' | 'running' | 'completed' | 'failed'

/**
 * Cycle types detected in the workflow
 */
export type CycleType =
  | 'review'
  | 'repair'
  | 'conversation'
  | 'unknown'

/**
 * Data for workflow event nodes
 */
export interface WorkflowEventNodeData extends Record<string, unknown> {
  label: string
  eventType: string
  status?: NodeStatus
  isActive: boolean
  metadata: Record<string, any>
  timestamp?: string
}

/**
 * Data for agent execution nodes
 */
export interface AgentExecutionNodeData extends Record<string, unknown> {
  label: string
  agentName: string
  status: NodeStatus
  isActive: boolean
  metadata: Record<string, any>
  executionIndex?: number
  taskId?: string
  timestamp?: string
}

/**
 * Data for decision nodes
 */
export interface DecisionNodeData extends Record<string, unknown> {
  label: string
  decisionType: string
  category?: string
  metadata: Record<string, any>
  timestamp?: string
}

/**
 * Data for review cycle nodes
 */
export interface ReviewNodeData extends Record<string, unknown> {
  label: string
  reviewType: string
  metadata: Record<string, any>
  timestamp?: string
}

/**
 * Data for cycle bounding nodes
 */
export interface CycleBoundingNodeData extends Record<string, unknown> {
  cycleId: string
  cycleType: CycleType
  label: string
  iterationCount: number
  isCollapsed: boolean
  width: number
  height: number
  cyclePadding: number
  startTime?: string
  endTime?: string
  timestamp?: string
  events?: WorkflowEvent[]
  onToggleCollapse?: (cycleId: string) => void
}

/**
 * Union type for all node data types
 */
export type FlowNodeData =
  | WorkflowEventNodeData
  | AgentExecutionNodeData
  | DecisionNodeData
  | ReviewNodeData
  | CycleBoundingNodeData

/**
 * Custom flow node type
 */
export interface FlowNode extends Omit<Node, 'type'> {
  type: FlowNodeType
  data: FlowNodeData
}

/**
 * Custom edge type with animation support
 */
export interface FlowEdge extends Edge {
  animated?: boolean
  label?: string
  labelStyle?: React.CSSProperties
  markerEnd?: {
    type: typeof MarkerType.ArrowClosed
    color?: string
  }
}

/**
 * Cycle detection result
 */
export interface Cycle {
  id: string
  type: CycleType
  events: WorkflowEvent[]
  entryPoint: string
  exitPoint: string
  startTime: string
  endTime?: string
  iterations: number
  isCollapsed: boolean
  agentExecutions?: Array<{
    agent: string
    taskId: string
    executionIndex: number
    timestamp: string
  }>
  decisionEvents?: WorkflowEvent[]
}

/**
 * Flow graph data structure
 */
export interface FlowGraph {
  nodes: FlowNode[]
  edges: FlowEdge[]
  cycles: Map<string, Cycle>
}

/**
 * Layout options for flow diagram
 */
export interface LayoutOptions {
  nodeWidth?: number
  nodeHeight?: number
  horizontalSpacing?: number
  verticalSpacing?: number
  cycleGap?: number
  cyclePadding?: number
  viewportWidth?: number
  viewportHeight?: number
  centerX?: number
}

/**
 * Agent execution tracking data
 */
export interface AgentExecution {
  taskId: string
  startTime: string
  startEvent: WorkflowEvent
  endTime: string | null
  endEvent: WorkflowEvent | null
  status: NodeStatus
  isActive: boolean
}

/**
 * Node style configuration
 */
export interface NodeStyleConfig {
  background: string
  borderColor: string
  textColor: string
}
