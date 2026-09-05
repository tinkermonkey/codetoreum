import { useContext } from 'react'
import { SystemStateContext } from '../contexts/SystemStateContextValue'

/**
 * Hook to access system state
 */
export function useSystemState() {
  const context = useContext(SystemStateContext)
  if (!context) {
    throw new Error('useSystemState must be used within SystemStateProvider')
  }
  return context
}
