import { test, expect } from '@playwright/test'

test.describe('Authentication', () => {
  test('should show auth required page when no token', async ({ page }) => {
    await page.goto('/')

    // Should show authentication required page
    await expect(page.getByText('Authentication Required')).toBeVisible()
    await expect(page.getByText('How to get your authentication token')).toBeVisible()
  })

  test('should extract token from URL and set httpOnly cookie', async ({ page, context }) => {
    const mockToken = 'test-token-123'

    // Mock the token validation endpoint to set cookie
    await page.route('**/api/v2/health*', async (route) => {
      await route.fulfill({
        status: 200,
        headers: {
          'Set-Cookie': `codetoreum_token=${mockToken}; HttpOnly; Path=/; SameSite=Strict`,
        },
        body: JSON.stringify({ status: 'healthy' }),
      })
    })

    // Visit with token in URL
    await page.goto(`/?token=${mockToken}`)

    // Wait for redirect (URL should be cleaned)
    await page.waitForURL('/')

    // URL should no longer contain token
    expect(page.url()).not.toContain('token=')

    // Check that httpOnly cookie is set
    const cookies = await context.cookies()
    const authCookie = cookies.find((c) => c.name === 'codetoreum_token')
    expect(authCookie).toBeDefined()
    expect(authCookie?.value).toBe(mockToken)
    expect(authCookie?.httpOnly).toBe(true)
  })

  test('should handle 401 response and show auth required', async ({ page, context }) => {
    // Set invalid httpOnly cookie
    await context.addCookies([
      {
        name: 'codetoreum_token',
        value: 'invalid-token',
        domain: 'localhost',
        path: '/',
        httpOnly: true,
        secure: false,
        sameSite: 'Strict',
      },
    ])

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
  })

  test('should send httpOnly cookie with requests', async ({ page, context }) => {
    const mockToken = 'valid-token-456'

    // Set httpOnly cookie
    await context.addCookies([
      {
        name: 'codetoreum_token',
        value: mockToken,
        domain: 'localhost',
        path: '/',
        httpOnly: true,
        secure: false,
        sameSite: 'Strict',
      },
    ])

    // Track cookie headers in requests
    const cookieHeaders: string[] = []
    page.on('request', (request) => {
      if (request.url().includes('/api/')) {
        const cookieHeader = request.headers()['cookie']
        if (cookieHeader) {
          cookieHeaders.push(cookieHeader)
        }
      }
    })

    // Mock successful API responses
    await page.route('**/api/v2/auth/token-info', (route) => {
      route.fulfill({
        status: 200,
        body: JSON.stringify({ is_valid: true }),
      })
    })

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

    // Check that requests included cookie header
    await page.waitForTimeout(1000) // Give time for API calls
    expect(cookieHeaders.length).toBeGreaterThan(0)
    expect(cookieHeaders[0]).toContain('codetoreum_token=' + mockToken)
  })
})

test.describe('Dashboard', () => {
  test.beforeEach(async ({ page, context }) => {
    // Set valid httpOnly cookie
    await context.addCookies([
      {
        name: 'codetoreum_token',
        value: 'valid-token',
        domain: 'localhost',
        path: '/',
        httpOnly: true,
        secure: false,
        sameSite: 'Strict',
      },
    ])

    // Mock token validation
    await page.route('**/api/v2/auth/token-info', (route) => {
      route.fulfill({
        status: 200,
        body: JSON.stringify({ is_valid: true }),
      })
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
