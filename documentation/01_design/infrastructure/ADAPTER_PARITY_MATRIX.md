# Adapter Parity Matrix

This document provides a comprehensive inventory of all 29 adapter slots in the Codetoreum system, showing which have production implementations available and which are simulation-only.

## Overview

An **adapter slot** is a port interface that can be swapped between implementations without changing application code. Each slot can have:
- **Simulation adapter**: Deterministic, in-memory, no external dependencies (for testing)
- **Production adapter**: Real implementation connecting to external systems
- **Status**: Implementation availability and readiness

## Quick Reference

| Slot | Simulation | Production | Status | Use Case |
|------|-----------|-----------|--------|----------|
| board | MockBoardAdapter | GitHubBoardAdapter | ✅ Available | Project board operations (columns, work items) |
| ticket | InMemoryTicketAdapter | GitHubTicketAdapter | ✅ Available | Issue/ticket lifecycle management |
| llm | MockLLMAdapter | ClaudeCodeAdapter | ✅ Available | LLM provider integration |
| container | FakeContainerAdapter | DockerContainerAdapter | ✅ Available | Container runtime (execute agents) |
| version_control | InMemoryVersionControlService | *(Planned)* | 🔧 Simulation-only | Git operations (clone, commit, push) |
| discussion_adapter | MockDiscussionAdapter | GitHubDiscussionAdapter | ✅ Available | Comments and discussion threads |
| code_review | MockCodeReviewAdapter | *(Planned)* | 🔧 Simulation-only | Code review management |
| review_cycle | MockReviewCycleAdapter | GitHubCodeReviewAdapter | ✅ Available | Code review lifecycle (PRs, approvals) |
| event_store | InMemoryEventStore | RedisEventStore | ✅ Available | Domain event persistence and replay |
| message_broker | InMemoryMessageBroker | RedisPubSubAdapter | ✅ Available | Async pub/sub for event distribution |
| metrics | InMemoryMetricsAdapter | PrometheusMetricsAdapter | ✅ Available | Metrics collection and reporting |
| storage | InMemoryStorageAdapter | S3StorageAdapter | ✅ Available | Artifact storage (code, reports) |
| config_store | InMemoryConfigStore | DatabaseConfigStore | ✅ Available | Configuration persistence |
| notifier | MockNotifierAdapter | SlackNotifierAdapter | ✅ Available | Notifications (Slack, email, etc.) |
| encryption | SimpleEncryptionAdapter | *(Planned)* | 🔧 Simulation-only | Encrypt sensitive config values |
| project_manager | MockProjectManagerAdapter | *(Planned)* | 🔧 Simulation-only | Project-level operations |
| lock_service | InMemoryLockService | RedisLockService | ✅ Available | Distributed pipeline locking |
| workflow_config | InMemoryWorkflowConfigService | DatabaseWorkflowConfigService | ✅ Available | Workflow definition management |
| queue_service | InMemoryQueueService | KedroQueueService | ✅ Available | Agent execution queue |
| event_emitter | MockEventEmitter | RealEventEmitter | ✅ Available | Domain event emission |
| identity_service | ConfigurableIdentityService | GitHubIdentityService | ✅ Available | Bot/human user identification |
| checkpoint_store | InMemoryCheckpointStore | *(Planned)* | 🔧 Simulation-only | Agent execution checkpoints |
| agent_repository | InMemoryAgentRepository | *(Planned)* | 🔧 Simulation-only | Agent definition storage |
| run_registry | InMemoryActiveWorkflowRunRegistry | *(Planned)* | 🔧 Simulation-only | Active workflow run tracking |
| branch_tracker | InMemoryWorkItemBranchTracker | *(Planned)* | 🔧 Simulation-only | Work item branch association |
| work_item_service | MockWorkItemService | GitHubWorkItemService | ✅ Available | Work item CRUD operations |
| repair_cycle | MockRepairCycleAdapter | *(Planned)* | 🔧 Simulation-only | Test-fix-validate cycles |
| container_recovery | MockContainerRecoveryAdapter | *(Planned)* | 🔧 Simulation-only | Container failure recovery and restart |
| repository | InMemoryRepositoryAdapter | *(Planned)* | 🔧 Simulation-only | Git repository operations |

**Legend:**
- ✅ Available: Real production adapter exists and is tested
- 🔧 Simulation-only: Only mock/in-memory implementation exists (planned for production)
- Blank cell in Production column: Planned for future implementation

---

## Detailed Descriptions

### Ticket System Adapters

#### board (IBoardService)
- **Simulation**: MockBoardAdapter
- **Production**: GitHubBoardAdapter
- **Status**: ✅ Available
- **Purpose**: Manage project board structure (columns, work items, ordering)
- **Example Usage**: `await board_service.get_columns()`, `await board_service.move_work_item(item_id, column)`
- **Credentials Required (GitHub)**: `GITHUB_TOKEN`, `GITHUB_ORG`

#### ticket (ITicketSystem)
- **Simulation**: InMemoryTicketAdapter
- **Production**: GitHubTicketAdapter
- **Status**: ✅ Available
- **Purpose**: Issue/ticket lifecycle management (create, update, close)
- **Example Usage**: `await ticket_system.create_issue(title, description)`, `await ticket_system.close_issue(issue_id)`
- **Credentials Required (GitHub)**: `GITHUB_TOKEN`, `GITHUB_REPO`

#### discussion_adapter (IDiscussionAdapter)
- **Simulation**: MockDiscussionAdapter
- **Production**: GitHubDiscussionAdapter
- **Status**: ✅ Available
- **Purpose**: Comment and discussion thread management
- **Example Usage**: `await discussion.add_comment(item_id, text)`, `await discussion.get_comments(item_id)`
- **Credentials Required (GitHub)**: `GITHUB_TOKEN`

#### work_item_service (IWorkItemService)
- **Simulation**: MockWorkItemService
- **Production**: GitHubWorkItemService
- **Status**: ✅ Available
- **Purpose**: Work item CRUD operations and metadata management
- **Example Usage**: `await work_item_service.get_work_item(id)`, `await work_item_service.update_work_item(id, updates)`
- **Credentials Required (GitHub)**: `GITHUB_TOKEN`

#### code_review (ICodeReviewService)
- **Simulation**: MockCodeReviewAdapter
- **Production**: *(Planned)*
- **Status**: 🔧 Simulation-only
- **Purpose**: Code review management (PR feedback, review status)
- **Example Usage**: `await code_review.create_review(pr_id, body)`, `await code_review.request_review(pr_id, reviewer)`
- **Target Production**: GitHub or GitLab code review integration
- **Credentials Required (GitHub)**: `GITHUB_TOKEN` (when implemented)

#### container_recovery (IContainerRecoveryService)
- **Simulation**: MockContainerRecoveryAdapter
- **Production**: *(Planned)*
- **Status**: 🔧 Simulation-only
- **Purpose**: Container failure detection, recovery orchestration, and restart
- **Example Usage**: `await container_recovery.create_recovery_plan(failed_container)`, `await container_recovery.execute_recovery(plan)`
- **Target Production**: Container monitoring and recovery service
- **Credentials Required**: Docker daemon access (when implemented)

---

### Code Review Adapters

#### review_cycle (ICodeReviewService)
- **Simulation**: MockReviewCycleAdapter
- **Production**: GitHubCodeReviewAdapter
- **Status**: ✅ Available
- **Purpose**: Pull request lifecycle and approval management
- **Example Usage**: `await review_service.create_pull_request(title, head, base)`, `await review_service.request_review(pr_id)`
- **Credentials Required (GitHub)**: `GITHUB_TOKEN`

#### repair_cycle (IRepairCycleService)
- **Simulation**: MockRepairCycleAdapter
- **Production**: *(Planned)*
- **Status**: 🔧 Simulation-only
- **Purpose**: Test-fix-validate cycles for failure recovery
- **Example Usage**: `await repair_cycle.run_test_phase()`, `await repair_cycle.apply_fix()`
- **Target Production**: Custom orchestrator service

---

### Execution & Orchestration Adapters

#### llm (ILLMProvider)
- **Simulation**: MockLLMAdapter
- **Production**: ClaudeCodeAdapter
- **Status**: ✅ Available
- **Purpose**: LLM provider integration for agent execution
- **Example Usage**: `response = await llm.execute_agent(agent_config, context)`
- **Credentials Required (Claude Code)**: `CLAUDE_CODE_API_KEY` or CLI authentication

#### container (IContainer)
- **Simulation**: FakeContainerAdapter
- **Production**: DockerContainerAdapter
- **Status**: ✅ Available
- **Purpose**: Container runtime for isolated agent execution
- **Example Usage**: `container_id = await container.create_container(image, mounts)`, `output = await container.execute(container_id, command)`
- **Credentials Required (Docker)**: Docker daemon access, Docker socket
- **Security Note**: Containers run with limited privileges (no git/GitHub credentials, no docker socket)

#### queue_service (IQueueService)
- **Simulation**: InMemoryQueueService
- **Production**: KedroQueueService
- **Status**: ✅ Available
- **Purpose**: Agent execution queue with position-based ordering
- **Example Usage**: `await queue_service.enqueue_execution(agent_id, work_item_id)`, `pending = await queue_service.get_pending()`
- **Credentials Required**: Depends on backend (Kedro, Redis, etc.)

---

### Version Control & Storage Adapters

#### version_control (IVersionControlService)
- **Simulation**: InMemoryVersionControlService
- **Production**: *(Planned)*
- **Status**: 🔧 Simulation-only
- **Purpose**: Git operations (clone, checkout, commit, push)
- **Example Usage**: `await vc.clone_repo(url)`, `await vc.commit_and_push(branch, message)`
- **Target Production**: GitPython or libgit2 wrapper
- **Credentials Required (Git)**: SSH keys or GitHub credentials (when implemented)
- **Note**: Currently orchestrator handles git operations directly

#### repository (IVersionControlService)
- **Simulation**: InMemoryRepositoryAdapter
- **Production**: *(Planned)*
- **Status**: 🔧 Simulation-only
- **Purpose**: Git repository operations (clone, commit, push, branch management)
- **Example Usage**: `await repository.clone(url)`, `await repository.commit(message)`, `await repository.push(branch)`
- **Target Production**: GitPython, libgit2 wrapper, or Git subprocess integration
- **Credentials Required (Git)**: SSH keys or GitHub token for authenticated repositories (when implemented)
- **Note**: Separate from version_control; handles repository-level operations

#### storage (IStorage)
- **Simulation**: InMemoryStorageAdapter
- **Production**: S3StorageAdapter
- **Status**: ✅ Available
- **Purpose**: Artifact storage for code, reports, logs
- **Example Usage**: `url = await storage.upload(filename, content)`, `content = await storage.download(url)`
- **Credentials Required (AWS S3)**: `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_S3_BUCKET`

---

### Infrastructure & Observability Adapters

#### event_store (IEventStore)
- **Simulation**: InMemoryEventStore
- **Production**: RedisEventStore
- **Status**: ✅ Available
- **Purpose**: Domain event persistence for audit trail and replay
- **Example Usage**: `await event_store.append(event)`, `events = await event_store.get_events(aggregate_id)`
- **Credentials Required (Redis)**: `REDIS_URL` or `REDIS_HOST`, `REDIS_PORT`

#### message_broker (IMessageBroker)
- **Simulation**: InMemoryMessageBroker
- **Production**: RedisPubSubAdapter
- **Status**: ✅ Available
- **Purpose**: Pub/sub event distribution and async handler execution
- **Example Usage**: `await broker.publish(event)`, `broker.subscribe(event_type, handler)`
- **Credentials Required (Redis)**: `REDIS_URL` or `REDIS_HOST`, `REDIS_PORT`

#### event_emitter (IEventEmitter)
- **Simulation**: MockEventEmitter
- **Production**: RealEventEmitter
- **Status**: ✅ Available
- **Purpose**: Domain event emission to event bus
- **Example Usage**: `event_emitter.emit(WorkflowStartedEvent(...))`
- **Credentials Required**: None (internal)

#### metrics (IMetricsAdapter)
- **Simulation**: InMemoryMetricsAdapter
- **Production**: PrometheusMetricsAdapter
- **Status**: ✅ Available
- **Purpose**: Metrics collection for observability
- **Example Usage**: `metrics.counter('workflow_started', 1)`, `metrics.gauge('queue_size', 42)`
- **Credentials Required (Prometheus)**: Depends on scraper configuration

---

### Configuration & State Management Adapters

#### config_store (IConfigStore)
- **Simulation**: InMemoryConfigStore
- **Production**: DatabaseConfigStore
- **Status**: ✅ Available
- **Purpose**: Configuration persistence for workflows, agents, environments
- **Example Usage**: `config = await config_store.get_config(project_id, 'workflow')`, `await config_store.save_config(project_id, config)`
- **Credentials Required (Database)**: `DATABASE_URL` or `POSTGRES_*` vars

#### workflow_config (IWorkflowConfigService)
- **Simulation**: InMemoryWorkflowConfigService
- **Production**: DatabaseWorkflowConfigService
- **Status**: ✅ Available
- **Purpose**: Workflow definition management (pipeline stages, entry conditions)
- **Example Usage**: `workflow = await workflow_config.get_workflow(workflow_id)`, `await workflow_config.save_workflow(workflow)`
- **Credentials Required (Database)**: `DATABASE_URL` or `POSTGRES_*` vars

#### checkpoint_store (ICheckpointStore)
- **Simulation**: InMemoryCheckpointStore
- **Production**: *(Planned)*
- **Status**: 🔧 Simulation-only
- **Purpose**: Agent execution checkpoints for resumable work
- **Example Usage**: `await checkpoint_store.save_checkpoint(execution_id, state)`, `state = await checkpoint_store.load_checkpoint(execution_id)`
- **Target Production**: Database or S3-based storage

#### lock_service (IPipelineLockService)
- **Simulation**: InMemoryLockService
- **Production**: RedisLockService
- **Status**: ✅ Available
- **Purpose**: Distributed pipeline locking to coordinate workflow execution
- **Example Usage**: `async with lock_service.acquire('workflow_lock')`, `await lock_service.release('workflow_lock')`
- **Credentials Required (Redis)**: `REDIS_URL` or `REDIS_HOST`, `REDIS_PORT`

---

### Identity & Security Adapters

#### identity_service (IIdentityService)
- **Simulation**: ConfigurableIdentityService
- **Production**: GitHubIdentityService
- **Status**: ✅ Available
- **Purpose**: Bot/human user identification for audit and permissions
- **Example Usage**: `user = await identity_service.get_user(user_id)`, `is_bot = await identity_service.is_bot(user_id)`
- **Credentials Required (GitHub)**: `GITHUB_TOKEN`, `GITHUB_ORG`

#### encryption (IEncryptionAdapter)
- **Simulation**: SimpleEncryptionAdapter
- **Production**: *(Planned)*
- **Status**: 🔧 Simulation-only
- **Purpose**: Encrypt sensitive configuration values (tokens, API keys)
- **Example Usage**: `encrypted = encryption.encrypt(secret)`, `decrypted = encryption.decrypt(encrypted)`
- **Target Production**: AWS KMS or HashiCorp Vault
- **Note**: SimpleEncryptionAdapter is NOT SECURE for production (only for tests)

#### notifier (INotifierAdapter)
- **Simulation**: MockNotifierAdapter
- **Production**: SlackNotifierAdapter
- **Status**: ✅ Available
- **Purpose**: Notifications for workflow events (Slack, email, etc.)
- **Example Usage**: `await notifier.notify('channel', 'Workflow started')`, `await notifier.alert('alert_type', details)`
- **Credentials Required (Slack)**: `SLACK_WEBHOOK_URL` or `SLACK_BOT_TOKEN`

---

### Repository & Agent Management Adapters

#### agent_repository (IAgentRepository)
- **Simulation**: InMemoryAgentRepository
- **Production**: *(Planned)*
- **Status**: 🔧 Simulation-only
- **Purpose**: Agent definition storage and retrieval
- **Example Usage**: `agent = await agent_repo.get_agent(agent_id)`, `await agent_repo.list_agents()`
- **Target Production**: Database or GitHub registry

#### run_registry (IActiveWorkflowRunRegistry)
- **Simulation**: InMemoryActiveWorkflowRunRegistry
- **Production**: *(Planned)*
- **Status**: 🔧 Simulation-only
- **Purpose**: Track active workflow runs for lifecycle management
- **Example Usage**: `runs = await run_registry.get_active_runs(workflow_id)`, `await run_registry.register_run(run_id)`
- **Target Production**: Database or Redis-based registry

#### branch_tracker (IWorkItemBranchTracker)
- **Simulation**: InMemoryWorkItemBranchTracker
- **Production**: *(Planned)*
- **Status**: 🔧 Simulation-only
- **Purpose**: Track which Git branches correspond to which work items
- **Example Usage**: `branch = await tracker.get_branch_for_item(item_id)`, `await tracker.associate_branch(item_id, branch)`
- **Target Production**: Database or GitHub metadata

#### project_manager (IProjectManagerService)
- **Simulation**: MockProjectManagerAdapter
- **Production**: *(Planned)*
- **Status**: 🔧 Simulation-only
- **Purpose**: Project-level operations (settings, access control)
- **Example Usage**: `settings = await project_manager.get_settings(project_id)`, `await project_manager.update_settings(project_id, settings)`
- **Target Production**: GitHub organization APIs

---

## Default Configuration

The default SimulationConfig uses all simulation adapters for maximum determinism:

```python
AdapterSelectionConfig(
    board="mock",
    ticket="in_memory",
    llm="mock",
    version_control="in_memory",
    container="fake",
    event_store="in_memory",
    metrics="in_memory",
    storage="in_memory",
    config_store="in_memory",
    notifier="mock",
    encryption="simple",
    discussion_adapter="mock",
    code_review="mock",
    review_cycle="mock",
    repair_cycle="mock",
    container_recovery="mock",
    project_manager="mock",
    lock_service="in_memory",
    workflow_config="in_memory",
    queue_service="in_memory",
    event_emitter="capturing",
    message_broker="in_memory",
    identity_service="configurable",
    checkpoint_store="in_memory",
    agent_repository="in_memory",
    run_registry="in_memory",
    branch_tracker="in_memory",
    work_item_service="mock",
    repository="in_memory",
)
```

---

## Swapping Adapters

### In Code

```python
from codetoreum.infrastructure.simulation.simulation_config import SimulationConfig
import dataclasses

# Start with default config (all simulation)
config = SimulationConfig.create_fast_config("my_test")

# Override one slot
config = dataclasses.replace(
    config,
    adapters=dataclasses.replace(
        config.adapters,
        board="github",  # Use GitHub instead of mock
        ticket="github",  # Use GitHub instead of in_memory
    )
)

# Boot the application
bootstrap = SimulationApplicationBootstrap(config)
await bootstrap.setup()
```

### Via YAML Configuration

See `documentation/01_design/infrastructure/ADAPTER_CREDENTIALS.md` and example scenario files in `scenarios/`:
- `scenarios/mixed_github_real.yaml` - GitHub + simulated agents
- `scenarios/mixed_full_real.yaml` - All real systems

---

## Common Mixed Configurations

### Real GitHub + Simulated Agents
**When**: Integration testing with real issues but simulated responses
**Adapters**:
- board, ticket, discussion, review_cycle, work_item_service, version_control: GitHub
- llm, container: Simulation (fast, deterministic)
- event_store, message_broker: Redis (persistent, production-like)
**Benefits**: Tests real workflow patterns against actual GitHub data without LLM costs
**Example**: `scenarios/mixed_github_real.yaml`

### All Real Systems
**When**: Production deployment or production-like testing
**Adapters**:
- All board, ticket, review, discussion adapters: GitHub
- llm: ClaudeCodeAdapter
- container: DockerContainerAdapter
- event_store, message_broker: Redis
**Benefits**: Complete end-to-end testing with real systems
**Example**: `scenarios/mixed_full_real.yaml`

### All Simulation (Default)
**When**: Unit tests, CI/CD, development
**Adapters**: All simulation variants
**Benefits**: 10-100x faster, no external dependencies, deterministic
**Example**: Default `SimulationConfig.create_fast_config()`

---

## Adapter Validation & Credentials

Each adapter has required environment variables for production use. At application startup, missing credentials trigger `AdapterConfigurationError` with a clear message listing:
1. The adapter slot name (e.g., "board")
2. The configured implementation (e.g., "github")
3. Missing environment variables (e.g., "GITHUB_TOKEN, GITHUB_ORG")

See `documentation/01_design/infrastructure/ADAPTER_CREDENTIALS.md` for complete credential reference.

---

## Future Work

Planned production adapters to complete parity:
- **version_control**: Git operations (GitPython or libgit2 wrapper)
- **encryption**: Vault integration (AWS KMS, HashiCorp Vault)
- **checkpoint_store**: Database or S3-based storage
- **project_manager**: GitHub organization APIs
- **repair_cycle**: Custom orchestrator service
- **agent_repository**: Database or GitHub registry
- **run_registry**: Database or Redis-based registry
- **branch_tracker**: Database or GitHub metadata
