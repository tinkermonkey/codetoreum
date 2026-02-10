/**
 * API Client
 *
 * Primary adapter for HTTP communication with backend services.
 * Wrapped with infrastructure-layer resilience patterns.
 */

import axios, { AxiosInstance, AxiosRequestConfig, AxiosError } from 'axios'
import toast from 'react-hot-toast'
import type {
  ProjectConfig,
  AgentConfig,
  PipelineConfig,
  ConfigurationCommandResult,
  UpdateProjectConfigRequest,
  UpdateAgentConfigRequest,
  AddEnvironmentVariableRequest,
  MountCommandRequest,
  MountSubAgentRequest,
  ConfigurationHistory,
  WorkItem,
  CreateWorkItemRequest,
  UpdateWorkItemRequest,
  Execution,
  ExecutionSummary,
  StartExecutionRequest,
} from '../types'
import { ApiError, createApiError, ErrorCode } from '../types/errors'
import { apiConfig } from '../config/api.config'
import { createResilienceDecoratorFromConfig } from '../infrastructure/resilience'
import { dispatchEvent, AppEventType } from '../infrastructure/events'

/**
 * Request cancellation management
 * Using WeakMap for automatic garbage collection
 */
class RequestCancellation {
  private controllers = new Map<string, AbortController>()
  private timeouts = new WeakMap<AbortController, number>()

  /**
   * Get or create an AbortController for a request
   */
  getController(key: string): AbortController {
    // Cancel existing request with same key
    this.cancel(key)

    const controller = new AbortController()
    this.controllers.set(key, controller)

    // Auto-cleanup after timeout
    const timeout = setTimeout(() => {
      this.cancel(key)
    }, apiConfig.timeout + 5000) // Cleanup 5s after timeout

    this.timeouts.set(controller, timeout)

    return controller
  }

  /**
   * Cancel a specific request
   */
  cancel(key: string): void {
    const controller = this.controllers.get(key)
    if (controller) {
      // Clear timeout
      const timeout = this.timeouts.get(controller)
      if (timeout) {
        clearTimeout(timeout)
      }

      controller.abort()
      this.controllers.delete(key)
    }
  }

  /**
   * Cancel all active requests
   */
  cancelAll(): void {
    for (const [key] of this.controllers) {
      this.cancel(key)
    }
  }

  /**
   * Cleanup after request completion
   */
  cleanup(key: string): void {
    const controller = this.controllers.get(key)
    if (controller) {
      const timeout = this.timeouts.get(controller)
      if (timeout) {
        clearTimeout(timeout)
      }
      this.controllers.delete(key)
    }
  }
}

/**
 * Generate correlation ID for request tracking
 */
function generateCorrelationId(): string {
  return `${Date.now()}-${Math.random().toString(36).substring(2, 9)}`
}

/**
 * API Client class
 */
class APIClient {
  private client: AxiosInstance
  private resilience: ReturnType<typeof createResilienceDecoratorFromConfig>
  private cancellation = new RequestCancellation()

  constructor() {
    // Create axios instance
    this.client = axios.create({
      baseURL: apiConfig.baseURL,
      withCredentials: true, // Send httpOnly cookies with requests
      timeout: apiConfig.timeout,
      headers: {
        'Content-Type': 'application/json',
      },
    })

    // Create resilience decorator with config
    this.resilience = createResilienceDecoratorFromConfig(apiConfig)

    // Setup interceptors
    this.setupInterceptors()
  }

  /**
   * Setup request and response interceptors
   */
  private setupInterceptors(): void {
    // Request interceptor
    this.client.interceptors.request.use(
      (config) => {
        // Add correlation ID for request tracking
        const correlationId = generateCorrelationId()
        config.headers['X-Correlation-ID'] = correlationId

        // Log request in development
        if (apiConfig.features.enableLogging && import.meta.env.DEV) {
          console.info('[API Request]', {
            method: config.method?.toUpperCase(),
            url: config.url,
            correlationId,
          })
        }

        return config
      },
      (error) => Promise.reject(error)
    )

    // Response interceptor
    this.client.interceptors.response.use(
      (response) => {
        // Log response in development
        if (apiConfig.features.enableLogging && import.meta.env.DEV) {
          console.info('[API Response]', {
            status: response.status,
            url: response.config.url,
            correlationId: response.config.headers['X-Correlation-ID'],
          })
        }

        return response
      },
      async (error: AxiosError) => {
        // Log error in development
        if (apiConfig.features.enableLogging && import.meta.env.DEV) {
          console.error('[API Error]', {
            status: error.response?.status,
            url: error.config?.url,
            correlationId: error.config?.headers?.['X-Correlation-ID'],
            message: error.message,
          })
        }

        // Handle specific error cases
        await this.handleErrorResponse(error)

        return Promise.reject(error)
      }
    )
  }

  /**
   * Handle specific error responses
   */
  private async handleErrorResponse(error: AxiosError): Promise<void> {
    const status = error.response?.status

    if (status === 401) {
      // Unauthorized - dispatch event for auth handling
      await dispatchEvent(AppEventType.AUTH_UNAUTHORIZED, {
        message: 'Authentication required',
        statusCode: 401,
      })
      toast.error('You need to sign in to continue')
    } else if (status === 429) {
      // Rate limited
      const retryAfter = error.response?.headers['retry-after']
      await dispatchEvent(AppEventType.API_RATE_LIMITED, {
        retryAfter: retryAfter ? parseInt(retryAfter, 10) : undefined,
        message: 'Too many requests',
      })
      toast.error('Too many requests. Please wait a moment.')
    } else if (status && status >= 500) {
      // Server error
      toast.error('Server error. Please try again later.')
    }
  }

  /**
   * Generic request wrapper with resilience
   */
  private async request<T>(
    config: AxiosRequestConfig,
    cancelKey?: string
  ): Promise<T> {
    // Setup cancellation if key provided
    if (cancelKey) {
      config.signal = this.cancellation.getController(cancelKey).signal
    }

    try {
      // Execute request with resilience decorator
      const response = await this.resilience.execute(
        () => this.client.request<T>(config),
        (context) => {
          // Log retry attempts
          console.info(
            `[API] Retrying request (${context.attempt}/${context.maxAttempts}) after ${context.nextDelay}ms`
          )
        }
      )

      return response.data
    } catch (error) {
      throw createApiError(error)
    } finally {
      // Cleanup cancellation
      if (cancelKey) {
        this.cancellation.cleanup(cancelKey)
      }
    }
  }

  /**
   * GET request
   */
  async get<T>(url: string, config?: AxiosRequestConfig & { cancelKey?: string }): Promise<T> {
    const { cancelKey, ...axiosConfig } = config || {}
    return this.request<T>({ ...axiosConfig, method: 'GET', url }, cancelKey)
  }

  /**
   * POST request
   */
  async post<T>(
    url: string,
    data?: any,
    config?: AxiosRequestConfig & { cancelKey?: string }
  ): Promise<T> {
    const { cancelKey, ...axiosConfig } = config || {}
    return this.request<T>({ ...axiosConfig, method: 'POST', url, data }, cancelKey)
  }

  /**
   * PUT request
   */
  async put<T>(
    url: string,
    data?: any,
    config?: AxiosRequestConfig & { cancelKey?: string }
  ): Promise<T> {
    const { cancelKey, ...axiosConfig } = config || {}
    return this.request<T>({ ...axiosConfig, method: 'PUT', url, data }, cancelKey)
  }

  /**
   * PATCH request
   */
  async patch<T>(
    url: string,
    data?: any,
    config?: AxiosRequestConfig & { cancelKey?: string }
  ): Promise<T> {
    const { cancelKey, ...axiosConfig } = config || {}
    return this.request<T>({ ...axiosConfig, method: 'PATCH', url, data }, cancelKey)
  }

  /**
   * DELETE request
   */
  async delete<T>(url: string, config?: AxiosRequestConfig & { cancelKey?: string }): Promise<T> {
    const { cancelKey, ...axiosConfig } = config || {}
    return this.request<T>({ ...axiosConfig, method: 'DELETE', url }, cancelKey)
  }

  /**
   * Cancel a specific request
   */
  cancelRequest(key: string): void {
    this.cancellation.cancel(key)
  }

  /**
   * Cancel all pending requests
   */
  cancelAllRequests(): void {
    this.cancellation.cancelAll()
  }

  /**
   * Get circuit breaker stats
   */
  getCircuitBreakerStats() {
    return this.resilience.getCircuitBreakerStats()
  }

  /**
   * Reset circuit breaker
   */
  resetCircuitBreaker(): void {
    this.resilience.resetCircuitBreaker()
  }
}

// Create singleton instance
const apiClient = new APIClient()

// =============================================================================
// Project Configuration API
// =============================================================================

export const projectConfigApi = {
  getAll: async () => {
    const response = await apiClient.get<{ projects: ProjectConfig[]; total_count: number }>('/config/projects')
    return response.projects
  },

  getByName: (projectName: string) =>
    apiClient.get<ProjectConfig>(`/config/projects/${projectName}`),

  create: (config: ProjectConfig) =>
    apiClient.post<ProjectConfig>('/config/projects', config),

  update: (projectName: string, config: UpdateProjectConfigRequest) =>
    apiClient.put<ProjectConfig>(`/config/projects/${projectName}`, config),

  delete: (projectName: string) =>
    apiClient.delete<void>(`/config/projects/${projectName}`),

  getHistory: async (projectId: string): Promise<ConfigurationHistory[]> => {
    const response = await apiClient.get<{
      config_id: string
      config_type: string
      current_version: number
      history: Array<{
        version: number
        created_at: string
        created_by: string | null
        changes: Record<string, any>
        reason: string | null
      }>
      total_versions: number
    }>(`/config/projects/${projectId}/history`)
    return response.history.map((entry, index) => ({
      id: `${response.config_id}-v${entry.version}`,
      project_id: response.config_id,
      config_type: response.config_type as 'project' | 'agent' | 'pipeline',
      config_name: response.config_id,
      config_version: entry.version,
      change_type: entry.version === 1 ? 'created' as const : 'updated' as const,
      changes: Object.entries(entry.changes).map(([field, value]) => ({
        field,
        old_value: null,
        new_value: value,
        operation: (entry.version === 1 ? 'add' : 'modify') as 'add' | 'remove' | 'modify',
      })),
      changed_by: entry.created_by || 'system',
      changed_at: entry.created_at,
      reason: entry.reason || undefined,
      can_rollback: entry.version < response.current_version,
    }))
  },

  addEnvironmentVariable: (projectName: string, request: AddEnvironmentVariableRequest) =>
    apiClient.post<ProjectConfig>(
      `/config/projects/${projectName}/environment-variables`,
      request
    ),

  removeEnvironmentVariable: (projectName: string, key: string) =>
    apiClient.delete<ProjectConfig>(
      `/config/projects/${projectName}/environment-variables/${key}`
    ),

  addMountCommand: (projectName: string, request: MountCommandRequest) =>
    apiClient.post<ProjectConfig>(`/config/projects/${projectName}/mount-commands`, request),

  removeMountCommand: (projectName: string, commandId: string) =>
    apiClient.delete<ProjectConfig>(
      `/config/projects/${projectName}/mount-commands/${commandId}`
    ),
}

// =============================================================================
// Agent Configuration API
// =============================================================================

export const agentConfigApi = {
  getAll: async () => {
    const response = await apiClient.get<{ agents: AgentConfig[]; total_count: number }>('/config/agents')
    return response.agents
  },

  getByName: (agentName: string) => apiClient.get<AgentConfig>(`/config/agents/${agentName}`),

  create: (config: AgentConfig) => apiClient.post<AgentConfig>('/config/agents', config),

  update: (agentName: string, config: UpdateAgentConfigRequest) =>
    apiClient.put<AgentConfig>(`/config/agents/${agentName}`, config),

  delete: (agentName: string) => apiClient.delete<void>(`/config/agents/${agentName}`),

  getHistory: (agentName: string) =>
    apiClient.get<ConfigurationHistory[]>(`/config/agents/${agentName}/history`),

  addMountCommand: (agentName: string, request: MountCommandRequest) =>
    apiClient.post<AgentConfig>(`/config/agents/${agentName}/mount-commands`, request),

  removeMountCommand: (agentName: string, commandId: string) =>
    apiClient.delete<AgentConfig>(`/config/agents/${agentName}/mount-commands/${commandId}`),

  addSubAgent: (agentName: string, request: MountSubAgentRequest) =>
    apiClient.post<AgentConfig>(`/config/agents/${agentName}/sub-agents`, request),

  removeSubAgent: (agentName: string, subAgentId: string) =>
    apiClient.delete<AgentConfig>(`/config/agents/${agentName}/sub-agents/${subAgentId}`),
}

// =============================================================================
// Pipeline Configuration API
// =============================================================================

export const pipelineConfigApi = {
  getAll: async () => {
    const response = await apiClient.get<{ pipelines: PipelineConfig[]; total_count: number }>('/config/pipelines')
    return response.pipelines
  },

  getByName: (pipelineName: string) =>
    apiClient.get<PipelineConfig>(`/config/pipelines/${pipelineName}`),

  create: (config: PipelineConfig) =>
    apiClient.post<PipelineConfig>('/config/pipelines', config),

  update: (pipelineName: string, config: Partial<PipelineConfig>) =>
    apiClient.put<PipelineConfig>(`/config/pipelines/${pipelineName}`, config),

  delete: (pipelineName: string) => apiClient.delete<void>(`/config/pipelines/${pipelineName}`),

  getHistory: (pipelineName: string) =>
    apiClient.get<ConfigurationHistory[]>(`/config/pipelines/${pipelineName}/history`),
}

// =============================================================================
// Configuration Commands API
// =============================================================================

export const configurationCommandsApi = {
  validate: (config: ProjectConfig | AgentConfig | PipelineConfig) =>
    apiClient.post<ConfigurationCommandResult>('/config/commands/validate', config),

  deploy: (configType: 'project' | 'agent' | 'pipeline', configName: string) =>
    apiClient.post<ConfigurationCommandResult>(`/config/commands/deploy`, {
      configType,
      configName,
    }),

  rollback: (configType: 'project' | 'agent' | 'pipeline', configName: string, version: number) =>
    apiClient.post<ConfigurationCommandResult>(`/config/commands/rollback`, {
      configType,
      configName,
      version,
    }),
}

// =============================================================================
// Work Items API
// =============================================================================

export const workItemsApi = {
  getAll: async (projectId?: string) => {
    const response = await apiClient.get<{ work_items: WorkItem[]; total_count: number }>('/work-items', {
      params: projectId ? { projectId } : undefined,
    })
    return response.work_items
  },

  getById: (workItemId: string) => apiClient.get<WorkItem>(`/work-items/${workItemId}`),

  create: (request: CreateWorkItemRequest) =>
    apiClient.post<WorkItem>('/work-items', request),

  update: (workItemId: string, request: UpdateWorkItemRequest) =>
    apiClient.put<WorkItem>(`/work-items/${workItemId}`, request),

  delete: (workItemId: string) => apiClient.delete<void>(`/work-items/${workItemId}`),

  sync: (projectId: string) =>
    apiClient.post<{ synced: number; created: number; updated: number }>(
      `/work-items/sync/${projectId}`
    ),
}

// =============================================================================
// Executions API
// =============================================================================

export const executionsApi = {
  getAll: async (workItemId?: string) => {
    const response = await apiClient.get<{ executions: ExecutionSummary[]; total_count: number }>('/executions', {
      params: workItemId ? { workItemId } : undefined,
    })
    return response.executions
  },

  getById: (executionId: string) => apiClient.get<Execution>(`/executions/${executionId}`),

  start: (request: StartExecutionRequest) =>
    apiClient.post<Execution>('/executions', request),

  cancel: (executionId: string) => apiClient.post<void>(`/executions/${executionId}/cancel`),

  retry: (executionId: string) => apiClient.post<Execution>(`/executions/${executionId}/retry`),

  getOutput: (executionId: string) =>
    apiClient.get<{ output: string; logs: string[] }>(`/executions/${executionId}/output`),
}

// =============================================================================
// Authentication API
// =============================================================================

export const authApi = {
  logout: () => apiClient.post<{ message: string }>('/auth/logout'),

  getTokenInfo: () => apiClient.get<{
    issued_at: string
    expires_at: string
    subject: string
    is_valid: boolean
  }>('/auth/token-info'),
}

// Export client for advanced usage
export { apiClient }
export default apiClient
export type { ApiError }
