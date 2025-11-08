/**
 * Workflow Event Type Definitions
 *
 * Types for workflow execution events and timeline display.
 */

export type WorkflowEventType =
  | 'WorkflowStarted'
  | 'WorkflowCompleted'
  | 'WorkflowFailed'
  | 'WorkflowCancelled'
  | 'ExecutionStarted'
  | 'ExecutionCompleted'
  | 'ExecutionFailed'
  | 'ExecutionCancelled'
  | 'StageAdvanced'
  | 'ReviewStarted'
  | 'ReviewCompleted'
  | 'ReviewRejected'
  | 'ErrorOccurred'
  | 'StatusUpdate';

export interface WorkflowEventData {
  executionId?: string;
  agentName?: string;
  stageName?: string;
  decision?: string;
  message?: string;
  errorMessage?: string;
  exitCode?: number;
  metadata?: Record<string, any>;
}

export interface WorkflowEvent {
  id: string;
  eventType: WorkflowEventType;
  workflowRunId: string;
  timestamp: string;
  agentName?: string;
  stageName?: string;
  status?: string;

  // Event-specific data
  data: WorkflowEventData;
}

export interface WorkflowEventsResponse {
  events: WorkflowEvent[];
  total: number;
}
