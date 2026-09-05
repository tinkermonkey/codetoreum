/**
 * System Health Test Fixtures
 *
 * Mock data for system health, API usage, and circuit breakers used in E2E tests.
 */

import type {
  SystemHealth,
  CircuitBreaker,
  ApiUsage,
  HealthCheck,
  ClaudeUsageCheck,
} from '../../src/types/system-status'

/**
 * Sample GitHub health check (healthy)
 */
export const healthyGitHubCheck: HealthCheck = {
  available: true,
  healthy: true,
  tested_org: 'codetoreum',
  projects_access: 'read-write',
}

/**
 * Sample Claude health check (healthy)
 */
export const healthyClaudeCheck: HealthCheck = {
  available: true,
  healthy: true,
  message: 'Claude API is operational',
}

/**
 * Sample disk health check (healthy)
 */
export const healthyDiskCheck: HealthCheck = {
  available: true,
  healthy: true,
  free_gb: 125.5,
  usage_percent: 45,
  available_gb: 280,
}

/**
 * Sample memory health check (healthy)
 */
export const healthyMemoryCheck: HealthCheck = {
  available: true,
  healthy: true,
  free_gb: 6.2,
  usage_percent: 38,
  available_gb: 16,
}

/**
 * Sample Claude usage check (healthy)
 */
export const healthyClaudeUsageCheck: ClaudeUsageCheck = {
  available: true,
  healthy: true,
  weeklyUsage: 15000000,
  weeklyQuota: 50000000,
  weeklyUsagePercent: 30,
  sessionUsage: 2500000,
  sessionQuota: 5000000,
  sessionUsagePercent: 50,
  sessionRemainingMinutes: 120,
  lastDayTokens: 3200000,
  lastDayCost: 48.5,
}

/**
 * Sample Claude usage check (degraded - high usage)
 */
export const degradedClaudeUsageCheck: ClaudeUsageCheck = {
  available: true,
  healthy: false,
  weeklyUsage: 42000000,
  weeklyQuota: 50000000,
  weeklyUsagePercent: 84,
  sessionUsage: 4200000,
  sessionQuota: 5000000,
  sessionUsagePercent: 84,
  sessionRemainingMinutes: 30,
  lastDayTokens: 8500000,
  lastDayCost: 127.5,
  warnings: ['Weekly usage is above 80% threshold'],
}

/**
 * Sample system health (healthy state)
 */
export const healthySystemHealth: SystemHealth = {
  status: 'healthy',
  message: 'All systems operational',
  orchestrator: {
    status: 'healthy',
    checks: {
      github: healthyGitHubCheck,
      claude: healthyClaudeCheck,
      disk: healthyDiskCheck,
      memory: healthyMemoryCheck,
      claude_usage: healthyClaudeUsageCheck,
    },
  },
  checks: {
    github: healthyGitHubCheck,
    claude: healthyClaudeCheck,
    disk: healthyDiskCheck,
    memory: healthyMemoryCheck,
    claude_usage: healthyClaudeUsageCheck,
  },
  circuitBreakers: [],
}

/**
 * Sample system health (degraded state)
 */
export const degradedSystemHealth: SystemHealth = {
  status: 'degraded',
  message: 'Some components experiencing issues',
  orchestrator: {
    status: 'degraded',
    checks: {
      github: healthyGitHubCheck,
      claude: healthyClaudeCheck,
      disk: healthyDiskCheck,
      memory: healthyMemoryCheck,
      claude_usage: degradedClaudeUsageCheck,
    },
  },
  checks: {
    github: healthyGitHubCheck,
    claude: healthyClaudeCheck,
    disk: healthyDiskCheck,
    memory: healthyMemoryCheck,
    claude_usage: degradedClaudeUsageCheck,
  },
  circuitBreakers: [],
}

/**
 * Sample circuit breaker (closed/healthy)
 */
export const closedCircuitBreaker: CircuitBreaker = {
  name: 'github_api',
  state: 'closed',
  failureCount: 0,
  successCount: 150,
  totalRejected: 0,
  lastFailure: undefined,
  rateLimit: {
    remaining: 4500,
    limit: 5000,
    percentageUsed: 10,
  },
}

/**
 * Sample circuit breaker (half-open)
 */
export const halfOpenCircuitBreaker: CircuitBreaker = {
  name: 'claude_api',
  state: 'half_open',
  failureCount: 3,
  successCount: 1,
  totalRejected: 12,
  lastFailure: new Date(Date.now() - 120000).toISOString(),
  rateLimit: {
    remaining: 45,
    limit: 50,
    percentageUsed: 10,
  },
}

/**
 * Sample circuit breaker (open/unhealthy)
 */
export const openCircuitBreaker: CircuitBreaker = {
  name: 'docker_engine',
  state: 'open',
  failureCount: 5,
  successCount: 0,
  totalRejected: 25,
  lastFailure: new Date(Date.now() - 30000).toISOString(),
  rateLimit: undefined,
}

/**
 * Collection of sample circuit breakers
 */
export const sampleCircuitBreakers: CircuitBreaker[] = [
  closedCircuitBreaker,
  halfOpenCircuitBreaker,
  openCircuitBreaker,
]

/**
 * Sample API usage (healthy)
 */
export const healthyApiUsage: ApiUsage = {
  weeklyUsed: 15000000,
  weeklyQuota: 50000000,
  weeklyPercent: 30,
  sessionUsed: 2500000,
  sessionQuota: 5000000,
  sessionPercent: 50,
  sessionRemainingMinutes: 120,
}

/**
 * Sample API usage (high usage)
 */
export const highApiUsage: ApiUsage = {
  weeklyUsed: 42000000,
  weeklyQuota: 50000000,
  weeklyPercent: 84,
  sessionUsed: 4200000,
  sessionQuota: 5000000,
  sessionPercent: 84,
  sessionRemainingMinutes: 30,
}

/**
 * Sample system health with circuit breakers
 */
export const systemHealthWithBreakers: SystemHealth = {
  status: 'degraded',
  message: 'Circuit breakers open',
  orchestrator: {
    status: 'degraded',
    checks: {
      github: healthyGitHubCheck,
      claude: healthyClaudeCheck,
      disk: healthyDiskCheck,
      memory: healthyMemoryCheck,
      claude_usage: healthyClaudeUsageCheck,
    },
  },
  checks: {
    github: healthyGitHubCheck,
    claude: healthyClaudeCheck,
    disk: healthyDiskCheck,
    memory: healthyMemoryCheck,
    claude_usage: healthyClaudeUsageCheck,
  },
  circuitBreakers: sampleCircuitBreakers,
}
