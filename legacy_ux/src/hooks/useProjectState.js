import { useContext } from 'react'
import { ProjectStateContext } from '../contexts/ProjectStateContextValue'

/**
 * Hook to access project state
 */
export function useProjectState() {
  const context = useContext(ProjectStateContext)
  if (!context) {
    throw new Error('useProjectState must be used within ProjectStateProvider')
  }
  return context
}
