/**
 * Metrics Hook
 *
 * React Query hooks for fetching system metrics and usage data.
 */

import { useQuery } from '@tanstack/react-query'
import { apiClient } from '../api/client'
import type { SystemMetrics, TokenUsageSummary, ExecutionMetrics } from '../types/metrics'

/**
 * Metrics query keys
 */
export const metricsQueryKeys = {
  all: ['metrics'] as const,
  system: () => [...metricsQueryKeys.all, 'system'] as const,
  tokenUsage: (period: string) => [...metricsQueryKeys.all, 'token-usage', period] as const,
  executions: (period: string) => [...metricsQueryKeys.all, 'executions', period] as const,
}

/**
 * Fetch system metrics
 */
async function fetchSystemMetrics(): Promise<SystemMetrics> {
  return await apiClient.get<SystemMetrics>('/metrics/system')
}

/**
 * Fetch token usage for a period
 */
async function fetchTokenUsage(period: 'today' | 'week' | 'month'): Promise<TokenUsageSummary> {
  return await apiClient.get<TokenUsageSummary>(`/metrics/token-usage/${period}`)
}

/**
 * Fetch execution metrics for a period
 */
async function fetchExecutionMetrics(period: 'today' | 'week' | 'month'): Promise<ExecutionMetrics> {
  return await apiClient.get<ExecutionMetrics>(`/metrics/executions/${period}`)
}

/**
 * Hook for fetching system metrics
 */
export function useSystemMetrics() {
  return useQuery({
    queryKey: metricsQueryKeys.system(),
    queryFn: fetchSystemMetrics,
    refetchInterval: 30000, // Refresh every 30 seconds
    staleTime: 25000,
  })
}

/**
 * Hook for fetching token usage metrics
 */
export function useTokenUsage(period: 'today' | 'week' | 'month' = 'week') {
  return useQuery({
    queryKey: metricsQueryKeys.tokenUsage(period),
    queryFn: () => fetchTokenUsage(period),
    refetchInterval: 60000, // Refresh every minute
    staleTime: 50000,
  })
}

/**
 * Hook for fetching execution metrics
 */
export function useExecutionMetrics(period: 'today' | 'week' | 'month' = 'week') {
  return useQuery({
    queryKey: metricsQueryKeys.executions(period),
    queryFn: () => fetchExecutionMetrics(period),
    refetchInterval: 30000, // Refresh every 30 seconds
    staleTime: 25000,
  })
}
