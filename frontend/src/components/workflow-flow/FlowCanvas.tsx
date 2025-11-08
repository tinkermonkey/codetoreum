import React, { useCallback } from 'react'
import {
  ReactFlow,
  Background,
  useNodesState,
  useEdgesState,
  ReactFlowProvider,
  type NodeTypes,
  type EdgeTypes,
  type NodeChange,
  type EdgeChange,
} from '@xyflow/react'
import '@xyflow/react/dist/style.css'

import { WorkflowEventNode } from './nodes/WorkflowEventNode'
import { AgentExecutionNode } from './nodes/AgentExecutionNode'
import { DecisionNode } from './nodes/DecisionNode'
import { CycleBoundingNode } from './nodes/CycleBoundingNode'
import { AnimatedEdge } from './edges/AnimatedEdge'
import { FlowControls } from './FlowControls'
import type { FlowNode, FlowEdge } from '@/types/flow'

const nodeTypes: NodeTypes = {
  'workflow-event': WorkflowEventNode,
  'agent-execution': AgentExecutionNode,
  decision: DecisionNode,
  cycle: CycleBoundingNode,
}

const edgeTypes: EdgeTypes = {
  animated: AnimatedEdge,
}

interface FlowCanvasProps {
  nodes: FlowNode[]
  edges: FlowEdge[]
  chartHeight: number
  onNodesChange?: (changes: NodeChange<FlowNode>[]) => void
  onEdgesChange?: (changes: EdgeChange<FlowEdge>[]) => void
}

function FlowCanvasInner({
  nodes: initialNodes,
  edges: initialEdges,
  chartHeight,
  onNodesChange: externalOnNodesChange,
  onEdgesChange: externalOnEdgesChange,
}: FlowCanvasProps) {
  const [nodes, setNodes, onNodesChange] = useNodesState(initialNodes)
  const [edges, setEdges, onEdgesChange] = useEdgesState(initialEdges)

  // Update nodes when initialNodes change
  React.useEffect(() => {
    setNodes(initialNodes)
  }, [initialNodes, setNodes])

  // Update edges when initialEdges change
  React.useEffect(() => {
    setEdges(initialEdges)
  }, [initialEdges, setEdges])

  const handleNodesChange = useCallback(
    (changes: NodeChange<FlowNode>[]) => {
      onNodesChange(changes)
      externalOnNodesChange?.(changes)
    },
    [onNodesChange, externalOnNodesChange]
  )

  const handleEdgesChange = useCallback(
    (changes: EdgeChange<FlowEdge>[]) => {
      onEdgesChange(changes)
      externalOnEdgesChange?.(changes)
    },
    [onEdgesChange, externalOnEdgesChange]
  )

  const handleFitView = useCallback(() => {
    // This will be handled by ReactFlow's internal fitView
  }, [])

  if (nodes.length === 0) {
    return (
      <div
        className="flex items-center justify-center bg-gray-50 rounded-md"
        style={{ height: `${chartHeight}px` }}
      >
        <p className="text-gray-500">No workflow events to display</p>
      </div>
    )
  }

  return (
    <div style={{ height: `${chartHeight}px` }} className="relative">
      <ReactFlow
        nodes={nodes}
        edges={edges}
        onNodesChange={handleNodesChange}
        onEdgesChange={handleEdgesChange}
        nodeTypes={nodeTypes}
        edgeTypes={edgeTypes}
        nodesDraggable={false}
        nodesConnectable={false}
        fitView
        fitViewOptions={{ padding: 0.1, duration: 300 }}
        minZoom={0.5}
        maxZoom={1.5}
        zoomOnScroll={false}
        panOnScroll={true}
      >
        <Background />
        <FlowControls onFitView={handleFitView} />
      </ReactFlow>
    </div>
  )
}

export function FlowCanvas(props: FlowCanvasProps) {
  return (
    <ReactFlowProvider>
      <FlowCanvasInner {...props} />
    </ReactFlowProvider>
  )
}
