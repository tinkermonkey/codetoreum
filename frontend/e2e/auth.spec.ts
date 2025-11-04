import { test, expect } from '@playwright/test'

test.describe('Authentication', () => {
  test('should show auth required page when no token', async ({ page }) => {
    await page.goto('/')

    // Should show authentication required page
    await expect(page.getByText('Authentication Required')).toBeVisible()
    await expect(page.getByText('How to get your authentication token')).toBeVisible()
  })

  test('should extract token from URL and store in localStorage', async ({ page }) => {
    const mockToken = 'test-token-123'

    // Visit with token in URL
    await page.goto(`/?token=${mockToken}`)

    // Wait for redirect (URL should be cleaned)
    await page.waitForURL('/')

    // Check that token is stored in localStorage
    const storedToken = await page.evaluate(() => localStorage.getItem('codetoreum_token'))
    expect(storedToken).toBe(mockToken)

    // URL should no longer contain token
    expect(page.url()).not.toContain('token=')
  })

  test('should clear token on 401 response', async ({ page, context }) => {
    const mockToken = 'invalid-token'

    // Set invalid token in localStorage
    await context.addInitScript((token) => {
      localStorage.setItem('codetoreum_token', token)
    }, mockToken)

    // Mock API to return 401
    await page.route('**/api/**', (route) => {
      route.fulfill({
        status: 401,
        body: JSON.stringify({ message: 'Unauthorized' }),
      })
    })

    await page.goto('/')

    // Should eventually show auth required page after 401
    await expect(page.getByText('Authentication Required')).toBeVisible({
      timeout: 10000,
    })

    // Token should be cleared from localStorage
    const storedToken = await page.evaluate(() => localStorage.getItem('codetoreum_token'))
    expect(storedToken).toBeNull()
  })

  test('should send token in Authorization header', async ({ page, context }) => {
    const mockToken = 'valid-token-456'

    // Set token in localStorage
    await context.addInitScript((token) => {
      localStorage.setItem('codetoreum_token', token)
    }, mockToken)

    // Track API requests
    const requests: string[] = []
    page.on('request', (request) => {
      if (request.url().includes('/api/')) {
        const authHeader = request.headers()['authorization']
        if (authHeader) {
          requests.push(authHeader)
        }
      }
    })

    // Mock successful API responses
    await page.route('**/api/v1/work-items*', (route) => {
      route.fulfill({
        status: 200,
        body: JSON.stringify([]),
      })
    })

    await page.route('**/api/v1/executions*', (route) => {
      route.fulfill({
        status: 200,
        body: JSON.stringify([]),
      })
    })

    await page.goto('/')

    // Wait for page to load
    await expect(page.getByText('Dashboard')).toBeVisible()

    // Check that requests included Authorization header
    await page.waitForTimeout(1000) // Give time for API calls
    expect(requests.length).toBeGreaterThan(0)
    expect(requests[0]).toBe(`Bearer ${mockToken}`)
  })
})

test.describe('Dashboard', () => {
  test.beforeEach(async ({ page, context }) => {
    // Set valid token
    await context.addInitScript(() => {
      localStorage.setItem('codetoreum_token', 'valid-token')
    })

    // Mock API responses
    await page.route('**/api/v1/work-items*', (route) => {
      route.fulfill({
        status: 200,
        body: JSON.stringify([
          {
            id: '1',
            title: 'Test Work Item',
            description: 'Test description',
            status: 'in_progress',
            labels: ['bug', 'high-priority'],
            url: 'https://github.com/test/repo/issues/1',
            created_at: new Date().toISOString(),
            updated_at: new Date().toISOString(),
            metadata: {},
          },
        ]),
      })
    })

    await page.route('**/api/v1/executions*', (route) => {
      route.fulfill({
        status: 200,
        body: JSON.stringify([
          {
            id: 'exec-1',
            work_item_id: '1',
            work_item_title: 'Test Work Item',
            agent_name: 'test_agent',
            status: 'running',
            started_at: new Date().toISOString(),
          },
        ]),
      })
    })
  })

  test('should display dashboard with work items and executions', async ({ page }) => {
    await page.goto('/')

    // Should show dashboard
    await expect(page.getByRole('heading', { name: 'Dashboard' })).toBeVisible()

    // Should show work items section
    await expect(page.getByText('Active Work Items')).toBeVisible()
    await expect(page.getByText('Test Work Item')).toBeVisible()
    await expect(page.getByText('Test description')).toBeVisible()

    // Should show executions section
    await expect(page.getByText('Recent Executions')).toBeVisible()
    await expect(page.getByText('Agent: test_agent')).toBeVisible()

    // Should show real-time events section
    await expect(page.getByText('Real-time Events')).toBeVisible()
  })

  test('should show WebSocket connection status', async ({ page }) => {
    await page.goto('/')

    // Should show connection status indicator
    await expect(page.getByText('Live').or(page.getByText('Disconnected'))).toBeVisible()
  })
})
