import { useState, useCallback, useMemo } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { RefreshCw, ArrowLeft } from 'lucide-react'
import { FlowCanvas } from '@/components/workflow-flow/FlowCanvas'
import { FlowLegend } from '@/components/workflow-flow/FlowLegend'
import { useWorkflowRunDetails } from '@/hooks/useWorkflowRunDetails'
import { useWorkflowEvents } from '@/hooks/useWorkflowEvents'
import { useFlowData } from '@/hooks/useFlowData'

interface PipelineFlowPageProps {
  chartHeight?: number
}

export function PipelineFlowPage({ chartHeight = 600 }: PipelineFlowPageProps = {}) {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const [legendOpen, setLegendOpen] = useState(true)

  // Fetch workflow run details and events
  const { workflowRun, events, isLoading: loadingDetails } = useWorkflowRunDetails(id || null)

  // Also get refetch function from events hook
  const { refetch } = useWorkflowEvents(id || null)

  // Transform events to flow graph
  const { nodes, edges } = useFlowData(
    events || [],
    id
  )

  // Track cycle collapse states
  const [collapsedCycles, setCollapsedCycles] = useState<Map<string, boolean>>(new Map())

  // Handle cycle toggle
  const handleToggleCycle = useCallback((cycleId: string) => {
    setCollapsedCycles((prev) => {
      const updated = new Map(prev)
      const currentState = updated.get(cycleId) || false
      updated.set(cycleId, !currentState)
      return updated
    })
  }, [])

  // Update nodes with collapse toggle handler
  const nodesWithHandlers = useMemo(() => {
    return nodes.map((node) => {
      if (node.type === 'cycle') {
        return {
          ...node,
          data: {
            ...node.data,
            onToggleCollapse: handleToggleCycle,
            isCollapsed: collapsedCycles.get(node.id) || false,
          },
        }
      }
      return node
    })
  }, [nodes, handleToggleCycle, collapsedCycles])

  // Note: Edge routing for collapsed cycles is simplified for now
  // Edges connect to the nearest visible nodes (not to collapsed cycle containers)

  const handleRefresh = useCallback(() => {
    refetch()
  }, [refetch])

  const handleBack = useCallback(() => {
    navigate(-1)
  }, [navigate])

  if (!id) {
    return (
      <div className="flex items-center justify-center min-h-screen">
        <p className="text-gray-500">No workflow run selected</p>
      </div>
    )
  }

  if (loadingDetails) {
    return (
      <div className="flex items-center justify-center min-h-screen">
        <RefreshCw className="w-8 h-8 animate-spin text-blue-600" />
      </div>
    )
  }

  if (!workflowRun) {
    return (
      <div className="flex items-center justify-center min-h-screen">
        <div className="text-center">
          <p className="text-gray-500 mb-4">Workflow run not found</p>
          <button
            onClick={handleBack}
            className="px-4 py-2 bg-gray-200 hover:bg-gray-300 rounded-md transition-colors"
          >
            Go Back
          </button>
        </div>
      </div>
    )
  }

  return (
    <div className="min-h-screen p-5 bg-gray-50">
      {/* Header */}
      <div className="mb-4">
        <div className="flex items-center justify-between mb-2">
          <div className="flex items-center gap-3">
            <button
              onClick={handleBack}
              className="p-2 hover:bg-gray-200 rounded-md transition-colors"
              title="Go back"
            >
              <ArrowLeft className="w-5 h-5" />
            </button>
            <div>
              <h1 className="text-2xl font-bold">{workflowRun.issueTitle || 'Workflow Run'}</h1>
              <p className="text-sm text-gray-500 mt-1">
                Run ID: {id} • Status: <span className="capitalize">{workflowRun.status}</span>
              </p>
            </div>
          </div>
          <button
            onClick={handleRefresh}
            className="px-4 py-2 bg-white border border-gray-300 rounded-md hover:bg-gray-50 transition-colors text-sm flex items-center gap-2"
          >
            <RefreshCw className={`w-4 h-4 ${loadingDetails ? 'animate-spin' : ''}`} />
            Refresh
          </button>
        </div>
      </div>

      {/* Main content */}
      <div className="flex gap-4">
        {/* Flow visualization */}
        <div className="flex-1 bg-white rounded-md border border-gray-200 p-4">
          {nodesWithHandlers.length > 0 ? (
            <FlowCanvas
              nodes={nodesWithHandlers}
              edges={edges}
              chartHeight={chartHeight}
            />
          ) : (
            <div
              className="flex items-center justify-center bg-gray-50 rounded-md"
              style={{ height: `${chartHeight}px` }}
            >
              <p className="text-gray-500">No workflow events to display</p>
            </div>
          )}
        </div>

        {/* Legend */}
        <FlowLegend
          isOpen={legendOpen}
          onToggle={() => setLegendOpen(!legendOpen)}
          chartHeight={chartHeight}
        />
      </div>
    </div>
  )
}
