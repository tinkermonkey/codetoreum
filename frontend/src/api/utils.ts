/**
 * API Client Utility Functions
 */

/**
 * Generate a unique correlation ID for request tracking
 * Format: timestamp-random
 */
export function generateCorrelationId(): string {
  const timestamp = Date.now().toString(36)
  const randomPart = Math.random().toString(36).substring(2, 10)
  return `${timestamp}-${randomPart}`
}

/**
 * Check if an error is retriable
 */
export function isRetriableError(error: any): boolean {
  // Network errors
  if (!error.response) {
    return true
  }

  // Server errors (5xx)
  const status = error.response?.status
  if (status && status >= 500 && status < 600) {
    return true
  }

  // Specific retriable status codes
  const retriableStatuses = [
    408, // Request Timeout
    429, // Too Many Requests (with retry-after)
  ]

  return status && retriableStatuses.includes(status)
}

/**
 * Calculate exponential backoff delay
 */
export function calculateBackoffDelay(
  retryCount: number,
  baseDelay = 1000,
  maxDelay = 30000
): number {
  const exponentialDelay = baseDelay * Math.pow(2, retryCount)
  const jitter = Math.random() * 0.3 * exponentialDelay // 0-30% jitter
  return Math.min(exponentialDelay + jitter, maxDelay)
}

/**
 * Format error message for user display
 */
export function formatErrorMessage(error: any): string {
  if (error.response) {
    // Server error
    const status = error.response.status
    const message = error.response.data?.message || error.message

    if (status === 401) {
      return 'Authentication required. Please log in.'
    } else if (status === 403) {
      return 'Access denied. You do not have permission to perform this action.'
    } else if (status === 404) {
      return 'Resource not found.'
    } else if (status === 429) {
      return 'Too many requests. Please wait a moment and try again.'
    } else if (status >= 500) {
      return `Server error: ${message}`
    }

    return message
  } else if (error.request) {
    // Network error
    return 'Network error: Unable to reach server. Please check your connection.'
  }

  // Unknown error
  return error.message || 'An unexpected error occurred.'
}

/**
 * Parse retry-after header (seconds or HTTP date)
 */
export function parseRetryAfter(retryAfter: string | null | undefined): number | null {
  if (!retryAfter) {
    return null
  }

  // Try parsing as seconds
  const seconds = parseInt(retryAfter, 10)
  if (!isNaN(seconds)) {
    return seconds * 1000 // Convert to milliseconds
  }

  // Try parsing as HTTP date
  const date = new Date(retryAfter)
  if (!isNaN(date.getTime())) {
    return Math.max(0, date.getTime() - Date.now())
  }

  return null
}

/**
 * Create an AbortController with timeout
 */
export function createTimeoutController(timeoutMs: number): AbortController {
  const controller = new AbortController()

  const timeoutId = setTimeout(() => {
    controller.abort()
  }, timeoutMs)

  // Store timeout ID for cleanup
  ;(controller as any)._timeoutId = timeoutId

  return controller
}

/**
 * Clear timeout from AbortController
 */
export function clearControllerTimeout(controller: AbortController): void {
  const timeoutId = (controller as any)._timeoutId
  if (timeoutId) {
    clearTimeout(timeoutId)
  }
}
