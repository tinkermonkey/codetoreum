/**
 * ApiUsageCard Component
 *
 * Displays Claude API usage quotas with progress bars.
 * Shows both weekly and session quotas with visual indicators.
 */

import { Progress } from '../ui/progress'
import { StatusCard } from './StatusCard'
import { useSystemStatusStore } from '../../store/systemStatusStore'

/**
 * Format token count for display
 */
function formatTokens(tokens: number): string {
  if (!tokens) return '0'
  const millions = tokens / 1000000
  return millions >= 1000 ? `${(millions / 1000).toFixed(1)}B` : `${millions.toFixed(0)}M`
}

/**
 * Get progress bar color based on usage percentage
 */
function getQuotaColor(percent: number): string {
  if (percent >= 90) return 'bg-red-500'
  if (percent >= 75) return 'bg-yellow-500'
  return 'bg-green-500'
}

export function ApiUsageCard() {
  const { apiUsage } = useSystemStatusStore()

  if (!apiUsage) {
    return null
  }

  const weeklyPercent = apiUsage.weeklyPercent || 0
  const sessionPercent = apiUsage.sessionPercent || 0

  return (
    <StatusCard title="Claude Usage">
      <div className="space-y-2">
        {apiUsage.weeklyQuota > 0 && (
          <div>
            <div className="flex justify-between items-center text-xs mb-0.5">
              <span className="text-muted-foreground">Weekly</span>
              <span className="font-semibold">
                {formatTokens(apiUsage.weeklyUsed)}/{formatTokens(apiUsage.weeklyQuota)}
              </span>
            </div>
            <Progress
              value={weeklyPercent}
              max={100}
              className="h-1.5 bg-secondary"
              indicatorClassName={getQuotaColor(weeklyPercent)}
            />
          </div>
        )}
        {apiUsage.sessionQuota > 0 && (
          <div>
            <div className="flex justify-between items-center text-xs mb-0.5">
              <span className="text-muted-foreground">
                Session ({apiUsage.sessionRemainingMinutes || 0}m)
              </span>
              <span className="font-semibold">
                {formatTokens(apiUsage.sessionUsed)}/{formatTokens(apiUsage.sessionQuota)}
              </span>
            </div>
            <Progress
              value={sessionPercent}
              max={100}
              className="h-1.5 bg-secondary"
              indicatorClassName={getQuotaColor(sessionPercent)}
            />
          </div>
        )}
      </div>
    </StatusCard>
  )
}
