/**
 * System Status Hook
 *
 * React Query hook for fetching system health and status data.
 * Automatically updates the Zustand store with real-time data.
 */

import { useQuery } from '@tanstack/react-query'
import { useEffect } from 'react'
import { apiClient } from '../api/client'
import { useSystemStatusStore } from '../store/systemStatusStore'
import type { SystemHealth } from '../types/system-status'

/**
 * System health query key
 */
export const systemHealthQueryKey = ['system-health']

/**
 * Fetch system health from API
 */
async function fetchSystemHealth(): Promise<SystemHealth> {
  return await apiClient.get<SystemHealth>('/api/v2/metrics/health')
}

/**
 * Hook for fetching and managing system status
 *
 * Features:
 * - Polls health endpoint every 5 seconds
 * - Automatically updates Zustand store
 * - Provides loading and error states
 *
 * @returns Query result with system health data
 */
export function useSystemStatus() {
  const updateSystemHealth = useSystemStatusStore((state) => state.updateSystemHealth)

  const query = useQuery({
    queryKey: systemHealthQueryKey,
    queryFn: fetchSystemHealth,
    refetchInterval: 5000, // Poll every 5 seconds
    staleTime: 4000, // Consider data stale after 4 seconds
    retry: 3,
    retryDelay: (attemptIndex) => Math.min(1000 * 2 ** attemptIndex, 10000),
  })

  // Update Zustand store when data changes
  useEffect(() => {
    if (query.data) {
      updateSystemHealth(query.data)
    }
  }, [query.data, updateSystemHealth])

  return query
}
