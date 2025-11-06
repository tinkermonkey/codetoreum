# API Client Improvements

## Overview

The API client has been refactored to follow hexagonal architecture principles with resilience patterns extracted to the infrastructure layer. This implementation provides robust error handling, automatic retries, circuit breaker protection, and comprehensive request management.

## Architecture

### Hexagonal Architecture Alignment

The implementation follows the project's hexagonal architecture:

- **Primary Adapter**: `APIClient` class (`client.ts`) - Clean HTTP adapter without embedded resilience logic
- **Infrastructure Layer**: Resilience decorators (`infrastructure/resilience/`) - Centralized retry, circuit breaker, and resilience patterns
- **Configuration**: Environment-based configuration (`config/api.config.ts`) - Externalized settings
- **Types**: Unified error types (`types/errors.ts`) - Consistent with backend error structures
- **Events**: Type-safe event system (`infrastructure/events.ts`) - Decoupled communication

### Key Files

```
frontend/src/
├── api/
│   └── client.ts                          # Primary HTTP adapter
├── config/
│   └── api.config.ts                      # Environment configuration
├── infrastructure/
│   ├── events.ts                          # Event system
│   └── resilience/
│       ├── circuitBreaker.ts              # Circuit breaker implementation
│       ├── retryPolicy.ts                 # Retry logic
│       ├── resilienceDecorator.ts         # Decorator infrastructure
│       ├── index.ts                       # Exports
│       └── __tests__/
│           └── circuitBreaker.test.ts     # Unit tests
└── types/
    └── errors.ts                          # Unified error types
```

## Features

### 1. Request Timeouts

- **Default**: 30 seconds (configurable via `VITE_API_TIMEOUT`)
- **Per-Environment**: Different timeouts for dev/staging/production
- **Configurable**: Set via environment variables

```bash
# .env
VITE_API_TIMEOUT=30000  # 30 seconds
```

### 2. Retry Logic with Exponential Backoff

Handled by `RetryPolicy` in infrastructure layer:

- **Max Retries**: 3 (configurable via `VITE_API_MAX_RETRIES`)
- **Strategy**: Exponential backoff with jitter
- **Base Delay**: 1 second
- **Max Delay**: 30 seconds
- **Jitter**: 30% to prevent thundering herd
- **Retry-After Header**: Automatically respected for rate limiting

**Retryable Conditions**:
- Network errors (ECONNRESET, ETIMEDOUT, etc.)
- HTTP 408 (Request Timeout)
- HTTP 429 (Too Many Requests)
- HTTP 5xx (Server Errors)

```bash
# .env
VITE_API_MAX_RETRIES=3
VITE_API_RETRY_BASE_DELAY=1000
VITE_API_RETRY_MAX_DELAY=30000
VITE_API_RETRY_JITTER=0.3
```

### 3. Circuit Breaker Pattern

Handled by `CircuitBreaker` in infrastructure layer:

- **Failure Threshold**: 5 consecutive failures (configurable)
- **Reset Timeout**: 60 seconds (configurable)
- **States**: CLOSED → OPEN → HALF_OPEN → CLOSED
- **Events**: Dispatches events on state changes
- **User Notifications**: Toast messages when circuit opens

**States**:
- **CLOSED**: Normal operation, all requests pass through
- **OPEN**: Service unavailable, requests fail immediately
- **HALF_OPEN**: Testing recovery, limited requests allowed

```bash
# .env
VITE_API_CB_FAILURE_THRESHOLD=5
VITE_API_CB_RESET_TIMEOUT=60000  # 1 minute
```

### 4. Enhanced Error Handling

Unified error handling with backend-aligned types:

- **Structured Errors**: `ApiError` interface matches backend
- **Error Codes**: Enum-based error classification
- **User-Friendly Messages**: Contextual error messages
- **Status Code Mapping**: Automatic mapping to error codes
- **Error Events**: Dispatches events for specific errors (401, 429, etc.)

**Special Handling**:
- **401 Unauthorized**: Dispatches auth event, shows sign-in message
- **403 Forbidden**: Permission error message
- **404 Not Found**: Resource not found message
- **429 Rate Limited**: Respects Retry-After, shows wait message
- **5xx Server Errors**: Generic server error message

### 5. Request/Response Interceptors

- **Request Interceptor**:
  - Adds correlation IDs (format: `timestamp-random`)
  - Development logging (method, URL, correlation ID)

- **Response Interceptor**:
  - Success logging in development
  - Error logging with correlation ID
  - Special error handling (auth, rate limiting)

### 6. Request Cancellation Support

Improved with automatic cleanup:

- **AbortController-based**: Standard Web API
- **Automatic Cleanup**: WeakMap for garbage collection
- **Timeout-based Cleanup**: Auto-cleanup after request timeout
- **Duplicate Prevention**: Cancels existing request with same key

```typescript
// Usage
await apiClient.get<Data>('/endpoint', {
  cancelKey: 'unique-key'
})

// Cancel specific request
apiClient.cancelRequest('unique-key')

// Cancel all requests
apiClient.cancelAllRequests()
```

### 7. Correlation IDs

- **Format**: `${timestamp}-${random}`
- **Header**: `X-Correlation-ID`
- **Purpose**: Track requests across frontend and backend
- **Logging**: Included in all log messages

### 8. Event System

Type-safe event system for decoupled communication:

- **Auth Events**: `AUTH_UNAUTHORIZED`, `AUTH_TOKEN_EXPIRED`, etc.
- **API Events**: `API_RATE_LIMITED`, `API_CIRCUIT_BREAKER_OPEN`, etc.
- **Network Events**: `NETWORK_ONLINE`, `NETWORK_OFFLINE`

```typescript
import { subscribeToEvent, AppEventType } from './infrastructure/events'

// Subscribe to events
subscribeToEvent(AppEventType.AUTH_UNAUTHORIZED, ({ message }) => {
  router.push('/login')
})

subscribeToEvent(AppEventType.API_CIRCUIT_BREAKER_OPEN, ({ failureCount }) => {
  toast.error('Service temporarily unavailable')
})
```

### 9. Toast Notifications

Integrated `react-hot-toast` for user feedback:

- **Error Messages**: User-friendly error notifications
- **Rate Limiting**: Notification when rate limited
- **Circuit Breaker**: Notification when service unavailable
- **Auth Events**: Sign-in prompt on unauthorized

## Configuration

### Environment Variables

Create `.env` file:

```bash
# API Configuration
VITE_API_BASE_URL=http://localhost:8000
VITE_API_TIMEOUT=30000

# Retry Configuration
VITE_API_MAX_RETRIES=3
VITE_API_RETRY_BASE_DELAY=1000
VITE_API_RETRY_MAX_DELAY=30000
VITE_API_RETRY_JITTER=0.3

# Circuit Breaker Configuration
VITE_API_CB_FAILURE_THRESHOLD=5
VITE_API_CB_RESET_TIMEOUT=60000

# Feature Flags
VITE_API_ENABLE_LOGGING=true
VITE_API_ENABLE_RETRY=true
VITE_API_ENABLE_CIRCUIT_BREAKER=true
```

### Per-Environment Configuration

```bash
# .env.development
VITE_API_BASE_URL=http://localhost:8000
VITE_API_TIMEOUT=60000
VITE_API_ENABLE_LOGGING=true

# .env.production
VITE_API_BASE_URL=https://api.codetoreum.com
VITE_API_TIMEOUT=30000
VITE_API_ENABLE_LOGGING=false
```

## Usage

### Basic Usage

```typescript
import { workItemsApi } from './api/client'

// Get all work items
const workItems = await workItemsApi.getAll()

// Create work item
const newItem = await workItemsApi.create({
  title: 'New Work Item',
  description: 'Description',
})
```

### With Request Cancellation

```typescript
import { apiClient } from './api/client'

// Make request with cancellation key
const data = await apiClient.get<Data>('/endpoint', {
  cancelKey: 'fetch-data',
  params: { page: 1 }
})

// Cancel if needed
apiClient.cancelRequest('fetch-data')
```

### Error Handling

```typescript
import { workItemsApi } from './api/client'
import { ApiError, ErrorCode } from './types/errors'

try {
  const item = await workItemsApi.getById('123')
} catch (error) {
  const apiError = error as ApiError

  if (apiError.code === ErrorCode.NOT_FOUND) {
    // Handle not found
  } else if (apiError.code === ErrorCode.UNAUTHORIZED) {
    // Handle unauthorized
  } else {
    console.error(apiError.message, apiError.correlationId)
  }
}
```

### Listening to Events

```typescript
import { subscribeToEvent, AppEventType } from './infrastructure/events'

// Handle auth events
subscribeToEvent(AppEventType.AUTH_UNAUTHORIZED, ({ message }) => {
  console.log('User needs to sign in:', message)
  router.push('/login')
})

// Handle circuit breaker events
subscribeToEvent(AppEventType.API_CIRCUIT_BREAKER_OPEN, ({ failureCount }) => {
  console.warn(`Circuit breaker opened after ${failureCount} failures`)
})
```

### Circuit Breaker Stats

```typescript
import { apiClient } from './api/client'

// Get current stats
const stats = apiClient.getCircuitBreakerStats()
console.log('Circuit breaker state:', stats?.state)
console.log('Failure count:', stats?.failureCount)

// Reset circuit breaker (admin/testing)
apiClient.resetCircuitBreaker()
```

## Testing

### Unit Tests

Run the circuit breaker tests:

```bash
cd frontend
npm test src/infrastructure/resilience/__tests__/circuitBreaker.test.ts
```

### Test Coverage

- ✅ Circuit breaker state transitions
- ✅ Failure threshold detection
- ✅ Reset timeout behavior
- ✅ Statistics tracking
- ✅ Error handling

## Benefits

1. **Reliability**: Automatic retries handle transient failures
2. **Resilience**: Circuit breaker prevents cascading failures
3. **User Experience**: Clear error messages and toast notifications
4. **Debugging**: Correlation IDs track requests end-to-end
5. **Performance**: Request cancellation prevents wasted resources
6. **Maintainability**: Centralized resilience logic in infrastructure layer
7. **Testability**: Pure adapter with mockable resilience decorators
8. **Observability**: Comprehensive logging and event system
9. **Flexibility**: Environment-based configuration
10. **Architecture**: Follows hexagonal architecture principles

## Troubleshooting

### Circuit Breaker Frequently Opening

- Increase `VITE_API_CB_FAILURE_THRESHOLD` (e.g., to 10)
- Increase `VITE_API_CB_RESET_TIMEOUT` (e.g., to 120000 for 2 minutes)
- Check backend health

### Requests Timing Out

- Increase `VITE_API_TIMEOUT`
- Check network connectivity
- Optimize backend endpoints

### Too Many Retries

- Reduce `VITE_API_MAX_RETRIES`
- Disable retries with `VITE_API_ENABLE_RETRY=false`

### Disable Features

```bash
VITE_API_ENABLE_CIRCUIT_BREAKER=false
VITE_API_ENABLE_RETRY=false
VITE_API_ENABLE_LOGGING=false
```

## Migration Notes

### Breaking Changes

- `axios-retry` removed - replaced with infrastructure `RetryPolicy`
- Circuit breaker moved to `infrastructure/resilience/`
- Error types now in `types/errors.ts`
- Toast notifications now use `react-hot-toast`

### Migration Steps

1. Install dependencies: `npm install react-hot-toast`
2. Update imports to use infrastructure layer components
3. Update error handling to use unified `ApiError` type
4. Subscribe to events instead of using global event dispatching

## Future Enhancements

- Request deduplication
- Response caching with TTL
- Request queue with priority
- Metrics collection
- Admin dashboard for circuit breaker monitoring
- Adaptive timeout based on endpoint performance
- Bulkhead pattern for request isolation

---

*Architecture: Hexagonal with infrastructure-layer resilience patterns*
