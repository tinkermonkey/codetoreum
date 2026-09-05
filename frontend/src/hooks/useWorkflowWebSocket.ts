/**
 * WebSocket integration for Workflow Run real-time updates
 *
 * Listens to workflow-related WebSocket events and invalidates React Query caches
 * to ensure the UI stays up-to-date with backend changes.
 */

import { useEffect } from 'react';
import { useQueryClient } from '@tanstack/react-query';

import { useWebSocket } from './useWebSocket';

interface WorkflowWebSocketData {
  workflowRunId?: string;
  workflowId?: string;
  status?: string;
  eventType?: string;
}

interface WorkflowWebSocketMessage {
  type: string;
  data: WorkflowWebSocketData;
}

interface UseWorkflowWebSocketReturn {
  isConnected: boolean;
}

/**
 * Hook to manage WebSocket subscriptions for workflow runs
 * and automatically invalidate relevant queries on events.
 */
export function useWorkflowWebSocket(
  isAuthenticated: boolean,
  isAuthLoading: boolean
): UseWorkflowWebSocketReturn {
  const queryClient = useQueryClient();
  const { isConnected, events, subscribe, unsubscribe } = useWebSocket(
    isAuthenticated,
    isAuthLoading
  );

  // Subscribe to workflow-related events
  useEffect(() => {
    if (!isConnected) {
      return undefined;
    }

    // Subscribe to workflow execution events
    const eventTypes = [
      'workflow.started',
      'workflow.completed',
      'workflow.failed',
      'workflow.cancelled',
      'workflow.stage_advanced',
      'execution.started',
      'execution.completed',
      'execution.failed',
      'execution.cancelled',
      'review.started',
      'review.completed',
      'review.rejected',
    ];

    eventTypes.forEach((eventType) => subscribe(eventType));

    // Cleanup function to unsubscribe from all event types
    return () => {
      eventTypes.forEach((eventType) => unsubscribe(eventType));
    };
  }, [isConnected, subscribe, unsubscribe]);

  // Process incoming events and invalidate queries
  useEffect(() => {
    if (events.length === 0) {
      return;
    }

    // Get the latest event
    const latestEvent = events[0];
    const message = latestEvent.data as WorkflowWebSocketMessage;

    // Invalidate workflow runs queries on any workflow event
    if (
      latestEvent.type.startsWith('workflow.') ||
      latestEvent.type.startsWith('execution.') ||
      latestEvent.type.startsWith('review.')
    ) {
      // Invalidate the workflow runs list
      queryClient.invalidateQueries({ queryKey: ['workflow-runs'] });

      // If we have a specific workflow run ID, invalidate its details and events
      if (message.data?.workflowRunId) {
        queryClient.invalidateQueries({
          queryKey: ['workflow-runs', message.data.workflowRunId],
        });
        queryClient.invalidateQueries({
          queryKey: ['workflow-events', message.data.workflowRunId],
        });
      }
    }
  }, [events, queryClient]);

  return {
    isConnected,
  };
}
