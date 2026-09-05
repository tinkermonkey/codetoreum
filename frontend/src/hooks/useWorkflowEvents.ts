/**
 * React Query hooks for fetching workflow events
 */

import { useQuery, UseQueryOptions } from '@tanstack/react-query';
import { WorkflowEvent, WorkflowEventsResponse } from '../types/workflow-event';
import { apiClient } from '../api/client';

/**
 * Fetch events for a specific workflow run
 */
export function useWorkflowEvents(
  workflowRunId: string | null,
  options?: UseQueryOptions<WorkflowEvent[], Error>
) {
  return useQuery<WorkflowEvent[], Error>({
    queryKey: ['workflow-events', workflowRunId],
    queryFn: async () => {
      if (!workflowRunId) {
        throw new Error('Workflow run ID is required');
      }

      const response = await apiClient.get<WorkflowEventsResponse>(
        `/workflows/runs/${workflowRunId}/events`
      );
      return response.events;
    },
    enabled: !!workflowRunId,
    ...options,
  });
}
