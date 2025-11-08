import type { FlowNode, FlowEdge, Cycle, LayoutOptions } from '@/types/flow'

/**
 * Applies custom vertical layout algorithm to flow nodes
 * - Centers all nodes vertically on a timeline
 * - Groups review cycles into expandable/collapsible bounding boxes
 * - Shows each iteration of a cycle horizontally within the box
 */
export function applyCycleLayout(
  nodes: FlowNode[],
  edges: FlowEdge[],
  cycles: Map<string, Cycle>,
  options: LayoutOptions = {}
): { nodes: FlowNode[]; cycleNodes: FlowNode[]; edges: FlowEdge[] } {
  const {
    nodeWidth = 250,
    nodeHeight = 80,
    horizontalSpacing = 150,
    verticalSpacing = 120,
    cycleGap = 40,
    cyclePadding = 40,
    viewportWidth = 1200,
    centerX = null,
  } = options

  // Calculate center X for vertical layout
  const centerXPosition = centerX !== null ? centerX : viewportWidth / 2

  // Group nodes by cycle membership
  const nodesByCycle = new Map<string, FlowNode[]>()
  const standaloneNodes: FlowNode[] = []

  nodes.forEach((node) => {
    // Skip special nodes (created, completed)
    if (node.id === 'created' || node.id === 'completed') {
      standaloneNodes.push(node)
      return
    }

    // Check if this node is part of a cycle
    let belongsToCycle = false

    for (const [cycleId, cycleData] of cycles.entries()) {
      let inCycle = false

      // Check if this is an agent execution node
      if (node.id.startsWith('agent-')) {
        inCycle =
          cycleData.agentExecutions?.some((execution) => {
            return (
              execution.executionIndex >= 0 &&
              node.id === `agent-${execution.agent}-${execution.executionIndex}`
            )
          }) || false
      }

      // Check if this is a decision node
      else if (node.id.startsWith('decision-') && node.data.timestamp) {
        const nodeTime = new Date(node.data.timestamp).getTime()
        const cycleStart = new Date(cycleData.startTime).getTime()
        const cycleEnd = cycleData.endTime
          ? new Date(cycleData.endTime).getTime()
          : Date.now()
        inCycle = nodeTime >= cycleStart && nodeTime <= cycleEnd
      }

      if (inCycle) {
        if (!nodesByCycle.has(cycleId)) {
          nodesByCycle.set(cycleId, [])
        }
        nodesByCycle.get(cycleId)!.push(node)
        belongsToCycle = true
        break
      }
    }

    if (!belongsToCycle) {
      standaloneNodes.push(node)
    }
  })

  // Build vertical layout for root-level elements
  const layoutItems: Array<{
    type: 'standalone' | 'cycle'
    node?: FlowNode
    cycleId?: string
    cycleData?: Cycle
    cycleX?: number
    cycleY?: number
    cycleWidth?: number
    cycleHeight?: number
    childNodes?: Array<{
      node: FlowNode
      cycleId: string
      relativeX: number
      relativeY: number
    }>
    y: number
  }> = []

  let currentY = 100 // Starting Y position

  // Sort standalone nodes by their original position/order
  const sortedStandalone = [...standaloneNodes].sort((a, b) => {
    const getSequence = (id: string) => {
      const match = id.match(/-(\d+)$/)
      return match ? parseInt(match[1]) : 0
    }
    return getSequence(a.id) - getSequence(b.id)
  })

  // Add 'created' node
  const createdNode = nodes.find((n) => n.id === 'created')
  if (createdNode) {
    layoutItems.push({
      type: 'standalone',
      node: createdNode,
      y: currentY,
    })
    currentY += verticalSpacing
  }

  // Add other standalone nodes
  sortedStandalone
    .filter((n) => n.id !== 'created' && n.id !== 'completed')
    .forEach((node) => {
      layoutItems.push({
        type: 'standalone',
        node,
        y: currentY,
      })
      currentY += verticalSpacing
    })

  // Add cycles with their internal horizontal layout
  const cycleNodes: FlowNode[] = []

  for (const [cycleId, cycleData] of cycles.entries()) {
    const cycleNodeList = nodesByCycle.get(cycleId) || []

    if (cycleNodeList.length === 0) continue

    // Sort cycle nodes by timestamp (chronologically)
    cycleNodeList.sort((a, b) => {
      const getTimestamp = (node: FlowNode) => {
        if (node.data.timestamp) {
          return new Date(node.data.timestamp).getTime()
        }
        // Agent nodes: try to find matching execution in cycleData
        if (node.id.startsWith('agent-')) {
          const match = node.id.match(/^agent-(.+)-(\d+)$/)
          if (match) {
            const [, agent, executionIndex] = match
            const execution = cycleData.agentExecutions?.find(
              (e) => e.agent === agent && e.executionIndex === parseInt(executionIndex)
            )
            if (execution) {
              return new Date(execution.timestamp).getTime()
            }
          }
        }
        return 0
      }
      return getTimestamp(a) - getTimestamp(b)
    })

    // Calculate cycle dimensions
    const cycleWidth =
      cycleNodeList.length * (nodeWidth + horizontalSpacing) -
      horizontalSpacing +
      cyclePadding * 2
    const cycleHeight = nodeHeight + cyclePadding * 2

    // Position cycle centered horizontally
    const cycleX = centerXPosition - cycleWidth / 2
    const cycleY = currentY

    // Layout nodes within the cycle horizontally (left to right)
    const cycleChildNodes = cycleNodeList.map((node, index) => {
      const relativeX = cyclePadding + index * (nodeWidth + horizontalSpacing)
      const relativeY = cyclePadding

      return {
        node,
        cycleId,
        relativeX,
        relativeY,
      }
    })

    layoutItems.push({
      type: 'cycle',
      cycleId,
      cycleData,
      cycleX,
      cycleY,
      cycleWidth,
      cycleHeight,
      childNodes: cycleChildNodes,
      y: currentY,
    })

    // Get cycle type label
    const typeLabels: Record<string, string> = {
      review: 'Review Cycle',
      repair: 'Repair Cycle',
      conversation: 'Conversational Loop',
      unknown: 'Cycle',
    }
    const cycleLabel = typeLabels[cycleData.type] || 'Cycle'

    // Create cycle bounding node (parent node)
    const cycleNode: FlowNode = {
      id: cycleId,
      type: 'cycle',
      position: {
        x: cycleX,
        y: cycleY,
      },
      data: {
        cycleId,
        cycleType: cycleData.type,
        label: cycleLabel,
        iterationCount: cycleNodeList.length,
        isCollapsed: cycleData.isCollapsed || false,
        width: cycleWidth,
        height: cycleHeight,
        cyclePadding,
        startTime: cycleData.startTime,
        endTime: cycleData.endTime,
        events: cycleData.events,
      },
      style: {
        width: cycleWidth,
        height: cycleHeight,
        zIndex: -1, // Behind other nodes
      },
      draggable: false,
    }

    cycleNodes.push(cycleNode)

    // Move Y position down for next element
    currentY += cycleHeight + cycleGap + verticalSpacing
  }

  // Add 'completed' node
  const completedNode = nodes.find((n) => n.id === 'completed')
  if (completedNode) {
    layoutItems.push({
      type: 'standalone',
      node: completedNode,
      y: currentY,
    })
  }

  // Apply positions to all nodes
  const layoutedNodes: FlowNode[] = []

  layoutItems.forEach((item) => {
    if (item.type === 'standalone' && item.node) {
      // Standalone nodes: center horizontally
      layoutedNodes.push({
        ...item.node,
        position: {
          x: centerXPosition - nodeWidth / 2,
          y: item.y,
        },
      })
    } else if (item.type === 'cycle' && item.childNodes) {
      // Cycle child nodes: position relative to parent
      item.childNodes.forEach(({ node, cycleId, relativeX, relativeY }) => {
        layoutedNodes.push({
          ...node,
          position: {
            x: relativeX,
            y: relativeY,
          },
          parentId: cycleId,
          style: {
            ...node.style,
            zIndex: 10,
          },
        } as FlowNode)
      })
    }
  })

  // Parent nodes must come before child nodes
  const parentNodes = [...cycleNodes, ...layoutedNodes.filter((n) => !('parentId' in n))]
  const childNodes = layoutedNodes.filter((n) => 'parentId' in n)

  return {
    nodes: [...parentNodes, ...childNodes],
    cycleNodes,
    edges,
  }
}

/**
 * Updates edges to connect to cycle bounding nodes when collapsed
 */
export function updateEdgesForCycles(
  edges: FlowEdge[],
  cycles: Map<string, Cycle>
): FlowEdge[] {
  const updatedEdges: FlowEdge[] = []

  edges.forEach((edge) => {
    let newEdge = { ...edge }

    // Check if source or target is in a collapsed cycle
    for (const [cycleId, cycleData] of cycles.entries()) {
      if (cycleData.isCollapsed) {
        // Check if source is in cycle
        const sourceInCycle = cycleData.agentExecutions?.some((exec) =>
          edge.source.startsWith(`agent-${exec.agent}`)
        )

        if (sourceInCycle) {
          newEdge = {
            ...newEdge,
            source: cycleId,
          }
        }

        // Check if target is in cycle
        const targetInCycle = cycleData.agentExecutions?.some((exec) =>
          edge.target.startsWith(`agent-${exec.agent}`)
        )

        if (targetInCycle) {
          newEdge = {
            ...newEdge,
            target: cycleId,
          }
        }
      }
    }

    updatedEdges.push(newEdge)
  })

  // Remove duplicate edges
  const edgeKeys = new Set<string>()
  return updatedEdges.filter((edge) => {
    const key = `${edge.source}->${edge.target}`
    if (edgeKeys.has(key)) {
      return false
    }
    edgeKeys.add(key)
    return true
  })
}
