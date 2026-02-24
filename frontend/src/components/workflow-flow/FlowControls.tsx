import { ZoomIn, ZoomOut, Maximize2 } from 'lucide-react'
import { useReactFlow } from '@xyflow/react'

interface FlowControlsProps {
  onFitView: () => void
}

export function FlowControls({ onFitView }: FlowControlsProps) {
  const { zoomIn, zoomOut } = useReactFlow()

  return (
    <div className="absolute top-4 right-4 flex flex-col gap-2 bg-white border border-gray-200 rounded-md shadow-sm p-1">
      <button
        onClick={() => zoomIn()}
        className="p-2 hover:bg-gray-100 rounded transition-colors"
        title="Zoom In"
      >
        <ZoomIn className="w-4 h-4" />
      </button>
      <button
        onClick={() => zoomOut()}
        className="p-2 hover:bg-gray-100 rounded transition-colors"
        title="Zoom Out"
      >
        <ZoomOut className="w-4 h-4" />
      </button>
      <div className="border-t border-gray-200 my-1" />
      <button
        onClick={onFitView}
        className="p-2 hover:bg-gray-100 rounded transition-colors"
        title="Fit View"
      >
        <Maximize2 className="w-4 h-4" />
      </button>
    </div>
  )
}
