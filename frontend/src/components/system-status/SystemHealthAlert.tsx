/**
 * SystemHealthAlert Component
 *
 * Displays alert banners for system health issues and circuit breaker problems.
 * Shows detailed information about unhealthy components and problematic breakers.
 */

import { AlertTriangle, AlertCircle } from 'lucide-react'
import { useSystemStatusStore } from '../../store/systemStatusStore'
import type { HealthCheck } from '../../types/system-status'

/**
 * Get human-readable component name
 */
function getHealthComponentName(key: string): string {
  const names: Record<string, string> = {
    github: 'GitHub API',
    claude: 'Claude Code CLI',
    disk: 'Disk Space',
    memory: 'Memory',
    claude_usage: 'Claude Code Usage',
  }
  return names[key] || key
}

/**
 * Get detailed health component information
 */
function getHealthComponentDetails(key: string, check: HealthCheck): string {
  if (!check) return 'No information available'

  switch (key) {
    case 'github':
      if (!check.healthy) {
        return check.error || 'GitHub connectivity issue'
      }
      return `Connected to ${check.tested_org || 'GitHub'} • Projects: ${check.projects_access || 'unknown'}`

    case 'disk':
      return check.healthy
        ? `${check.free_gb?.toFixed(1)}GB free (${check.usage_percent?.toFixed(1)}% used)`
        : `Low disk space: ${check.usage_percent?.toFixed(1)}% used`

    case 'memory':
      return check.healthy
        ? `${check.available_gb?.toFixed(1)}GB available (${check.usage_percent?.toFixed(1)}% used)`
        : `High memory usage: ${check.usage_percent?.toFixed(1)}%`

    case 'claude':
      return check.healthy ? 'Available' : 'Not accessible'

    default:
      return check.healthy ? 'OK' : (check.error || 'Failed')
  }
}

/**
 * Get icon for circuit breaker state
 */
function getBreakerIcon(state: string) {
  switch (state) {
    case 'half_open':
      return <AlertCircle className="w-4 h-4" />
    case 'open':
      return <AlertTriangle className="w-4 h-4" />
    default:
      return null
  }
}

/**
 * Get color class for circuit breaker state
 */
function getBreakerColor(state: string): string {
  switch (state) {
    case 'open':
      return 'text-red-500'
    case 'half_open':
      return 'text-yellow-500'
    default:
      return 'text-muted-foreground'
  }
}

export function SystemHealthAlert() {
  const {
    systemHealth,
    healthStatus,
    unhealthyComponents,
    hasOpenBreakers,
    hasHalfOpenBreakers,
    circuitBreakerSummary,
    circuitBreakers,
  } = useSystemStatusStore()

  // Get problematic circuit breakers (open or half-open)
  const problematicBreakers = circuitBreakers.filter(
    (cb) => cb.state === 'open' || cb.state === 'half_open'
  )

  // Determine if we should show health alert
  const shouldShowHealthAlert =
    systemHealth &&
    (healthStatus === 'unhealthy' ||
      healthStatus === 'error' ||
      healthStatus === 'starting' ||
      (healthStatus === 'degraded' && unhealthyComponents.length > 0))

  // Determine if we should show circuit breaker alert
  const shouldShowBreakerAlert = hasOpenBreakers || hasHalfOpenBreakers

  if (!shouldShowHealthAlert && !shouldShowBreakerAlert) {
    return null
  }

  return (
    <div className="space-y-3">
      {/* System Health Alert Banner */}
      {shouldShowHealthAlert && (
        <div
          className={`p-4 rounded-md border ${
            healthStatus === 'error' || healthStatus === 'unhealthy'
              ? 'bg-red-50 dark:bg-red-900/20 border-red-500'
              : 'bg-yellow-50 dark:bg-yellow-900/20 border-yellow-500'
          }`}
        >
          <div className="flex items-start gap-3">
            <AlertTriangle
              className={`w-5 h-5 mt-0.5 ${
                healthStatus === 'error' || healthStatus === 'unhealthy'
                  ? 'text-red-500'
                  : 'text-yellow-600 dark:text-yellow-500'
              }`}
            />
            <div className="flex-1">
              <h3
                className={`font-semibold mb-1 ${
                  healthStatus === 'error' || healthStatus === 'unhealthy'
                    ? 'text-red-700 dark:text-red-400'
                    : 'text-yellow-800 dark:text-yellow-300'
                }`}
              >
                {healthStatus === 'starting' && 'System Starting Up'}
                {healthStatus === 'error' && 'Health Check Error'}
                {healthStatus === 'unhealthy' && 'System Health Issues Detected'}
                {healthStatus === 'degraded' && 'System Running with Reduced Functionality'}
              </h3>
              <p className="text-sm text-foreground mb-2">
                {healthStatus === 'starting' && 'Orchestrator is initializing, health checks not yet complete.'}
                {healthStatus === 'error' && (systemHealth?.message || systemHealth?.error || 'Unable to retrieve system health status.')}
                {healthStatus === 'unhealthy' && `${unhealthyComponents.length} component${unhealthyComponents.length > 1 ? 's are' : ' is'} reporting issues.`}
                {healthStatus === 'degraded' && 'Core functionality is operational, but some features are unavailable.'}
              </p>
              {unhealthyComponents.length > 0 && (
                <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
                  {unhealthyComponents.map(([key, check]) => (
                    <div key={key} className="bg-background p-2 rounded border text-sm">
                      <div className="flex items-center gap-2 mb-1">
                        <AlertTriangle className="w-4 h-4 text-red-500" />
                        <span className="font-semibold">{getHealthComponentName(key)}</span>
                      </div>
                      <div className="text-xs text-muted-foreground">
                        {getHealthComponentDetails(key, check)}
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>
        </div>
      )}

      {/* Circuit Breaker Alert Banner */}
      {shouldShowBreakerAlert && (
        <div
          className={`p-4 rounded-md border ${
            hasOpenBreakers
              ? 'bg-red-50 dark:bg-red-900/20 border-red-500'
              : 'bg-yellow-50 dark:bg-yellow-900/20 border-yellow-500'
          }`}
        >
          <div className="flex items-start gap-3">
            <AlertTriangle
              className={`w-5 h-5 mt-0.5 ${
                hasOpenBreakers ? 'text-red-500' : 'text-yellow-600 dark:text-yellow-500'
              }`}
            />
            <div className="flex-1">
              <h3
                className={`font-semibold mb-1 ${
                  hasOpenBreakers
                    ? 'text-red-700 dark:text-red-400'
                    : 'text-yellow-800 dark:text-yellow-300'
                }`}
              >
                {hasOpenBreakers ? 'Circuit Breakers Open' : 'Circuit Breakers Testing Recovery'}
              </h3>
              <p className="text-sm text-foreground mb-2">
                {hasOpenBreakers
                  ? `${circuitBreakerSummary.open} circuit breaker${circuitBreakerSummary.open > 1 ? 's are' : ' is'} open. Services are failing and requests are being rejected.`
                  : `${circuitBreakerSummary.halfOpen} circuit breaker${circuitBreakerSummary.halfOpen > 1 ? 's are' : ' is'} testing recovery.`}
              </p>
              <div className="grid grid-cols-1 md:grid-cols-3 gap-2">
                {problematicBreakers.map((cb, idx) => (
                  <div key={idx} className="bg-background p-2 rounded border text-sm">
                    <div className="flex items-center gap-2 mb-1">
                      <span className={getBreakerColor(cb.state)}>{getBreakerIcon(cb.state)}</span>
                      <span className="font-semibold">{cb.name}</span>
                    </div>
                    <div className="text-xs text-muted-foreground">
                      State:{' '}
                      <span className={`font-medium ${getBreakerColor(cb.state)}`}>
                        {cb.state.replace('_', ' ').toUpperCase()}
                      </span>
                      {cb.state === 'open' && ` • Rejected: ${cb.totalRejected}`}
                      {cb.state === 'half_open' && ' • Testing...'}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
