/**
 * Agent Execution Test Fixtures
 *
 * Mock data for active agent executions used in E2E tests.
 */

import type { AgentExecution } from '../../src/types/system-status'
import type { Execution } from '../../src/types'

/**
 * Sample active agent execution
 */
export const runningAgentExecution: AgentExecution = {
  id: 'exec-001',
  agentName: 'planner_agent',
  workItemId: 'work-item-001',
  status: 'running',
  startedAt: new Date(Date.now() - 120000).toISOString(), // Started 2 minutes ago
  containerName: 'codetoreum-planner-abc123',
  project: 'test-project',
  issueNumber: 123,
}

/**
 * Sample completed agent execution
 */
export const completedAgentExecution: AgentExecution = {
  id: 'exec-002',
  agentName: 'coder_agent',
  workItemId: 'work-item-002',
  status: 'completed',
  startedAt: new Date(Date.now() - 600000).toISOString(), // Started 10 minutes ago
  containerName: 'codetoreum-coder-def456',
  project: 'test-project',
  issueNumber: 122,
}

/**
 * Sample failed agent execution
 */
export const failedAgentExecution: AgentExecution = {
  id: 'exec-003',
  agentName: 'tester_agent',
  workItemId: 'work-item-003',
  status: 'failed',
  startedAt: new Date(Date.now() - 300000).toISOString(), // Started 5 minutes ago
  containerName: 'codetoreum-tester-ghi789',
  project: 'test-project',
  issueNumber: 121,
}

/**
 * Collection of sample agent executions
 */
export const sampleAgentExecutions: AgentExecution[] = [
  runningAgentExecution,
  completedAgentExecution,
  failedAgentExecution,
]

/**
 * Sample API execution format (for API responses)
 */
export const runningExecution: Execution = {
  id: 'exec-001',
  work_item_id: 'work-item-001',
  agent_name: 'planner_agent',
  status: 'running',
  started_at: new Date(Date.now() - 120000).toISOString(),
  completed_at: undefined,
  duration_seconds: undefined,
  exit_code: undefined,
  container_id: 'codetoreum-planner-abc123',
  error_message: undefined,
  logs: [],
  metadata: {
    project: 'test-project',
    issue_number: 123,
    workflow_run_id: 'wf-run-001',
    stage_name: 'planning',
  },
}

/**
 * Sample API executions list response
 */
export const sampleExecutionsResponse: Execution[] = [
  runningExecution,
  {
    id: 'exec-004',
    work_item_id: 'work-item-004',
    agent_name: 'reviewer_agent',
    status: 'running',
    started_at: new Date(Date.now() - 60000).toISOString(),
    completed_at: undefined,
    duration_seconds: undefined,
    exit_code: undefined,
    container_id: 'codetoreum-reviewer-jkl012',
    error_message: undefined,
    logs: [],
    metadata: {
      project: 'test-project',
      issue_number: 124,
      workflow_run_id: 'wf-run-004',
      stage_name: 'review',
    },
  },
]
