/**
 * System Status Header Tests
 *
 * Comprehensive test suite for SystemStatusHeader component and related functionality.
 */

import { describe, it, expect, beforeEach, vi } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { SystemStatusHeader } from '../SystemStatusHeader'
import { useSystemStatusStore } from '../../../store/systemStatusStore'
import type { AgentExecution, SystemHealth } from '../../../types/system-status'

// Mock the hooks
vi.mock('../../../hooks/useSystemStatus', () => ({
  useSystemStatus: () => ({
    isLoading: false,
    error: null,
  }),
}))

vi.mock('../../../hooks/useActiveAgents', () => ({
  useActiveAgents: () => ({
    isLoading: false,
    error: null,
  }),
}))

vi.mock('../../../hooks/useAuth', () => ({
  useAuth: () => ({
    isAuthenticated: true,
    isLoading: false,
  }),
}))

describe('SystemStatusHeader', () => {
  let queryClient: QueryClient

  beforeEach(() => {
    queryClient = new QueryClient({
      defaultOptions: {
        queries: {
          retry: false,
        },
      },
    })

    // Reset store
    useSystemStatusStore.getState().reset()
  })

  it('renders without crashing', () => {
    render(
      <QueryClientProvider client={queryClient}>
        <SystemStatusHeader />
      </QueryClientProvider>
    )

    expect(screen.getByText('Active Agents')).toBeInTheDocument()
    expect(screen.getByText('API Usage')).toBeInTheDocument()
    expect(screen.getByText('Circuit Breakers')).toBeInTheDocument()
  })

  it('displays active agent count', () => {
    const mockAgents: AgentExecution[] = [
      {
        id: '1',
        agentName: 'test-agent',
        workItemId: 'work-1',
        status: 'running',
        startedAt: new Date().toISOString(),
        project: 'test-project',
      },
    ]

    useSystemStatusStore.getState().updateActiveAgents(mockAgents)

    render(
      <QueryClientProvider client={queryClient}>
        <SystemStatusHeader />
      </QueryClientProvider>
    )

    expect(screen.getByText('1')).toBeInTheDocument()
  })

  it('shows system health status', async () => {
    const mockHealth: SystemHealth = {
      status: 'healthy',
      checks: {
        github: {
          healthy: true,
          message: 'OK',
        },
      },
      circuitBreakers: [],
    }

    useSystemStatusStore.getState().updateSystemHealth(mockHealth)

    render(
      <QueryClientProvider client={queryClient}>
        <SystemStatusHeader />
      </QueryClientProvider>
    )

    await waitFor(() => {
      // Component should render without errors
      expect(screen.getByText('Active Agents')).toBeInTheDocument()
    })
  })
})

describe('useSystemStatusStore', () => {
  beforeEach(() => {
    useSystemStatusStore.getState().reset()
  })

  it('updates active agents efficiently using Map', () => {
    const agents: AgentExecution[] = [
      {
        id: '1',
        agentName: 'agent-1',
        workItemId: 'work-1',
        status: 'running',
        startedAt: new Date().toISOString(),
        project: 'project-1',
      },
      {
        id: '2',
        agentName: 'agent-2',
        workItemId: 'work-2',
        status: 'running',
        startedAt: new Date().toISOString(),
        project: 'project-2',
      },
    ]

    useSystemStatusStore.getState().updateActiveAgents(agents)

    const state = useSystemStatusStore.getState()
    expect(state.agentCount).toBe(2)
    expect(state.activeAgents).toHaveLength(2)
  })

  it('updates single agent execution', () => {
    const agent: AgentExecution = {
      id: '1',
      agentName: 'agent-1',
      workItemId: 'work-1',
      status: 'running',
      startedAt: new Date().toISOString(),
      project: 'project-1',
    }

    useSystemStatusStore.getState().updateAgentExecution(agent)

    const state = useSystemStatusStore.getState()
    expect(state.agentCount).toBe(1)
    expect(state.activeAgents[0].id).toBe('1')
  })

  it('removes agent execution', () => {
    const agents: AgentExecution[] = [
      {
        id: '1',
        agentName: 'agent-1',
        workItemId: 'work-1',
        status: 'running',
        startedAt: new Date().toISOString(),
        project: 'project-1',
      },
    ]

    useSystemStatusStore.getState().updateActiveAgents(agents)
    useSystemStatusStore.getState().removeAgentExecution('1')

    const state = useSystemStatusStore.getState()
    expect(state.agentCount).toBe(0)
    expect(state.activeAgents).toHaveLength(0)
  })

  it('updates circuit breakers and calculates summary', () => {
    const breakers = [
      {
        name: 'github',
        state: 'closed' as const,
        failureCount: 0,
        successCount: 10,
        totalRejected: 0,
      },
      {
        name: 'claude',
        state: 'open' as const,
        failureCount: 5,
        successCount: 0,
        totalRejected: 10,
      },
    ]

    useSystemStatusStore.getState().updateCircuitBreakers(breakers)

    const state = useSystemStatusStore.getState()
    expect(state.circuitBreakerSummary.total).toBe(2)
    expect(state.circuitBreakerSummary.closed).toBe(1)
    expect(state.circuitBreakerSummary.open).toBe(1)
    expect(state.hasOpenBreakers).toBe(true)
  })
})
