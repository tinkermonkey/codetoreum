/**
 * Circuit Breaker Pattern Implementation
 *
 * Infrastructure layer component for resilience patterns.
 * Prevents cascading failures by stopping requests to failing services
 * and giving them time to recover.
 */

import { dispatchEvent, AppEventType } from '../events'

export interface CircuitBreakerConfig {
  failureThreshold: number  // Number of failures before opening circuit
  resetTimeout: number      // Time in ms before attempting to close circuit
  monitoringWindow?: number // Time window for tracking failures (default: same as resetTimeout)
}

export type CircuitState = 'closed' | 'open' | 'half-open'

export interface CircuitBreakerStats {
  state: CircuitState
  failureCount: number
  successCount: number
  lastFailureTime: number | null
  lastStateChange: number
}

/**
 * CircuitBreaker implementation with state management
 *
 * States:
 * - CLOSED: Normal operation, requests pass through
 * - OPEN: Circuit is open, requests fail immediately
 * - HALF_OPEN: Testing if service has recovered, limited requests allowed
 */
export class CircuitBreaker {
  private failureCount = 0
  private successCount = 0
  private lastFailureTime: number | null = null
  private lastStateChange: number = Date.now()
  private state: CircuitState = 'closed'
  private readonly config: Required<CircuitBreakerConfig>

  constructor(config: CircuitBreakerConfig) {
    this.config = {
      ...config,
      monitoringWindow: config.monitoringWindow ?? config.resetTimeout,
    }
  }

  /**
   * Execute a function with circuit breaker protection
   */
  async execute<T>(fn: () => Promise<T>): Promise<T> {
    // Check if enough time has passed to transition from OPEN to HALF_OPEN
    if (this.state === 'open') {
      const timeSinceLastFailure = Date.now() - (this.lastFailureTime ?? 0)

      if (timeSinceLastFailure > this.config.resetTimeout) {
        this.transitionToHalfOpen()
      } else {
        throw new CircuitBreakerError(
          'Circuit breaker is open - service temporarily unavailable',
          this.getStats()
        )
      }
    }

    try {
      const result = await fn()
      this.onSuccess()
      return result
    } catch (error) {
      this.onFailure()
      throw error
    }
  }

  /**
   * Handle successful execution
   */
  private onSuccess(): void {
    this.successCount++

    if (this.state === 'half-open') {
      // Success in half-open state means service recovered
      this.transitionToClosed()
    } else if (this.state === 'closed') {
      // Reset failure count on success in closed state
      this.failureCount = 0
    }
  }

  /**
   * Handle failed execution
   */
  private onFailure(): void {
    this.failureCount++
    this.lastFailureTime = Date.now()

    if (this.state === 'half-open') {
      // Failure in half-open state means service still unhealthy
      this.transitionToOpen()
    } else if (
      this.state === 'closed' &&
      this.failureCount >= this.config.failureThreshold
    ) {
      // Too many failures in closed state
      this.transitionToOpen()
    }
  }

  /**
   * Transition to CLOSED state (normal operation)
   */
  private transitionToClosed(): void {
    this.state = 'closed'
    this.failureCount = 0
    this.successCount = 0
    this.lastStateChange = Date.now()
    console.info('[CircuitBreaker] Transitioned to CLOSED state - service healthy')

    // Dispatch event
    dispatchEvent(AppEventType.API_CIRCUIT_BREAKER_CLOSED, {
      recoveryTime: Date.now() - this.lastStateChange,
    }).catch(console.error)
  }

  /**
   * Transition to OPEN state (blocking requests)
   */
  private transitionToOpen(): void {
    this.state = 'open'
    this.lastStateChange = Date.now()
    console.warn(
      `[CircuitBreaker] Transitioned to OPEN state - ${this.failureCount} failures detected`
    )

    // Dispatch event
    dispatchEvent(AppEventType.API_CIRCUIT_BREAKER_OPEN, {
      failureCount: this.failureCount,
    }).catch(console.error)
  }

  /**
   * Transition to HALF_OPEN state (testing recovery)
   */
  private transitionToHalfOpen(): void {
    this.state = 'half-open'
    this.failureCount = 0
    this.successCount = 0
    this.lastStateChange = Date.now()
    console.info('[CircuitBreaker] Transitioned to HALF_OPEN state - testing service recovery')
  }

  /**
   * Get current circuit breaker statistics
   */
  getStats(): CircuitBreakerStats {
    return {
      state: this.state,
      failureCount: this.failureCount,
      successCount: this.successCount,
      lastFailureTime: this.lastFailureTime,
      lastStateChange: this.lastStateChange,
    }
  }

  /**
   * Get current state
   */
  getState(): CircuitState {
    return this.state
  }

  /**
   * Manually reset circuit breaker (for testing/admin purposes)
   */
  reset(): void {
    this.transitionToClosed()
  }
}

/**
 * Custom error for circuit breaker open state
 */
export class CircuitBreakerError extends Error {
  constructor(
    message: string,
    public stats: CircuitBreakerStats
  ) {
    super(message)
    this.name = 'CircuitBreakerError'
  }
}
