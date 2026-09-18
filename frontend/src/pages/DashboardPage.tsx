import React from 'react'
import { Link } from 'react-router-dom'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import {
  Activity,
  Clock,
  CheckCircle2,
  XCircle,
  Loader2,
  CircleDot,
  ArrowRight,
  Radio,
  AlertCircle,
} from 'lucide-react'
import { format, formatDistanceToNow } from 'date-fns'
import { workItemsApi, executionsApi } from '../api/client'
import { useWebSocket } from '../hooks/useWebSocket'
import { useAuth } from '../hooks/useAuth'
import { Skeleton } from '../components/ui/skeleton'
import { PageHeader } from '../components/layout/PageHeader'
import { cn } from '../lib/utils'
import type { WorkItemStatus, ExecutionStatus, WorkItem, ExecutionSummary } from '../types'

function statusTone(status: WorkItemStatus | ExecutionStatus) {
  switch (status) {
    case 'completed':
      return 'bg-success/10 text-success'
    case 'in_progress':
    case 'running':
      return 'bg-primary/10 text-primary'
    case 'failed':
      return 'bg-destructive/10 text-destructive'
    case 'queued':
    case 'pending':
      return 'bg-warning/10 text-warning'
    default:
      return 'bg-muted text-muted-foreground'
  }
}

function statusIcon(status: WorkItemStatus | ExecutionStatus, live?: boolean) {
  switch (status) {
    case 'completed':
      return <CheckCircle2 className="h-3.5 w-3.5" aria-hidden />
    case 'in_progress':
    case 'running':
      return live ? (
        <Loader2 className="h-3.5 w-3.5 animate-spin" aria-hidden />
      ) : (
        <CircleDot className="h-3.5 w-3.5" aria-hidden />
      )
    case 'failed':
      return <XCircle className="h-3.5 w-3.5" aria-hidden />
    case 'queued':
    case 'pending':
      return <Clock className="h-3.5 w-3.5" aria-hidden />
    default:
      return <Activity className="h-3.5 w-3.5" aria-hidden />
  }
}

function StatusPill({
  status,
  live,
}: {
  status: WorkItemStatus | ExecutionStatus
  live?: boolean
}) {
  const label = status.replace(/_/g, ' ')
  return (
    <span
      className={cn(
        'inline-flex shrink-0 items-center gap-1 rounded-full px-2 py-0.5 text-xs font-medium capitalize',
        statusTone(status)
      )}
      title={live ? 'Agent is running' : undefined}
    >
      {statusIcon(status, live)}
      <span>{label}</span>
      <span className="sr-only">{live ? ', live execution' : ''}</span>
    </span>
  )
}

function EmptyState({
  title,
  body,
  action,
}: {
  title: string
  body: string
  action?: React.ReactNode
}) {
  return (
    <div className="flex flex-col items-start gap-3 px-1 py-10">
      <p className="text-[15px] font-medium text-foreground">{title}</p>
      <p className="max-w-sm text-sm text-muted-foreground text-balance">{body}</p>
      {action}
    </div>
  )
}

function ListSkeleton() {
  return (
    <div className="space-y-3 p-1" aria-hidden>
      {[0, 1, 2].map((i) => (
        <div key={i} className="space-y-2 rounded-lg border border-border/60 p-4">
          <Skeleton className="h-4 w-2/3" />
          <Skeleton className="h-3 w-full" />
          <Skeleton className="h-3 w-1/3" />
        </div>
      ))}
    </div>
  )
}

function ErrorState({ message }: { message: string }) {
  return (
    <div className="flex items-start gap-2 px-1 py-6 text-sm text-destructive">
      <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" aria-hidden />
      <p>{message}</p>
    </div>
  )
}

export default function DashboardPage() {
  const { isAuthenticated, isLoading: isAuthLoading } = useAuth()
  const queryClient = useQueryClient()

  const {
    data: workItems = [],
    isLoading: loadingWorkItems,
    error: workItemsError,
  } = useQuery({
    queryKey: ['workItems'],
    queryFn: () => workItemsApi.getAll(),
  })

  const {
    data: executions = [],
    isLoading: loadingExecutions,
    error: executionsError,
  } = useQuery({
    queryKey: ['executions'],
    queryFn: () => executionsApi.getAll(),
  })

  const runningWorkItemIds = React.useMemo(() => {
    return new Set(
      executions
        .filter((e: ExecutionSummary) =>
          ['running', 'queued', 'pending', 'initialized'].includes(e.status)
        )
        .map((e: ExecutionSummary) => e.work_item_id)
        .filter(Boolean)
    )
  }, [executions])

  const activeWorkItems = React.useMemo(() => {
    const terminal = new Set(['completed', 'failed', 'cancelled'])
    return workItems.filter((item: WorkItem) => !terminal.has(item.status))
  }, [workItems])

  const recentExecutions = React.useMemo(
    () => executions.slice(0, 8),
    [executions]
  )

  const { events, isConnected, subscribe } = useWebSocket(isAuthenticated, isAuthLoading)

  React.useEffect(() => {
    if (isConnected) {
      subscribe('ExecutionStarted')
      subscribe('ExecutionCompleted')
      subscribe('ExecutionFailed')
    }
  }, [isConnected, subscribe])

  React.useEffect(() => {
    if (events.length === 0) return
    const latestEvent = events[0]
    const eventData = latestEvent.data as Record<string, unknown> | undefined
    const eventType = eventData?.event_type as string | undefined

    if (latestEvent.type === 'event' && eventType === 'WorkItemColumnChanged') {
      queryClient.invalidateQueries({ queryKey: ['workItems'] })
    }
    if (
      latestEvent.type === 'event' &&
      (eventType === 'ExecutionStarted' ||
        eventType === 'ExecutionCompleted' ||
        eventType === 'ExecutionFailed')
    ) {
      queryClient.invalidateQueries({ queryKey: ['executions'] })
    }
  }, [events, queryClient])

  return (
    <div className="space-y-8">
      <PageHeader
        title="Overview"
        description="What agents are doing now, and what is waiting in the queue."
        actions={
          <div
            className={cn(
              'inline-flex items-center gap-2 rounded-full border px-3 py-1.5 text-sm',
              isConnected
                ? 'border-live/30 bg-live/10 text-live'
                : 'border-border bg-muted text-muted-foreground'
            )}
            role="status"
            aria-live="polite"
          >
            <Radio className={cn('h-3.5 w-3.5', isConnected && 'animate-pulse')} aria-hidden />
            <span className="font-medium">
              {isConnected ? 'Live updates on' : 'Live updates off'}
            </span>
          </div>
        }
      />

      {/* Primary work surfaces */}
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
        <section className="surface-panel shadow-soft" aria-labelledby="queue-heading">
          <div className="flex items-center justify-between border-b border-border/70 px-5 py-4">
            <div>
              <h2 id="queue-heading" className="text-[15px] font-semibold text-foreground">
                Work queue
              </h2>
              <p className="text-xs text-muted-foreground">Open items ready for an agent</p>
            </div>
            <span className="font-mono text-xs text-muted-foreground tabular-nums">
              {activeWorkItems.length}
            </span>
          </div>

          <div className="px-4 py-3">
            {loadingWorkItems ? (
              <ListSkeleton />
            ) : workItemsError ? (
              <ErrorState message="Couldn't load the work queue. Try refreshing the page." />
            ) : activeWorkItems.length === 0 ? (
              <EmptyState
                title="Nothing in the queue"
                body="Create a work item or move a card into an automated column to start an agent."
                action={
                  <Link
                    to="/config"
                    className="inline-flex items-center gap-1.5 text-sm font-medium text-primary hover:underline"
                  >
                    Open project settings
                    <ArrowRight className="h-3.5 w-3.5" aria-hidden />
                  </Link>
                }
              />
            ) : (
              <ul className="divide-y divide-border/60">
                {activeWorkItems.map((item: WorkItem) => {
                  const live = runningWorkItemIds.has(item.id)
                  return (
                    <li key={item.id} className="py-3.5 first:pt-1 last:pb-1">
                      <div className="flex items-start justify-between gap-3 px-1">
                        <div className="min-w-0 flex-1">
                          <p className="truncate text-[15px] font-medium text-foreground">
                            {item.title}
                          </p>
                          {item.description ? (
                            <p className="mt-1 line-clamp-2 text-sm text-muted-foreground">
                              {item.description}
                            </p>
                          ) : null}
                          <div className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-muted-foreground">
                            {item.current_stage ? (
                              <span>Stage {item.current_stage}</span>
                            ) : null}
                            <span>
                              Updated{' '}
                              {formatDistanceToNow(new Date(item.updated_at), { addSuffix: true })}
                            </span>
                          </div>
                        </div>
                        <StatusPill status={item.status} live={live} />
                      </div>
                    </li>
                  )
                })}
              </ul>
            )}
          </div>
        </section>

        <section className="surface-panel shadow-soft" aria-labelledby="runs-heading">
          <div className="flex items-center justify-between border-b border-border/70 px-5 py-4">
            <div>
              <h2 id="runs-heading" className="text-[15px] font-semibold text-foreground">
                Agent runs
              </h2>
              <p className="text-xs text-muted-foreground">Recent executions</p>
            </div>
            <Link
              to="/workflows/runs"
              className="inline-flex items-center gap-1 text-xs font-medium text-primary hover:underline"
            >
              View runs
              <ArrowRight className="h-3 w-3" aria-hidden />
            </Link>
          </div>

          <div className="px-4 py-3">
            {loadingExecutions ? (
              <ListSkeleton />
            ) : executionsError ? (
              <ErrorState message="Couldn't load recent runs. Try refreshing the page." />
            ) : recentExecutions.length === 0 ? (
              <EmptyState
                title="No runs yet"
                body="When an agent starts, its execution shows up here with status and timing."
              />
            ) : (
              <ul className="divide-y divide-border/60">
                {recentExecutions.map((execution: ExecutionSummary) => (
                  <li key={execution.id} className="py-3.5 first:pt-1 last:pb-1">
                    <div className="flex items-start justify-between gap-3 px-1">
                      <div className="min-w-0 flex-1">
                        <p className="truncate text-[15px] font-medium text-foreground">
                          {execution.work_item_title || 'Untitled work item'}
                        </p>
                        <p className="mt-1 font-mono text-xs text-muted-foreground">
                          {execution.agent_name}
                        </p>
                        <div className="mt-2 flex flex-wrap gap-x-3 text-xs text-muted-foreground">
                          {execution.started_at ? (
                            <span>
                              Started{' '}
                              {formatDistanceToNow(new Date(execution.started_at), {
                                addSuffix: true,
                              })}
                            </span>
                          ) : null}
                          {execution.duration_seconds != null ? (
                            <span className="tabular-nums">{execution.duration_seconds}s</span>
                          ) : null}
                        </div>
                      </div>
                      <StatusPill
                        status={execution.status}
                        live={['running', 'queued', 'pending'].includes(execution.status)}
                      />
                    </div>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </section>
      </div>

      {/* Secondary: event stream — compact, not raw JSON dump */}
      <section className="surface-panel shadow-soft" aria-labelledby="events-heading">
        <div className="flex items-center justify-between border-b border-border/70 px-5 py-4">
          <div>
            <h2 id="events-heading" className="text-[15px] font-semibold text-foreground">
              Event stream
            </h2>
            <p className="text-xs text-muted-foreground">Last 10 live events from the orchestrator</p>
          </div>
        </div>

        <div className="px-5 py-4">
          {events.length === 0 ? (
            <EmptyState
              title={isConnected ? 'Waiting for events' : 'Connect for live events'}
              body={
                isConnected
                  ? 'Agent starts, completions, and board moves will appear here as they happen.'
                  : 'Live updates are off. Re-open the dashboard with your auth token to reconnect.'
              }
            />
          ) : (
            <ol className="space-y-0">
              {events.slice(0, 10).map((event, index) => {
                const eventData = event.data as Record<string, unknown> | undefined
                const eventType =
                  (eventData?.event_type as string | undefined) || event.type || 'Event'
                const summary =
                  typeof eventData?.message === 'string'
                    ? eventData.message
                    : typeof eventData?.title === 'string'
                      ? eventData.title
                      : null

                return (
                  <li
                    key={`${event.timestamp}-${index}`}
                    className="flex gap-4 border-b border-border/50 py-3 last:border-0"
                  >
                    <time
                      className="w-16 shrink-0 font-mono text-xs tabular-nums text-muted-foreground"
                      dateTime={event.timestamp}
                    >
                      {format(new Date(event.timestamp), 'HH:mm:ss')}
                    </time>
                    <div className="min-w-0 flex-1">
                      <p className="font-mono text-sm font-medium text-foreground">{eventType}</p>
                      {summary ? (
                        <p className="mt-0.5 truncate text-sm text-muted-foreground">{summary}</p>
                      ) : null}
                    </div>
                  </li>
                )
              })}
            </ol>
          )}
        </div>
      </section>
    </div>
  )
}
