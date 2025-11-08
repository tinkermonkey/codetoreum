/**
 * Workflow Run Type Definitions
 *
 * Types for workflow execution tracking and pipeline run details.
 */

export type WorkflowRunStatus = 'pending' | 'running' | 'paused' | 'completed' | 'failed' | 'cancelled';

export interface WorkflowRun {
  id: string;
  workItemId: string;
  workflowId: string;
  projectId: string;
  status: WorkflowRunStatus;
  currentStageIndex: number;
  currentStageName: string;
  startedAt: string | null;
  completedAt: string | null;
  duration: number | null;

  // Work item details
  issueTitle: string;
  issueNumber: number;
  project: string;

  // Metadata
  triggeredBy: string;
  priority: string;
}

export interface WorkflowRunsResponse {
  runs: WorkflowRun[];
  total: number;
  offset: number;
  limit: number;
}

export interface WorkflowRunFilters {
  status?: WorkflowRunStatus | WorkflowRunStatus[];
  projectId?: string;
  search?: string;
  offset?: number;
  limit?: number;
}
