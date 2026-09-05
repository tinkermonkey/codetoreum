/**
 * API Mock Utilities
 *
 * Helper functions for mocking API responses in E2E tests.
 */

import { Page, Route } from '@playwright/test'
import type { SystemHealth, CircuitBreaker } from '../../src/types/system-status'
import type { WorkflowRun, WorkflowRunsResponse } from '../../src/types/workflow-run'
import type { Execution } from '../../src/types'

/**
 * Mock system health endpoint
 */
export async function mockSystemHealth(page: Page, health: SystemHealth) {
  await page.route('**/api/v2/metrics/health', (route) => {
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(health),
    })
  })
}

/**
 * Mock active executions endpoint
 */
export async function mockActiveExecutions(page: Page, executions: Execution[]) {
  await page.route('**/api/v1/executions*', (route) => {
    const url = new URL(route.request().url())
    const status = url.searchParams.get('status')

    // Filter by status if provided
    const filtered = status
      ? executions.filter((e) => e.status === status)
      : executions

    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(filtered),
    })
  })
}

/**
 * Mock workflow runs endpoint
 */
export async function mockWorkflowRuns(page: Page, response: WorkflowRunsResponse) {
  await page.route('**/api/v1/workflow-runs*', (route) => {
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(response),
    })
  })
}

/**
 * Mock workflow run details endpoint
 */
export async function mockWorkflowRunDetails(page: Page, workflowRun: WorkflowRun) {
  await page.route(`**/api/v1/workflow-runs/${workflowRun.id}`, (route) => {
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(workflowRun),
    })
  })
}

/**
 * Mock workflow events endpoint
 */
export async function mockWorkflowEvents(page: Page, workflowRunId: string, events: any[]) {
  await page.route(`**/api/v1/workflow-runs/${workflowRunId}/events`, (route) => {
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(events),
    })
  })
}

/**
 * Mock work items endpoint
 */
export async function mockWorkItems(page: Page, workItems: any[]) {
  await page.route('**/api/v1/work-items*', (route) => {
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(workItems),
    })
  })
}

/**
 * Mock circuit breakers in system health response
 */
export async function mockCircuitBreakers(page: Page, health: SystemHealth, breakers: CircuitBreaker[]) {
  const healthWithBreakers = {
    ...health,
    circuitBreakers: breakers,
  }

  await mockSystemHealth(page, healthWithBreakers)
}

/**
 * Helper to create dynamic mock that can be updated
 */
export class DynamicMock<T> {
  private data: T
  private routes: Route[] = []

  constructor(private page: Page, private pattern: string, initialData: T) {
    this.data = initialData
  }

  async setup() {
    await this.page.route(this.pattern, (route) => {
      this.routes.push(route)
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(this.data),
      })
    })
  }

  update(data: T) {
    this.data = data
  }

  async cleanup() {
    await this.page.unroute(this.pattern)
    this.routes = []
  }
}

/**
 * Create a dynamic mock for system health that can be updated during test
 */
export async function createDynamicHealthMock(page: Page, initialHealth: SystemHealth) {
  const mock = new DynamicMock<SystemHealth>(page, '**/api/v2/metrics/health', initialHealth)
  await mock.setup()
  return mock
}

/**
 * Create a dynamic mock for active agents that can be updated during test
 */
export async function createDynamicAgentsMock(page: Page, initialExecutions: Execution[]) {
  const mock = new DynamicMock<Execution[]>(page, '**/api/v1/executions*', initialExecutions)
  await mock.setup()
  return mock
}
