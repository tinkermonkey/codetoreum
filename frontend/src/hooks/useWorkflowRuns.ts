/**
 * React Query hooks for fetching workflow runs
 */

import { useQuery, UseQueryOptions } from '@tanstack/react-query';
import { WorkflowRun, WorkflowRunsResponse, WorkflowRunFilters } from '../types/workflow-run';
import { apiClient } from '../api/client';

/**
 * Fetch active workflow runs (currently running)
 */
export function useActiveWorkflowRuns(
  filters?: Omit<WorkflowRunFilters, 'status'>,
  options?: UseQueryOptions<WorkflowRun[], Error>
) {
  return useQuery<WorkflowRun[], Error>({
    queryKey: ['workflow-runs', 'active', filters],
    queryFn: async () => {
      const params = new URLSearchParams({
        status: 'running',
        ...(filters?.projectId && { projectId: filters.projectId }),
        ...(filters?.search && { search: filters.search }),
      });

      const response = await apiClient.get<WorkflowRunsResponse>(
        `/workflows/runs?${params.toString()}`
      );
      return response.runs;
    },
    refetchInterval: 10000, // Refresh every 10 seconds
    ...options,
  });
}

/**
 * Fetch completed workflow runs (paginated)
 */
export function useCompletedWorkflowRuns(
  filters?: WorkflowRunFilters,
  options?: UseQueryOptions<WorkflowRunsResponse, Error>
) {
  const offset = filters?.offset ?? 0;
  const limit = filters?.limit ?? 10;

  return useQuery<WorkflowRunsResponse, Error>({
    queryKey: ['workflow-runs', 'completed', offset, limit, filters],
    queryFn: async () => {
      const params = new URLSearchParams({
        status: 'completed,failed,cancelled',
        offset: offset.toString(),
        limit: limit.toString(),
        ...(filters?.projectId && { projectId: filters.projectId }),
        ...(filters?.search && { search: filters.search }),
      });

      const response = await apiClient.get<WorkflowRunsResponse>(
        `/workflows/runs?${params.toString()}`
      );
      return response;
    },
    ...options,
  });
}

/**
 * Fetch a single workflow run by ID
 */
export function useWorkflowRun(
  workflowRunId: string | null,
  options?: UseQueryOptions<WorkflowRun, Error>
) {
  return useQuery<WorkflowRun, Error>({
    queryKey: ['workflow-runs', workflowRunId],
    queryFn: async () => {
      if (!workflowRunId) {
        throw new Error('Workflow run ID is required');
      }
      const response = await apiClient.get<WorkflowRun>(
        `/workflows/runs/${workflowRunId}`
      );
      return response;
    },
    enabled: !!workflowRunId,
    ...options,
  });
}
