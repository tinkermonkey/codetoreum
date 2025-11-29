/**
 * Polling Configuration
 *
 * Centralized configuration for all polling intervals in the application.
 * Can be overridden via environment variables for production tuning.
 */

const getEnvNumber = (key: string, defaultValue: number): number => {
  const value = import.meta.env[key];
  return value ? parseInt(value, 10) : defaultValue;
};

export const POLLING_CONFIG = {
  /**
   * System health polling interval (milliseconds)
   * Default: 5000ms (5 seconds)
   * Env: VITE_POLL_SYSTEM_HEALTH_MS
   */
  SYSTEM_HEALTH: getEnvNumber('VITE_POLL_SYSTEM_HEALTH_MS', 5000),

  /**
   * Active agents polling interval (milliseconds)
   * Default: 10000ms (10 seconds)
   * Env: VITE_POLL_ACTIVE_AGENTS_MS
   */
  ACTIVE_AGENTS: getEnvNumber('VITE_POLL_ACTIVE_AGENTS_MS', 10000),

  /**
   * Stale time for cached data (milliseconds)
   * Default: 4000ms (4 seconds)
   * Env: VITE_STALE_TIME_MS
   */
  STALE_TIME: getEnvNumber('VITE_STALE_TIME_MS', 4000),
} as const;

export const RETRY_CONFIG = {
  /**
   * Maximum number of retry attempts
   * Default: 3
   * Env: VITE_RETRY_MAX_ATTEMPTS
   */
  MAX_ATTEMPTS: getEnvNumber('VITE_RETRY_MAX_ATTEMPTS', 3),

  /**
   * Base delay for exponential backoff (milliseconds)
   * Default: 1000ms (1 second)
   * Env: VITE_RETRY_BASE_DELAY_MS
   */
  BASE_DELAY: getEnvNumber('VITE_RETRY_BASE_DELAY_MS', 1000),
} as const;
