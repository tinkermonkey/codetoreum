/**
 * System Status Store
 *
 * Zustand store for managing system status, health, and monitoring data.
 * Provides centralized state for real-time system information.
 */

import { create } from 'zustand'
import type {
  SystemStatusState,
  AgentExecution,
  ApiUsage,
  CircuitBreaker,
  SystemHealth,
  HealthStatus,
  HealthCheck,
  CircuitBreakerSummary,
  ClaudeUsageCheck,
} from '../types/system-status'

/**
 * Calculate circuit breaker summary statistics
 */
function calculateCircuitBreakerSummary(breakers: CircuitBreaker[]): CircuitBreakerSummary {
  return {
    total: breakers.length,
    closed: breakers.filter((b) => b.state === 'closed').length,
    halfOpen: breakers.filter((b) => b.state === 'half_open').length,
    open: breakers.filter((b) => b.state === 'open').length,
  }
}

/**
 * Extract API usage from system health data
 */
function extractApiUsage(health: SystemHealth | null): ApiUsage | null {
  if (!health) return null

  const checks = health.orchestrator?.checks || health.checks
  const usage = checks?.claude_usage as ClaudeUsageCheck | undefined

  if (!usage?.available) return null

  return {
    weeklyUsed: usage.weeklyUsage || 0,
    weeklyQuota: usage.weeklyQuota || 0,
    weeklyPercent: usage.weeklyUsagePercent || 0,
    sessionUsed: usage.sessionUsage || 0,
    sessionQuota: usage.sessionQuota || 0,
    sessionPercent: usage.sessionUsagePercent || 0,
    sessionRemainingMinutes: usage.sessionRemainingMinutes || 0,
  }
}

/**
 * Determine overall health status
 */
function determineHealthStatus(health: SystemHealth | null): HealthStatus {
  if (!health) return 'error'
  return health.orchestrator?.status || health.status || 'error'
}

/**
 * Extract unhealthy components from health data
 */
function extractUnhealthyComponents(health: SystemHealth | null): Array<[string, HealthCheck]> {
  if (!health) return []

  const checks = health.orchestrator?.checks || health.checks
  if (!checks) return []

  return Object.entries(checks).filter(([_key, check]) => {
    return check && typeof check === 'object' && 'healthy' in check && !check.healthy
  }) as Array<[string, HealthCheck]>
}

/**
 * System Status Store
 */
export const useSystemStatusStore = create<SystemStatusState>((set) => ({
  // Initial state
  activeAgents: [],
  agentCount: 0,
  apiUsage: null,
  circuitBreakers: [],
  circuitBreakerSummary: {
    total: 0,
    closed: 0,
    halfOpen: 0,
    open: 0,
  },
  hasOpenBreakers: false,
  hasHalfOpenBreakers: false,
  systemHealth: null,
  healthStatus: 'starting',
  unhealthyComponents: [],

  // Actions
  updateActiveAgents: (agents: AgentExecution[]) =>
    set({
      activeAgents: agents,
      agentCount: agents.length,
    }),

  updateApiUsage: (usage: ApiUsage | null) =>
    set({
      apiUsage: usage,
    }),

  updateCircuitBreakers: (breakers: CircuitBreaker[]) => {
    const summary = calculateCircuitBreakerSummary(breakers)
    set({
      circuitBreakers: breakers,
      circuitBreakerSummary: summary,
      hasOpenBreakers: summary.open > 0,
      hasHalfOpenBreakers: summary.halfOpen > 0,
    })
  },

  updateSystemHealth: (health: SystemHealth) => {
    const healthStatus = determineHealthStatus(health)
    const unhealthyComponents = extractUnhealthyComponents(health)
    const apiUsage = extractApiUsage(health)
    const breakers = health.circuitBreakers || health.orchestrator?.checks?.claude_usage ? [] : []

    set({
      systemHealth: health,
      healthStatus,
      unhealthyComponents,
      apiUsage,
    })

    // Also update circuit breakers if present in health data
    if (health.circuitBreakers) {
      const summary = calculateCircuitBreakerSummary(health.circuitBreakers)
      set({
        circuitBreakers: health.circuitBreakers,
        circuitBreakerSummary: summary,
        hasOpenBreakers: summary.open > 0,
        hasHalfOpenBreakers: summary.halfOpen > 0,
      })
    }
  },

  reset: () =>
    set({
      activeAgents: [],
      agentCount: 0,
      apiUsage: null,
      circuitBreakers: [],
      circuitBreakerSummary: {
        total: 0,
        closed: 0,
        halfOpen: 0,
        open: 0,
      },
      hasOpenBreakers: false,
      hasHalfOpenBreakers: false,
      systemHealth: null,
      healthStatus: 'starting',
      unhealthyComponents: [],
    }),
}))
