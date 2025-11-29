# E2E Testing Suite

End-to-end smoke tests for critical user paths in the Codetoreum frontend application.

## Overview

This E2E test suite uses [Playwright](https://playwright.dev/) to test critical user workflows across the application. The tests are designed to be:

- **Fast**: Deterministic mocks avoid dependency on external services
- **Reliable**: Retry logic and proper waits prevent flakiness
- **Maintainable**: Shared fixtures and utilities reduce duplication
- **Comprehensive**: Cover all critical user paths

## Test Structure

```
frontend/e2e/
├── fixtures/              # Mock data for tests
│   ├── workflows.ts       # Workflow run fixtures
│   ├── agents.ts          # Agent execution fixtures
│   └── health.ts          # System health fixtures
├── utils/                 # Test utilities
│   ├── setup.ts           # Common test setup functions
│   ├── api-mocks.ts       # API mocking helpers
│   └── websocket-mock.ts  # WebSocket mocking utilities
├── system-status.spec.ts  # System status monitoring tests
├── workflow-runs.spec.ts  # Workflow run monitoring tests
├── pipeline-flow.spec.ts  # Pipeline flow visualization tests
├── realtime-updates.spec.ts # Real-time WebSocket tests
└── auth.spec.ts           # Authentication tests (existing)
```

## Running Tests

### Run all E2E tests
```bash
npm run test:e2e
```

### Run specific test file
```bash
npx playwright test system-status.spec.ts
```

### Run tests in headed mode (see browser)
```bash
npx playwright test --headed
```

### Run tests in UI mode (interactive debugging)
```bash
npx playwright test --ui
```

### Run tests with specific browser
```bash
npx playwright test --project=chromium
```

## Test Coverage

### 1. System Status Monitoring (`system-status.spec.ts`)

Tests the system status header functionality:

- ✅ Display active agent count
- ✅ Show Claude API usage with progress bars
- ✅ Display circuit breaker status
- ✅ Show health alerts when unhealthy
- ✅ Handle API errors gracefully
- ✅ Update status in real-time

**Critical Path**: Dashboard → System Status Header

### 2. Workflow Run Monitoring (`workflow-runs.spec.ts`)

Tests workflow run list and details pages:

- ✅ Navigate to Pipeline Run Details page
- ✅ View workflow run list in sidebar
- ✅ Filter workflow runs by status
- ✅ Select workflow run and view details
- ✅ View event timeline for selected run
- ✅ Display workflow metadata

**Critical Path**: Dashboard → Workflow Runs → Run Details

### 3. Pipeline Flow Visualization (`pipeline-flow.spec.ts`)

Tests the interactive flow diagram:

- ✅ Navigate to Pipeline Flow page
- ✅ Display interactive flow diagram
- ✅ Show stage statuses (completed, running, pending)
- ✅ Click nodes to view stage details
- ✅ Display flow legend and controls
- ✅ Handle empty workflow runs

**Critical Path**: Workflow Run Details → Flow Diagram

### 4. Real-time Updates (`realtime-updates.spec.ts`)

Tests WebSocket-based real-time functionality:

- ✅ WebSocket connects on page load
- ✅ New agent execution appears in Active Agents
- ✅ Workflow status updates in real-time
- ✅ Circuit breaker state changes reflect immediately
- ✅ Display real-time events feed
- ✅ Handle WebSocket reconnection

**Critical Path**: Dashboard with running workflows

## Fixtures

### Workflow Fixtures (`fixtures/workflows.ts`)

Sample workflow runs in different states:
- `runningWorkflowRun` - Active workflow in progress
- `completedWorkflowRun` - Successfully completed workflow
- `failedWorkflowRun` - Failed workflow
- `pendingWorkflowRun` - Queued workflow
- `sampleWorkflowEvents` - Timeline of workflow events

### Agent Fixtures (`fixtures/agents.ts`)

Sample agent executions:
- `runningAgentExecution` - Active agent execution
- `completedAgentExecution` - Finished execution
- `failedAgentExecution` - Failed execution
- `sampleExecutionsResponse` - API response format

### Health Fixtures (`fixtures/health.ts`)

System health states:
- `healthySystemHealth` - All systems operational
- `degradedSystemHealth` - Some issues detected
- `systemHealthWithBreakers` - Circuit breakers open
- `sampleCircuitBreakers` - Various breaker states
- API usage samples (healthy and high usage)

## Utilities

### Setup Utilities (`utils/setup.ts`)

Common test setup functions:
- `setupAuth()` - Configure authentication cookie
- `mockTokenValidation()` - Mock auth validation
- `mockEmptyResponses()` - Mock empty API responses
- `waitForPageLoad()` - Wait for page hydration
- `setupTestEnvironment()` - Combined setup

### API Mocking (`utils/api-mocks.ts`)

API mocking helpers:
- `mockSystemHealth()` - Mock health endpoint
- `mockActiveExecutions()` - Mock executions endpoint
- `mockWorkflowRuns()` - Mock workflow runs
- `mockWorkflowRunDetails()` - Mock run details
- `mockWorkflowEvents()` - Mock event timeline
- `createDynamicHealthMock()` - Updatable health mock

### WebSocket Mocking (`utils/websocket-mock.ts`)

WebSocket test utilities:
- `mockWebSocket()` - Replace WebSocket with mock
- `sendMockWebSocketEvent()` - Send test events
- `waitForMockWebSocketConnection()` - Wait for connection
- `sendEventSequence()` - Send multiple events

## Configuration

### Playwright Config (`playwright.config.ts`)

Key settings:
- **Base URL**: `http://localhost:3010` (Vite dev server)
- **Retries**: 2 in CI, 1 locally (for flaky network issues)
- **Screenshot**: Captured on failure
- **Video**: Retained on failure
- **Timeout**: 120s for dev server startup
- **Browser**: Chromium (can add Firefox/WebKit)

## Writing New Tests

### Example Test Structure

```typescript
import { test, expect } from '@playwright/test'
import { setupTestEnvironment } from './utils/setup'
import { mockSystemHealth } from './utils/api-mocks'
import { healthySystemHealth } from './fixtures/health'

test.describe('My Feature', () => {
  test.beforeEach(async ({ page, context }) => {
    await setupTestEnvironment(page, context)
    await mockSystemHealth(page, healthySystemHealth)
  })

  test('should do something', async ({ page }) => {
    await page.goto('/')
    await expect(page.locator('text=My Feature')).toBeVisible()
  })
})
```

### Best Practices

1. **Use shared fixtures** - Don't duplicate mock data
2. **Use utility functions** - Reuse common setup logic
3. **Mock external APIs** - Don't depend on backend
4. **Wait properly** - Use `waitFor*` instead of `waitForTimeout`
5. **Test user paths** - Focus on critical workflows
6. **Keep tests independent** - Each test should run alone
7. **Use meaningful selectors** - Prefer text/role over classes

## Debugging Tests

### View test report
```bash
npx playwright show-report
```

### Debug specific test
```bash
npx playwright test --debug system-status.spec.ts
```

### View screenshots/videos
After test failure, artifacts are in `playwright-report/` and `test-results/`

### Enable verbose logging
```bash
DEBUG=pw:api npx playwright test
```

## CI Integration

Tests run automatically in CI with:
- 2 retries for transient failures
- Screenshot and video capture on failure
- HTML report generation
- Single worker for consistency

### CI Command
```bash
npm run test:e2e
```

## Troubleshooting

### Tests timing out
- Check that dev server is running (`npm run dev`)
- Verify port 3010 is available
- Increase timeout in test if needed

### Flaky tests
- Check for race conditions in async operations
- Ensure proper waits (use `waitForSelector` not `waitForTimeout`)
- Verify mocks are setup before navigation

### Selector not found
- Check element is actually rendered
- Try alternative selectors (role, text, test-id)
- Verify mock data contains expected values

### WebSocket issues
- Ensure `mockWebSocket()` is called before page load
- Check browser console for connection errors
- Verify events are sent after connection established

## Future Enhancements

- [ ] Add visual regression testing
- [ ] Add performance testing (Core Web Vitals)
- [ ] Add accessibility testing (axe-core)
- [ ] Add cross-browser testing (Firefox, Safari)
- [ ] Add mobile viewport testing
- [ ] Add API contract testing
- [ ] Add data-driven tests with CSV/JSON

## Resources

- [Playwright Documentation](https://playwright.dev/)
- [Playwright Best Practices](https://playwright.dev/docs/best-practices)
- [Test Fixtures Guide](https://playwright.dev/docs/test-fixtures)
- [Debugging Guide](https://playwright.dev/docs/debug)
