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
 * - Automatic data refresh
 */

import { useEffect } from 'react'
import { useSystemStatus } from '../../hooks/useSystemStatus'
import { useActiveAgents } from '../../hooks/useActiveAgents'
import { SystemHealthAlert } from './SystemHealthAlert'
import { ActiveAgentsCard } from './ActiveAgentsCard'
import { ApiUsageCard } from './ApiUsageCard'
import { CircuitBreakersCard } from './CircuitBreakersCard'

export function SystemStatusHeader() {
  // Fetch system health (polls every 5 seconds)
  const { isLoading: isHealthLoading, error: healthError } = useSystemStatus()

  // Fetch active agents (polls every 10 seconds + WebSocket updates)
  const { isLoading: isAgentsLoading, error: agentsError } = useActiveAgents()

  // Log errors in development
  useEffect(() => {
    if (healthError) {
      console.error('System health fetch error:', healthError)
    }
    if (agentsError) {
      console.error('Active agents fetch error:', agentsError)
    }
  }, [healthError, agentsError])

  return (
    <div className="space-y-3">
      {/* Alert Banners */}
      <SystemHealthAlert />

      {/* Status Cards */}
      <div className="flex gap-4 flex-wrap">
        {/* Show loading state only on initial load */}
        {isHealthLoading && isAgentsLoading ? (
          <div className="text-sm text-muted-foreground">Loading system status...</div>
        ) : (
          <>
            <ActiveAgentsCard />
            <ApiUsageCard />
            <CircuitBreakersCard />
          </>
        )}
      </div>
    </div>
  )
}
