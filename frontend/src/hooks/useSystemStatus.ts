/**
 * System Status Hook
 *
 * Fetches component health + Claude API usage and normalizes into SystemHealth
 * for the dashboard status header.
 */

import { useQuery } from '@tanstack/react-query'
import { useEffect } from 'react'
import { apiClient } from '../api/client'
import { useSystemStatusStore } from '../store/systemStatusStore'
import type { HealthCheck, SystemHealth, SystemHealthChecks } from '../types/system-status'
import type { ApiError } from '../types/errors'
import { POLLING_CONFIG, RETRY_CONFIG } from '../config/polling'

export const systemHealthQueryKey = ['system-health']

interface MetricsHealthComponent {
  component_name: string
  status: string
  message?: string | null
}

interface MetricsHealthResponse {
  status: string
  components?: MetricsHealthComponent[]
  uptime_seconds?: number
  version?: string
}

interface ApiUsageResponse {
  claude?: {
    available?: boolean
    weeklyUsage?: number
    weeklyQuota?: number
    weeklyUsagePercent?: number
    sessionUsage?: number
    sessionQuota?: number
    sessionUsagePercent?: number
    sessionRemainingMinutes?: number
  }
}

function mapComponentName(name: string): keyof SystemHealthChecks | string {
  switch (name) {
    case 'github_api':
      return 'github'
    case 'docker_runtime':
      return 'docker'
    default:
      return name
  }
}

function toHealthCheck(component: MetricsHealthComponent): HealthCheck {
  const healthy = component.status === 'healthy'
  return {
    available: healthy,
    healthy,
    message: component.message ?? undefined,
  }
}

async function fetchApiUsage(): Promise<{ usage: ApiUsageResponse | null; error?: string }> {
  try {
    const usage = await apiClient.get<ApiUsageResponse>('/metrics/api-usage')
    return { usage }
  } catch (err) {
    const apiError = err as ApiError
    console.error('[useSystemStatus] /metrics/api-usage request failed', apiError)
    return { usage: null, error: apiError.message || 'Failed to load API usage' }
  }
}

/**
 * Normalize backend metrics payloads into the SystemHealth shape the UI expects.
 */
async function fetchSystemHealth(): Promise<SystemHealth> {
  const [health, { usage, error: usageError }] = await Promise.all([
    apiClient.get<MetricsHealthResponse>('/metrics/health'),
    fetchApiUsage(),
  ])

  const checks: SystemHealthChecks = {}

  for (const component of health.components || []) {
    const key = mapComponentName(component.component_name)
    // Store known keys on checks; unknown components still useful via unhealthy list casting
    ;(checks as Record<string, HealthCheck>)[key] = toHealthCheck(component)
  }

  if (usageError) {
    checks.claude_usage = {
      available: false,
      healthy: false,
      error: usageError,
    }
  } else if (usage?.claude) {
    const c = usage.claude
    checks.claude_usage = {
      available: Boolean(c.available),
      healthy: Boolean(c.available),
      weeklyUsage: c.weeklyUsage,
      weeklyQuota: c.weeklyQuota,
      weeklyUsagePercent: c.weeklyUsagePercent,
      sessionUsage: c.sessionUsage,
      sessionQuota: c.sessionQuota,
      sessionUsagePercent: c.sessionUsagePercent,
      sessionRemainingMinutes: c.sessionRemainingMinutes,
    }
  }

  return {
    status: (health.status as SystemHealth['status']) || 'error',
    checks,
  }
}

function calculateRetryDelay(attemptIndex: number): number {
  return Math.min(RETRY_CONFIG.BASE_DELAY * Math.pow(2, attemptIndex), 30000)
}

export function useSystemStatus() {
  const updateSystemHealth = useSystemStatusStore((state) => state.updateSystemHealth)

  const query = useQuery({
    queryKey: systemHealthQueryKey,
    queryFn: fetchSystemHealth,
    refetchInterval: POLLING_CONFIG.SYSTEM_HEALTH,
    staleTime: POLLING_CONFIG.STALE_TIME,
    retry: RETRY_CONFIG.MAX_ATTEMPTS,
    retryDelay: calculateRetryDelay,
  })

  useEffect(() => {
    if (query.data) {
      updateSystemHealth(query.data)
    }
  }, [query.data, updateSystemHealth])

  return query
}
