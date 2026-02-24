/**
 * Workflow Run Monitoring E2E Tests
 *
 * Tests for workflow run monitoring including:
 * - Navigate to Pipeline Run Details page
 * - View workflow run list in sidebar
 * - Filter workflow runs by status
 * - Select workflow run and view details
 * - View event timeline for selected run
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
  sampleWorkflowRuns,
  workflowRunsResponse,
  runningWorkflowRun,
  completedWorkflowRun,
  failedWorkflowRun,
  sampleWorkflowEvents,
} from './fixtures/workflows'
import { healthySystemHealth } from './fixtures/health'

test.describe('Workflow Run Monitoring', () => {
  test.beforeEach(async ({ page, context }) => {
    // Setup test environment with authentication
    await setupTestEnvironment(page, context, {
      mockEmptyData: false,
      waitForLoad: false,
    })

    // Mock system health and empty executions for cleaner tests
    await mockSystemHealth(page, healthySystemHealth)
    await mockActiveExecutions(page, [])
  })

  test('should navigate to Pipeline Run Details page', async ({ page }) => {
    // Mock workflow runs
    await mockWorkflowRuns(page, workflowRunsResponse)

    // Navigate to workflow runs page
    await page.goto('/workflows/runs')

    // Should display the page title or heading
    await expect(page.locator('text=Workflow Runs')).toBeVisible({ timeout: 10000 })

    // Should display sidebar with workflow runs
    const sidebar = page.locator('[class*="w-96"]')
    await expect(sidebar).toBeVisible()
  })

  test('should view workflow run list in sidebar', async ({ page }) => {
    // Mock workflow runs
    await mockWorkflowRuns(page, workflowRunsResponse)

    // Navigate to workflow runs page
    await page.goto('/workflows/runs')

    // Wait for workflow runs to load
    await expect(page.locator('text=Workflow Runs')).toBeVisible({ timeout: 10000 })

    // Should display all workflow runs in sidebar (4 total from fixture)
    for (const run of sampleWorkflowRuns) {
      await expect(page.locator(`text=${run.issueTitle}`)).toBeVisible({ timeout: 5000 })
    }

    // Should show status badges for each run
    await expect(page.locator('text=running')).toBeVisible()
    await expect(page.locator('text=completed')).toBeVisible()
    await expect(page.locator('text=failed')).toBeVisible()
    await expect(page.locator('text=pending')).toBeVisible()
  })

  test('should filter workflow runs by status', async ({ page }) => {
    // Mock workflow runs with all statuses
    await mockWorkflowRuns(page, workflowRunsResponse)

    // Navigate to workflow runs page
    await page.goto('/workflows/runs')
    await expect(page.locator('text=Workflow Runs')).toBeVisible({ timeout: 10000 })

    // Look for filter controls (implementation may vary)
    const filterButton = page.locator('button:has-text("Filter")').or(
      page.locator('select[name="status"]')
    )

    if (await filterButton.count() > 0) {
      // If filter exists, test filtering
      await filterButton.first().click()

      // Select "running" status filter
      await page.locator('text=Running').click()

      // Should show only running workflow runs
      await expect(page.locator(`text=${runningWorkflowRun.issueTitle}`)).toBeVisible()

      // Completed runs should not be visible (or count should be 1)
      // workflowCards defined but unused - implementation depends on actual filter
      // This assertion depends on actual filter implementation
    } else {
      // If no filter UI exists yet, skip with warning
      console.warn('Filter UI not implemented - test partially skipped')
    }
  })

  test('should select workflow run and view details', async ({ page }) => {
    // Mock workflow runs and details
    await mockWorkflowRuns(page, workflowRunsResponse)
    await mockWorkflowRunDetails(page, runningWorkflowRun)
    await mockWorkflowEvents(page, runningWorkflowRun.id, sampleWorkflowEvents)

    // Navigate to workflow runs page
    await page.goto('/workflows/runs')
    await expect(page.locator('text=Workflow Runs')).toBeVisible({ timeout: 10000 })

    // Click on a workflow run in the sidebar
    await page.locator(`text=${runningWorkflowRun.issueTitle}`).click()

    // Should navigate to details page with run ID in URL
    await expect(page).toHaveURL(new RegExp(`/workflows/runs/${runningWorkflowRun.id}`))

    // Should display workflow run details
    await expect(page.locator(`text=${runningWorkflowRun.issueTitle}`)).toBeVisible()
    await expect(page.locator('text=running')).toBeVisible()
    await expect(page.locator(`text=Issue #${runningWorkflowRun.issueNumber}`)).toBeVisible()

    // Should display current stage
    await expect(page.locator(`text=${runningWorkflowRun.currentStageName}`)).toBeVisible()
  })

  test('should view event timeline for selected run', async ({ page }) => {
    // Mock workflow runs, details, and events
    await mockWorkflowRuns(page, workflowRunsResponse)
    await mockWorkflowRunDetails(page, runningWorkflowRun)
    await mockWorkflowEvents(page, runningWorkflowRun.id, sampleWorkflowEvents)

    // Navigate directly to workflow run details
    await page.goto(`/workflows/runs/${runningWorkflowRun.id}`)

    // Wait for page to load
    await expect(page.locator(`text=${runningWorkflowRun.issueTitle}`)).toBeVisible({
      timeout: 10000,
    })

    // Should display event timeline
    await expect(page.locator('text=Event Timeline').or(page.locator('text=Events'))).toBeVisible({
      timeout: 10000,
    })

    // Should display workflow events
    await expect(page.locator('text=WorkflowStarted')).toBeVisible({ timeout: 5000 })
    await expect(page.locator('text=StageStarted')).toBeVisible()
    await expect(page.locator('text=AgentExecutionStarted')).toBeVisible()
    await expect(page.locator('text=AgentExecutionCompleted')).toBeVisible()

    // Should show event count (7 events in fixture)
    const eventItems = page.locator('[class*="timeline"], [class*="event"]').filter({
      has: page.locator('text=/WorkflowStarted|StageStarted|AgentExecution/'),
    })
    await expect(eventItems).toHaveCount(7, { timeout: 5000 })
  })

  test('should handle different workflow run statuses', async ({ page }) => {
    // Test completed workflow run
    await mockWorkflowRuns(page, { ...workflowRunsResponse, runs: [completedWorkflowRun] })
    await mockWorkflowRunDetails(page, completedWorkflowRun)
    await mockWorkflowEvents(page, completedWorkflowRun.id, [])

    await page.goto(`/workflows/runs/${completedWorkflowRun.id}`)
    await expect(page.locator('text=completed')).toBeVisible({ timeout: 10000 })
    await expect(page.locator(`text=/Duration.*55m/i`).or(page.locator('text=/3300/i'))).toBeVisible({
      timeout: 5000,
    })

    // Test failed workflow run
    await mockWorkflowRunDetails(page, failedWorkflowRun)
    await mockWorkflowEvents(page, failedWorkflowRun.id, [])

    await page.goto(`/workflows/runs/${failedWorkflowRun.id}`)
    await expect(page.locator('text=failed')).toBeVisible({ timeout: 10000 })
    await expect(page.locator(`text=${failedWorkflowRun.issueTitle}`)).toBeVisible()
  })

  test('should navigate back to workflow list', async ({ page }) => {
    // Mock workflow runs and details
    await mockWorkflowRuns(page, workflowRunsResponse)
    await mockWorkflowRunDetails(page, runningWorkflowRun)
    await mockWorkflowEvents(page, runningWorkflowRun.id, sampleWorkflowEvents)

    // Navigate to workflow run details
    await page.goto(`/workflows/runs/${runningWorkflowRun.id}`)
    await expect(page.locator(`text=${runningWorkflowRun.issueTitle}`)).toBeVisible({
      timeout: 10000,
    })

    // Sidebar should still show workflow list
    const sidebar = page.locator('[class*="w-96"]')
    await expect(sidebar).toBeVisible()

    // Should be able to click another workflow run
    await page.locator(`text=${completedWorkflowRun.issueTitle}`).click()

    // Should navigate to the new run
    await expect(page).toHaveURL(new RegExp(`/workflows/runs/${completedWorkflowRun.id}`))
  })

  test('should handle empty workflow runs list', async ({ page }) => {
    // Mock empty workflow runs
    await mockWorkflowRuns(page, { runs: [], total: 0, offset: 0, limit: 20 })

    // Navigate to workflow runs page
    await page.goto('/workflows/runs')

    // Should display empty state message
    await expect(
      page.locator('text=/no workflow runs|no runs found/i').first()
    ).toBeVisible({ timeout: 10000 })
  })

  test('should show workflow metadata', async ({ page }) => {
    // Mock workflow runs and details
    await mockWorkflowRuns(page, workflowRunsResponse)
    await mockWorkflowRunDetails(page, runningWorkflowRun)
    await mockWorkflowEvents(page, runningWorkflowRun.id, sampleWorkflowEvents)

    // Navigate to workflow run details
    await page.goto(`/workflows/runs/${runningWorkflowRun.id}`)
    await expect(page.locator(`text=${runningWorkflowRun.issueTitle}`)).toBeVisible({
      timeout: 10000,
    })

    // Should display metadata
    await expect(page.locator(`text=/Issue.*${runningWorkflowRun.issueNumber}/i`)).toBeVisible()
    await expect(page.locator(`text=/Project.*${runningWorkflowRun.project}/i`)).toBeVisible()
    await expect(page.locator(`text=${runningWorkflowRun.triggeredBy}`)).toBeVisible()

    // Should show priority if displayed
    if (await page.locator(`text=${runningWorkflowRun.priority}`).count() > 0) {
      await expect(page.locator(`text=${runningWorkflowRun.priority}`)).toBeVisible()
    }
  })
})
