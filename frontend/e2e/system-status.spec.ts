/**
 * System Status Monitoring E2E Tests
 *
 * Tests for the system status header including:
 * - Active agent count display
 * - Claude API usage with progress bars
 * - Circuit breaker status display
 * - Health alerts when unhealthy
 */

import { test, expect } from '@playwright/test'
import { setupTestEnvironment, waitForPageLoad } from './utils/setup'
import { mockSystemHealth, mockActiveExecutions } from './utils/api-mocks'
import {
  healthySystemHealth,
  degradedSystemHealth,
  systemHealthWithBreakers,
} from './fixtures/health'
import { sampleExecutionsResponse } from './fixtures/agents'

test.describe('System Status Monitoring', () => {
  test.beforeEach(async ({ page, context }) => {
    // Setup test environment with authentication
    await setupTestEnvironment(page, context, {
      mockEmptyData: false,
      waitForLoad: false,
    })
  })

  test('should display active agent count', async ({ page }) => {
    // Mock system health and active executions
    await mockSystemHealth(page, healthySystemHealth)
    await mockActiveExecutions(page, sampleExecutionsResponse)

    // Navigate to dashboard
    await page.goto('/')
    await waitForPageLoad(page)

    // Should display system status header
    await expect(page.locator('text=Loading system status')).not.toBeVisible()

    // Should display active agents card
    const activeAgentsCard = page.locator('text=Active Agents').locator('..')
    await expect(activeAgentsCard).toBeVisible()

    // Should show correct agent count (2 running agents from fixture)
    await expect(activeAgentsCard.locator(`text=${sampleExecutionsResponse.length}`)).toBeVisible({
      timeout: 10000,
    })
  })

  test('should show Claude API usage with progress bars', async ({ page }) => {
    // Mock system health with usage data
    await mockSystemHealth(page, healthySystemHealth)
    await mockActiveExecutions(page, [])

    // Navigate to dashboard
    await page.goto('/')
    await waitForPageLoad(page)

    // Should display API usage card
    const apiUsageCard = page.locator('text=API Usage').locator('..')
    await expect(apiUsageCard).toBeVisible({ timeout: 10000 })

    // Should show weekly usage percentage
    await expect(apiUsageCard.locator('text=/Weekly:.*30%/')).toBeVisible({ timeout: 5000 })

    // Should show session usage percentage
    await expect(apiUsageCard.locator('text=/Session:.*50%/')).toBeVisible({ timeout: 5000 })

    // Should display progress bars (look for progress elements)
    const progressBars = apiUsageCard.locator('[role="progressbar"]')
    await expect(progressBars).toHaveCount(2) // Weekly and session
  })

  test('should display circuit breaker status', async ({ page }) => {
    // Mock system health with circuit breakers
    await mockSystemHealth(page, systemHealthWithBreakers)
    await mockActiveExecutions(page, [])

    // Navigate to dashboard
    await page.goto('/')
    await waitForPageLoad(page)

    // Should display circuit breakers card
    const breakersCard = page.locator('text=Circuit Breakers').locator('..')
    await expect(breakersCard).toBeVisible({ timeout: 10000 })

    // Should show circuit breaker summary
    // 3 total: 1 closed, 1 half-open, 1 open
    await expect(breakersCard.locator('text=/3 total/')).toBeVisible({ timeout: 5000 })
    await expect(breakersCard.locator('text=/1 open/')).toBeVisible({ timeout: 5000 })

    // Should display individual breakers when expanded (if clickable)
    // Note: This depends on the actual implementation of expandable cards
  })

  test('should show health alerts when unhealthy', async ({ page }) => {
    // Mock degraded system health
    await mockSystemHealth(page, degradedSystemHealth)
    await mockActiveExecutions(page, [])

    // Navigate to dashboard
    await page.goto('/')
    await waitForPageLoad(page)

    // Should display health alert banner
    const healthAlert = page.locator('[class*="bg-yellow"], [class*="bg-red"]')
    await expect(healthAlert.first()).toBeVisible({ timeout: 10000 })

    // Should show degraded status message
    await expect(page.locator('text=/degraded/i')).toBeVisible({ timeout: 5000 })

    // Should show warning about high usage
    await expect(page.locator('text=/usage.*80%/i')).toBeVisible({ timeout: 5000 })
  })

  test('should update system status in real-time', async ({ page }) => {
    // Start with healthy system
    await mockSystemHealth(page, healthySystemHealth)
    await mockActiveExecutions(page, [])

    // Navigate to dashboard
    await page.goto('/')
    await waitForPageLoad(page)

    // Verify healthy status initially
    await expect(page.locator('text=All systems operational')).toBeVisible({ timeout: 10000 })

    // Update to degraded health (simulate polling)
    await mockSystemHealth(page, degradedSystemHealth)

    // Wait for polling interval to trigger update (default is 5 seconds)
    // Note: In real test, this would wait for the actual polling interval
    await page.waitForTimeout(6000)

    // Should show degraded status
    await expect(page.locator('text=/degraded/i')).toBeVisible({ timeout: 5000 })
  })

  test('should handle API errors gracefully', async ({ page }) => {
    // Mock API error response
    await page.route('**/api/v2/metrics/health', (route) => {
      route.fulfill({
        status: 500,
        contentType: 'application/json',
        body: JSON.stringify({ error: 'Internal server error' }),
      })
    })

    await mockActiveExecutions(page, [])

    // Navigate to dashboard
    await page.goto('/')
    await waitForPageLoad(page)

    // Should show error state or fallback UI
    // Depending on implementation, this might be an error boundary or error message
    await expect(
      page.locator('text=/error|failed|unavailable/i').first()
    ).toBeVisible({ timeout: 10000 })
  })

  test('should display all status cards together', async ({ page }) => {
    // Mock complete system with all data
    await mockSystemHealth(page, systemHealthWithBreakers)
    await mockActiveExecutions(page, sampleExecutionsResponse)

    // Navigate to dashboard
    await page.goto('/')
    await waitForPageLoad(page)

    // Should display all three status cards
    await expect(page.locator('text=Active Agents')).toBeVisible({ timeout: 10000 })
    await expect(page.locator('text=API Usage')).toBeVisible({ timeout: 10000 })
    await expect(page.locator('text=Circuit Breakers')).toBeVisible({ timeout: 10000 })

    // All cards should be visible simultaneously
    const statusCards = page.locator('[class*="gap-4"] > div')
    await expect(statusCards).toHaveCount(3, { timeout: 5000 })
  })
})
