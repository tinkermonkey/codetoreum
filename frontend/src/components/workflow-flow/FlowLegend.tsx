import { XCircle, AlertCircle } from 'lucide-react'

interface FlowLegendProps {
  isOpen: boolean
  onToggle: () => void
  chartHeight: number
}

export function FlowLegend({ isOpen, onToggle, chartHeight }: FlowLegendProps) {
  return (
    <div
      className={`transition-all duration-300 ${
        isOpen ? 'w-64' : 'w-10'
      } bg-white border border-gray-200 rounded-md`}
    >
      <div className="flex items-center justify-between p-3 border-b border-gray-200">
        {isOpen && <h3 className="text-sm font-semibold">Legend</h3>}
        <button
          onClick={onToggle}
          className="p-1 hover:bg-gray-100 rounded transition-colors"
          title={isOpen ? 'Collapse legend' : 'Expand legend'}
        >
          {isOpen ? <XCircle className="w-4 h-4" /> : <AlertCircle className="w-4 h-4" />}
        </button>
      </div>

      {isOpen && (
        <div
          className="p-3 space-y-4 overflow-y-auto"
          style={{ maxHeight: `${chartHeight}px` }}
        >
          <div>
            <h4 className="text-xs font-semibold mb-2 text-gray-500">Pipeline States</h4>
            <div className="space-y-2 text-xs">
              <div className="flex items-center gap-2">
                <div
                  className="w-4 h-4 rounded flex-shrink-0"
                  style={{ background: '#10b981' }}
                />
                <span>Pipeline Started</span>
              </div>
              <div className="flex items-center gap-2">
                <div
                  className="w-4 h-4 rounded flex-shrink-0"
                  style={{ background: '#1f6feb' }}
                />
                <span>Agent Running</span>
              </div>
              <div className="flex items-center gap-2">
                <div
                  className="w-4 h-4 rounded flex-shrink-0"
                  style={{ background: '#238636' }}
                />
                <span>Agent Completed</span>
              </div>
              <div className="flex items-center gap-2">
                <div
                  className="w-4 h-4 rounded flex-shrink-0"
                  style={{ background: '#da3633' }}
                />
                <span>Agent Failed</span>
              </div>
              <div className="flex items-center gap-2">
                <div
                  className="w-4 h-4 rounded flex-shrink-0"
                  style={{ background: '#6366f1' }}
                />
                <span>Pipeline Completed</span>
              </div>
              <div className="flex items-center gap-2">
                <div
                  className="w-4 h-4 rounded border-2 flex-shrink-0"
                  style={{ borderColor: '#58a6ff', background: '#1f6feb' }}
                >
                  <div
                    style={{
                      height: '100%',
                      backgroundImage:
                        'linear-gradient(45deg, rgba(255,255,255,.2) 25%, transparent 25%)',
                      backgroundSize: '4px 4px',
                    }}
                  />
                </div>
                <span>Active (Animated)</span>
              </div>
            </div>
          </div>

          <div>
            <h4 className="text-xs font-semibold mb-2 text-gray-500">Decision Categories</h4>
            <div className="space-y-2 text-xs">
              <div className="flex items-center gap-2">
                <div
                  className="w-4 h-4 rounded flex-shrink-0"
                  style={{ background: '#3b82f6' }}
                />
                <span>Routing</span>
              </div>
              <div className="flex items-center gap-2">
                <div
                  className="w-4 h-4 rounded flex-shrink-0"
                  style={{ background: '#10b981' }}
                />
                <span>Progression</span>
              </div>
              <div className="flex items-center gap-2">
                <div
                  className="w-4 h-4 rounded flex-shrink-0"
                  style={{ background: '#8b5cf6' }}
                />
                <span>Review Cycle</span>
              </div>
              <div className="flex items-center gap-2">
                <div
                  className="w-4 h-4 rounded flex-shrink-0"
                  style={{ background: '#f59e0b' }}
                />
                <span>Feedback</span>
              </div>
              <div className="flex items-center gap-2">
                <div
                  className="w-4 h-4 rounded flex-shrink-0"
                  style={{ background: '#ef4444' }}
                />
                <span>Error Handling</span>
              </div>
              <div className="flex items-center gap-2">
                <div
                  className="w-4 h-4 rounded flex-shrink-0"
                  style={{ background: '#06b6d4' }}
                />
                <span>Task Management</span>
              </div>
              <div className="flex items-center gap-2">
                <div
                  className="w-4 h-4 rounded flex-shrink-0"
                  style={{ background: '#84cc16' }}
                />
                <span>Branch Management</span>
              </div>
              <div className="flex items-center gap-2">
                <div
                  className="w-4 h-4 rounded flex-shrink-0"
                  style={{ background: '#ec4899' }}
                />
                <span>Conversational</span>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
