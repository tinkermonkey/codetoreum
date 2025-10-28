export interface ProjectConfig {
  id: string
  name: string
  version: number
  tech_stacks: Record<string, any>
  pipelines: Pipeline[]
  testing: Record<string, any>
  environment_variables: Record<string, EnvironmentVariable>
  mounted_commands: Record<string, MountedCommand>
  mounted_subagents: Record<string, MountedSubAgent>
  created_at: string
  updated_at: string
  metadata: Record<string, any>
}

export interface AgentConfig {
  project_id: string
  agent_name: string
  model: string
  timeout: number
  requires_docker: boolean
  makes_code_changes: boolean
  mcp_servers: string[]
  capabilities: string[]
  constraints: Record<string, any>
  version: number
  created_at: string
  updated_at: string
  metadata: Record<string, any>
}

export interface PipelineConfig {
  id: string
  project_id: string
  name: string
  stages: Stage[]
  triggers: Trigger[]
  version: number
  created_at: string
  updated_at: string
  metadata: Record<string, any>
}

export interface Pipeline {
  name: string
  description?: string
  stages: Stage[]
}

export interface Stage {
  name: string
  agent: string
  entry_conditions?: any[]
  transitions?: string[]
}

export interface Trigger {
  type: string
  config: Record<string, any>
}

export interface EnvironmentVariable {
  value: string
  is_secret: boolean
  description?: string
  created_at: string
  created_by: string
}

export interface MountedCommand {
  path: string
  description?: string
  created_at: string
  created_by: string
}

export interface MountedSubAgent {
  config: Record<string, any>
  description?: string
  created_at: string
  created_by: string
}

export interface ConfigurationHistory {
  id: string
  project_id: string
  config_version: number
  change_type: string
  changes: Record<string, any>
  changed_by: string
  changed_at: string
  reason?: string
}

export interface ConfigurationCommandResult {
  success: boolean
  config_version: number
  message: string
  changes_applied: Record<string, any>
  errors?: string[]
}

export interface UpdateProjectConfigRequest {
  updates: Record<string, any>
  user_id: string
  reason?: string
}

export interface UpdateAgentConfigRequest {
  updates: Record<string, any>
  user_id: string
  reason?: string
}

export interface AddEnvironmentVariableRequest {
  variable_name: string
  variable_value: string
  user_id: string
  is_secret?: boolean
  description?: string
}

export interface MountCommandRequest {
  command_name: string
  command_path: string
  user_id: string
  description?: string
}

export interface MountSubAgentRequest {
  subagent_name: string
  subagent_config: Record<string, any>
  user_id: string
  description?: string
}
