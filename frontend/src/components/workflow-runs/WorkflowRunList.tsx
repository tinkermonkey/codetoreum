/**
 * WorkflowRunList Component
 *
 * Displays a list of workflow runs with loading and empty states.
 */

import React from 'react';
import { Inbox } from 'lucide-react';

import { WorkflowRun } from '../../types/workflow-run';
import { WorkflowRunCard, WorkflowRunCardSkeleton } from './WorkflowRunCard';

interface WorkflowRunListProps {
  runs: WorkflowRun[];
  selectedRunId: string | null;
  onSelectRun: (id: string) => void;
  isLoading?: boolean;
  emptyMessage?: string;
}

export function WorkflowRunList({
  runs,
  selectedRunId,
  onSelectRun,
  isLoading = false,
  emptyMessage = 'No workflow runs found',
}: WorkflowRunListProps): React.ReactElement {
  if (isLoading) {
    return (
      <div className="space-y-2">
        {Array.from({ length: 3 }).map((_, i) => (
          <WorkflowRunCardSkeleton key={i} />
        ))}
      </div>
    );
  }

  if (runs.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center py-12 px-4 text-center">
        <Inbox className="w-12 h-12 text-gray-300 dark:text-gray-600 mb-3" />
        <p className="text-sm text-gray-500 dark:text-gray-400">{emptyMessage}</p>
      </div>
    );
  }

  return (
    <div className="space-y-2">
      {runs.map((run) => (
        <WorkflowRunCard
          key={run.id}
          run={run}
          isSelected={run.id === selectedRunId}
          onClick={() => onSelectRun(run.id)}
        />
      ))}
    </div>
  );
}
