/**
 * System Status Types
 *
 * TypeScript interfaces for system status, health checks, and monitoring.
 */

// ============================================================================
// Agent Execution Types
// ============================================================================

export type AgentExecutionStatus = 'running' | 'completed' | 'failed'

export interface AgentExecution {
  id: string
  agentName: string
  workItemId: string
  status: AgentExecutionStatus
  startedAt: string
  containerName?: string
  project: string
  issueNumber?: number
}

// ============================================================================
// Circuit Breaker Types
// ============================================================================

export type CircuitBreakerState = 'closed' | 'half_open' | 'open'

export interface RateLimit {
  remaining: number
  limit: number
  percentageUsed: number
}

export interface CircuitBreaker {
  name: string
  state: CircuitBreakerState
  failureCount: number
  successCount: number
  totalRejected: number
  lastFailure?: string
  rateLimit?: RateLimit
}

export interface CircuitBreakerSummary {
  total: number
  closed: number
  halfOpen: number
  open: number
}

// ============================================================================
// Health Check Types
// ============================================================================

export type HealthStatus = 'healthy' | 'degraded' | 'unhealthy' | 'error' | 'starting'

export interface HealthCheck {
  available: boolean
  healthy: boolean
  error?: string
  message?: string
  warnings?: string[]
  // Component-specific fields
  tested_org?: string
  projects_access?: string
  free_gb?: number
  usage_percent?: number
  available_gb?: number
}

export interface ClaudeUsageCheck extends HealthCheck {
  weeklyUsage?: number
  weeklyQuota?: number
  weeklyUsagePercent?: number
  sessionUsage?: number
  sessionQuota?: number
  sessionUsagePercent?: number
  sessionRemainingMinutes?: number
  lastDayTokens?: number
  lastDayCost?: number
}

export interface SystemHealthChecks {
  github?: HealthCheck
  claude?: HealthCheck
  disk?: HealthCheck
  memory?: HealthCheck
  claude_usage?: ClaudeUsageCheck
}

export interface SystemHealth {
  status: HealthStatus
  message?: string
  error?: string
  orchestrator?: {
    status: HealthStatus
    checks: SystemHealthChecks
  }
  checks?: SystemHealthChecks
  circuitBreakers?: CircuitBreaker[]
}

// ============================================================================
// API Usage Types
// ============================================================================

export interface ApiUsage {
  weeklyUsed: number
  weeklyQuota: number
  weeklyPercent: number
  sessionUsed: number
  sessionQuota: number
  sessionPercent: number
  sessionRemainingMinutes: number
}

// ============================================================================
// System Status Store State
// ============================================================================

export interface SystemStatusState {
  // Active Agents
  activeAgents: AgentExecution[]
  agentCount: number

  // API Usage
  apiUsage: ApiUsage | null

  // Circuit Breakers
  circuitBreakers: CircuitBreaker[]
  circuitBreakerSummary: CircuitBreakerSummary
  hasOpenBreakers: boolean
  hasHalfOpenBreakers: boolean

  // System Health
  systemHealth: SystemHealth | null
  healthStatus: HealthStatus
  unhealthyComponents: Array<[string, HealthCheck]>

  // Actions
  updateActiveAgents: (agents: AgentExecution[]) => void
  updateApiUsage: (usage: ApiUsage | null) => void
  updateCircuitBreakers: (breakers: CircuitBreaker[]) => void
  updateSystemHealth: (health: SystemHealth) => void
  reset: () => void
}
