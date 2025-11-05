/**
 * Retry Policy Implementation
 *
 * Infrastructure layer component for automatic retry logic
 * with exponential backoff and jitter.
 */

export interface RetryConfig {
  maxRetries: number
  baseDelay: number
  maxDelay: number
  jitter: number
  retryableStatusCodes?: number[]
  retryableErrors?: string[]
}

export interface RetryContext {
  attempt: number
  maxAttempts: number
  lastError?: any
  nextDelay?: number
}

/**
 * Default retryable conditions
 */
const DEFAULT_RETRYABLE_STATUS_CODES = [408, 429, 500, 502, 503, 504]
const DEFAULT_RETRYABLE_ERRORS = ['ECONNRESET', 'ETIMEDOUT', 'ENOTFOUND', 'ERR_NETWORK']

/**
 * Calculate exponential backoff delay with jitter
 */
function calculateDelay(
  attempt: number,
  baseDelay: number,
  maxDelay: number,
  jitter: number
): number {
  // Exponential backoff: baseDelay * 2^attempt
  const exponentialDelay = Math.min(baseDelay * Math.pow(2, attempt), maxDelay)

  // Add jitter to prevent thundering herd
  const jitterAmount = exponentialDelay * jitter * Math.random()

  return Math.floor(exponentialDelay + jitterAmount)
}

/**
 * Check if an error is retryable
 */
function isRetryableError(
  error: any,
  config: Required<RetryConfig>
): boolean {
  // Check HTTP status code
  if (error?.response?.status) {
    return config.retryableStatusCodes.includes(error.response.status)
  }

  // Check error code
  if (error?.code) {
    return config.retryableErrors.includes(error.code)
  }

  // Check error message
  if (error?.message) {
    return config.retryableErrors.some((retryableError) =>
      error.message.includes(retryableError)
    )
  }

  return false
}

/**
 * Respect Retry-After header if present
 */
function getRetryAfterDelay(error: any): number | null {
  const retryAfter = error?.response?.headers?.['retry-after']

  if (!retryAfter) {
    return null
  }

  // Retry-After can be a number (seconds) or a date
  if (/^\d+$/.test(retryAfter)) {
    return parseInt(retryAfter, 10) * 1000
  }

  const retryDate = new Date(retryAfter)
  if (!isNaN(retryDate.getTime())) {
    return Math.max(0, retryDate.getTime() - Date.now())
  }

  return null
}

/**
 * Sleep utility
 */
function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms))
}

/**
 * Retry Policy class
 */
export class RetryPolicy {
  private readonly config: Required<RetryConfig>

  constructor(config: RetryConfig) {
    this.config = {
      ...config,
      retryableStatusCodes: config.retryableStatusCodes ?? DEFAULT_RETRYABLE_STATUS_CODES,
      retryableErrors: config.retryableErrors ?? DEFAULT_RETRYABLE_ERRORS,
    }
  }

  /**
   * Execute a function with retry logic
   */
  async execute<T>(
    fn: () => Promise<T>,
    onRetry?: (context: RetryContext) => void
  ): Promise<T> {
    let lastError: any

    for (let attempt = 0; attempt <= this.config.maxRetries; attempt++) {
      try {
        return await fn()
      } catch (error) {
        lastError = error

        // Don't retry if we've exhausted attempts
        if (attempt >= this.config.maxRetries) {
          break
        }

        // Don't retry if error is not retryable
        if (!isRetryableError(error, this.config)) {
          throw error
        }

        // Calculate delay
        const retryAfterDelay = getRetryAfterDelay(error)
        const delay =
          retryAfterDelay ??
          calculateDelay(attempt, this.config.baseDelay, this.config.maxDelay, this.config.jitter)

        // Notify about retry
        if (onRetry) {
          const context: RetryContext = {
            attempt: attempt + 1,
            maxAttempts: this.config.maxRetries + 1,
            lastError: error,
            nextDelay: delay,
          }
          onRetry(context)
        }

        console.warn(
          `[RetryPolicy] Retrying request (attempt ${attempt + 1}/${this.config.maxRetries}) after ${delay}ms`,
          { error: (error as any)?.message || String(error) }
        )

        // Wait before retrying
        await sleep(delay)
      }
    }

    // All retries exhausted
    throw lastError
  }

  /**
   * Get configuration
   */
  getConfig(): Required<RetryConfig> {
    return { ...this.config }
  }
}
