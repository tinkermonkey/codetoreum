import type { WorkflowEvent } from '@/types/workflow-event'
import type { Cycle, CycleType, AgentExecution } from '@/types/flow'

/**
 * Detects strongly connected components (cycles) in the event graph
 * using Tarjan's algorithm
 */
export function detectCycles(events: WorkflowEvent[]): Cycle[] {
  const cycles: Cycle[] = []

  // Sort events chronologically
  const sortedEvents = [...events].sort(
    (a, b) => new Date(a.timestamp).getTime() - new Date(b.timestamp).getTime()
  )

  // Track open cycles by type
  const openCycles: Record<string, Cycle | null> = {
    review_cycle: null,
    repair_cycle: null,
    conversational_loop: null,
  }

  // Filter to decision events for cycle boundary detection
  const decisionEvents = sortedEvents.filter(
    (e) => e.event_category === 'decision'
  )

  decisionEvents.forEach((event) => {
    const eventType = event.event_type

    // Review cycles
    if (eventType === 'review_cycle_started') {
      const cycleId = `review_cycle_${cycles.length + 1}`
      openCycles.review_cycle = {
        id: cycleId,
        type: 'review',
        events: [],
        entryPoint: event.event_id || '',
        exitPoint: '',
        startTime: event.timestamp,
        endTime: undefined,
        iterations: 0,
        isCollapsed: false,
        agentExecutions: [],
        decisionEvents: [],
      }
    } else if (eventType === 'review_cycle_completed' && openCycles.review_cycle) {
      openCycles.review_cycle.endTime = event.timestamp
      openCycles.review_cycle.exitPoint = event.event_id || ''
      cycles.push(openCycles.review_cycle)
      openCycles.review_cycle = null
    }

    // Repair cycles
    else if (
      eventType === 'repair_cycle_test_cycle_started' ||
      eventType === 'repair_cycle_fix_cycle_started'
    ) {
      const cycleId = `repair_cycle_${cycles.length + 1}`
      openCycles.repair_cycle = {
        id: cycleId,
        type: 'repair',
        events: [],
        entryPoint: event.event_id || '',
        exitPoint: '',
        startTime: event.timestamp,
        endTime: undefined,
        iterations: 0,
        isCollapsed: false,
        agentExecutions: [],
        decisionEvents: [],
      }
    } else if (
      (eventType === 'repair_cycle_test_cycle_completed' ||
        eventType === 'repair_cycle_fix_cycle_completed') &&
      openCycles.repair_cycle
    ) {
      openCycles.repair_cycle.endTime = event.timestamp
      openCycles.repair_cycle.exitPoint = event.event_id || ''
      cycles.push(openCycles.repair_cycle)
      openCycles.repair_cycle = null
    }

    // Conversational loops
    else if (eventType === 'conversational_loop_started') {
      const cycleId = `conv_loop_${cycles.length + 1}`
      openCycles.conversational_loop = {
        id: cycleId,
        type: 'conversation',
        events: [],
        entryPoint: event.event_id || '',
        exitPoint: '',
        startTime: event.timestamp,
        endTime: undefined,
        iterations: 0,
        isCollapsed: false,
        agentExecutions: [],
        decisionEvents: [],
      }
    } else if (
      eventType === 'conversational_loop_completed' &&
      openCycles.conversational_loop
    ) {
      openCycles.conversational_loop.endTime = event.timestamp
      openCycles.conversational_loop.exitPoint = event.event_id || ''
      cycles.push(openCycles.conversational_loop)
      openCycles.conversational_loop = null
    }
  })

  // Close any remaining open cycles (still in progress)
  Object.values(openCycles).forEach((openCycle) => {
    if (openCycle) {
      openCycle.endTime = sortedEvents[sortedEvents.length - 1]?.timestamp
      cycles.push(openCycle)
    }
  })

  return cycles
}

/**
 * Groups agent executions into detected cycles based on time boundaries
 */
export function groupExecutionsIntoCycles(
  cycles: Cycle[],
  agentExecutions: Map<string, AgentExecution[]>
): Map<string, Cycle> {
  const cycleMap = new Map<string, Cycle>()

  cycles.forEach((cycle) => {
    const cycleStart = new Date(cycle.startTime).getTime()
    const cycleEnd = cycle.endTime
      ? new Date(cycle.endTime).getTime()
      : Date.now()

    // Find all agent executions within this cycle's time range
    const executionsInCycle: Array<{
      agent: string
      taskId: string
      executionIndex: number
      timestamp: string
    }> = []

    let executionIndex = 0
    agentExecutions.forEach((executions, agent) => {
      executions.forEach((execution) => {
        const execStart = new Date(execution.startTime).getTime()

        if (execStart >= cycleStart && execStart <= cycleEnd) {
          executionsInCycle.push({
            agent,
            taskId: execution.taskId,
            executionIndex: executionIndex++,
            timestamp: execution.startTime,
          })
        }
      })
    })

    // Only include cycles that have agent executions
    if (executionsInCycle.length > 0) {
      cycleMap.set(cycle.id, {
        ...cycle,
        agentExecutions: executionsInCycle,
        iterations: executionsInCycle.length,
        isCollapsed: false,
      })
    }
  })

  return cycleMap
}

/**
 * Identifies cycles from agent executions (simple detection)
 * Falls back to this when boundary detection doesn't find cycles
 */
export function identifyCyclesSimple(
  agentExecutions: Map<string, AgentExecution[]>
): Map<string, Cycle> {
  const cycles = new Map<string, Cycle>()

  agentExecutions.forEach((executions, agent) => {
    if (executions.length > 1) {
      const cycleId = `${agent}_cycle`
      cycles.set(cycleId, {
        id: cycleId,
        type: 'unknown',
        events: [],
        entryPoint: '',
        exitPoint: '',
        startTime: executions[0].startTime,
        endTime: executions[executions.length - 1].endTime || undefined,
        iterations: executions.length,
        isCollapsed: false,
        agentExecutions: executions.map((exec, index) => ({
          agent,
          taskId: exec.taskId,
          executionIndex: index,
          timestamp: exec.startTime,
        })),
      })
    }
  })

  return cycles
}

/**
 * Main cycle identification function - optimized single-pass algorithm
 * Combines decision event boundary detection with agent execution grouping in one pass
 */
export function identifyCycles(
  events: WorkflowEvent[],
  agentExecutions: Map<string, AgentExecution[]>
): Map<string, Cycle> {
  const cycleMap = new Map<string, Cycle>()

  // Sort events chronologically
  const sortedEvents = [...events].sort(
    (a, b) => new Date(a.timestamp).getTime() - new Date(b.timestamp).getTime()
  )

  // Track open cycles by type
  const openCycles: Record<string, {
    cycle: Cycle
    startTime: number
  } | null> = {
    review_cycle: null,
    repair_cycle: null,
    conversational_loop: null,
  }

  // Single pass through events
  sortedEvents.forEach((event) => {
    const eventCategory = event.event_category || ''
    if (eventCategory !== 'decision') return

    const eventType = event.event_type || ''
    const eventTimestamp = new Date(event.timestamp).getTime()

    // Review cycles
    if (eventType === 'ReviewCycleStarted' || eventType === 'review_cycle_started') {
      const cycleId = `review_cycle_${cycleMap.size + 1}`
      openCycles.review_cycle = {
        cycle: {
          id: cycleId,
          type: 'review',
          events: [],
          entryPoint: event.event_id || '',
          exitPoint: '',
          startTime: event.timestamp,
          endTime: undefined,
          iterations: 0,
          isCollapsed: false,
          agentExecutions: [],
          decisionEvents: [],
        },
        startTime: eventTimestamp,
      }
    } else if ((eventType === 'ReviewCycleCompleted' || eventType === 'review_cycle_completed') && openCycles.review_cycle) {
      const { cycle, startTime } = openCycles.review_cycle
      cycle.endTime = event.timestamp
      cycle.exitPoint = event.event_id || ''

      // Collect agent executions in one iteration
      const cycleExecutions: Array<{
        agent: string
        taskId: string
        executionIndex: number
        timestamp: string
      }> = []

      agentExecutions.forEach((executions, agent) => {
        executions.forEach((execution, index) => {
          const execTime = new Date(execution.startTime).getTime()
          if (execTime >= startTime && execTime <= eventTimestamp) {
            cycleExecutions.push({
              agent,
              taskId: execution.taskId,
              executionIndex: index,
              timestamp: execution.startTime,
            })
          }
        })
      })

      cycle.agentExecutions = cycleExecutions
      cycle.iterations = cycleExecutions.length
      cycleMap.set(cycle.id, cycle)
      openCycles.review_cycle = null
    }

    // Repair cycles
    else if (
      eventType === 'RepairCycleTestCycleStarted' || eventType === 'repair_cycle_test_cycle_started' ||
      eventType === 'RepairCycleFixCycleStarted' || eventType === 'repair_cycle_fix_cycle_started'
    ) {
      const cycleId = `repair_cycle_${cycleMap.size + 1}`
      openCycles.repair_cycle = {
        cycle: {
          id: cycleId,
          type: 'repair',
          events: [],
          entryPoint: event.event_id || '',
          exitPoint: '',
          startTime: event.timestamp,
          endTime: undefined,
          iterations: 0,
          isCollapsed: false,
          agentExecutions: [],
          decisionEvents: [],
        },
        startTime: eventTimestamp,
      }
    } else if (
      (eventType === 'RepairCycleTestCycleCompleted' || eventType === 'repair_cycle_test_cycle_completed' ||
        eventType === 'RepairCycleFixCycleCompleted' || eventType === 'repair_cycle_fix_cycle_completed') &&
      openCycles.repair_cycle
    ) {
      const { cycle, startTime } = openCycles.repair_cycle
      cycle.endTime = event.timestamp
      cycle.exitPoint = event.event_id || ''

      // Collect agent executions
      const cycleExecutions: Array<{
        agent: string
        taskId: string
        executionIndex: number
        timestamp: string
      }> = []

      agentExecutions.forEach((executions, agent) => {
        executions.forEach((execution, index) => {
          const execTime = new Date(execution.startTime).getTime()
          if (execTime >= startTime && execTime <= eventTimestamp) {
            cycleExecutions.push({
              agent,
              taskId: execution.taskId,
              executionIndex: index,
              timestamp: execution.startTime,
            })
          }
        })
      })

      cycle.agentExecutions = cycleExecutions
      cycle.iterations = cycleExecutions.length
      cycleMap.set(cycle.id, cycle)
      openCycles.repair_cycle = null
    }

    // Conversational loops
    else if (eventType === 'ConversationalLoopStarted' || eventType === 'conversational_loop_started') {
      const cycleId = `conv_loop_${cycleMap.size + 1}`
      openCycles.conversational_loop = {
        cycle: {
          id: cycleId,
          type: 'conversation',
          events: [],
          entryPoint: event.event_id || '',
          exitPoint: '',
          startTime: event.timestamp,
          endTime: undefined,
          iterations: 0,
          isCollapsed: false,
          agentExecutions: [],
          decisionEvents: [],
        },
        startTime: eventTimestamp,
      }
    } else if (
      (eventType === 'ConversationalLoopCompleted' || eventType === 'conversational_loop_completed') &&
      openCycles.conversational_loop
    ) {
      const { cycle, startTime } = openCycles.conversational_loop
      cycle.endTime = event.timestamp
      cycle.exitPoint = event.event_id || ''

      // Collect agent executions
      const cycleExecutions: Array<{
        agent: string
        taskId: string
        executionIndex: number
        timestamp: string
      }> = []

      agentExecutions.forEach((executions, agent) => {
        executions.forEach((execution, index) => {
          const execTime = new Date(execution.startTime).getTime()
          if (execTime >= startTime && execTime <= eventTimestamp) {
            cycleExecutions.push({
              agent,
              taskId: execution.taskId,
              executionIndex: index,
              timestamp: execution.startTime,
            })
          }
        })
      })

      cycle.agentExecutions = cycleExecutions
      cycle.iterations = cycleExecutions.length
      cycleMap.set(cycle.id, cycle)
      openCycles.conversational_loop = null
    }
  })

  // Close any remaining open cycles (still in progress)
  Object.values(openCycles).forEach((openCycle) => {
    if (openCycle) {
      const { cycle, startTime } = openCycle
      const now = Date.now()
      cycle.endTime = sortedEvents[sortedEvents.length - 1]?.timestamp

      // Collect agent executions for incomplete cycles
      const cycleExecutions: Array<{
        agent: string
        taskId: string
        executionIndex: number
        timestamp: string
      }> = []

      agentExecutions.forEach((executions, agent) => {
        executions.forEach((execution, index) => {
          const execTime = new Date(execution.startTime).getTime()
          if (execTime >= startTime && execTime <= now) {
            cycleExecutions.push({
              agent,
              taskId: execution.taskId,
              executionIndex: index,
              timestamp: execution.startTime,
            })
          }
        })
      })

      cycle.agentExecutions = cycleExecutions
      cycle.iterations = cycleExecutions.length
      cycleMap.set(cycle.id, cycle)
    }
  })

  // Fallback: If no cycles detected, use simple agent repeat counting
  if (cycleMap.size === 0) {
    return identifyCyclesSimple(agentExecutions)
  }

  return cycleMap
}

/**
 * Toggles the collapsed state of a cycle
 */
export function toggleCycleCollapsed(
  cycles: Map<string, Cycle>,
  cycleId: string
): Map<string, Cycle> {
  const updatedCycles = new Map(cycles)
  const cycleData = updatedCycles.get(cycleId)

  if (cycleData) {
    updatedCycles.set(cycleId, {
      ...cycleData,
      isCollapsed: !cycleData.isCollapsed,
    })
  }

  return updatedCycles
}
