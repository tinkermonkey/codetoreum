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

export interface EventMetadata {
  [key: string]: string | number | boolean | null;
}

export interface WorkflowEventData {
  executionId?: string;
  agentName?: string;
  stageName?: string;
  decision?: string;
  message?: string;
  errorMessage?: string;
  exitCode?: number;
  metadata?: EventMetadata;
}

export interface WorkflowEvent {
  id: string;
  event_id?: string; // Legacy field
  eventType: WorkflowEventType;
  event_type?: string; // Legacy field
  event_category?: string; // Legacy field for categorization
  workflowRunId: string;
  timestamp: string;
  agentName?: string;
  agent?: string; // Legacy field
  agent_name?: string; // Legacy field
  stageName?: string;
  status?: string;
  task_id?: string; // Legacy field for task identification
  reason?: string; // Legacy field for decision reason
  decision_category?: string; // Legacy field for decision categorization

  // Event-specific data
  data: WorkflowEventData;
}

export interface WorkflowEventsResponse {
  events: WorkflowEvent[];
  total: number;
}
