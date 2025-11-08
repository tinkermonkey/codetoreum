/**
 * SystemStatusHeader Component
 *
 * Main container for system status information.
 * Displays active agents, API usage, circuit breakers, and system health alerts.
 *
 * Features:
 * - Real-time updates via WebSocket and polling
 * - Expandable cards for detailed information
 * - Alert banners for critical issues
 * - Automatic data refresh with retry logic
 * - Error boundaries for fault isolation
 */

import { useEffect } from 'react'
import { ErrorBoundary } from '../ErrorBoundary'
import { useSystemStatus } from '../../hooks/useSystemStatus'
import { useActiveAgents } from '../../hooks/useActiveAgents'
import { SystemHealthAlert } from './SystemHealthAlert'
import { ActiveAgentsCard } from './ActiveAgentsCard'
import { ApiUsageCard } from './ApiUsageCard'
import { CircuitBreakersCard } from './CircuitBreakersCard'

/**
 * Error fallback for individual status cards
 */
function StatusCardErrorFallback() {
  return (
    <div className="rounded-lg border border-red-200 dark:border-red-800 bg-red-50 dark:bg-red-900/20 p-3">
      <p className="text-sm text-red-800 dark:text-red-200">
        Failed to load status card
      </p>
    </div>
  )
}

function SystemStatusHeaderContent() {
  // Fetch system health (polls with configurable interval)
  const { isLoading: isHealthLoading, error: healthError } = useSystemStatus()

  // Fetch active agents (polls + WebSocket updates with configurable interval)
  const { isLoading: isAgentsLoading, error: agentsError } = useActiveAgents()

  // Log errors in development
  useEffect(() => {
    if (healthError) {
      console.error('[SystemStatusHeader] System health fetch error:', healthError)
    }
    if (agentsError) {
      console.error('[SystemStatusHeader] Active agents fetch error:', agentsError)
    }
  }, [healthError, agentsError])

  return (
    <div className="space-y-3">
      {/* Alert Banners */}
      <ErrorBoundary fallback={StatusCardErrorFallback}>
        <SystemHealthAlert />
      </ErrorBoundary>

      {/* Status Cards */}
      <div className="flex gap-4 flex-wrap">
        {/* Show loading state only on initial load */}
        {isHealthLoading && isAgentsLoading ? (
          <div className="text-sm text-muted-foreground">Loading system status...</div>
        ) : (
          <>
            <ErrorBoundary fallback={StatusCardErrorFallback}>
              <ActiveAgentsCard />
            </ErrorBoundary>
            <ErrorBoundary fallback={StatusCardErrorFallback}>
              <ApiUsageCard />
            </ErrorBoundary>
            <ErrorBoundary fallback={StatusCardErrorFallback}>
              <CircuitBreakersCard />
            </ErrorBoundary>
          </>
        )}
      </div>
    </div>
  )
}

export function SystemStatusHeader() {
  return (
    <ErrorBoundary>
      <SystemStatusHeaderContent />
    </ErrorBoundary>
  )
}
