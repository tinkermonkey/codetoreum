import axios from 'axios'
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
} from '../types'

const api = axios.create({
  baseURL: '/api/v1',
  headers: {
    'Content-Type': 'application/json',
  },
})

// Project Configuration API
export const projectConfigApi = {
  get: async (projectName: string): Promise<ProjectConfig> => {
    const response = await api.get(`/configurations/projects/${projectName}`)
    return response.data
  },

  update: async (
    projectName: string,
    request: UpdateProjectConfigRequest
  ): Promise<ConfigurationCommandResult> => {
    const response = await api.patch(
      `/configurations/projects/${projectName}`,
      request
    )
    return response.data
  },

  addEnvironmentVariable: async (
    projectName: string,
    request: AddEnvironmentVariableRequest
  ): Promise<ConfigurationCommandResult> => {
    const response = await api.post(
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
    const response = await api.delete(
      `/configurations/projects/${projectName}/environment/${variableName}`,
      { params: { user_id: userId } }
    )
    return response.data
  },

  mountCommand: async (
    projectName: string,
    request: MountCommandRequest
  ): Promise<ConfigurationCommandResult> => {
    const response = await api.post(
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
    const response = await api.delete(
      `/configurations/projects/${projectName}/commands/${commandName}`,
      { params: { user_id: userId } }
    )
    return response.data
  },

  mountSubAgent: async (
    projectName: string,
    request: MountSubAgentRequest
  ): Promise<ConfigurationCommandResult> => {
    const response = await api.post(
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
    const response = await api.delete(
      `/configurations/projects/${projectName}/subagents/${subagentName}`,
      { params: { user_id: userId } }
    )
    return response.data
  },

  getHistory: async (projectName: string): Promise<ConfigurationHistory[]> => {
    const response = await api.get(
      `/configurations/projects/${projectName}/history`
    )
    return response.data
  },

  rollback: async (
    projectName: string,
    version: number,
    userId: string
  ): Promise<ConfigurationCommandResult> => {
    const response = await api.post(
      `/configurations/projects/${projectName}/rollback`,
      { version, user_id: userId }
    )
    return response.data
  },
}

// Agent Configuration API
export const agentConfigApi = {
  get: async (projectName: string, agentName: string): Promise<AgentConfig> => {
    const response = await api.get(
      `/configurations/projects/${projectName}/agents/${agentName}`
    )
    return response.data
  },

  list: async (projectName: string): Promise<AgentConfig[]> => {
    const response = await api.get(
      `/configurations/projects/${projectName}/agents`
    )
    return response.data
  },

  update: async (
    projectName: string,
    agentName: string,
    request: UpdateAgentConfigRequest
  ): Promise<ConfigurationCommandResult> => {
    const response = await api.patch(
      `/configurations/projects/${projectName}/agents/${agentName}`,
      request
    )
    return response.data
  },
}

// Pipeline Configuration API
export const pipelineConfigApi = {
  get: async (
    projectName: string,
    pipelineName: string
  ): Promise<PipelineConfig> => {
    const response = await api.get(
      `/configurations/projects/${projectName}/pipelines/${pipelineName}`
    )
    return response.data
  },

  list: async (projectName: string): Promise<PipelineConfig[]> => {
    const response = await api.get(
      `/configurations/projects/${projectName}/pipelines`
    )
    return response.data
  },

  update: async (
    projectName: string,
    pipelineName: string,
    request: UpdateAgentConfigRequest
  ): Promise<ConfigurationCommandResult> => {
    const response = await api.patch(
      `/configurations/projects/${projectName}/pipelines/${pipelineName}`,
      request
    )
    return response.data
  },
}

export default api
