import axios, { AxiosError, AxiosInstance, AxiosRequestConfig } from 'axios'
import axiosRetry from 'axios-retry'
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
  ApiError,
  WorkItem,
  CreateWorkItemRequest,
  UpdateWorkItemRequest,
  Execution,
  ExecutionSummary,
  StartExecutionRequest,
} from '../types'
import { CircuitBreaker, CircuitBreakerError } from './circuitBreaker'
import {
  generateCorrelationId,
  isRetriableError,
  parseRetryAfter,
  formatErrorMessage,
} from './utils'

// Configuration constants
const API_BASE_URL =
  import.meta.env.VITE_API_BASE_URL || window.location.origin + '/api/v1'
const API_TIMEOUT = 30000 // 30 seconds
const MAX_RETRIES = 3
const CIRCUIT_BREAKER_THRESHOLD = 5
const CIRCUIT_BREAKER_RESET_TIMEOUT = 60000 // 1 minute

// Global circuit breaker for API
const circuitBreaker = new CircuitBreaker({
  failureThreshold: CIRCUIT_BREAKER_THRESHOLD,
  resetTimeout: CIRCUIT_BREAKER_RESET_TIMEOUT,
})

// Create axios instance with proper configuration
const api: AxiosInstance = axios.create({
  baseURL: API_BASE_URL,
  withCredentials: true, // Send httpOnly cookies with requests
  headers: {
    'Content-Type': 'application/json',
  },
  timeout: API_TIMEOUT,
})

// Configure retry logic with exponential backoff
axiosRetry(api, {
  retries: MAX_RETRIES,
  retryDelay: (retryCount, error) => {
    // Check for Retry-After header
    const retryAfter = error.response?.headers['retry-after']
    const retryDelay = parseRetryAfter(retryAfter)
    if (retryDelay !== null) {
      console.info(`[API] Respecting Retry-After header: ${retryDelay}ms`)
      return retryDelay
    }

    // Exponential backoff with jitter
    const baseDelay = 1000 // 1 second
    const exponentialDelay = baseDelay * Math.pow(2, retryCount - 1)
    const jitter = Math.random() * 0.3 * exponentialDelay
    const delay = Math.min(exponentialDelay + jitter, 30000) // Max 30s

    console.info(`[API] Retry attempt ${retryCount}/${MAX_RETRIES} after ${delay}ms`)
    return delay
  },
  retryCondition: (error) => {
    // Use custom retry logic
    const shouldRetry = isRetriableError(error)

    if (shouldRetry) {
      console.warn(`[API] Retrying failed request: ${error.config?.url}`, {
        status: error.response?.status,
        message: error.message,
      })
    }

    return shouldRetry
  },
  onRetry: (retryCount, error, requestConfig) => {
    console.info(`[API] Retrying request (${retryCount}/${MAX_RETRIES}):`, {
      url: requestConfig.url,
      method: requestConfig.method,
      error: error.message,
    })
  },
})

// Request interceptor for logging and correlation IDs
api.interceptors.request.use(
  (config) => {
    // Add correlation ID for request tracking
    const correlationId = generateCorrelationId()
    config.headers['X-Correlation-ID'] = correlationId

    // Log outgoing request (in development)
    if (import.meta.env.DEV) {
      console.debug(`[API] ${config.method?.toUpperCase()} ${config.url}`, {
        correlationId,
        params: config.params,
        data: config.data,
      })
    }

    // httpOnly cookies are sent automatically by the browser
    // No need to manually add Authorization header for cookie-based auth
    return config
  },
  (error) => {
    console.error('[API] Request setup error:', error)
    return Promise.reject(error)
  }
)

// Response interceptor for error handling and logging
api.interceptors.response.use(
  (response) => {
    // Log successful response (in development)
    if (import.meta.env.DEV) {
      console.debug(`[API] ${response.status} ${response.config.url}`, {
        correlationId: response.config.headers['X-Correlation-ID'],
        data: response.data,
      })
    }

    return response
  },
  (error: AxiosError<ApiError>) => {
    // Log error response
    const correlationId = error.config?.headers?.['X-Correlation-ID']
    console.error(`[API] Request failed: ${error.config?.url}`, {
      correlationId,
      status: error.response?.status,
      message: error.message,
      response: error.response?.data,
    })

    // Enhanced error handling with structured error types
    if (error.response) {
      // Handle 401 Unauthorized - trigger auth event (cookie will be cleared by server)
      if (error.response.status === 401) {
        console.warn('[API] Unauthorized - triggering auth event')
        window.dispatchEvent(new CustomEvent('auth:unauthorized'))
      }

      // Handle 429 Rate Limiting
      if (error.response.status === 429) {
        const retryAfter = error.response.headers['retry-after']
        console.warn('[API] Rate limited', { retryAfter })

        // Show user notification if toast exists
        if (typeof window !== 'undefined' && (window as any).toast) {
          ;(window as any).toast.error(
            'Too many requests. Please wait a moment and try again.'
          )
        }
      }

      // Server responded with error status
      const apiError: ApiError = {
        message: error.response.data?.message || formatErrorMessage(error),
        statusCode: error.response.status,
        details: error.response.data?.details,
        timestamp: new Date().toISOString(),
      }
      return Promise.reject(apiError)
    } else if (error.request) {
      // Request made but no response received (network error)
      const apiError: ApiError = {
        message: 'Network error: Unable to reach server',
        statusCode: 0,
        details: { originalError: error.message },
        timestamp: new Date().toISOString(),
      }
      return Promise.reject(apiError)
    } else {
      // Error in request setup
      const apiError: ApiError = {
        message: error.message || 'Unknown error occurred',
        statusCode: 500,
        timestamp: new Date().toISOString(),
      }
      return Promise.reject(apiError)
    }
  }
)

/**
 * Request cancellation support
 * Store active requests by key for cancellation
 */
const activeRequests = new Map<string, AbortController>()

/**
 * Create a cancellable request
 */
function createCancellableRequest(key: string): AbortController {
  // Cancel existing request with same key
  const existingController = activeRequests.get(key)
  if (existingController) {
    existingController.abort()
    activeRequests.delete(key)
  }

  // Create new controller
  const controller = new AbortController()
  activeRequests.set(key, controller)

  return controller
}

/**
 * Remove request from active requests
 */
function removeActiveRequest(key: string): void {
  activeRequests.delete(key)
}

/**
 * Cancel a specific request by key
 */
export function cancelRequest(key: string): void {
  const controller = activeRequests.get(key)
  if (controller) {
    controller.abort()
    activeRequests.delete(key)
    console.info(`[API] Cancelled request: ${key}`)
  }
}

/**
 * Cancel all active requests
 */
export function cancelAllRequests(): void {
  console.info(`[API] Cancelling ${activeRequests.size} active requests`)
  activeRequests.forEach((controller) => controller.abort())
  activeRequests.clear()
}

/**
 * Wrapper for API calls with circuit breaker protection
 */
async function withCircuitBreaker<T>(
  fn: () => Promise<T>,
  operationName: string
): Promise<T> {
  try {
    return await circuitBreaker.execute(fn)
  } catch (error) {
    if (error instanceof CircuitBreakerError) {
      console.error(`[API] Circuit breaker open for: ${operationName}`, error.stats)

      // Notify user of service unavailability
      if (typeof window !== 'undefined' && (window as any).toast) {
        ;(window as any).toast.error(
          'Service temporarily unavailable. Please try again in a moment.'
        )
      }
    }
    throw error
  }
}

/**
 * Enhanced API wrapper with cancellation support
 */
interface CancellableRequestConfig extends AxiosRequestConfig {
  cancelKey?: string // Unique key for request cancellation
}

/**
 * Make a GET request with circuit breaker and cancellation support
 */
async function apiGet<T>(
  url: string,
  config?: CancellableRequestConfig
): Promise<T> {
  const { cancelKey, ...axiosConfig } = config || {}

  let controller: AbortController | undefined
  if (cancelKey) {
    controller = createCancellableRequest(cancelKey)
    axiosConfig.signal = controller.signal
  }

  try {
    const response = await withCircuitBreaker(
      () => api.get<T>(url, axiosConfig),
      `GET ${url}`
    )
    return response.data
  } finally {
    if (cancelKey) {
      removeActiveRequest(cancelKey)
    }
  }
}

/**
 * Make a POST request with circuit breaker and cancellation support
 */
async function apiPost<T>(
  url: string,
  data?: any,
  config?: CancellableRequestConfig
): Promise<T> {
  const { cancelKey, ...axiosConfig } = config || {}

  let controller: AbortController | undefined
  if (cancelKey) {
    controller = createCancellableRequest(cancelKey)
    axiosConfig.signal = controller.signal
  }

  try {
    const response = await withCircuitBreaker(
      () => api.post<T>(url, data, axiosConfig),
      `POST ${url}`
    )
    return response.data
  } finally {
    if (cancelKey) {
      removeActiveRequest(cancelKey)
    }
  }
}

/**
 * Make a PATCH request with circuit breaker and cancellation support
 */
async function apiPatch<T>(
  url: string,
  data?: any,
  config?: CancellableRequestConfig
): Promise<T> {
  const { cancelKey, ...axiosConfig } = config || {}

  let controller: AbortController | undefined
  if (cancelKey) {
    controller = createCancellableRequest(cancelKey)
    axiosConfig.signal = controller.signal
  }

  try {
    const response = await withCircuitBreaker(
      () => api.patch<T>(url, data, axiosConfig),
      `PATCH ${url}`
    )
    return response.data
  } finally {
    if (cancelKey) {
      removeActiveRequest(cancelKey)
    }
  }
}

/**
 * Make a DELETE request with circuit breaker and cancellation support
 */
async function apiDelete<T>(
  url: string,
  config?: CancellableRequestConfig
): Promise<T> {
  const { cancelKey, ...axiosConfig } = config || {}

  let controller: AbortController | undefined
  if (cancelKey) {
    controller = createCancellableRequest(cancelKey)
    axiosConfig.signal = controller.signal
  }

  try {
    const response = await withCircuitBreaker(
      () => api.delete<T>(url, axiosConfig),
      `DELETE ${url}`
    )
    return response.data
  } finally {
    if (cancelKey) {
      removeActiveRequest(cancelKey)
    }
  }
}

/**
 * Get circuit breaker statistics (for monitoring/debugging)
 */
export function getCircuitBreakerStats() {
  return circuitBreaker.getStats()
}

/**
 * Manually reset circuit breaker (for admin/testing purposes)
 */
export function resetCircuitBreaker() {
  circuitBreaker.reset()
  console.info('[API] Circuit breaker manually reset')
}

// Project Configuration API
export const projectConfigApi = {
  get: async (projectName: string): Promise<ProjectConfig> => {
    return apiGet<ProjectConfig>(
      `/configurations/projects/${projectName}`,
      { cancelKey: `project-config-${projectName}` }
    )
  },

  update: async (
    projectName: string,
    request: UpdateProjectConfigRequest
  ): Promise<ConfigurationCommandResult> => {
    return apiPatch<ConfigurationCommandResult>(
      `/configurations/projects/${projectName}`,
      request
    )
  },

  addEnvironmentVariable: async (
    projectName: string,
    request: AddEnvironmentVariableRequest
  ): Promise<ConfigurationCommandResult> => {
    return apiPost<ConfigurationCommandResult>(
      `/configurations/projects/${projectName}/environment`,
      request
    )
  },

  removeEnvironmentVariable: async (
    projectName: string,
    variableName: string,
    userId: string
  ): Promise<ConfigurationCommandResult> => {
    return apiDelete<ConfigurationCommandResult>(
      `/configurations/projects/${projectName}/environment/${variableName}`,
      { params: { user_id: userId } }
    )
  },

  mountCommand: async (
    projectName: string,
    request: MountCommandRequest
  ): Promise<ConfigurationCommandResult> => {
    return apiPost<ConfigurationCommandResult>(
      `/configurations/projects/${projectName}/commands`,
      request
    )
  },

  unmountCommand: async (
    projectName: string,
    commandName: string,
    userId: string
  ): Promise<ConfigurationCommandResult> => {
    return apiDelete<ConfigurationCommandResult>(
      `/configurations/projects/${projectName}/commands/${commandName}`,
      { params: { user_id: userId } }
    )
  },

  mountSubAgent: async (
    projectName: string,
    request: MountSubAgentRequest
  ): Promise<ConfigurationCommandResult> => {
    return apiPost<ConfigurationCommandResult>(
      `/configurations/projects/${projectName}/subagents`,
      request
    )
  },

  unmountSubAgent: async (
    projectName: string,
    subagentName: string,
    userId: string
  ): Promise<ConfigurationCommandResult> => {
    return apiDelete<ConfigurationCommandResult>(
      `/configurations/projects/${projectName}/subagents/${subagentName}`,
      { params: { user_id: userId } }
    )
  },
}

// Agent Configuration API
export const agentConfigApi = {
  list: async (projectName?: string): Promise<AgentConfig[]> => {
    return apiGet<AgentConfig[]>('/configurations/agents', {
      params: { project_name: projectName },
      cancelKey: 'agent-config-list',
    })
  },

  get: async (agentName: string): Promise<AgentConfig> => {
    return apiGet<AgentConfig>(
      `/configurations/agents/${agentName}`,
      { cancelKey: `agent-config-${agentName}` }
    )
  },

  update: async (
    agentName: string,
    request: UpdateAgentConfigRequest
  ): Promise<ConfigurationCommandResult> => {
    return apiPatch<ConfigurationCommandResult>(
      `/configurations/agents/${agentName}`,
      request
    )
  },
}

// Pipeline Configuration API
export const pipelineConfigApi = {
  list: async (projectName?: string): Promise<PipelineConfig[]> => {
    return apiGet<PipelineConfig[]>('/configurations/pipelines', {
      params: { project_name: projectName },
      cancelKey: 'pipeline-config-list',
    })
  },

  get: async (pipelineName: string): Promise<PipelineConfig> => {
    return apiGet<PipelineConfig>(
      `/configurations/pipelines/${pipelineName}`,
      { cancelKey: `pipeline-config-${pipelineName}` }
    )
  },

  update: async (
    pipelineName: string,
    request: UpdateAgentConfigRequest
  ): Promise<ConfigurationCommandResult> => {
    return apiPatch<ConfigurationCommandResult>(
      `/configurations/pipelines/${pipelineName}`,
      request
    )
  },
}

// Configuration History API
export const configHistoryApi = {
  list: async (filters?: {
    projectName?: string
    configType?: 'project' | 'agent' | 'pipeline'
    limit?: number
    offset?: number
  }): Promise<ConfigurationHistory[]> => {
    return apiGet<ConfigurationHistory[]>('/configurations/history', {
      params: {
        project_name: filters?.projectName,
        config_type: filters?.configType,
        limit: filters?.limit || 50,
        offset: filters?.offset || 0,
      },
      cancelKey: 'config-history-list',
    })
  },

  rollback: async (
    changeId: string,
    userId: string,
    reason?: string
  ): Promise<ConfigurationCommandResult> => {
    return apiPost<ConfigurationCommandResult>(
      `/configurations/rollback/${changeId}`,
      null,
      { params: { user_id: userId, reason } }
    )
  },
}

// Work Items API
export const workItemsApi = {
  list: async (filters?: {
    status?: string
    assignee?: string
    limit?: number
    offset?: number
  }): Promise<WorkItem[]> => {
    return apiGet<WorkItem[]>('/work-items', {
      params: {
        status: filters?.status,
        assignee: filters?.assignee,
        limit: filters?.limit || 50,
        offset: filters?.offset || 0,
      },
      cancelKey: 'work-items-list',
    })
  },

  get: async (id: string): Promise<WorkItem> => {
    return apiGet<WorkItem>(`/work-items/${id}`, {
      cancelKey: `work-item-${id}`,
    })
  },

  create: async (request: CreateWorkItemRequest): Promise<WorkItem> => {
    return apiPost<WorkItem>('/work-items', request)
  },

  update: async (id: string, request: UpdateWorkItemRequest): Promise<WorkItem> => {
    return apiPatch<WorkItem>(`/work-items/${id}`, request)
  },

  delete: async (id: string): Promise<void> => {
    await apiDelete<void>(`/work-items/${id}`)
  },
}

// Executions API
export const executionsApi = {
  list: async (filters?: {
    work_item_id?: string
    agent_name?: string
    status?: string
    limit?: number
    offset?: number
  }): Promise<ExecutionSummary[]> => {
    return apiGet<ExecutionSummary[]>('/executions', {
      params: {
        work_item_id: filters?.work_item_id,
        agent_name: filters?.agent_name,
        status: filters?.status,
        limit: filters?.limit || 50,
        offset: filters?.offset || 0,
      },
      cancelKey: 'executions-list',
    })
  },

  get: async (id: string): Promise<Execution> => {
    return apiGet<Execution>(`/executions/${id}`, {
      cancelKey: `execution-${id}`,
    })
  },

  start: async (request: StartExecutionRequest): Promise<Execution> => {
    return apiPost<Execution>('/executions', request)
  },

  cancel: async (id: string): Promise<void> => {
    await apiPost<void>(`/executions/${id}/cancel`)
  },

  getLogs: async (id: string): Promise<string[]> => {
    const result = await apiGet<{ logs: string[] }>(`/executions/${id}/logs`, {
      cancelKey: `execution-logs-${id}`,
    })
    return result.logs
  },
}

// Authentication API
export const authApi = {
  logout: async (): Promise<void> => {
    await apiPost<void>('/v2/auth/logout')
  },
}

export default api
