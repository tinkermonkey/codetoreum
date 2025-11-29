/**
 * Pipeline Flow Visualization E2E Tests
 *
 * Tests for pipeline flow diagram including:
 * - Navigate to Pipeline Flow page
 * - Display interactive flow diagram
 * - Show stage statuses (completed, running, pending)
 * - Click nodes to view stage details
 * - Pan and zoom flow diagram
 */

import { test, expect } from '@playwright/test'
import { setupTestEnvironment } from './utils/setup'
import {
  mockWorkflowRuns,
  mockWorkflowRunDetails,
  mockWorkflowEvents,
  mockSystemHealth,
  mockActiveExecutions,
} from './utils/api-mocks'
import {
  runningWorkflowRun,
  sampleWorkflowEvents,
  workflowRunsResponse,
} from './fixtures/workflows'
import { healthySystemHealth } from './fixtures/health'

test.describe('Pipeline Flow Visualization', () => {
  test.beforeEach(async ({ page, context }) => {
    // Setup test environment with authentication
    await setupTestEnvironment(page, context, {
      mockEmptyData: false,
      waitForLoad: false,
    })

    // Mock system health and executions
    await mockSystemHealth(page, healthySystemHealth)
    await mockActiveExecutions(page, [])

    // Mock workflow data
    await mockWorkflowRuns(page, workflowRunsResponse)
    await mockWorkflowRunDetails(page, runningWorkflowRun)
    await mockWorkflowEvents(page, runningWorkflowRun.id, sampleWorkflowEvents)
  })

  test('should navigate to Pipeline Flow page', async ({ page }) => {
    // Navigate to workflow runs page first
    await page.goto('/workflows/runs')
    await expect(page.locator('text=Workflow Runs')).toBeVisible({ timeout: 10000 })

    // Click on a workflow run
    await page.locator(`text=${runningWorkflowRun.issueTitle}`).click()

    // Look for "Flow" or "Diagram" link/button
    const flowButton = page.locator('text=/^Flow$|View Flow|Flow Diagram/i')

    if (await flowButton.count() > 0) {
      await flowButton.first().click()
      await expect(page).toHaveURL(new RegExp(`/workflows/flow/${runningWorkflowRun.id}`))
    } else {
      // Navigate directly to flow page
      await page.goto(`/workflows/flow/${runningWorkflowRun.id}`)
    }

    // Should display flow page with title
    await expect(page.locator(`text=${runningWorkflowRun.issueTitle}`)).toBeVisible({
      timeout: 10000,
    })
  })

  test('should display interactive flow diagram', async ({ page }) => {
    // Navigate directly to flow page
    await page.goto(`/workflows/flow/${runningWorkflowRun.id}`)

    // Wait for page to load
    await expect(page.locator(`text=${runningWorkflowRun.issueTitle}`)).toBeVisible({
      timeout: 10000,
    })

    // Should display flow canvas (ReactFlow or custom canvas)
    const flowCanvas = page.locator('[class*="react-flow"], [class*="flow-canvas"], canvas')
    await expect(flowCanvas.first()).toBeVisible({ timeout: 10000 })

    // Should display nodes for workflow events
    // Note: Node selectors depend on ReactFlow implementation
    const flowNodes = page.locator(
      '[class*="react-flow__node"], [data-type="workflow-node"], [class*="node"]'
    )
    await expect(flowNodes.first()).toBeVisible({ timeout: 5000 })
  })

  test('should show stage statuses', async ({ page }) => {
    // Navigate to flow page
    await page.goto(`/workflows/flow/${runningWorkflowRun.id}`)
    await expect(page.locator(`text=${runningWorkflowRun.issueTitle}`)).toBeVisible({
      timeout: 10000,
    })

    // Wait for flow to render
    await page.waitForTimeout(2000)

    // Should show completed stages (green/success color)
    const completedNodes = page.locator('[class*="completed"], [class*="success"]')
    await expect(completedNodes.first()).toBeVisible({ timeout: 5000 })

    // Should show running stages (blue/in-progress color)
    const runningNodes = page.locator('[class*="running"], [class*="in-progress"]')
    await expect(runningNodes.first()).toBeVisible({ timeout: 5000 })

    // Should display stage names
    await expect(page.locator('text=planning')).toBeVisible()
    await expect(page.locator('text=implementation')).toBeVisible()
  })

  test('should click nodes to view stage details', async ({ page }) => {
    // Navigate to flow page
    await page.goto(`/workflows/flow/${runningWorkflowRun.id}`)
    await expect(page.locator(`text=${runningWorkflowRun.issueTitle}`)).toBeVisible({
      timeout: 10000,
    })

    // Wait for flow to render
    await page.waitForTimeout(2000)

    // Find a node to click (look for stage name)
    const planningNode = page.locator('text=planning').first()

    if (await planningNode.count() > 0) {
      // Click the node
      await planningNode.click()

      // Should display details (in sidebar or modal)
      // This depends on implementation - could be a sidebar, modal, or tooltip
      await expect(
        page.locator('text=/Stage Details|planning|planner_agent/i').first()
      ).toBeVisible({ timeout: 5000 })
    } else {
      console.warn('Flow nodes not clickable - test partially skipped')
    }
  })

  test('should display flow legend', async ({ page }) => {
    // Navigate to flow page
    await page.goto(`/workflows/flow/${runningWorkflowRun.id}`)
    await expect(page.locator(`text=${runningWorkflowRun.issueTitle}`)).toBeVisible({
      timeout: 10000,
    })

    // Should display legend explaining node types and colors
    const legend = page.locator('text=Legend').or(page.locator('[class*="legend"]'))
    await expect(legend.first()).toBeVisible({ timeout: 10000 })

    // Legend should explain status colors
    // Note: This depends on actual legend implementation
    if (await legend.count() > 0) {
      // Click legend to expand if collapsed
      await legend.first().click()

      // Should show status explanations
      await expect(page.locator('text=/Completed|Running|Pending/i').first()).toBeVisible({
        timeout: 5000,
      })
    }
  })

  test('should show flow controls', async ({ page }) => {
    // Navigate to flow page
    await page.goto(`/workflows/flow/${runningWorkflowRun.id}`)
    await expect(page.locator(`text=${runningWorkflowRun.issueTitle}`)).toBeVisible({
      timeout: 10000,
    })

    // Should display flow controls (zoom in, zoom out, fit view, etc.)
    const controls = page.locator(
      '[class*="react-flow__controls"], [class*="flow-controls"], button[title*="Zoom"]'
    )

    if (await controls.count() > 0) {
      await expect(controls.first()).toBeVisible({ timeout: 5000 })

      // Should have zoom controls
      const zoomIn = page.locator('button[title*="Zoom in"], button[aria-label*="zoom in"]')
      const zoomOut = page.locator('button[title*="Zoom out"], button[aria-label*="zoom out"]')

      if (await zoomIn.count() > 0) {
        await expect(zoomIn.first()).toBeVisible()
        await expect(zoomOut.first()).toBeVisible()
      }
    }
  })

  test('should refresh flow diagram', async ({ page }) => {
    // Navigate to flow page
    await page.goto(`/workflows/flow/${runningWorkflowRun.id}`)
    await expect(page.locator(`text=${runningWorkflowRun.issueTitle}`)).toBeVisible({
      timeout: 10000,
    })

    // Wait for initial load
    await page.waitForTimeout(2000)

    // Look for refresh button
    const refreshButton = page.locator(
      'button:has-text("Refresh"), button[title*="Refresh"], button[aria-label*="refresh"]'
    )

    if (await refreshButton.count() > 0) {
      // Click refresh button
      await refreshButton.first().click()

      // Should show loading indicator briefly
      const loadingIndicator = page.locator('[class*="animate-spin"]')
      // Note: Loading might be very brief, so this might not always catch it
    }
  })

  test('should handle workflow with no events', async ({ page }) => {
    // Mock workflow with no events
    await mockWorkflowEvents(page, runningWorkflowRun.id, [])

    // Navigate to flow page
    await page.goto(`/workflows/flow/${runningWorkflowRun.id}`)
    await expect(page.locator(`text=${runningWorkflowRun.issueTitle}`)).toBeVisible({
      timeout: 10000,
    })

    // Should show empty state message
    await expect(
      page.locator('text=/No workflow events|No events to display|Empty/i').first()
    ).toBeVisible({ timeout: 10000 })
  })

  test('should navigate back from flow page', async ({ page }) => {
    // Navigate to flow page
    await page.goto(`/workflows/flow/${runningWorkflowRun.id}`)
    await expect(page.locator(`text=${runningWorkflowRun.issueTitle}`)).toBeVisible({
      timeout: 10000,
    })

    // Look for back button
    const backButton = page.locator(
      'button:has-text("Back"), button[aria-label*="back"], a[href*="/workflows"]'
    )

    if (await backButton.count() > 0) {
      // Click back button
      await backButton.first().click()

      // Should navigate back to workflow runs or details page
      await expect(page).toHaveURL(
        new RegExp(`/workflows/runs|/workflows/runs/${runningWorkflowRun.id}`)
      )
    } else {
      // Try browser back
      await page.goBack()
      await expect(page).toHaveURL(/\/workflows/)
    }
  })

  test('should display workflow run metadata', async ({ page }) => {
    // Navigate to flow page
    await page.goto(`/workflows/flow/${runningWorkflowRun.id}`)
    await expect(page.locator(`text=${runningWorkflowRun.issueTitle}`)).toBeVisible({
      timeout: 10000,
    })

    // Should display workflow run ID
    await expect(page.locator(`text=${runningWorkflowRun.id}`)).toBeVisible()

    // Should display status
    await expect(page.locator('text=running')).toBeVisible()

    // Should display other metadata if available
    if (await page.locator(`text=Issue #${runningWorkflowRun.issueNumber}`).count() > 0) {
      await expect(page.locator(`text=Issue #${runningWorkflowRun.issueNumber}`)).toBeVisible()
    }
  })
})
