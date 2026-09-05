/**
 * useWorkflowRunEvents Hook
 *
 * Provides real-time event updates for a specific workflow run via WebSocket.
 * Automatically subscribes when connected and unsubscribes on cleanup.
 *
 * Features:
 * - Subscribes to workflow-specific events (WorkflowStarted, StageStarted, etc.)
 * - Filters events by workflow_run_id server-side for efficiency
 * - Automatically handles subscription lifecycle
 * - Works with the shared WebSocket connection (singleton)
 *
 * @param workflowRunId - The workflow run ID to subscribe to (null/undefined = no subscription)
 * @param isAuthenticated - Whether the user is authenticated
 * @param isAuthLoading - Whether authentication is loading
 * @returns WebSocket connection status and workflow-specific events
 */

import { useEffect, useMemo } from 'react'
import { useWebSocketStore, WebSocketEvent } from '../store/websocketStore'

export interface UseWorkflowRunEventsReturn {
  isConnected: boolean
  events: WebSocketEvent[]
  workflowEvents: WebSocketEvent[]
}

/**
 * Hook for subscribing to workflow run events via WebSocket
 */
export function useWorkflowRunEvents(
  workflowRunId: string | null | undefined,
  isAuthenticated: boolean,
  isAuthLoading: boolean
): UseWorkflowRunEventsReturn {
  const {
    isConnected,
    events,
    connect,
    subscribeToWorkflowRun,
    unsubscribeFromWorkflowRun,
  } = useWebSocketStore()

  // Connect to WebSocket if authenticated
  useEffect(() => {
    if (isAuthLoading) {
      return
    }

    if (isAuthenticated && !isConnected) {
      connect(isAuthenticated)
    }
  }, [isAuthenticated, isAuthLoading, isConnected, connect])

  // Subscribe to workflow run when connected and workflowRunId is available
  useEffect(() => {
    if (!isConnected || !workflowRunId) {
      return undefined
    }

    // Subscribe to this workflow run
    subscribeToWorkflowRun(workflowRunId)

    // Cleanup: unsubscribe when component unmounts or workflowRunId changes
    return () => {
      unsubscribeFromWorkflowRun(workflowRunId)
    }
  }, [isConnected, workflowRunId, subscribeToWorkflowRun, unsubscribeFromWorkflowRun])

  // Filter events for this specific workflow run
  const workflowEvents = useMemo(() => {
    if (!workflowRunId) {
      return []
    }

    return events.filter((event) => {
      // Event data structure can vary, check multiple possible locations for workflow_run_id
      const data = event.data as any

      // Check top-level data
      if (data?.workflow_run_id === workflowRunId) {
        return true
      }

      // Check nested data.data (for EventMessage wrapper)
      if (data?.data?.workflow_run_id === workflowRunId) {
        return true
      }

      // Check payload (for some event structures)
      if (data?.payload?.workflow_run_id === workflowRunId) {
        return true
      }

      return false
    })
  }, [events, workflowRunId])

  return {
    isConnected,
    events: workflowEvents,
    workflowEvents,
  }
}
