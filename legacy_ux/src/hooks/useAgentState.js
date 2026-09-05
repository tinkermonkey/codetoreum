import { useContext } from 'react'
import { AgentStateContext } from '../contexts/AgentStateContextValue'

/**
 * Hook to access agent state
 */
export function useAgentState() {
  const context = useContext(AgentStateContext)
  if (!context) {
    throw new Error('useAgentState must be used within AgentStateProvider')
  }
  return context
}
