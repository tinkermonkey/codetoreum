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
import { POLLING_CONFIG, RETRY_CONFIG } from '../config/polling'

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
 * Calculate retry delay with exponential backoff
 */
function calculateRetryDelay(attemptIndex: number): number {
  return Math.min(
    RETRY_CONFIG.BASE_DELAY * Math.pow(2, attemptIndex),
    30000 // Max 30 seconds
  )
}

/**
 * Hook for fetching and managing system status
 *
 * Features:
 * - Configurable polling interval (default: 5 seconds)
 * - Automatic retry with exponential backoff
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
    refetchInterval: POLLING_CONFIG.SYSTEM_HEALTH,
    staleTime: POLLING_CONFIG.STALE_TIME,
    retry: RETRY_CONFIG.MAX_ATTEMPTS,
    retryDelay: calculateRetryDelay,
  })

  // Update Zustand store when data changes
  useEffect(() => {
    if (query.data) {
      updateSystemHealth(query.data)
    }
  }, [query.data, updateSystemHealth])

  return query
}
