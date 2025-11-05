# API Client Improvements

## Overview

The frontend API client has been enhanced with robust error handling, retry logic, circuit breaker pattern, request cancellation, and comprehensive logging capabilities.

## Key Improvements

### 1. Request Timeouts
- Default timeout: 30 seconds (configurable via `API_TIMEOUT` constant)
- Prevents requests from hanging indefinitely
- Configured at the axios instance level

### 2. Retry Logic with Exponential Backoff
- **Library**: axios-retry
- **Max Retries**: 3 attempts (configurable via `MAX_RETRIES`)
- **Backoff Strategy**: Exponential with jitter (30% randomization)
- **Retry Conditions**:
  - Network errors (no response received)
  - Server errors (5xx status codes)
  - Request timeout (408)
  - Rate limiting (429) - respects `Retry-After` header
- **Delay Calculation**: Base 1s, max 30s with exponential growth
- **Logging**: Each retry attempt is logged with details

### 3. Circuit Breaker Pattern
- **Implementation**: Custom `CircuitBreaker` class in `api/circuitBreaker.ts`
- **Failure Threshold**: 5 consecutive failures
- **Reset Timeout**: 60 seconds
- **States**:
  - `CLOSED`: Normal operation, requests pass through
  - `OPEN`: Too many failures, requests fail immediately
  - `HALF_OPEN`: Testing recovery, limited requests allowed
- **Benefits**: Prevents cascading failures and gives failing services time to recover
- **User Notification**: Shows error toast when circuit opens

### 4. Enhanced Error Handling
- **Structured Error Types**: All errors converted to `ApiError` interface
- **Status Code Mapping**: Specific handling for 401, 403, 404, 429, 5xx
- **User-Friendly Messages**: Formatted error messages via `formatErrorMessage()`
- **Auth Events**: 401 errors trigger `auth:unauthorized` event
- **Rate Limiting**: 429 errors show user notification

### 5. Request/Response Interceptors
**Request Interceptor**:
- Adds correlation ID (`X-Correlation-ID` header) for request tracking
- Logs outgoing requests in development mode
- Automatically includes httpOnly cookies

**Response Interceptor**:
- Logs successful responses in development mode
- Comprehensive error logging with correlation IDs
- Special handling for 401 (auth) and 429 (rate limit)
- Structured error transformation

### 6. Request Cancellation Support
- **AbortController**: Native browser API for request cancellation
- **Cancel Keys**: Unique identifiers for tracking requests
- **Automatic Cleanup**: Controllers removed after request completion
- **Duplicate Prevention**: Cancels previous request with same key
- **API Functions**:
  - `cancelRequest(key)`: Cancel specific request
  - `cancelAllRequests()`: Cancel all active requests
- **Use Cases**:
  - User navigates away from page
  - User initiates new search before previous completes
  - Component unmount cleanup

### 7. Correlation IDs
- **Format**: `timestamp-random` (e.g., `1z2x3c4v-a8b7c6d5`)
- **Purpose**: Track requests across frontend and backend
- **Usage**: Included in all request headers as `X-Correlation-ID`
- **Benefits**: Debugging, logging, distributed tracing

## File Structure

```
frontend/src/api/
├── client.ts           # Main API client with all integrations
├── circuitBreaker.ts   # Circuit breaker implementation
└── utils.ts           # Utility functions (correlation ID, retry logic, etc.)
```

## API Wrapper Functions

All API calls now use wrapper functions with circuit breaker protection:

```typescript
// GET request with cancellation support
await apiGet<Type>('/endpoint', {
  cancelKey: 'unique-key',
  params: { ... }
})

// POST request
await apiPost<Type>('/endpoint', requestBody, {
  cancelKey: 'unique-key'
})

// PATCH request
await apiPatch<Type>('/endpoint', requestBody)

// DELETE request
await apiDelete<Type>('/endpoint', { params: { ... } })
```

## Configuration Constants

Located in `frontend/src/api/client.ts`:

```typescript
const API_TIMEOUT = 30000                        // 30 seconds
const MAX_RETRIES = 3                            // 3 retry attempts
const CIRCUIT_BREAKER_THRESHOLD = 5              // 5 failures before opening
const CIRCUIT_BREAKER_RESET_TIMEOUT = 60000      // 1 minute reset time
```

## Usage Examples

### Request Cancellation

```typescript
// In a React component
useEffect(() => {
  const fetchData = async () => {
    try {
      const data = await projectConfigApi.get('my-project')
      // Use data...
    } catch (error) {
      // Handle error...
    }
  }

  fetchData()

  // Cancel request on unmount
  return () => {
    cancelRequest('project-config-my-project')
  }
}, [])
```

### Circuit Breaker Monitoring

```typescript
import { getCircuitBreakerStats, resetCircuitBreaker } from './api/client'

// Get current stats
const stats = getCircuitBreakerStats()
console.log('Circuit state:', stats.state)
console.log('Failure count:', stats.failureCount)

// Manually reset (admin action)
resetCircuitBreaker()
```

### Error Handling

```typescript
try {
  const result = await workItemsApi.create(newItem)
  // Success...
} catch (error) {
  if (error.statusCode === 401) {
    // Unauthorized - handled by interceptor
  } else if (error.statusCode === 429) {
    // Rate limited - user already notified
  } else if (error instanceof CircuitBreakerError) {
    // Circuit open - service unavailable
    console.error('Service temporarily down', error.stats)
  } else {
    // Other error
    console.error(error.message)
  }
}
```

## Logging

All API interactions are logged in development mode:

```
[API] GET /configurations/projects/my-project {correlationId: '...'}
[API] 200 /configurations/projects/my-project {correlationId: '...', data: {...}}
[API] Retrying request (1/3): {url: '...', method: 'GET', error: '...'}
[API] Circuit breaker open - 5 failures detected
```

## Testing Recommendations

1. **Unit Tests**: Test circuit breaker state transitions
2. **Integration Tests**: Test retry logic with mock server
3. **E2E Tests**: Test request cancellation on navigation
4. **Load Tests**: Verify circuit breaker under high failure rate
5. **Network Tests**: Simulate network errors and timeouts

## Migration Notes

- All existing API calls automatically benefit from retry logic and circuit breaker
- No changes needed to existing API usage
- Request cancellation is opt-in via `cancelKey` parameter
- Circuit breaker is global across all API calls

## Future Enhancements

1. **Per-Endpoint Circuit Breakers**: Individual breakers for different services
2. **Adaptive Timeouts**: Dynamic timeout based on historical response times
3. **Request Queuing**: Queue requests when circuit is open, retry when closed
4. **Metrics Dashboard**: Visualize retry rates, circuit breaker state, error rates
5. **Request Deduplication**: Prevent duplicate requests with same parameters

## Dependencies

- `axios`: ^1.6.2 (HTTP client)
- `axios-retry`: ^4.5.0 (Retry logic)

## References

- Circuit Breaker Pattern: https://martinfowler.com/bliki/CircuitBreaker.html
- Exponential Backoff: https://en.wikipedia.org/wiki/Exponential_backoff
- axios-retry: https://github.com/softonic/axios-retry
