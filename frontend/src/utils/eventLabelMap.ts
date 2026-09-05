import type { WorkflowEventType } from '../types/workflow-event'

/**
 * Get human-readable label for workflow event type
 */
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
  }

  return labels[eventType]
}
