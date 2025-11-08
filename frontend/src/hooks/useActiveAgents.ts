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
 * Hook for managing active agent executions
 *
 * Features:
 * - Polls API every 10 seconds
 * - Subscribes to real-time WebSocket events
 * - Automatically updates Zustand store
 *
 * @returns Query result with active agents data
 */
export function useActiveAgents() {
  const { isAuthenticated, isLoading: isAuthLoading } = useAuth()
  const updateActiveAgents = useSystemStatusStore((state) => state.updateActiveAgents)

  // Poll API for active agents
  const query = useQuery({
    queryKey: activeAgentsQueryKey,
    queryFn: fetchActiveAgents,
    enabled: isAuthenticated && !isAuthLoading,
    refetchInterval: 10000, // Poll every 10 seconds
    staleTime: 8000,
    retry: 2,
  })

  // Subscribe to WebSocket events for real-time updates
  const { events } = useWebSocket(isAuthenticated, isAuthLoading)

  // Update store when query data changes
  useEffect(() => {
    if (query.data) {
      updateActiveAgents(query.data)
    }
  }, [query.data, updateActiveAgents])

  // Handle WebSocket events
  useEffect(() => {
    const relevantEvents = events.filter((event) =>
      ['ExecutionStarted', 'ExecutionCompleted', 'ExecutionFailed'].includes(event.type)
    )

    if (relevantEvents.length > 0) {
      // Refetch data when execution events occur
      query.refetch()
    }
  }, [events, query])

  return query
}
