/**
 * E2E Test Setup Utilities
 *
 * Common test setup functions for Playwright E2E tests.
 */

import { Page, BrowserContext } from '@playwright/test'

/**
 * Setup authentication for tests
 * Sets up a valid httpOnly cookie for authenticated requests
 */
export async function setupAuth(context: BrowserContext, token: string = 'test-token-e2e') {
  await context.addCookies([
    {
      name: 'codetoreum_token',
      value: token,
      domain: 'localhost',
      path: '/',
      httpOnly: true,
      secure: false,
      sameSite: 'Strict',
    },
  ])
}

/**
 * Mock token validation endpoint
 * Returns a successful validation response
 */
export async function mockTokenValidation(page: Page) {
  await page.route('**/api/v2/auth/token-info', (route) => {
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        issued_at: new Date(Date.now() - 3600000).toISOString(),
        expires_at: new Date(Date.now() + 86400000).toISOString(),
        subject: 'test-user',
        is_valid: true,
      }),
    })
  })
}

/**
 * Mock empty API responses
 * Useful for initial page load without specific data
 */
export async function mockEmptyResponses(page: Page) {
  // Mock work items
  await page.route('**/api/v1/work-items*', (route) => {
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify([]),
    })
  })

  // Mock executions
  await page.route('**/api/v1/executions*', (route) => {
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify([]),
    })
  })

  // Mock workflow runs
  await page.route('**/api/v1/workflow-runs*', (route) => {
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ runs: [], total: 0, offset: 0, limit: 20 }),
    })
  })

  // Mock system health
  await page.route('**/api/v2/metrics/health', (route) => {
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        status: 'healthy',
        message: 'All systems operational',
      }),
    })
  })
}

/**
 * Wait for initial page load and hydration
 */
export async function waitForPageLoad(page: Page, title: string = 'Dashboard') {
  await page.waitForLoadState('networkidle')
  await page.waitForSelector(`h2:has-text("${title}")`, { timeout: 10000 })
}

/**
 * Clean up test data between tests
 */
export async function cleanupTestData(page: Page) {
  // Clear any intercepted routes
  await page.unrouteAll({ behavior: 'ignoreErrors' })

  // Clear local storage
  await page.evaluate(() => localStorage.clear())

  // Clear session storage
  await page.evaluate(() => sessionStorage.clear())
}

/**
 * Wait for WebSocket connection
 */
export async function waitForWebSocketConnection(page: Page, timeout: number = 5000) {
  await page.waitForFunction(
    () => {
      const indicator = document.querySelector('[class*="bg-green-500"]')
      return indicator !== null
    },
    { timeout }
  )
}

/**
 * Common test setup combining auth and initial mocks
 */
export async function setupTestEnvironment(
  page: Page,
  context: BrowserContext,
  options: {
    mockEmptyData?: boolean
    waitForLoad?: boolean
    pageTitle?: string
  } = {}
) {
  const { mockEmptyData = true, waitForLoad = false, pageTitle = 'Dashboard' } = options

  // Setup authentication
  await setupAuth(context)

  // Mock token validation
  await mockTokenValidation(page)

  // Mock empty responses if requested
  if (mockEmptyData) {
    await mockEmptyResponses(page)
  }

  // Navigate to home page
  await page.goto('/')

  // Wait for page load if requested
  if (waitForLoad) {
    await waitForPageLoad(page, pageTitle)
  }
}
