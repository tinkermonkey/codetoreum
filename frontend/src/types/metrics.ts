/**
 * Metrics Types
 *
 * TypeScript interfaces for system metrics and monitoring data.
 */

// ============================================================================
// Token Usage Types
// ============================================================================

export interface TokenUsage {
  tokens: number
  cost: number
  timestamp: string
}

export interface TokenUsageSummary {
  total_tokens: number
  total_cost: number
  period_start: string
  period_end: string
  by_model?: Record<string, TokenUsage>
}

// ============================================================================
// Execution Metrics Types
// ============================================================================

export interface ExecutionMetrics {
  total_executions: number
  successful_executions: number
  failed_executions: number
  avg_duration_seconds: number
  success_rate: number
  period_start: string
  period_end: string
}

// ============================================================================
// System Resource Types
// ============================================================================

export interface DiskUsage {
  total_gb: number
  used_gb: number
  free_gb: number
  usage_percent: number
}

export interface MemoryUsage {
  total_gb: number
  used_gb: number
  available_gb: number
  usage_percent: number
}

export interface ResourceMetrics {
  disk: DiskUsage
  memory: MemoryUsage
  timestamp: string
}

// ============================================================================
// Aggregate Metrics Types
// ============================================================================

export interface SystemMetrics {
  token_usage?: TokenUsageSummary
  executions?: ExecutionMetrics
  resources?: ResourceMetrics
  circuit_breakers?: {
    total: number
    by_state: Record<string, number>
  }
}
