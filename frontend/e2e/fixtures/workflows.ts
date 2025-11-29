/**
 * Workflow Run Test Fixtures
 *
 * Mock data for workflow runs and related entities used in E2E tests.
 */

import type { WorkflowRun, WorkflowRunsResponse } from '../../src/types/workflow-run'

/**
 * Sample workflow run in running state
 */
export const runningWorkflowRun: WorkflowRun = {
  id: 'wf-run-001',
  workItemId: 'work-item-001',
  workflowId: 'workflow-001',
  projectId: 'codetoreum/test-project',
  status: 'running',
  currentStageIndex: 1,
  currentStageName: 'implementation',
  startedAt: new Date(Date.now() - 300000).toISOString(), // Started 5 minutes ago
  completedAt: null,
  duration: null,
  issueTitle: 'Add user authentication feature',
  issueNumber: 123,
  project: 'test-project',
  triggeredBy: 'issue_created',
  priority: 'high',
}

/**
 * Sample workflow run in completed state
 */
export const completedWorkflowRun: WorkflowRun = {
  id: 'wf-run-002',
  workItemId: 'work-item-002',
  workflowId: 'workflow-001',
  projectId: 'codetoreum/test-project',
  status: 'completed',
  currentStageIndex: 3,
  currentStageName: 'review',
  startedAt: new Date(Date.now() - 3600000).toISOString(), // Started 1 hour ago
  completedAt: new Date(Date.now() - 300000).toISOString(), // Completed 5 minutes ago
  duration: 3300,
  issueTitle: 'Fix login redirect bug',
  issueNumber: 122,
  project: 'test-project',
  triggeredBy: 'manual',
  priority: 'critical',
}

/**
 * Sample workflow run in failed state
 */
export const failedWorkflowRun: WorkflowRun = {
  id: 'wf-run-003',
  workItemId: 'work-item-003',
  workflowId: 'workflow-001',
  projectId: 'codetoreum/test-project',
  status: 'failed',
  currentStageIndex: 1,
  currentStageName: 'testing',
  startedAt: new Date(Date.now() - 1800000).toISOString(), // Started 30 minutes ago
  completedAt: new Date(Date.now() - 600000).toISOString(), // Failed 10 minutes ago
  duration: 1200,
  issueTitle: 'Optimize database queries',
  issueNumber: 121,
  project: 'test-project',
  triggeredBy: 'schedule',
  priority: 'medium',
}

/**
 * Sample workflow run in pending state
 */
export const pendingWorkflowRun: WorkflowRun = {
  id: 'wf-run-004',
  workItemId: 'work-item-004',
  workflowId: 'workflow-001',
  projectId: 'codetoreum/test-project',
  status: 'pending',
  currentStageIndex: 0,
  currentStageName: 'planning',
  startedAt: null,
  completedAt: null,
  duration: null,
  issueTitle: 'Add dark mode support',
  issueNumber: 124,
  project: 'test-project',
  triggeredBy: 'issue_created',
  priority: 'low',
}

/**
 * Collection of all sample workflow runs
 */
export const sampleWorkflowRuns: WorkflowRun[] = [
  runningWorkflowRun,
  completedWorkflowRun,
  failedWorkflowRun,
  pendingWorkflowRun,
]

/**
 * Sample workflow runs API response
 */
export const workflowRunsResponse: WorkflowRunsResponse = {
  runs: sampleWorkflowRuns,
  total: 4,
  offset: 0,
  limit: 20,
}

/**
 * Sample workflow events for a workflow run
 */
export const sampleWorkflowEvents = [
  {
    id: 'evt-001',
    workflowRunId: 'wf-run-001',
    type: 'WorkflowStarted',
    timestamp: new Date(Date.now() - 300000).toISOString(),
    data: {
      workItemId: 'work-item-001',
      triggeredBy: 'issue_created',
    },
  },
  {
    id: 'evt-002',
    workflowRunId: 'wf-run-001',
    type: 'StageStarted',
    timestamp: new Date(Date.now() - 295000).toISOString(),
    data: {
      stageName: 'planning',
      stageIndex: 0,
    },
  },
  {
    id: 'evt-003',
    workflowRunId: 'wf-run-001',
    type: 'AgentExecutionStarted',
    timestamp: new Date(Date.now() - 290000).toISOString(),
    data: {
      executionId: 'exec-001',
      agentName: 'planner_agent',
      stageName: 'planning',
    },
  },
  {
    id: 'evt-004',
    workflowRunId: 'wf-run-001',
    type: 'AgentExecutionCompleted',
    timestamp: new Date(Date.now() - 250000).toISOString(),
    data: {
      executionId: 'exec-001',
      agentName: 'planner_agent',
      status: 'completed',
      duration: 40,
    },
  },
  {
    id: 'evt-005',
    workflowRunId: 'wf-run-001',
    type: 'StageCompleted',
    timestamp: new Date(Date.now() - 245000).toISOString(),
    data: {
      stageName: 'planning',
      stageIndex: 0,
      status: 'completed',
    },
  },
  {
    id: 'evt-006',
    workflowRunId: 'wf-run-001',
    type: 'StageStarted',
    timestamp: new Date(Date.now() - 240000).toISOString(),
    data: {
      stageName: 'implementation',
      stageIndex: 1,
    },
  },
  {
    id: 'evt-007',
    workflowRunId: 'wf-run-001',
    type: 'AgentExecutionStarted',
    timestamp: new Date(Date.now() - 235000).toISOString(),
    data: {
      executionId: 'exec-002',
      agentName: 'coder_agent',
      stageName: 'implementation',
    },
  },
]
