/**
 * Aggregate hook combining workflow run details and events
 */

import { useWorkflowRun } from './useWorkflowRuns';
import { useWorkflowEvents } from './useWorkflowEvents';

export function useWorkflowRunDetails(workflowRunId: string | null) {
  const {
    data: workflowRun,
    isLoading: isLoadingRun,
    error: runError,
  } = useWorkflowRun(workflowRunId);

  const {
    data: events,
    isLoading: isLoadingEvents,
    error: eventsError,
  } = useWorkflowEvents(workflowRunId);

  return {
    workflowRun,
    events,
    isLoading: isLoadingRun || isLoadingEvents,
    error: runError || eventsError,
  };
}
