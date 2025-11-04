import React from 'react'
import { useQuery } from '@tanstack/react-query'
import { Activity, Clock, CheckCircle2, XCircle, Loader2 } from 'lucide-react'
import { format, formatDistanceToNow } from 'date-fns'
import { workItemsApi, executionsApi } from '../api/client'
import { useWebSocket } from '../hooks/useWebSocket'
import { useAuth } from '../hooks/useAuth'
import { Card } from '../components/ui/card'
import type { WorkItemStatus, ExecutionStatus } from '../types'

export default function DashboardPage() {
  const { token } = useAuth()

  // Fetch work items
  const { data: workItems = [], isLoading: loadingWorkItems } = useQuery({
    queryKey: ['workItems'],
    queryFn: () => workItemsApi.list({ limit: 20 }),
  })

  // Fetch recent executions
  const { data: executions = [], isLoading: loadingExecutions } = useQuery({
    queryKey: ['executions'],
    queryFn: () => executionsApi.list({ limit: 10 }),
  })

  // WebSocket for real-time events
  const { events, isConnected, subscribe } = useWebSocket(token)

  // Subscribe to execution events on mount
  React.useEffect(() => {
    subscribe('ExecutionStarted')
    subscribe('ExecutionCompleted')
    subscribe('ExecutionFailed')
  }, [subscribe])

  const getStatusColor = (status: WorkItemStatus | ExecutionStatus) => {
    switch (status) {
      case 'completed':
        return 'text-green-600 bg-green-50 dark:bg-green-900/20'
      case 'in_progress':
      case 'running':
        return 'text-blue-600 bg-blue-50 dark:bg-blue-900/20'
      case 'failed':
        return 'text-red-600 bg-red-50 dark:bg-red-900/20'
      case 'queued':
        return 'text-yellow-600 bg-yellow-50 dark:bg-yellow-900/20'
      case 'cancelled':
        return 'text-gray-600 bg-gray-50 dark:bg-gray-900/20'
      default:
        return 'text-gray-600 bg-gray-50 dark:bg-gray-900/20'
    }
  }

  const getStatusIcon = (status: WorkItemStatus | ExecutionStatus) => {
    switch (status) {
      case 'completed':
        return <CheckCircle2 className="h-4 w-4" />
      case 'in_progress':
      case 'running':
        return <Loader2 className="h-4 w-4 animate-spin" />
      case 'failed':
        return <XCircle className="h-4 w-4" />
      case 'queued':
        return <Clock className="h-4 w-4" />
      default:
        return <Activity className="h-4 w-4" />
    }
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h2 className="text-3xl font-bold">Dashboard</h2>
        <div className="flex items-center space-x-2">
          <div
            className={`h-2 w-2 rounded-full ${
              isConnected ? 'bg-green-500 animate-pulse' : 'bg-gray-400'
            }`}
          />
          <span className="text-sm text-muted-foreground">
            {isConnected ? 'Live' : 'Disconnected'}
          </span>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Active Work Items */}
        <Card className="p-6">
          <h3 className="text-xl font-semibold mb-4">Active Work Items</h3>
          {loadingWorkItems ? (
            <div className="flex items-center justify-center py-8">
              <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
            </div>
          ) : workItems.length === 0 ? (
            <p className="text-center py-8 text-muted-foreground">No work items found</p>
          ) : (
            <div className="space-y-3">
              {workItems.map((item) => (
                <div
                  key={item.id}
                  className="border rounded-md p-4 hover:bg-accent/50 transition-colors"
                >
                  <div className="flex items-start justify-between">
                    <div className="flex-1">
                      <h4 className="font-medium">{item.title}</h4>
                      <p className="text-sm text-muted-foreground line-clamp-2 mt-1">
                        {item.description}
                      </p>
                      {item.current_stage && (
                        <p className="text-xs text-muted-foreground mt-2">
                          Stage: {item.current_stage}
                        </p>
                      )}
                    </div>
                    <span
                      className={`flex items-center space-x-1 px-2 py-1 rounded-md text-xs font-medium ${getStatusColor(
                        item.status
                      )}`}
                    >
                      {getStatusIcon(item.status)}
                      <span>{item.status}</span>
                    </span>
                  </div>
                  <div className="flex items-center space-x-4 mt-3 text-xs text-muted-foreground">
                    <span>Updated {formatDistanceToNow(new Date(item.updated_at), { addSuffix: true })}</span>
                    {item.labels.length > 0 && (
                      <div className="flex items-center space-x-1">
                        {item.labels.slice(0, 3).map((label) => (
                          <span key={label} className="px-2 py-0.5 rounded-full bg-muted">
                            {label}
                          </span>
                        ))}
                      </div>
                    )}
                  </div>
                </div>
              ))}
            </div>
          )}
        </Card>

        {/* Recent Executions */}
        <Card className="p-6">
          <h3 className="text-xl font-semibold mb-4">Recent Executions</h3>
          {loadingExecutions ? (
            <div className="flex items-center justify-center py-8">
              <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
            </div>
          ) : executions.length === 0 ? (
            <p className="text-center py-8 text-muted-foreground">No executions found</p>
          ) : (
            <div className="space-y-3">
              {executions.map((execution) => (
                <div
                  key={execution.id}
                  className="border rounded-md p-4 hover:bg-accent/50 transition-colors"
                >
                  <div className="flex items-start justify-between">
                    <div className="flex-1">
                      <h4 className="font-medium">{execution.work_item_title}</h4>
                      <p className="text-sm text-muted-foreground mt-1">
                        Agent: {execution.agent_name}
                      </p>
                    </div>
                    <span
                      className={`flex items-center space-x-1 px-2 py-1 rounded-md text-xs font-medium ${getStatusColor(
                        execution.status
                      )}`}
                    >
                      {getStatusIcon(execution.status)}
                      <span>{execution.status}</span>
                    </span>
                  </div>
                  <div className="flex items-center space-x-4 mt-3 text-xs text-muted-foreground">
                    {execution.started_at && (
                      <span>
                        Started {formatDistanceToNow(new Date(execution.started_at), { addSuffix: true })}
                      </span>
                    )}
                    {execution.duration_seconds && (
                      <span>{execution.duration_seconds}s</span>
                    )}
                  </div>
                </div>
              ))}
            </div>
          )}
        </Card>
      </div>

      {/* Real-time Events */}
      <Card className="p-6">
        <h3 className="text-xl font-semibold mb-4">
          Real-time Events
          <span className="ml-2 text-sm font-normal text-muted-foreground">
            (Last 10 events)
          </span>
        </h3>
        {events.length === 0 ? (
          <p className="text-center py-8 text-muted-foreground">
            No recent events. Events will appear here in real-time.
          </p>
        ) : (
          <div className="space-y-2">
            {events.slice(0, 10).map((event, index) => (
              <div
                key={`${event.timestamp}-${index}`}
                className="border-l-4 border-primary/50 pl-4 py-2 bg-accent/30 rounded-r"
              >
                <div className="flex items-start justify-between">
                  <div className="flex-1">
                    <span className="font-medium">{event.type}</span>
                    {event.data && (
                      <pre className="text-xs text-muted-foreground mt-1 overflow-x-auto">
                        {JSON.stringify(event.data, null, 2)}
                      </pre>
                    )}
                  </div>
                  <span className="text-xs text-muted-foreground whitespace-nowrap ml-4">
                    {format(new Date(event.timestamp), 'HH:mm:ss')}
                  </span>
                </div>
              </div>
            ))}
          </div>
        )}
      </Card>
    </div>
  )
}
