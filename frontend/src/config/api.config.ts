/**
 * API Configuration
 *
 * Centralized configuration for API client behavior.
 * Values can be overridden via environment variables.
 */

export const apiConfig = {
  // Base URL for API requests
  // Use relative path to leverage Vite proxy in development
  // In production, set VITE_API_BASE_URL to full backend URL
  baseURL: import.meta.env.VITE_API_BASE_URL || '/api',

  // Request timeout in milliseconds
  timeout: parseInt(import.meta.env.VITE_API_TIMEOUT || '30000', 10),

  // Retry configuration
  retry: {
    maxRetries: parseInt(import.meta.env.VITE_API_MAX_RETRIES || '3', 10),
    baseDelay: parseInt(import.meta.env.VITE_API_RETRY_BASE_DELAY || '1000', 10),
    maxDelay: parseInt(import.meta.env.VITE_API_RETRY_MAX_DELAY || '30000', 10),
    jitter: parseFloat(import.meta.env.VITE_API_RETRY_JITTER || '0.3'),
  },

  // Circuit breaker configuration
  circuitBreaker: {
    failureThreshold: parseInt(import.meta.env.VITE_API_CB_FAILURE_THRESHOLD || '5', 10),
    resetTimeout: parseInt(import.meta.env.VITE_API_CB_RESET_TIMEOUT || '60000', 10),
  },

  // Feature flags
  features: {
    enableLogging: import.meta.env.VITE_API_ENABLE_LOGGING !== 'false',
    enableRetry: import.meta.env.VITE_API_ENABLE_RETRY !== 'false',
    enableCircuitBreaker: import.meta.env.VITE_API_ENABLE_CIRCUIT_BREAKER !== 'false',
  },
} as const

export type ApiConfig = typeof apiConfig
