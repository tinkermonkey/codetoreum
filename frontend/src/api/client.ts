import axios, { AxiosError, AxiosInstance } from 'axios'
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
} from '../types'

// Environment-aware API base URL
const API_BASE_URL =
  import.meta.env.VITE_API_BASE_URL || window.location.origin + '/api/v1'

// Create axios instance with proper configuration
const api: AxiosInstance = axios.create({
  baseURL: API_BASE_URL,
  headers: {
    'Content-Type': 'application/json',
  },
  timeout: 30000, // 30 second timeout
})

// Response interceptor for error handling
api.interceptors.response.use(
  (response) => response,
  (error: AxiosError<ApiError>) => {
    // Enhanced error handling with structured error types
    if (error.response) {
      // Server responded with error status
      const apiError: ApiError = {
        message: error.response.data?.message || error.message,
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

// Request interceptor for adding auth tokens (if needed in future)
api.interceptors.request.use(
  (config) => {
    // Future: Add authentication token here
    // const token = localStorage.getItem('auth_token')
    // if (token) {
    //   config.headers.Authorization = `Bearer ${token}`
    // }
    return config
  },
  (error) => Promise.reject(error)
)

// Project Configuration API
export const projectConfigApi = {
  get: async (projectName: string): Promise<ProjectConfig> => {
    const response = await api.get<ProjectConfig>(
      `/configurations/projects/${projectName}`
    )
    return response.data
  },

  update: async (
    projectName: string,
    request: UpdateProjectConfigRequest
  ): Promise<ConfigurationCommandResult> => {
    const response = await api.patch<ConfigurationCommandResult>(
      `/configurations/projects/${projectName}`,
      request
    )
    return response.data
  },

  addEnvironmentVariable: async (
    projectName: string,
    request: AddEnvironmentVariableRequest
  ): Promise<ConfigurationCommandResult> => {
    const response = await api.post<ConfigurationCommandResult>(
      `/configurations/projects/${projectName}/environment`,
      request
    )
    return response.data
  },

  removeEnvironmentVariable: async (
    projectName: string,
    variableName: string,
    userId: string
  ): Promise<ConfigurationCommandResult> => {
    const response = await api.delete<ConfigurationCommandResult>(
      `/configurations/projects/${projectName}/environment/${variableName}`,
      { params: { user_id: userId } }
    )
    return response.data
  },

  mountCommand: async (
    projectName: string,
    request: MountCommandRequest
  ): Promise<ConfigurationCommandResult> => {
    const response = await api.post<ConfigurationCommandResult>(
      `/configurations/projects/${projectName}/commands`,
      request
    )
    return response.data
  },

  unmountCommand: async (
    projectName: string,
    commandName: string,
    userId: string
  ): Promise<ConfigurationCommandResult> => {
    const response = await api.delete<ConfigurationCommandResult>(
      `/configurations/projects/${projectName}/commands/${commandName}`,
      { params: { user_id: userId } }
    )
    return response.data
  },

  mountSubAgent: async (
    projectName: string,
    request: MountSubAgentRequest
  ): Promise<ConfigurationCommandResult> => {
    const response = await api.post<ConfigurationCommandResult>(
      `/configurations/projects/${projectName}/subagents`,
      request
    )
    return response.data
  },

  unmountSubAgent: async (
    projectName: string,
    subagentName: string,
    userId: string
  ): Promise<ConfigurationCommandResult> => {
    const response = await api.delete<ConfigurationCommandResult>(
      `/configurations/projects/${projectName}/subagents/${subagentName}`,
      { params: { user_id: userId } }
    )
    return response.data
  },
}

// Agent Configuration API
export const agentConfigApi = {
  list: async (projectName?: string): Promise<AgentConfig[]> => {
    const response = await api.get<AgentConfig[]>('/configurations/agents', {
      params: { project_name: projectName },
    })
    return response.data
  },

  get: async (agentName: string): Promise<AgentConfig> => {
    const response = await api.get<AgentConfig>(
      `/configurations/agents/${agentName}`
    )
    return response.data
  },

  update: async (
    agentName: string,
    request: UpdateAgentConfigRequest
  ): Promise<ConfigurationCommandResult> => {
    const response = await api.patch<ConfigurationCommandResult>(
      `/configurations/agents/${agentName}`,
      request
    )
    return response.data
  },
}

// Pipeline Configuration API
export const pipelineConfigApi = {
  list: async (projectName?: string): Promise<PipelineConfig[]> => {
    const response = await api.get<PipelineConfig[]>(
      '/configurations/pipelines',
      {
        params: { project_name: projectName },
      }
    )
    return response.data
  },

  get: async (pipelineName: string): Promise<PipelineConfig> => {
    const response = await api.get<PipelineConfig>(
      `/configurations/pipelines/${pipelineName}`
    )
    return response.data
  },

  update: async (
    pipelineName: string,
    request: UpdateAgentConfigRequest
  ): Promise<ConfigurationCommandResult> => {
    const response = await api.patch<ConfigurationCommandResult>(
      `/configurations/pipelines/${pipelineName}`,
      request
    )
    return response.data
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
    const response = await api.get<ConfigurationHistory[]>(
      '/configurations/history',
      {
        params: {
          project_name: filters?.projectName,
          config_type: filters?.configType,
          limit: filters?.limit || 50,
          offset: filters?.offset || 0,
        },
      }
    )
    return response.data
  },

  rollback: async (
    changeId: string,
    userId: string,
    reason?: string
  ): Promise<ConfigurationCommandResult> => {
    const response = await api.post<ConfigurationCommandResult>(
      `/configurations/rollback/${changeId}`,
      null,
      {
        params: { user_id: userId, reason },
      }
    )
    return response.data
  },
}

export default api
