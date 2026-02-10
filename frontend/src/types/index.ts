// ============================================================================
// API Error Types
// ============================================================================

export interface ApiError {
  message: string
  statusCode: number
  details?: Record<string, unknown>
  timestamp: string
}

// ============================================================================
// Work Item Types
// ============================================================================

export type WorkItemStatus = 'open' | 'in_progress' | 'completed' | 'failed' | 'cancelled'

export interface WorkItem {
  id: string
  title: string
  description: string
  status: WorkItemStatus
  assignee?: string
  labels: string[]
  url: string
  created_at: string
  updated_at: string
  current_stage?: string
  current_execution_id?: string
  metadata: Record<string, any>
}

export interface CreateWorkItemRequest {
  title: string
  description: string
  assignee?: string
  labels?: string[]
  metadata?: Record<string, any>
}

export interface UpdateWorkItemRequest {
  title?: string
  description?: string
  status?: WorkItemStatus
  assignee?: string
  labels?: string[]
  metadata?: Record<string, any>
}

// ============================================================================
// Execution Types
// ============================================================================

export type ExecutionStatus = 'queued' | 'running' | 'completed' | 'failed' | 'cancelled' | 'timeout'

export interface Execution {
  id: string
  work_item_id: string
  agent_name: string
  status: ExecutionStatus
  started_at?: string
  completed_at?: string
  duration_seconds?: number
  exit_code?: number
  container_id?: string
  error_message?: string
  logs?: string[]
  metadata: Record<string, any>
}

export interface ExecutionSummary {
  id: string
  work_item_id: string
  work_item_title: string
  agent_name: string
  status: ExecutionStatus
  started_at?: string
  duration_seconds?: number
}

export interface StartExecutionRequest {
  work_item_id: string
  workflow_id?: string
  agent_name?: string
}

// ============================================================================
// Event Types
// ============================================================================

export interface WebSocketEvent {
  type: string
  data: any
  timestamp: string
}

export interface ExecutionStartedEvent {
  execution_id: string
  work_item_id: string
  agent_name: string
  started_at: string
}

export interface ExecutionCompletedEvent {
  execution_id: string
  work_item_id: string
  agent_name: string
  status: ExecutionStatus
  duration_seconds: number
  exit_code?: number
}

export interface ExecutionFailedEvent {
  execution_id: string
  work_item_id: string
  agent_name: string
  error_message: string
  error_type: 'container_crashed' | 'execution_timeout' | 'agent_logic_failure' | 'unknown'
}

// ============================================================================
// Configuration Types
// ============================================================================

export interface TechStack {
  language: string
  version: string
  framework?: string
  package_manager?: string
  test_framework?: string
  additional_tools?: string[]
}

export interface TestingConfig {
  unit_test_command?: string
  integration_test_command?: string
  e2e_test_command?: string
  coverage_threshold?: number
  test_directories?: string[]
}

export interface ProjectConfig {
  id: string
  name: string
  version: number
  tech_stacks: Record<string, TechStack>
  pipelines: Pipeline[]
  testing: TestingConfig
  environment_variables: Record<string, EnvironmentVariable>
  mounted_commands: Record<string, MountedCommand>
  mounted_subagents: Record<string, MountedSubAgent>
  created_at: string
  updated_at: string
  metadata: ProjectMetadata
}

export interface ProjectMetadata {
  description?: string
  repository_url?: string
  default_branch?: string
  owner?: string
  tags?: string[]
  last_modified_by?: string
}

export interface AgentConfig {
  project_id: string
  agent_name: string
  display_name?: string
  model: string
  timeout_seconds: number
  max_retries: number
  requires_docker: boolean
  requires_dev_container: boolean
  makes_code_changes: boolean
  filesystem_write_allowed: boolean
  mcp_servers: string[]
  capabilities: Record<string, any>
  version: number
  created_at: string
  updated_at: string
  metadata: AgentMetadata
}

export interface AgentMetadata {
  description?: string
  prompt_template?: string
  examples?: string[]
  success_criteria?: string[]
  failure_patterns?: string[]
  last_modified_by?: string
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
  metadata: PipelineMetadata
}

export interface PipelineMetadata {
  description?: string
  is_default?: boolean
  estimated_duration_minutes?: number
  last_run_at?: string
  total_runs?: number
  success_rate?: number
  last_modified_by?: string
}

export interface Pipeline {
  name: string
  description?: string
  stages: Stage[]
}

export interface StageCondition {
  type: 'success' | 'failure' | 'always' | 'manual' | 'conditional'
  expression?: string
  depends_on?: string[]
}

export interface Stage {
  name: string
  agent: string
  entry_conditions?: StageCondition[]
  transitions?: string[]
  timeout_minutes?: number
  retry_on_failure?: boolean
  max_retries?: number
}

export interface TriggerConfig {
  branch_pattern?: string
  event_types?: string[]
  schedule?: string
  webhook_url?: string
  filters?: Record<string, string>
}

export interface Trigger {
  type: 'push' | 'pull_request' | 'issue' | 'schedule' | 'webhook' | 'manual'
  config: TriggerConfig
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

export interface SubAgentConfig {
  model?: string
  timeout?: number
  capabilities?: string[]
  prompt_template?: string
}

export interface MountedSubAgent {
  config: SubAgentConfig
  description?: string
  created_at: string
  created_by: string
}

// ============================================================================
// Configuration History & Diff Types
// ============================================================================

export type ChangeType =
  | 'created'
  | 'updated'
  | 'deleted'
  | 'env_var_added'
  | 'env_var_removed'
  | 'command_mounted'
  | 'command_unmounted'
  | 'subagent_mounted'
  | 'subagent_unmounted'
  | 'stage_added'
  | 'stage_removed'
  | 'stage_updated'

export interface ConfigChange {
  field: string
  old_value: unknown
  new_value: unknown
  operation: 'add' | 'remove' | 'modify'
}

export interface ConfigurationHistory {
  id: string
  project_id: string
  config_type: 'project' | 'agent' | 'pipeline'
  config_name: string
  config_version: number
  change_type: ChangeType
  changes: ConfigChange[]
  changed_by: string
  changed_at: string
  reason?: string
  can_rollback: boolean
}

export interface DiffLine {
  type: 'added' | 'removed' | 'unchanged'
  content: string
  lineNumber?: number
}

export interface ConfigDiff {
  field: string
  before: string
  after: string
  lines: DiffLine[]
}

// ============================================================================
// API Request/Response Types
// ============================================================================

export interface ConfigurationCommandResult {
  success: boolean
  config_version: number
  message: string
  changes_applied: Record<string, ConfigChange>
  errors?: string[]
}

export interface UpdateProjectConfigRequest {
  updates: Partial<Omit<ProjectConfig, 'id' | 'version' | 'created_at' | 'updated_at'>>
  user_id: string
  reason?: string
}

export interface UpdateAgentConfigRequest {
  updates: Partial<Omit<AgentConfig, 'project_id' | 'agent_name' | 'version' | 'created_at' | 'updated_at'>>
  user_id: string
  reason?: string
}

export interface UpdatePipelineConfigRequest {
  updates: Partial<Omit<PipelineConfig, 'id' | 'project_id' | 'version' | 'created_at' | 'updated_at'>>
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
  subagent_config: SubAgentConfig
  user_id: string
  description?: string
}

// ============================================================================
// UI State Types
// ============================================================================

export interface LoadingState {
  isLoading: boolean
  progress?: number
  message?: string
}

export interface ErrorState {
  hasError: boolean
  error?: ApiError
  title?: string
}

export interface FormState<T> {
  data: T
  isDirty: boolean
  isSubmitting: boolean
  errors: Partial<Record<keyof T, string>>
}

// ============================================================================
// Validation Types
// ============================================================================

export interface ValidationResult {
  isValid: boolean
  errors: ValidationError[]
}

export interface ValidationError {
  field: string
  message: string
  severity: 'error' | 'warning' | 'info'
}

// ============================================================================
// Filter & Pagination Types
// ============================================================================

export interface PaginationParams {
  page: number
  pageSize: number
  totalItems: number
  totalPages: number
}

export interface SortParams {
  field: string
  direction: 'asc' | 'desc'
}

export interface FilterParams {
  searchQuery?: string
  configType?: 'project' | 'agent' | 'pipeline'
  dateRange?: {
    start: string
    end: string
  }
  changedBy?: string
  tags?: string[]
}
