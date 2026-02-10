import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { History, RotateCcw, Filter, ChevronDown, ChevronUp, AlertCircle } from 'lucide-react'
import { Button } from '../components/ui/button'
import { Input } from '../components/ui/input'
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '../components/ui/card'
import {
  projectConfigApi,
  agentConfigApi,
  pipelineConfigApi,
  configurationCommandsApi,
} from '../api/client'
import type { ConfigurationHistory, ConfigChange } from '../types'

export default function ConfigHistoryPage() {
  const [configType, setConfigType] = useState<'project' | 'agent' | 'pipeline' | 'all'>('all')
  const [searchQuery, setSearchQuery] = useState('')
  const [expandedItem, setExpandedItem] = useState<string | null>(null)
  const queryClient = useQueryClient()

  // Fetch projects so we can get history by project ID
  const { data: projects } = useQuery({
    queryKey: ['projects'],
    queryFn: () => projectConfigApi.getAll(),
  })

  // Fetch history for each project
  const { data: projectHistory } = useQuery({
    queryKey: ['projectHistory', projects?.map((p) => p.id)],
    queryFn: async () => {
      if (!projects?.length) return []
      const histories = await Promise.all(
        projects.map(async (project) => {
          try {
            return await projectConfigApi.getHistory(project.id)
          } catch {
            return []
          }
        })
      )
      return histories.flat()
    },
    enabled: (configType === 'all' || configType === 'project') && !!projects?.length,
  })

  const { data: agents } = useQuery({
    queryKey: ['agents'],
    queryFn: () => agentConfigApi.getAll(),
  })

  const { data: pipelines } = useQuery({
    queryKey: ['pipelines'],
    queryFn: () => pipelineConfigApi.getAll(),
  })

  // Combine all histories
  // Note: Only project-level version history is currently supported by the backend.
  // Agent and pipeline history endpoints are not yet implemented.
  const allHistory: ConfigurationHistory[] = [
    ...(projectHistory || []),
  ].sort((a, b) => new Date(b.changed_at).getTime() - new Date(a.changed_at).getTime())

  // Filter history
  const filteredHistory = allHistory.filter((item) => {
    if (!searchQuery) return true
    const query = searchQuery.toLowerCase()
    return (
      item.config_name.toLowerCase().includes(query) ||
      item.change_type.toLowerCase().includes(query) ||
      item.changed_by?.toLowerCase().includes(query) ||
      item.reason?.toLowerCase().includes(query)
    )
  })

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-3xl font-bold">Configuration History</h2>
        <p className="text-muted-foreground mt-1">
          View configuration changes, compare versions, and rollback changes
        </p>
      </div>

      {/* Filters */}
      <Card>
        <CardHeader>
          <div className="flex items-center justify-between">
            <div className="flex items-center space-x-2">
              <Filter className="h-5 w-5" />
              <CardTitle>Filters</CardTitle>
            </div>
          </div>
        </CardHeader>
        <CardContent>
          <div className="flex items-center space-x-4">
            <div className="flex-1">
              <Input
                placeholder="Search by name, type, user, or reason..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
              />
            </div>
            <div className="flex items-center space-x-2">
              <label className="text-sm font-medium">Config Type:</label>
              <select
                className="flex h-10 w-40 rounded-md border border-input bg-background px-3 py-2 text-sm"
                value={configType}
                onChange={(e) => setConfigType(e.target.value as any)}
              >
                <option value="all">All</option>
                <option value="project">Project</option>
                <option value="agent">Agent</option>
                <option value="pipeline">Pipeline</option>
              </select>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* History Timeline */}
      <Card>
        <CardHeader>
          <div className="flex items-center space-x-2">
            <History className="h-5 w-5" />
            <CardTitle>Change Timeline</CardTitle>
          </div>
          <CardDescription>
            {filteredHistory.length} change{filteredHistory.length !== 1 ? 's' : ''} found
          </CardDescription>
        </CardHeader>
        <CardContent>
          <div className="space-y-3">
            {filteredHistory.length === 0 ? (
              <div className="flex flex-col items-center justify-center py-12">
                <AlertCircle className="h-12 w-12 text-muted-foreground mb-4" />
                <p className="text-muted-foreground">No configuration changes found</p>
              </div>
            ) : (
              filteredHistory.map((item, index) => {
                const itemKey = item.id || `${item.config_type}-${item.config_name}-${item.config_version}-${index}`
                return (
                  <HistoryItem
                    key={itemKey}
                    item={{ ...item, id: item.id || itemKey }}
                    isExpanded={expandedItem === (item.id || itemKey)}
                    onToggle={() => setExpandedItem(expandedItem === (item.id || itemKey) ? null : (item.id || itemKey))}
                    queryClient={queryClient}
                  />
                )
              })
            )}
          </div>
        </CardContent>
      </Card>
    </div>
  )
}

// History Item Component
function HistoryItem({
  item,
  isExpanded,
  onToggle,
  queryClient,
}: {
  item: ConfigurationHistory
  isExpanded: boolean
  onToggle: () => void
  queryClient: any
}) {
  const rollbackMutation = useMutation({
    mutationFn: () =>
      configurationCommandsApi.rollback(item.config_type, item.config_name, item.config_version),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['projectHistory'] })
      queryClient.invalidateQueries({ queryKey: ['agentHistories'] })
      queryClient.invalidateQueries({ queryKey: ['pipelineHistories'] })
      queryClient.invalidateQueries({ queryKey: ['projectConfig'] })
      queryClient.invalidateQueries({ queryKey: ['agents'] })
      queryClient.invalidateQueries({ queryKey: ['pipelines'] })
    },
  })

  const handleRollback = () => {
    if (
      confirm(
        `Are you sure you want to rollback ${item.config_type} "${item.config_name}" to version ${item.config_version}?`
      )
    ) {
      rollbackMutation.mutate()
    }
  }

  const getChangeTypeColor = (type: string) => {
    switch (type) {
      case 'created':
        return 'bg-green-500/10 text-green-500 border-green-500/20'
      case 'updated':
        return 'bg-blue-500/10 text-blue-500 border-blue-500/20'
      case 'deleted':
        return 'bg-red-500/10 text-red-500 border-red-500/20'
      default:
        return 'bg-primary/10 text-primary border-primary/20'
    }
  }

  const getConfigTypeIcon = (type: string) => {
    switch (type) {
      case 'project':
        return '📦'
      case 'agent':
        return '🤖'
      case 'pipeline':
        return '🔄'
      default:
        return '⚙️'
    }
  }

  return (
    <div className="border rounded-md">
      <div
        className="flex items-center justify-between p-4 cursor-pointer hover:bg-muted/50 transition-colors"
        onClick={onToggle}
      >
        <div className="flex-1">
          <div className="flex items-center space-x-3">
            <span className="text-2xl">{getConfigTypeIcon(item.config_type)}</span>
            <div>
              <div className="flex items-center space-x-2">
                <span className="font-medium">{item.config_name}</span>
                <span
                  className={`text-xs px-2 py-0.5 rounded border ${getChangeTypeColor(item.change_type)}`}
                >
                  {item.change_type}
                </span>
                <span className="text-xs text-muted-foreground">v{item.config_version}</span>
              </div>
              <div className="text-sm text-muted-foreground mt-1">
                {item.changed_by} • {new Date(item.changed_at).toLocaleString()}
              </div>
              {item.reason && (
                <div className="text-sm text-muted-foreground mt-1 italic">"{item.reason}"</div>
              )}
            </div>
          </div>
        </div>
        <div className="flex items-center space-x-2">
          {item.can_rollback && (
            <Button
              size="sm"
              variant="outline"
              onClick={(e) => {
                e.stopPropagation()
                handleRollback()
              }}
              disabled={rollbackMutation.isPending}
            >
              <RotateCcw className="h-4 w-4 mr-2" />
              Rollback
            </Button>
          )}
          <button className="text-muted-foreground hover:text-foreground">
            {isExpanded ? <ChevronUp className="h-5 w-5" /> : <ChevronDown className="h-5 w-5" />}
          </button>
        </div>
      </div>

      {/* Expanded Details */}
      {isExpanded && (
        <div className="border-t p-4 bg-muted/20">
          <h4 className="font-medium mb-3">Changes ({(item.changes ?? []).length})</h4>
          <div className="space-y-2">
            {(item.changes ?? []).length > 0 ? (
              (item.changes ?? []).map((change, index) => (
                <ChangeDetails key={index} change={change} />
              ))
            ) : (
              <p className="text-muted-foreground text-sm">No detailed changes available</p>
            )}
          </div>
        </div>
      )}
    </div>
  )
}

// Change Details Component
function ChangeDetails({ change }: { change: ConfigChange }) {
  const getOperationColor = (operation: string) => {
    switch (operation) {
      case 'add':
        return 'text-green-600'
      case 'remove':
        return 'text-red-600'
      case 'modify':
        return 'text-blue-600'
      default:
        return 'text-muted-foreground'
    }
  }

  const getOperationSymbol = (operation: string) => {
    switch (operation) {
      case 'add':
        return '+'
      case 'remove':
        return '-'
      case 'modify':
        return '~'
      default:
        return '•'
    }
  }

  const formatValue = (value: unknown) => {
    if (value === null || value === undefined) return 'null'
    if (typeof value === 'object') return JSON.stringify(value, null, 2)
    return String(value)
  }

  return (
    <div className="border rounded-md p-3 bg-background">
      <div className="flex items-start space-x-2">
        <span className={`font-mono font-bold ${getOperationColor(change.operation)}`}>
          {getOperationSymbol(change.operation)}
        </span>
        <div className="flex-1">
          <div className="font-medium text-sm">{change.field}</div>
          <div className="mt-2 space-y-1">
            {change.operation !== 'add' && (
              <div className="flex items-start space-x-2">
                <span className="text-xs text-red-600 font-mono">-</span>
                <pre className="text-xs bg-red-50 dark:bg-red-950/20 border border-red-200 dark:border-red-900 rounded px-2 py-1 overflow-x-auto flex-1">
                  {formatValue(change.old_value)}
                </pre>
              </div>
            )}
            {change.operation !== 'remove' && (
              <div className="flex items-start space-x-2">
                <span className="text-xs text-green-600 font-mono">+</span>
                <pre className="text-xs bg-green-50 dark:bg-green-950/20 border border-green-200 dark:border-green-900 rounded px-2 py-1 overflow-x-auto flex-1">
                  {formatValue(change.new_value)}
                </pre>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}
