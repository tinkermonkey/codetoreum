/**
 * WorkflowRunCard Component
 *
 * Displays a single workflow run in the sidebar list.
 */

import React from 'react';
import { WorkflowRun } from '../../types/workflow-run';
import { formatDistanceToNow } from 'date-fns';
import { Clock, GitBranch, Hash } from 'lucide-react';
import { cn } from '../../lib/utils';

interface WorkflowRunCardProps {
  run: WorkflowRun;
  isSelected: boolean;
  onClick: () => void;
}

export function WorkflowRunCard({ run, isSelected, onClick }: WorkflowRunCardProps) {
  const statusColor = {
    pending: 'bg-gray-500',
    running: 'bg-blue-500',
    paused: 'bg-yellow-500',
    completed: 'bg-green-500',
    failed: 'bg-red-500',
    cancelled: 'bg-gray-600',
  }[run.status];

  const statusText = run.status.charAt(0).toUpperCase() + run.status.slice(1);

  const timeAgo = run.startedAt
    ? formatDistanceToNow(new Date(run.startedAt), { addSuffix: true })
    : 'Not started';

  return (
    <button
      onClick={onClick}
      className={cn(
        'w-full text-left p-4 rounded-lg border transition-all',
        'hover:bg-gray-50 dark:hover:bg-gray-800',
        isSelected
          ? 'border-blue-500 bg-blue-50 dark:bg-blue-900/20'
          : 'border-gray-200 dark:border-gray-700'
      )}
    >
      <div className="flex items-start justify-between mb-2">
        <div className="flex items-center gap-2 min-w-0 flex-1">
          <div className={cn('w-2 h-2 rounded-full flex-shrink-0', statusColor)} />
          <span className="text-xs font-medium text-gray-600 dark:text-gray-400 truncate">
            {statusText}
          </span>
        </div>
        <span className="text-xs text-gray-500 dark:text-gray-500 flex-shrink-0 ml-2">
          {timeAgo}
        </span>
      </div>

      <h3 className="text-sm font-semibold mb-2 line-clamp-2">
        {run.issueTitle}
      </h3>

      <div className="flex items-center gap-3 text-xs text-gray-600 dark:text-gray-400">
        <div className="flex items-center gap-1">
          <Hash className="w-3 h-3" />
          <span>{run.issueNumber}</span>
        </div>
        <div className="flex items-center gap-1">
          <GitBranch className="w-3 h-3" />
          <span className="truncate">{run.currentStageName}</span>
        </div>
      </div>

      {run.duration !== null && (
        <div className="flex items-center gap-1 text-xs text-gray-500 dark:text-gray-500 mt-2">
          <Clock className="w-3 h-3" />
          <span>{formatDuration(run.duration)}</span>
        </div>
      )}
    </button>
  );
}

function formatDuration(seconds: number): string {
  const hours = Math.floor(seconds / 3600);
  const minutes = Math.floor((seconds % 3600) / 60);
  const secs = Math.floor(seconds % 60);

  if (hours > 0) {
    return `${hours}h ${minutes}m`;
  }
  if (minutes > 0) {
    return `${minutes}m ${secs}s`;
  }
  return `${secs}s`;
}
