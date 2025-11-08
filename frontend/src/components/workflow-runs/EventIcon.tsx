/**
 * EventIcon Component
 *
 * Maps event types to appropriate icons and colors.
 */

import React from 'react';
import {
  PlayCircle,
  CheckCircle,
  XCircle,
  AlertCircle,
  Activity,
  ArrowRight,
  Pause,
  GitBranch,
  Eye,
  Ban,
} from 'lucide-react';
import { WorkflowEventType } from '../../types/workflow-event';
import { cn } from '../../lib/utils';

interface EventIconProps {
  eventType: WorkflowEventType;
  className?: string;
}

interface EventConfig {
  icon: React.ComponentType<{ className?: string }>;
  color: string;
  bgColor: string;
}

const EVENT_CONFIGS: Record<WorkflowEventType, EventConfig> = {
  WorkflowStarted: {
    icon: PlayCircle,
    color: 'text-green-600',
    bgColor: 'bg-green-100 dark:bg-green-900/30',
  },
  WorkflowCompleted: {
    icon: CheckCircle,
    color: 'text-indigo-600',
    bgColor: 'bg-indigo-100 dark:bg-indigo-900/30',
  },
  WorkflowFailed: {
    icon: XCircle,
    color: 'text-red-600',
    bgColor: 'bg-red-100 dark:bg-red-900/30',
  },
  WorkflowCancelled: {
    icon: Ban,
    color: 'text-gray-600',
    bgColor: 'bg-gray-100 dark:bg-gray-900/30',
  },
  ExecutionStarted: {
    icon: Activity,
    color: 'text-blue-600',
    bgColor: 'bg-blue-100 dark:bg-blue-900/30',
  },
  ExecutionCompleted: {
    icon: CheckCircle,
    color: 'text-green-600',
    bgColor: 'bg-green-100 dark:bg-green-900/30',
  },
  ExecutionFailed: {
    icon: XCircle,
    color: 'text-red-600',
    bgColor: 'bg-red-100 dark:bg-red-900/30',
  },
  ExecutionCancelled: {
    icon: Ban,
    color: 'text-gray-600',
    bgColor: 'bg-gray-100 dark:bg-gray-900/30',
  },
  StageAdvanced: {
    icon: ArrowRight,
    color: 'text-purple-600',
    bgColor: 'bg-purple-100 dark:bg-purple-900/30',
  },
  ReviewStarted: {
    icon: Eye,
    color: 'text-yellow-600',
    bgColor: 'bg-yellow-100 dark:bg-yellow-900/30',
  },
  ReviewCompleted: {
    icon: CheckCircle,
    color: 'text-green-600',
    bgColor: 'bg-green-100 dark:bg-green-900/30',
  },
  ReviewRejected: {
    icon: XCircle,
    color: 'text-orange-600',
    bgColor: 'bg-orange-100 dark:bg-orange-900/30',
  },
  ErrorOccurred: {
    icon: AlertCircle,
    color: 'text-red-600',
    bgColor: 'bg-red-100 dark:bg-red-900/30',
  },
  StatusUpdate: {
    icon: GitBranch,
    color: 'text-blue-600',
    bgColor: 'bg-blue-100 dark:bg-blue-900/30',
  },
};

export function EventIcon({ eventType, className }: EventIconProps) {
  const config = EVENT_CONFIGS[eventType];
  const Icon = config.icon;

  return (
    <div className={cn('p-2 rounded-full', config.bgColor, className)}>
      <Icon className={cn('w-4 h-4', config.color)} />
    </div>
  );
}

export function getEventLabel(eventType: WorkflowEventType): string {
  const labels: Record<WorkflowEventType, string> = {
    WorkflowStarted: 'Workflow Started',
    WorkflowCompleted: 'Workflow Completed',
    WorkflowFailed: 'Workflow Failed',
    WorkflowCancelled: 'Workflow Cancelled',
    ExecutionStarted: 'Agent Execution Started',
    ExecutionCompleted: 'Agent Execution Completed',
    ExecutionFailed: 'Agent Execution Failed',
    ExecutionCancelled: 'Agent Execution Cancelled',
    StageAdvanced: 'Stage Advanced',
    ReviewStarted: 'Review Started',
    ReviewCompleted: 'Review Approved',
    ReviewRejected: 'Review Rejected',
    ErrorOccurred: 'Error Occurred',
    StatusUpdate: 'Status Update',
  };

  return labels[eventType];
}
