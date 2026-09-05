/**
 * Resilience Decorator Infrastructure
 *
 * Provides decorator functions that wrap API clients with resilience patterns.
 * Follows hexagonal architecture by keeping resilience logic in infrastructure layer.
 */

import { CircuitBreaker, CircuitBreakerConfig } from './circuitBreaker'
import { RetryPolicy, RetryConfig, RetryContext } from './retryPolicy'

/**
 * Configuration for resilience decorators
 */
export interface ResilienceConfig {
  circuitBreaker?: CircuitBreakerConfig
  retry?: RetryConfig
  enableCircuitBreaker?: boolean
  enableRetry?: boolean
}

/**
 * Function type that can be wrapped with resilience
 */
export type ResilienceFunction<T> = () => Promise<T>

/**
 * Resilience decorator that wraps functions with circuit breaker and retry logic
 */
export class ResilienceDecorator {
  private circuitBreaker?: CircuitBreaker
  private retryPolicy?: RetryPolicy

  constructor(config: ResilienceConfig) {
    if (config.enableCircuitBreaker && config.circuitBreaker) {
      this.circuitBreaker = new CircuitBreaker(config.circuitBreaker)
    }

    if (config.enableRetry && config.retry) {
      this.retryPolicy = new RetryPolicy(config.retry)
    }
  }

  /**
   * Execute a function with resilience patterns applied
   */
  async execute<T>(
    fn: ResilienceFunction<T>,
    onRetry?: (context: RetryContext) => void
  ): Promise<T> {
    // Build the execution chain from innermost to outermost
    let executeFn = fn

    // Apply retry policy first (innermost)
    if (this.retryPolicy) {
      const originalFn = executeFn
      executeFn = () => this.retryPolicy!.execute(originalFn, onRetry)
    }

    // Apply circuit breaker (outermost)
    if (this.circuitBreaker) {
      const originalFn = executeFn
      executeFn = () => this.circuitBreaker!.execute(originalFn)
    }

    return executeFn()
  }

  /**
   * Get circuit breaker stats (if enabled)
   */
  getCircuitBreakerStats() {
    return this.circuitBreaker?.getStats()
  }

  /**
   * Reset circuit breaker (if enabled)
   */
  resetCircuitBreaker(): void {
    this.circuitBreaker?.reset()
  }

  /**
   * Get retry policy config (if enabled)
   */
  getRetryConfig() {
    return this.retryPolicy?.getConfig()
  }
}

/**
 * Create a resilience decorator with standard configuration
 */
export function createResilienceDecorator(
  config: ResilienceConfig
): ResilienceDecorator {
  return new ResilienceDecorator(config)
}

/**
 * Helper to create a resilience decorator from environment config
 */
export function createResilienceDecoratorFromConfig(
  apiConfig: {
    circuitBreaker: CircuitBreakerConfig
    retry: RetryConfig
    features: {
      enableCircuitBreaker: boolean
      enableRetry: boolean
    }
  }
): ResilienceDecorator {
  return new ResilienceDecorator({
    circuitBreaker: apiConfig.circuitBreaker,
    retry: apiConfig.retry,
    enableCircuitBreaker: apiConfig.features.enableCircuitBreaker,
    enableRetry: apiConfig.features.enableRetry,
  })
}
