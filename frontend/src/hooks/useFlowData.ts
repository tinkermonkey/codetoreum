import { useMemo, useCallback } from 'react'
import { MarkerType } from '@xyflow/react'
import type { WorkflowEvent } from '@/types/workflow-event'
import type { FlowNode, FlowEdge, AgentExecution, FlowGraph } from '@/types/flow'
import { identifyCycles } from '@/utils/cycleDetection'
import { applyCycleLayout } from '@/utils/flowLayout'

/**
 * Transforms workflow events into React Flow nodes and edges
 */
export function useFlowData(
  events: WorkflowEvent[],
  workflowRunId?: string
): FlowGraph & { buildFlowchart: () => void } {
  // Track agent executions from events
  const agentExecutions = useMemo(() => {
    const execMap = new Map<string, AgentExecution[]>()
    const activeAgents = new Set<string>()

    // Sort events chronologically
    const sortedEvents = [...events].sort(
      (a, b) => new Date(a.timestamp).getTime() - new Date(b.timestamp).getTime()
    )

    // First pass: identify agent executions
    sortedEvents.forEach((event) => {
      if (event.event_category === 'agent_lifecycle') {
        const agent = event.agent_name || event.agent || ''
        const taskId = event.task_id || event.event_id || ''

        const eventType = event.event_type || ''

        if (eventType === 'AgentInitialized' || eventType === 'agent_initialized') {
          if (!execMap.has(agent)) {
            execMap.set(agent, [])
          }
          const isActive = !sortedEvents.some(
            (e) => {
              const eTaskId = e.task_id || e.event_id || ''
              const eType = e.event_type || ''
              return eTaskId === taskId && (eType === 'AgentCompleted' || eType === 'agent_completed' || eType === 'AgentFailed' || eType === 'agent_failed')
            }
          )

          const agentExecs = execMap.get(agent)
          if (agentExecs) {
            agentExecs.push({
              taskId,
              startTime: event.timestamp,
              startEvent: event,
              endTime: null,
              endEvent: null,
              status: 'running',
              isActive,
            })
          }
        } else if (eventType === 'AgentCompleted' || eventType === 'agent_completed' || eventType === 'AgentFailed' || eventType === 'agent_failed') {
          const executions = execMap.get(agent) || []
          const execution = executions.find((e) => e.taskId === taskId)
          if (execution) {
            execution.endTime = event.timestamp
            execution.endEvent = event
            execution.status = (eventType === 'AgentCompleted' || eventType === 'agent_completed') ? 'completed' : 'failed'
            execution.isActive = false
          }
        }
      }
    })

    return execMap
  }, [events])

  // Detect cycles
  const cycles = useMemo(() => {
    return identifyCycles(events, agentExecutions)
  }, [events, agentExecutions])

  // Build flowchart nodes and edges
  const { nodes, edges } = useMemo(() => {
    if (!events.length || !workflowRunId) {
      return { nodes: [], edges: [] }
    }

    const newNodes: FlowNode[] = []
    const newEdges: FlowEdge[] = []

    // Add pipeline created node
    newNodes.push({
      id: 'created',
      type: 'workflow-event',
      position: { x: 0, y: 0 },
      data: {
        label: 'Workflow Started',
        eventType: 'WorkflowStarted',
        isActive: false,
        metadata: {},
      },
      draggable: false,
    })

    let previousNodeId = 'created'
    const processedAgents = new Set<string>()

    // Sort events chronologically
    const sortedEvents = [...events].sort(
      (a, b) => new Date(a.timestamp).getTime() - new Date(b.timestamp).getTime()
    )

    sortedEvents.forEach((event, idx) => {
      let currentNodeId: string | null = null

      const eventCategory = event.event_category || ''
      const eventType = event.event_type || ''

      // Decision events
      if (eventCategory === 'decision') {
        const nodeId = `decision-${idx}`
        const decisionType = eventType || 'decision'
        const reason = event.reason || ''
        const decisionCategory = event.decision_category

        newNodes.push({
          id: nodeId,
          type: 'decision',
          position: { x: 0, y: 0 },
          data: {
            label: decisionType.replace(/_/g, ' ').replace(/\b\w/g, (l: string) => l.toUpperCase()),
            decisionType,
            category: decisionCategory,
            metadata: { reason },
            timestamp: event.timestamp,
          },
          draggable: false,
        })

        currentNodeId = nodeId
      }

      // Agent execution starts
      else if (eventCategory === 'agent_lifecycle' && (eventType === 'AgentInitialized' || eventType === 'agent_initialized')) {
        const agent = event.agent_name || event.agent || ''
        const taskId = event.task_id || event.event_id || ''
        const executions = agentExecutions.get(agent) || []
        const executionIndex = executions.findIndex((e) => e.taskId === taskId)

        if (executionIndex >= 0 && executionIndex < executions.length) {
          const nodeId = `agent-${agent}-${executionIndex}`
          const execution = executions[executionIndex]

          if (execution) {
            newNodes.push({
              id: nodeId,
              type: 'agent-execution',
              position: { x: 0, y: 0 },
              data: {
                label: agent.replace(/_/g, ' ').replace(/\b\w/g, (l: string) => l.toUpperCase()),
                agentName: agent,
                status: execution.status,
                isActive: execution.isActive,
                metadata: {},
                executionIndex,
                taskId,
              },
              draggable: false,
            })

            currentNodeId = nodeId
            processedAgents.add(agent)
          }
        }
      }

      // Connect to previous node
      if (currentNodeId && previousNodeId) {
        newEdges.push({
          id: `edge-${previousNodeId}-${currentNodeId}`,
          source: previousNodeId,
          target: currentNodeId,
          type: 'smoothstep',
          markerEnd: {
            type: MarkerType.ArrowClosed,
            color: '#6e7681',
          },
          style: { stroke: '#6e7681' },
        })
        previousNodeId = currentNodeId
      }
    })

    // Add workflow completed node if appropriate
    const hasCompletedEvent = events.some((e) => {
      const eType = e.event_type || ''
      return eType === 'WorkflowCompleted' || eType === 'workflow_completed'
    })
    if (hasCompletedEvent) {
      newNodes.push({
        id: 'completed',
        type: 'workflow-event',
        position: { x: 0, y: 0 },
        data: {
          label: 'Workflow Completed',
          eventType: 'WorkflowCompleted',
          isActive: false,
          metadata: {},
        },
        draggable: false,
      })

      if (previousNodeId !== 'created') {
        newEdges.push({
          id: `edge-${previousNodeId}-completed`,
          source: previousNodeId,
          target: 'completed',
          type: 'smoothstep',
          markerEnd: {
            type: MarkerType.ArrowClosed,
            color: '#6e7681',
          },
          style: { stroke: '#6e7681' },
        })
      }
    }

    // Apply layout
    const { nodes: layoutedNodes, edges: layoutedEdges } = applyCycleLayout(
      newNodes,
      newEdges,
      cycles,
      {
        nodeWidth: 250,
        nodeHeight: 80,
        horizontalSpacing: 150,
        cycleGap: 100,
        cyclePadding: 40,
        viewportWidth: 1200,
      }
    )

    return { nodes: layoutedNodes, edges: layoutedEdges }
  }, [events, workflowRunId, agentExecutions, cycles])

  const buildFlowchart = useCallback(() => {
    // This function can be used to trigger a rebuild
    // Currently handled automatically through useMemo dependencies
  }, [])

  return {
    nodes,
    edges,
    cycles,
    buildFlowchart,
  }
}
