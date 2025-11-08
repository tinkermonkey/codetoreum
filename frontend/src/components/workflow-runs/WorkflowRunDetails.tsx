/**
 * WorkflowRunDetails Component
 *
 * Main panel displaying workflow run details and event timeline.
 */

import React from 'react';
import { useWorkflowRunDetails } from '../../hooks/useWorkflowRunDetails';
import { WorkflowHeader } from './WorkflowHeader';
import { EventTimeline } from './EventTimeline';
import { Loader2, Inbox } from 'lucide-react';

interface WorkflowRunDetailsProps {
  workflowRunId: string | null;
}

export function WorkflowRunDetails({ workflowRunId }: WorkflowRunDetailsProps) {
  const { workflowRun, events, isLoading, error } = useWorkflowRunDetails(workflowRunId);

  if (!workflowRunId) {
    return (
      <div className="flex flex-col items-center justify-center h-full px-4 text-center">
        <Inbox className="w-16 h-16 text-gray-300 dark:text-gray-600 mb-4" />
        <h2 className="text-lg font-semibold text-gray-700 dark:text-gray-300 mb-2">
          No workflow selected
        </h2>
        <p className="text-sm text-gray-500 dark:text-gray-400 max-w-md">
          Select a workflow run from the sidebar to view its details and event timeline
        </p>
      </div>
    );
  }

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-full">
        <Loader2 className="w-8 h-8 animate-spin text-gray-400" />
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex flex-col items-center justify-center h-full px-4 text-center">
        <div className="w-16 h-16 rounded-full bg-red-100 dark:bg-red-900/20 flex items-center justify-center mb-4">
          <span className="text-2xl">⚠️</span>
        </div>
        <h2 className="text-lg font-semibold text-gray-700 dark:text-gray-300 mb-2">
          Error loading workflow details
        </h2>
        <p className="text-sm text-gray-500 dark:text-gray-400 max-w-md">
          {error.message || 'An unexpected error occurred'}
        </p>
      </div>
    );
  }

  if (!workflowRun) {
    return (
      <div className="flex flex-col items-center justify-center h-full px-4 text-center">
        <Inbox className="w-16 h-16 text-gray-300 dark:text-gray-600 mb-4" />
        <h2 className="text-lg font-semibold text-gray-700 dark:text-gray-300 mb-2">
          Workflow not found
        </h2>
        <p className="text-sm text-gray-500 dark:text-gray-400">
          The requested workflow run could not be found
        </p>
      </div>
    );
  }

  return (
    <div className="h-full overflow-y-auto">
      <div className="max-w-4xl mx-auto p-6">
        <WorkflowHeader workflowRun={workflowRun} />

        <div className="mt-6">
          <h2 className="text-lg font-semibold mb-4">Event Timeline</h2>
          <EventTimeline events={events ?? []} isLoading={isLoading} />
        </div>
      </div>
    </div>
  );
}
