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
  const executions = await apiClient.get<Execution[]>('/executions', {
    params: {
      status: 'running',
      limit: 50,
    },
  })
  return executions.map(convertExecution)
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
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      const data: any = event.data || {}

      if (event.type === 'ExecutionStarted' && data.execution) {
        // Add new execution to store
        const execution = convertExecution(data.execution)
        updateAgentExecution(execution)
      } else if (event.type === 'ExecutionCompleted' && data.execution_id) {
        // Remove completed execution from store
        removeAgentExecution(data.execution_id)
      } else if (event.type === 'ExecutionFailed' && data.execution_id) {
        // Remove failed execution from store
        removeAgentExecution(data.execution_id)
      }
    })
  }, [events, updateAgentExecution, removeAgentExecution])

  return query
}
