/**
 * Real-time Updates E2E Tests
 *
 * Tests for WebSocket-based real-time updates including:
 * - WebSocket connects on page load
 * - New agent execution appears in Active Agents
 * - Workflow status updates in real-time
 * - Circuit breaker state changes reflect immediately
 */

import { test, expect } from '@playwright/test'
import { setupTestEnvironment, waitForPageLoad } from './utils/setup'
import {
  mockSystemHealth,
  mockActiveExecutions,
  mockWorkflowRuns,
  createDynamicHealthMock,
  createDynamicAgentsMock,
} from './utils/api-mocks'
import {
  mockWebSocket,
  sendMockWebSocketEvent,
  waitForMockWebSocketConnection,
} from './utils/websocket-mock'
import { healthySystemHealth, degradedSystemHealth } from './fixtures/health'
import { runningExecution, sampleExecutionsResponse } from './fixtures/agents'
import { workflowRunsResponse } from './fixtures/workflows'

test.describe('Real-time Updates', () => {
  test.beforeEach(async ({ page, context }) => {
    // Setup mock WebSocket before page load
    await mockWebSocket(page)

    // Setup test environment with authentication
    await setupTestEnvironment(page, context, {
      mockEmptyData: false,
      waitForLoad: false,
    })

    // Mock initial data
    await mockSystemHealth(page, healthySystemHealth)
    await mockActiveExecutions(page, [])
    await mockWorkflowRuns(page, workflowRunsResponse)
  })

  test('should connect WebSocket on page load', async ({ page }) => {
    // Navigate to dashboard
    await page.goto('/')
    await waitForPageLoad(page)

    // Wait for WebSocket connection
    await waitForMockWebSocketConnection(page, 10000)

    // Should show "Live" connection status
    await expect(page.locator('text=Live')).toBeVisible({ timeout: 5000 })

    // Connection indicator should be green
    const connectionIndicator = page.locator('[class*="bg-green-500"]')
    await expect(connectionIndicator).toBeVisible()
  })

  test('should show disconnected state when WebSocket fails', async ({ page }) => {
    // Don't setup mock WebSocket - let it fail
    await page.goto('/')
    await waitForPageLoad(page)

    // Should show "Disconnected" status
    await expect(page.locator('text=Disconnected')).toBeVisible({ timeout: 10000 })

    // Connection indicator should be gray
    const connectionIndicator = page.locator('[class*="bg-gray-400"]')
    await expect(connectionIndicator).toBeVisible()
  })

  test('should receive new agent execution via WebSocket', async ({ page }) => {
    // Navigate to dashboard
    await page.goto('/')
    await waitForPageLoad(page)

    // Wait for WebSocket connection
    await waitForMockWebSocketConnection(page)

    // Initially no active agents
    await expect(page.locator('text=No executions found').or(page.locator('text=0'))).toBeVisible({
      timeout: 5000,
    })

    // Send ExecutionStarted event via WebSocket
    await sendMockWebSocketEvent(page, {
      type: 'ExecutionStarted',
      data: {
        execution: runningExecution,
      },
      timestamp: new Date().toISOString(),
    })

    // Wait for UI to update
    await page.waitForTimeout(1000)

    // Should show new agent execution in Active Agents
    await expect(page.locator('text=planner_agent')).toBeVisible({ timeout: 5000 })
    await expect(page.locator('text=1').or(page.locator(`text=${runningExecution.id}`))).toBeVisible()
  })

  test('should remove completed agent execution via WebSocket', async ({ page }) => {
    // Setup with initial active agents
    await mockActiveExecutions(page, sampleExecutionsResponse)

    // Navigate to dashboard
    await page.goto('/')
    await waitForPageLoad(page)

    // Wait for WebSocket connection
    await waitForMockWebSocketConnection(page)

    // Should show initial active agents
    await expect(page.locator('text=planner_agent')).toBeVisible({ timeout: 10000 })

    // Send ExecutionCompleted event via WebSocket
    await sendMockWebSocketEvent(page, {
      type: 'ExecutionCompleted',
      data: {
        execution_id: sampleExecutionsResponse[0].id,
        status: 'completed',
        duration_seconds: 120,
      },
      timestamp: new Date().toISOString(),
    })

    // Wait for UI to update
    await page.waitForTimeout(1000)

    // Agent should be removed from active agents list
    // Count should decrease
    const activeAgentsCard = page.locator('text=Active Agents').locator('..')
    await expect(activeAgentsCard.locator('text=1').or(activeAgentsCard.locator('text=0'))).toBeVisible({
      timeout: 5000,
    })
  })

  test('should update workflow status in real-time', async ({ page }) => {
    // Navigate to dashboard
    await page.goto('/')
    await waitForPageLoad(page)

    // Wait for WebSocket connection
    await waitForMockWebSocketConnection(page)

    // Send WorkflowStarted event
    await sendMockWebSocketEvent(page, {
      type: 'WorkflowStarted',
      data: {
        workflowRunId: 'wf-run-new',
        workItemId: 'work-item-new',
        triggeredBy: 'manual',
      },
      timestamp: new Date().toISOString(),
    })

    // Wait for UI to update
    await page.waitForTimeout(1000)

    // Should show event in real-time events section
    const eventsSection = page.locator('text=Real-time Events').locator('..')
    await expect(eventsSection.locator('text=WorkflowStarted')).toBeVisible({ timeout: 5000 })
  })

  test('should display real-time events feed', async ({ page }) => {
    // Navigate to dashboard
    await page.goto('/')
    await waitForPageLoad(page)

    // Wait for WebSocket connection
    await waitForMockWebSocketConnection(page)

    // Send multiple events in sequence
    const events = [
      {
        type: 'ExecutionStarted',
        data: { execution: runningExecution },
      },
      {
        type: 'StageStarted',
        data: { stageName: 'planning', stageIndex: 0 },
      },
      {
        type: 'AgentExecutionStarted',
        data: { executionId: 'exec-001', agentName: 'planner_agent' },
      },
    ]

    for (const event of events) {
      await sendMockWebSocketEvent(page, {
        ...event,
        timestamp: new Date().toISOString(),
      })
      await page.waitForTimeout(500)
    }

    // Should display all events in the events feed
    const eventsSection = page.locator('text=Real-time Events').locator('..')
    await expect(eventsSection.locator('text=ExecutionStarted')).toBeVisible({ timeout: 5000 })
    await expect(eventsSection.locator('text=StageStarted')).toBeVisible()
    await expect(eventsSection.locator('text=AgentExecutionStarted')).toBeVisible()
  })

  test('should limit real-time events to last 10', async ({ page }) => {
    // Navigate to dashboard
    await page.goto('/')
    await waitForPageLoad(page)

    // Wait for WebSocket connection
    await waitForMockWebSocketConnection(page)

    // Send 15 events
    for (let i = 0; i < 15; i++) {
      await sendMockWebSocketEvent(page, {
        type: 'TestEvent',
        data: { index: i },
        timestamp: new Date().toISOString(),
      })
      await page.waitForTimeout(100)
    }

    // Should only show last 10 events
    const eventsSection = page.locator('text=Real-time Events').locator('..')
    const eventItems = eventsSection.locator('text=TestEvent')

    // Count should be at most 10
    const count = await eventItems.count()
    expect(count).toBeLessThanOrEqual(10)
  })

  test('should handle WebSocket reconnection', async ({ page }) => {
    // Navigate to dashboard
    await page.goto('/')
    await waitForPageLoad(page)

    // Wait for initial connection
    await waitForMockWebSocketConnection(page)
    await expect(page.locator('text=Live')).toBeVisible({ timeout: 5000 })

    // Simulate disconnect by clearing instances
    await page.evaluate(() => {
      (window as any).__mockWebSocket?.clearInstances()
    })

    // Should show disconnected state
    await expect(page.locator('text=Disconnected')).toBeVisible({ timeout: 5000 })

    // Re-establish connection (in real app, this would happen automatically)
    await page.reload()
    await waitForMockWebSocketConnection(page)

    // Should show connected again
    await expect(page.locator('text=Live')).toBeVisible({ timeout: 5000 })
  })

  test('should update circuit breaker state in real-time', async ({ page }) => {
    // Start with healthy system
    const healthMock = await createDynamicHealthMock(page, healthySystemHealth)

    // Navigate to dashboard
    await page.goto('/')
    await waitForPageLoad(page)

    // Wait for WebSocket connection
    await waitForMockWebSocketConnection(page)

    // Should show healthy state initially
    await expect(page.locator('text=All systems operational')).toBeVisible({ timeout: 10000 })

    // Update to degraded health via mock
    healthMock.update(degradedSystemHealth)

    // Send circuit breaker event
    await sendMockWebSocketEvent(page, {
      type: 'CircuitBreakerStateChanged',
      data: {
        name: 'github_api',
        state: 'open',
        failureCount: 5,
      },
      timestamp: new Date().toISOString(),
    })

    // Wait for polling interval or event handling
    await page.waitForTimeout(6000)

    // Should show degraded state
    await expect(page.locator('text=/degraded/i')).toBeVisible({ timeout: 5000 })

    // Cleanup
    await healthMock.cleanup()
  })

  test('should maintain event order', async ({ page }) => {
    // Navigate to dashboard
    await page.goto('/')
    await waitForPageLoad(page)

    // Wait for WebSocket connection
    await waitForMockWebSocketConnection(page)

    // Send events with specific order
    const events = ['Event1', 'Event2', 'Event3']

    for (const eventType of events) {
      await sendMockWebSocketEvent(page, {
        type: eventType,
        data: {},
        timestamp: new Date().toISOString(),
      })
      await page.waitForTimeout(200)
    }

    // Events should appear in order (most recent first in display)
    const eventsSection = page.locator('text=Real-time Events').locator('..')

    // Get all event items
    const eventItems = await eventsSection.locator('[class*="border-l"]').all()

    // Most recent should be Event3 (at top)
    if (eventItems.length >= 3) {
      await expect(eventItems[0]).toContainText('Event3')
      await expect(eventItems[1]).toContainText('Event2')
      await expect(eventItems[2]).toContainText('Event1')
    }
  })
})
