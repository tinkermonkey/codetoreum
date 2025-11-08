/**
 * WorkflowHeader Component
 *
 * Displays workflow run metadata and status.
 */

import React from 'react';
import { WorkflowRun } from '../../types/workflow-run';
import { format } from 'date-fns';
import { Clock, User, Hash, GitBranch, Calendar } from 'lucide-react';
import { cn } from '../../lib/utils';

interface WorkflowHeaderProps {
  workflowRun: WorkflowRun;
}

export function WorkflowHeader({ workflowRun }: WorkflowHeaderProps) {
  const statusConfig = {
    pending: {
      color: 'bg-gray-100 text-gray-700 dark:bg-gray-800 dark:text-gray-300',
      label: 'Pending',
    },
    running: {
      color: 'bg-blue-100 text-blue-700 dark:bg-blue-900 dark:text-blue-300',
      label: 'Running',
    },
    paused: {
      color: 'bg-yellow-100 text-yellow-700 dark:bg-yellow-900 dark:text-yellow-300',
      label: 'Paused',
    },
    completed: {
      color: 'bg-green-100 text-green-700 dark:bg-green-900 dark:text-green-300',
      label: 'Completed',
    },
    failed: {
      color: 'bg-red-100 text-red-700 dark:bg-red-900 dark:text-red-300',
      label: 'Failed',
    },
    cancelled: {
      color: 'bg-gray-100 text-gray-700 dark:bg-gray-800 dark:text-gray-300',
      label: 'Cancelled',
    },
  }[workflowRun.status];

  return (
    <div className="border-b border-gray-200 dark:border-gray-700 pb-6">
      {/* Status badge */}
      <div className="flex items-center gap-3 mb-4">
        <span
          className={cn(
            'px-3 py-1 rounded-full text-sm font-medium',
            statusConfig.color
          )}
        >
          {statusConfig.label}
        </span>
        <span className="text-sm text-gray-500 dark:text-gray-400">
          Stage {workflowRun.currentStageIndex + 1}: {workflowRun.currentStageName}
        </span>
      </div>

      {/* Issue title */}
      <h1 className="text-2xl font-bold mb-4">{workflowRun.issueTitle}</h1>

      {/* Metadata grid */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4 text-sm">
        <div className="flex items-center gap-2 text-gray-600 dark:text-gray-400">
          <Hash className="w-4 h-4" />
          <span>Issue #{workflowRun.issueNumber}</span>
        </div>

        <div className="flex items-center gap-2 text-gray-600 dark:text-gray-400">
          <GitBranch className="w-4 h-4" />
          <span>{workflowRun.project}</span>
        </div>

        <div className="flex items-center gap-2 text-gray-600 dark:text-gray-400">
          <User className="w-4 h-4" />
          <span>{workflowRun.triggeredBy}</span>
        </div>

        {workflowRun.startedAt && (
          <div className="flex items-center gap-2 text-gray-600 dark:text-gray-400">
            <Calendar className="w-4 h-4" />
            <span>{format(new Date(workflowRun.startedAt), 'MMM d, yyyy HH:mm')}</span>
          </div>
        )}

        {workflowRun.duration !== null && (
          <div className="flex items-center gap-2 text-gray-600 dark:text-gray-400">
            <Clock className="w-4 h-4" />
            <span>{formatDuration(workflowRun.duration)}</span>
          </div>
        )}
      </div>
    </div>
  );
}

function formatDuration(seconds: number): string {
  const hours = Math.floor(seconds / 3600);
  const minutes = Math.floor((seconds % 3600) / 60);
  const secs = Math.floor(seconds % 60);

  if (hours > 0) {
    return `${hours}h ${minutes}m ${secs}s`;
  }
  if (minutes > 0) {
    return `${minutes}m ${secs}s`;
  }
  return `${secs}s`;
}
