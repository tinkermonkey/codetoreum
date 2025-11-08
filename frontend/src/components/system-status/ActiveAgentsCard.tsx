/**
 * ActiveAgentsCard Component
 *
 * Displays count and status of actively running agent executions.
 */

import { useState } from 'react'
import { Activity, ChevronDown, ChevronUp } from 'lucide-react'
import { StatusCard } from './StatusCard'
import { Badge } from '../ui/badge'
import { useSystemStatusStore } from '../../store/systemStatusStore'
import { formatRelativeTime } from '../../lib/utils'

export function ActiveAgentsCard() {
  const [isExpanded, setIsExpanded] = useState(false)
  const { activeAgents, agentCount } = useSystemStatusStore()

  const handleToggle = () => {
    if (agentCount > 0) {
      setIsExpanded(!isExpanded)
    }
  }

  return (
    <StatusCard
      title="Active Agents"
      isExpandable={agentCount > 0}
      isExpanded={isExpanded}
      onClick={handleToggle}
      headerAction={
        <div className="flex items-center gap-2">
          <Badge variant={agentCount > 0 ? 'success' : 'secondary'}>
            {agentCount}
          </Badge>
          {agentCount > 0 && (
            isExpanded ? <ChevronUp className="h-3 w-3" /> : <ChevronDown className="h-3 w-3" />
          )}
        </div>
      }
    >
      {agentCount === 0 ? (
        <p className="text-xs text-muted-foreground">No active agents</p>
      ) : (
        <>
          {!isExpanded ? (
            <div className="flex items-center gap-2">
              <Activity className="h-4 w-4 text-green-500 animate-pulse" />
              <span className="text-sm font-medium">
                {agentCount} agent{agentCount > 1 ? 's' : ''} running
              </span>
            </div>
          ) : (
            <div className="space-y-2 mt-2">
              {activeAgents.slice(0, 5).map((agent) => (
                <div
                  key={agent.id}
                  className="text-xs bg-secondary/50 rounded p-2"
                >
                  <div className="flex items-center justify-between mb-1">
                    <span className="font-semibold truncate max-w-[120px]" title={agent.agentName}>
                      {agent.agentName}
                    </span>
                    <Badge variant="success" className="text-[10px] px-1.5 py-0">
                      Running
                    </Badge>
                  </div>
                  <div className="text-muted-foreground">
                    {agent.project}
                    {agent.issueNumber && ` #${agent.issueNumber}`}
                  </div>
                  <div className="text-muted-foreground mt-0.5">
                    Started {formatRelativeTime(agent.startedAt)}
                  </div>
                </div>
              ))}
              {agentCount > 5 && (
                <p className="text-xs text-muted-foreground italic text-center">
                  +{agentCount - 5} more
                </p>
              )}
            </div>
          )}
        </>
      )}
    </StatusCard>
  )
}
