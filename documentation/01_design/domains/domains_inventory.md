# Domains Inventory

## Overview

This document provides a comprehensive inventory of all domain models in the Codetoreum redesign. The domain layer contains pure business logic independent of infrastructure concerns, following Domain-Driven Design (DDD) principles within a Hexagonal Architecture pattern.

## Domain Architecture Pattern

The domain layer is organized following:
- **Hexagonal Architecture**: Pure domain logic isolated from infrastructure
- **Event Sourcing**: All state changes captured as immutable events
- **CQRS**: Separate command (write) and query (read) models
- **Domain-Driven Design**: Rich domain models with business logic

## Core Domains

Based on the system architecture and design documentation, the following domains have been identified:

### 1. Work Item Domain
**Purpose**: Represents a unit of work (issue, task, feature request) that flows through the system

**Type**: Aggregate Root

**Responsibilities**:
- Track work item lifecycle and status
- Manage work item metadata (title, description, labels)
- Enforce work item invariants
- Emit work item-related events

**Related Documentation**:
- `work_item_design.md`

---

### 2. Workflow Domain
**Purpose**: Orchestrates the execution of work items through defined stages and pipelines

**Type**: Aggregate Root

**Responsibilities**:
- Define workflow structure and stages
- Manage workflow execution state
- Coordinate agent assignments
- Track workflow progress and completion
- Enforce workflow invariants (stage dependencies, valid transitions)

**Related Documentation**:
- `workflow_design.md`

---

### 3. Agent Domain
**Purpose**: Represents AI agents with specific capabilities that perform work

**Type**: Aggregate Root

**Responsibilities**:
- Define agent capabilities and skills
- Track agent configuration (model, timeout, permissions)
- Manage agent execution context
- Enforce agent constraints (Docker requirements, file permissions)

**Related Documentation**:
- `agent_design.md`

---

### 4. Agent Execution Domain
**Purpose**: Represents a single instance of an agent performing work

**Type**: Entity

**Responsibilities**:
- Track execution lifecycle (initialized, running, completed, failed)
- Store execution context and results
- Record execution metrics (duration, tokens used)
- Link to parent work item and workflow

**Related Documentation**:
- `agent_execution_design.md`

---

### 5. Pipeline Stage Domain
**Purpose**: Represents a discrete stage within a workflow pipeline

**Type**: Entity

**Responsibilities**:
- Define stage configuration and requirements
- Manage stage dependencies
- Track stage execution status
- Support review cycles and maker-checker patterns

**Related Documentation**:
- `pipeline_stage_design.md`

---

### 6. Project Context Domain
**Purpose**: Encapsulates project-specific configuration and context

**Type**: Aggregate Root

**Responsibilities**:
- Store project metadata (name, repository, tech stack)
- Define project-specific pipelines and workflows
- Manage testing configuration
- Handle branch naming conventions
- Define environment variables

**Related Documentation**:
- `project_context_design.md`

---

### 7. Workflow Template Domain
**Purpose**: Defines reusable workflow structures and patterns

**Type**: Entity

**Responsibilities**:
- Define template structure (stages, agents, dependencies)
- Support customization and inheritance
- Validate template consistency
- Enable workflow instantiation from template

**Related Documentation**:
- `workflow_template_design.md`

---

### 8. Review Cycle Domain
**Purpose**: Manages iterative maker-checker review processes

**Type**: Aggregate Root

**Responsibilities**:
- Coordinate maker and reviewer agents
- Track review iterations and feedback
- Enforce maximum iteration limits
- Manage approval/rejection decisions
- Trigger escalation to human review when needed

**Related Documentation**:
- `review_cycle_design.md`

---

### 9. Workspace Context Domain
**Purpose**: Manages workspace isolation and routing (issues vs discussions vs hybrid)

**Type**: Value Object / Service

**Responsibilities**:
- Route work to appropriate workspace type
- Prepare execution environment (branches, discussions)
- Finalize workspace state (commits, comments)
- Handle workspace-specific operations

**Related Documentation**:
- `workspace_context_design.md`

---

### 10. Execution Result Domain
**Purpose**: Captures the outcome of an agent execution

**Type**: Value Object

**Responsibilities**:
- Store execution output (markdown, structured data)
- Record success/failure status
- Capture error messages and diagnostics
- Track session continuity (session_id)

**Related Documentation**:
- `execution_result_design.md`

---

## Supporting Domains (Value Objects & Services)

### Value Objects

These are immutable objects defined by their attributes rather than identity:

1. **WorkItemId**: Type-safe identifier for work items
2. **WorkflowStatus**: Enumeration of workflow states (NEW, IN_PROGRESS, COMPLETED, FAILED)
3. **AgentCapability**: Definition of agent skills and proficiency levels
4. **ReviewFeedback**: Structured review feedback with issues and approval status
5. **ExecutionContext**: Complete context for agent execution (workspace, config, metadata)

### Domain Services

These encapsulate business logic that doesn't naturally fit within a single aggregate:

1. **WorkAssignmentService**: Assigns work items to appropriate agents
2. **AgentMatchingService**: Matches agents to work requirements based on capabilities
3. **ReviewCycleService**: Orchestrates maker-checker review iterations
4. **WorkflowValidationService**: Validates workflow configurations and templates

---

## Domain Events

Events represent things that happened in the domain. All events are immutable and stored in the event store.

### Work Item Events
- `WorkItemCreated`: New work item created
- `WorkItemStarted`: Work item moved to in-progress
- `WorkItemCompleted`: Work item finished successfully
- `WorkItemFailed`: Work item failed

### Workflow Events
- `WorkflowStarted`: Workflow execution began
- `WorkflowStageCompleted`: A pipeline stage completed
- `WorkflowCompleted`: Entire workflow finished
- `WorkflowFailed`: Workflow encountered fatal error

### Agent Events
- `AgentAssigned`: Agent assigned to work item
- `AgentInitialized`: Agent execution initialized
- `AgentExecutionCompleted`: Agent finished execution
- `AgentExecutionFailed`: Agent execution failed

### Review Events
- `ReviewRequested`: Review cycle initiated
- `ReviewFeedbackProvided`: Reviewer provided feedback
- `ReviewApproved`: Review approved
- `ReviewChangesRequested`: Changes requested by reviewer
- `ReviewEscalated`: Review escalated to human

---

## Bounded Contexts

The domain is organized into logical bounded contexts:

### 1. Work Management Context
- Work Item
- Project Context
- Assignment tracking

### 2. Workflow Context
- Workflow
- Pipeline Stage
- Workflow Template

### 3. Agent Context
- Agent
- Agent Execution
- Agent Capabilities

### 4. Review Context
- Review Cycle
- Review Feedback
- Approval decisions

---

## Domain Invariants

### Work Item Invariants
- Must have a non-empty title
- Must belong to a project
- Can only complete if in progress
- Cannot be reassigned while in progress

### Workflow Invariants
- Must have at least one stage
- Cannot exceed maximum parallel stages (10)
- Stage dependencies must not create cycles
- All stage dependencies must be satisfied before execution

### Agent Invariants
- Must have at least one capability
- Docker-required agents must have verified container
- Cannot execute without required permissions
- Timeout must be positive

### Review Cycle Invariants
- Must have both maker and reviewer agents
- Maximum of 3 iterations before escalation
- Cannot approve without executing reviewer
- Maker and reviewer must be different agents

---

## Integration with Architecture Patterns

### Hexagonal Architecture Integration
- **Domain Layer**: All domains listed above (pure business logic)
- **Input Ports**: WorkflowCommandPort, TaskQueryPort, EventStreamPort, ConfigCommandPort
- **Output Ports**: ITicketSystem, ILLMProvider, IRepository, IContainer, IEventStore, IMetrics

### Event Sourcing Integration
- All domain state changes emit events
- Events stored in IEventStore
- Aggregates can be reconstructed from event streams
- Snapshots created periodically for performance

### CQRS Integration
- **Write Side**: Commands update domain models and emit events
- **Read Side**: Projections build optimized read models from events
- Separate models for commands and queries

---

## Domain Model Organization

```
documentation/01_design/domains/
├── domains_inventory.md           # This file
├── work_item_design.md           # Work Item aggregate design
├── workflow_design.md            # Workflow aggregate design
├── agent_design.md               # Agent aggregate design
├── agent_execution_design.md     # Agent Execution entity design
├── pipeline_stage_design.md      # Pipeline Stage entity design
├── project_context_design.md     # Project Context aggregate design
├── workflow_template_design.md   # Workflow Template entity design
├── review_cycle_design.md        # Review Cycle aggregate design
├── workspace_context_design.md   # Workspace Context design
├── execution_result_design.md    # Execution Result value object design
├── value_objects_design.md       # All value objects
├── domain_services_design.md     # Domain services
└── domain_events_design.md       # Domain events catalog
```

---

## Design Principles Applied

### 1. Ubiquitous Language
All domain models use business terminology consistently:
- "Work Item" not "Task" or "Issue"
- "Agent" not "Processor" or "Worker"
- "Workflow" not "Pipeline" or "Process"

### 2. Rich Domain Models
Domain models contain business logic, not just data:
- Work items know how to validate themselves
- Workflows enforce their own invariants
- Agents determine their own capabilities

### 3. Aggregate Boundaries
Each aggregate maintains its own consistency:
- Work Item aggregate controls its lifecycle
- Workflow aggregate manages its stages
- Review Cycle aggregate coordinates iterations

### 4. Side-Effect Free Functions
Pure functions for complex calculations:
- Agent matching score calculation
- Workflow validation
- Capability comparison

---

## Testing Approach

### Unit Testing
- Test domain models in isolation
- No infrastructure dependencies
- Fast and deterministic

### Property-Based Testing
- Test domain invariants hold under all conditions
- Use hypothesis for property testing
- Verify business rules

### Event Replay Testing
- Reconstruct state from events
- Verify event handling
- Test time-travel scenarios

---

## Migration from Legacy System

### Legacy → Redesign Mapping

| Legacy Component | Redesign Domain | Notes |
|-----------------|-----------------|-------|
| Task (in queue) | Work Item | More explicit lifecycle |
| Agent execution | Agent Execution | Separated from agent definition |
| Pipeline stage config | Pipeline Stage + Workflow Template | Cleaner separation of definition vs execution |
| Task context dict | Execution Context | Structured value object |
| Review cycle logic | Review Cycle aggregate | Extracted to own aggregate |
| Workspace routing | Workspace Context | Explicit domain concept |

### Key Differences
1. **Event Sourcing**: All state changes now captured as events
2. **CQRS**: Separate read/write models for optimization
3. **Hexagonal Ports**: Clear interfaces for external systems
4. **Rich Models**: Business logic in domain, not services
5. **Explicit Contexts**: Workspace and execution contexts as first-class concepts

---

## Next Steps

1. Review individual domain design documents for detailed specifications
2. See `domain_events_design.md` for complete event catalog
3. Consult `domain_services_design.md` for service implementations
4. Reference `value_objects_design.md` for value object specifications

---

## References

- **System Architecture**: `documentation/01_design/02_high_level_arch.md`
- **Domain Layer Overview**: `documentation/01_design/raw_input/08_domain_layer.md`
- **Event Sourcing & CQRS**: `documentation/01_design/raw_input/02-event-sourcing-cqrs.md`
- **Hexagonal Architecture**: `documentation/01_design/raw_input/01-hexagonal-architecture.md`
- **Legacy Components**: `documentation/00_legacy/01_components_and_layers.md`
