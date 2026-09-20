/**
 * Active Agents Hook
 *
 * Manages active agent executions using WebSocket events and API queries.
 * Combines real-time updates with periodic polling for reliability.
 */

import { useQuery } from '@tanstack/react-query'
import { useEffect } from 'react'
import { useWebSocket } from './useWebSocket'
import { useAuth } from './useAuth'
import { apiClient } from '../api/client'
import { useSystemStatusStore } from '../store/systemStatusStore'
import type { AgentExecution } from '../types/system-status'
import type { Execution } from '../types'
import type { ApiError } from '../types/errors'
import { POLLING_CONFIG, RETRY_CONFIG } from '../config/polling'

/**
 * Active agents query key
 */
export const activeAgentsQueryKey = ['active-agents']

/**
 * Convert API execution to AgentExecution format
 */
function convertExecution(execution: Execution): AgentExecution {
  return {
    id: execution.id,
    agentName: execution.agent_name,
    workItemId: execution.work_item_id,
    status: execution.status === 'running' ? 'running' : execution.status === 'failed' ? 'failed' : 'completed',
    startedAt: execution.started_at || new Date().toISOString(),
    containerName: execution.container_id,
    project: execution.metadata?.project || 'unknown',
    issueNumber: execution.metadata?.issue_number,
  }
}

/**
 * Fetch active agent executions from API
 */
async function fetchActiveAgents(): Promise<AgentExecution[]> {
  // Prefer dedicated metrics endpoint; fall back to executions list.
  try {
    const response = await apiClient.get<{
      agents: Array<{
        executionId: string
        agentName: string
        workItemId: string
        project: string
        issueNumber?: number
        status: string
        startedAt: string
        containerName?: string
      }>
      count: number
    }>('/metrics/active-agents')

    return (response.agents || []).map((agent) => ({
      id: agent.executionId,
      agentName: agent.agentName,
      workItemId: agent.workItemId,
      status: agent.status === 'failed' ? 'failed' : agent.status === 'completed' ? 'completed' : 'running',
      startedAt: agent.startedAt,
      containerName: agent.containerName,
      project: agent.project || 'unknown',
      issueNumber: agent.issueNumber,
    }))
  } catch (err) {
    const apiError = err as ApiError
    console.error('[useActiveAgents] /metrics/active-agents request failed', apiError)

    // Only fall back to the /executions endpoint when the canonical route is
    // genuinely unavailable (404). Any other failure (auth, server error,
    // network) is a real problem and must surface to the caller, not be
    // masked by silently substituting a narrower data source.
    if (apiError.statusCode !== 404) {
      throw err
    }

    const response = await apiClient.get<{ executions: Execution[]; total_count: number }>('/executions', {
      params: {
        status: 'running',
        limit: 50,
      },
    })
    return response.executions.map(convertExecution)
  }
}

/**
 * Calculate retry delay with exponential backoff
 */
function calculateRetryDelay(attemptIndex: number): number {
  return Math.min(
    RETRY_CONFIG.BASE_DELAY * Math.pow(2, attemptIndex),
    30000 // Max 30 seconds
  )
}

/**
 * Hook for managing active agent executions
 *
 * Features:
 * - Configurable polling interval (default: 10 seconds)
 * - Real-time WebSocket updates for ExecutionStarted/Completed/Failed events
 * - Automatic retry with exponential backoff
 * - Automatically updates Zustand store with efficient Map-based updates
 *
 * @returns Query result with active agents data
 */
export function useActiveAgents() {
  const { isAuthenticated, isLoading: isAuthLoading } = useAuth()
  const updateActiveAgents = useSystemStatusStore((state) => state.updateActiveAgents)
  const updateAgentExecution = useSystemStatusStore((state) => state.updateAgentExecution)
  const removeAgentExecution = useSystemStatusStore((state) => state.removeAgentExecution)

  // Poll API for active agents
  const query = useQuery({
    queryKey: activeAgentsQueryKey,
    queryFn: fetchActiveAgents,
    enabled: isAuthenticated && !isAuthLoading,
    refetchInterval: POLLING_CONFIG.ACTIVE_AGENTS,
    staleTime: POLLING_CONFIG.STALE_TIME,
    retry: RETRY_CONFIG.MAX_ATTEMPTS,
    retryDelay: calculateRetryDelay,
  })

  // Subscribe to WebSocket events for real-time updates
  const { events } = useWebSocket(isAuthenticated, isAuthLoading)

  // Update store when query data changes
  useEffect(() => {
    if (query.data) {
      updateActiveAgents(query.data)
    }
  }, [query.data, updateActiveAgents])

  // Handle WebSocket events for real-time updates
  useEffect(() => {
    const relevantEvents = events.filter((event) =>
      ['ExecutionStarted', 'ExecutionCompleted', 'ExecutionFailed'].includes(event.type)
    )

    relevantEvents.forEach((event) => {
      // Event data contains the execution information
      const data = event.data as Record<string, unknown>

      if (event.type === 'ExecutionStarted' && 'execution' in data && data.execution) {
        // Add new execution to store
        const execution = convertExecution(data.execution as Execution)
        updateAgentExecution(execution)
      } else if (event.type === 'ExecutionCompleted' && 'execution_id' in data && data.execution_id) {
        // Remove completed execution from store
        removeAgentExecution(data.execution_id as string)
      } else if (event.type === 'ExecutionFailed' && 'execution_id' in data && data.execution_id) {
        // Remove failed execution from store
        removeAgentExecution(data.execution_id as string)
      }
    })
  }, [events, updateAgentExecution, removeAgentExecution])

  return query
}
