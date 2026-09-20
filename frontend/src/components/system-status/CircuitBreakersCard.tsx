/**
 * CircuitBreakersCard Component
 *
 * Displays circuit breaker states with visual indicators.
 * Shows individual breaker status and rate limit information.
 */

import { useState } from 'react'
import { CheckCircle, XCircle, AlertCircle, ChevronDown, ChevronUp } from 'lucide-react'
import { StatusCard } from './StatusCard'
import { Badge } from '../ui/badge'
import { useSystemStatusStore } from '../../store/systemStatusStore'
import type { CircuitBreakerState } from '../../types/system-status'

/**
 * Get icon for circuit breaker state
 */
function getStateIcon(state: CircuitBreakerState) {
  switch (state) {
    case 'closed':
      return <CheckCircle className="h-3 w-3 text-success" aria-hidden />
    case 'half_open':
      return <AlertCircle className="h-3 w-3 text-warning" aria-hidden />
    case 'open':
      return <XCircle className="h-3 w-3 text-destructive" aria-hidden />
  }
}

/**
 * Get label for circuit breaker state
 */
function getStateLabel(state: CircuitBreakerState): string {
  switch (state) {
    case 'closed':
      return 'Closed'
    case 'half_open':
      return 'Half Open'
    case 'open':
      return 'Open'
  }
}

/**
 * Get badge variant for circuit breaker state
 */
function getStateBadgeVariant(state: CircuitBreakerState): 'success' | 'warning' | 'error' {
  switch (state) {
    case 'closed':
      return 'success'
    case 'half_open':
      return 'warning'
    case 'open':
      return 'error'
  }
}

export function CircuitBreakersCard() {
  const [isExpanded, setIsExpanded] = useState(false)
  const { circuitBreakers, circuitBreakerSummary } = useSystemStatusStore()
  const maxDisplayedBreakers = 5

  const handleToggle = () => {
    if (circuitBreakers.length > 0) {
      setIsExpanded(!isExpanded)
    }
  }

  return (
    <StatusCard
      title="Circuit Breakers"
      isExpandable={circuitBreakers.length > 0}
      isExpanded={isExpanded}
      onClick={circuitBreakers.length > 0 ? handleToggle : undefined}
      headerAction={
        <div className="flex items-center gap-2">
          <Badge variant="secondary">
            {circuitBreakerSummary.total}
          </Badge>
          {circuitBreakers.length > 0 && (
            isExpanded ? <ChevronUp className="h-3 w-3" aria-hidden /> : <ChevronDown className="h-3 w-3" aria-hidden />
          )}
        </div>
      }
    >
      {circuitBreakers.length === 0 ? (
        <p className="text-xs text-muted-foreground">No breakers</p>
      ) : (
        <>
          {!isExpanded ? (
            <div className="space-y-1">
              <div className="flex items-center justify-between text-xs">
                <span className="text-muted-foreground">Closed</span>
                <span className="font-semibold text-success">{circuitBreakerSummary.closed}</span>
              </div>
              {circuitBreakerSummary.halfOpen > 0 && (
                <div className="flex items-center justify-between text-xs">
                  <span className="text-muted-foreground">Half Open</span>
                  <span className="font-semibold text-warning">{circuitBreakerSummary.halfOpen}</span>
                </div>
              )}
              {circuitBreakerSummary.open > 0 && (
                <div className="flex items-center justify-between text-xs">
                  <span className="text-muted-foreground">Open</span>
                  <span className="font-semibold text-destructive">{circuitBreakerSummary.open}</span>
                </div>
              )}
            </div>
          ) : (
            <div className="space-y-2 mt-2">
              {circuitBreakers.slice(0, maxDisplayedBreakers).map((cb, idx) => (
                <div
                  key={idx}
                  className="text-xs bg-secondary/50 rounded p-2"
                >
                  <div className="flex items-center justify-between mb-1">
                    <div className="flex items-center gap-1.5">
                      {getStateIcon(cb.state)}
                      <span className="font-semibold truncate max-w-[100px]" title={cb.name}>
                        {cb.name}
                      </span>
                    </div>
                    <Badge variant={getStateBadgeVariant(cb.state)} className="text-[10px] px-1.5 py-0">
                      {getStateLabel(cb.state)}
                    </Badge>
                  </div>
                  {cb.rateLimit && (
                    <div className="text-muted-foreground">
                      API: {cb.rateLimit.remaining}/{cb.rateLimit.limit} ({cb.rateLimit.percentageUsed.toFixed(0)}%)
                    </div>
                  )}
                  {cb.state === 'open' && (
                    <div className="text-muted-foreground">
                      Rejected: {cb.totalRejected}
                    </div>
                  )}
                </div>
              ))}
              {circuitBreakers.length > maxDisplayedBreakers && (
                <p className="text-xs text-muted-foreground italic text-center">
                  +{circuitBreakers.length - maxDisplayedBreakers} more
                </p>
              )}
            </div>
          )}
        </>
      )}
    </StatusCard>
  )
}
