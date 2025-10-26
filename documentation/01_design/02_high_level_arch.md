I'll review the project files to understand your current system and design goals, then propose a high-level architecture for generation 2 of Claudetoreum.Based on my review of your current system architecture and redesign goals, I'll propose a high-level design for generation 2 of Claudetoreum that prioritizes testability through a **Hexagonal Architecture** pattern with support for simulation mode.

## Proposed Architecture: Hexagonal with Event Sourcing

### Core Design Principles

1. **Hexagonal Architecture (Ports & Adapters)** - Clear separation between business logic and external dependencies
2. **Event Sourcing** - All state changes as events for replay, testing, and observability
3. **Dependency Injection** - All dependencies injected through interfaces
4. **Domain-Driven Design** - Core domain models independent of infrastructure
5. **CQRS Pattern** - Separate command and query paths for cleaner testing

## High-Level Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        EXTERNAL TRIGGERS                        │
│     GitHub Webhooks | UI Dashboard | CLI | Scheduled Tasks      │
└────────────────────────────┬────────────────────────────────────┘
                             │
┌─────────────────────────────┴────────────────────────────────────┐
│                      PRIMARY ADAPTERS                             │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐        │
│  │  GitHub  │  │   REST   │  │WebSocket │  │   CLI    │        │
│  │ Webhook  │  │    API   │  │   API    │  │ Commands │        │
│  └─────┬────┘  └────┬─────┘  └────┬─────┘  └────┬─────┘        │
└────────┼────────────┼──────────────┼─────────────┼──────────────┘
         │            │              │             │
         ▼            ▼              ▼             ▼
┌─────────────────────────────────────────────────────────────────┐
│                      INPUT PORTS (Interfaces)                    │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │ WorkflowCommand | TaskQuery | EventStream | ConfigCommand│   │
│  └─────────────────────────────────────────────────────────┘   │
└─────────────────────────┬────────────────────────────────────┘
                          │
┌─────────────────────────▼────────────────────────────────────┐
│                    HEXAGONAL CORE                             │
│                                                                │
│  ┌──────────────────────────────────────────────────────┐    │
│  │              DOMAIN LAYER                            │    │
│  │  ┌────────────┐  ┌────────────┐  ┌────────────┐    │    │
│  │  │   Work     │  │   Agent    │  │  Pipeline  │    │    │
│  │  │   Item     │  │  Execution │  │   Stage    │    │    │
│  │  └────────────┘  └────────────┘  └────────────┘    │    │
│  │  ┌────────────┐  ┌────────────┐  ┌────────────┐    │    │
│  │  │  Project   │  │  Workflow  │  │   Review   │    │    │
│  │  │  Context   │  │  Template  │  │   Cycle    │    │    │
│  │  └────────────┘  └────────────┘  └────────────┘    │    │
│  └──────────────────────────────────────────────────────┘    │
│                                                                │
│  ┌──────────────────────────────────────────────────────┐    │
│  │            APPLICATION SERVICES                       │    │
│  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐ │    │
│  │  │  Workflow   │  │   Agent     │  │  Pipeline   │ │    │
│  │  │Orchestrator │  │  Scheduler  │  │  Manager    │ │    │
│  │  └─────────────┘  └─────────────┘  └─────────────┘ │    │
│  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐ │    │
│  │  │   Review    │  │  Workspace  │  │   Event     │ │    │
│  │  │   Service   │  │   Router    │  │  Processor  │ │    │
│  │  └─────────────┘  └─────────────┘  └─────────────┘ │    │
│  └──────────────────────────────────────────────────────┘    │
│                                                                │
│  ┌──────────────────────────────────────────────────────┐    │
│  │              EVENT STORE                              │    │
│  │  All domain events stored for replay and audit       │    │
│  └──────────────────────────────────────────────────────┘    │
└────────────────────────┬──────────────────────────────────────┘
                         │
┌────────────────────────▼──────────────────────────────────────┐
│                   OUTPUT PORTS (Interfaces)                   │
│  ┌───────────────────────────────────────────────────────┐   │
│  │ ITicketSystem | ILLMProvider | IRepository | IContainer│   │
│  │ IEventStore  | IMetrics     | INotifier   | IStorage  │   │
│  └───────────────────────────────────────────────────────┘   │
└────────────────────────┬──────────────────────────────────────┘
                         │
┌────────────────────────▼──────────────────────────────────────┐
│                    SECONDARY ADAPTERS                          │
│                                                                 │
│  ┌──────────────────────────────┐  ┌─────────────────────────┐    │
│  │     PRODUCTION                │  │      TESTING/MOCK       │    │
│  ├──────────────────────────────┤  ├─────────────────────────┤    │
│  │ • GitHubTicketAdapter         │  │ • InMemoryTicketAdapter │    │
│  │ • ClaudeCodeAdapter           │  │ • MockLLMAdapter        │    │
│  │ • GitRepositoryAdapter        │  │ • InMemoryRepoAdapter   │    │
│  │ • DockerContainerAdapter      │  │ • FakeContainerAdapter  │    │
│  │ • ElasticsearchEventStore     │  │ • InMemoryEventStore    │    │
│  │   + RedisEventBuffer          │  │                         │    │
│  │ • ElasticsearchConfigStore    │  │ • InMemoryConfigStore   │    │
│  │   + RedisConfigCache          │  │                         │    │
│  │ • ElasticsearchMetrics        │  │ • InMemoryMetrics       │    │
│  └──────────────────────────────┘  └─────────────────────────┘    │
└─────────────────────────────────────────────────────────────────┘
```

## Key Design Components

### 1. Domain Layer (Core Business Logic)
Pure domain models with no external dependencies:

```python
# Example domain model
class WorkItem:
    def __init__(self, id: str, title: str, description: str):
        self.id = id
        self.title = title
        self.description = description
        self.status = WorkItemStatus.NEW
        self.events = []
    
    def assign_to_agent(self, agent: Agent) -> DomainEvent:
        # Pure business logic
        event = WorkItemAssigned(self.id, agent.id)
        self.events.append(event)
        return event

class AgentExecution:
    def __init__(self, agent: Agent, work_item: WorkItem, context: ExecutionContext):
        self.id = generate_id()
        self.agent = agent
        self.work_item = work_item
        self.context = context
        self.status = ExecutionStatus.PENDING
```

### 2. Application Services
Orchestrate domain objects and coordinate with ports:

```python
class WorkflowOrchestrator:
    def __init__(self,
                 ticket_system: ITicketSystem,
                 agent_scheduler: AgentScheduler,
                 event_store: IEventStore):
        self.ticket_system = ticket_system
        self.agent_scheduler = agent_scheduler
        self.event_store = event_store
    
    async def handle_card_movement(self, event: CardMovedEvent):
        # Orchestration logic
        work_item = await self.ticket_system.get_work_item(event.item_id)
        agent = self.determine_agent(event.column)
        
        # Create domain event
        assignment_event = work_item.assign_to_agent(agent)
        
        # Store event
        await self.event_store.append(assignment_event)
        
        # Schedule execution
        await self.agent_scheduler.schedule(work_item, agent)
```

### 3. Port Interfaces
Clean contracts between core and adapters:

```python
from abc import ABC, abstractmethod

class ITicketSystem(ABC):
    @abstractmethod
    async def get_work_item(self, item_id: str) -> WorkItem:
        pass
    
    @abstractmethod
    async def update_work_item(self, item: WorkItem) -> None:
        pass
    
    @abstractmethod
    async def create_comment(self, item_id: str, comment: str) -> str:
        pass

class ILLMProvider(ABC):
    @abstractmethod
    async def execute_prompt(self, 
                            prompt: str, 
                            context: Dict,
                            stream_callback: Callable) -> ExecutionResult:
        pass

class IContainer(ABC):
    @abstractmethod
    async def run(self, 
                  image: str, 
                  command: List[str],
                  volumes: Dict,
                  environment: Dict) -> ContainerResult:
        pass
```

### 4. Adapter Implementations
Swappable implementations for different environments:

```python
# Production adapter
class GitHubTicketAdapter(ITicketSystem):
    def __init__(self, github_client: GitHubClient):
        self.client = github_client
    
    async def get_work_item(self, item_id: str) -> WorkItem:
        issue = await self.client.get_issue(item_id)
        return WorkItem(
            id=str(issue.number),
            title=issue.title,
            description=issue.body
        )

# Test/simulation adapter
class InMemoryTicketAdapter(ITicketSystem):
    def __init__(self):
        self.items = {}
    
    async def get_work_item(self, item_id: str) -> WorkItem:
        return self.items.get(item_id)
    
    def add_test_item(self, item: WorkItem):
        self.items[item.id] = item
```

## Testing Strategy

### 1. Unit Tests (Domain Layer)
Test pure business logic without any dependencies:

```python
def test_work_item_assignment():
    work_item = WorkItem("123", "Test", "Description")
    agent = Agent("agent-1", "BusinessAnalyst")
    
    event = work_item.assign_to_agent(agent)
    
    assert isinstance(event, WorkItemAssigned)
    assert event.work_item_id == "123"
    assert event.agent_id == "agent-1"
```

### 2. Integration Tests (Application Services)
Test with mock adapters:

```python
async def test_workflow_orchestration():
    # Setup mock adapters
    ticket_system = InMemoryTicketAdapter()
    event_store = InMemoryEventStore()
    agent_scheduler = MockAgentScheduler()
    
    # Create test data
    work_item = WorkItem("123", "Test Issue", "Description")
    ticket_system.add_test_item(work_item)
    
    # Create orchestrator with mocks
    orchestrator = WorkflowOrchestrator(
        ticket_system, 
        agent_scheduler,
        event_store
    )
    
    # Test card movement
    await orchestrator.handle_card_movement(
        CardMovedEvent("123", "Requirements Analysis")
    )
    
    # Verify
    assert agent_scheduler.scheduled_count == 1
    assert len(event_store.events) == 1
```

### 3. End-to-End Simulation Tests
Full workflow testing with configurable speed:

```python
class SimulationRunner:
    def __init__(self, config: SimulationConfig):
        self.config = config
        self.setup_mock_adapters()
    
    def setup_mock_adapters(self):
        # Create all mock adapters
        self.ticket_system = InMemoryTicketAdapter()
        self.llm_provider = MockLLMProvider(
            response_delay=self.config.llm_delay,
            responses=self.config.predefined_responses
        )
        self.container = FakeContainerAdapter()
        
    async def run_scenario(self, scenario: TestScenario):
        # Load scenario events
        for event in scenario.events:
            await self.process_event(event)
            
        # Verify outcomes
        return self.verify_scenario_outcomes(scenario.expected)
```

## Configuration Management

### Elasticsearch-Backed Configuration with Redis Caching
Replace YAML files with Elasticsearch-stored, versioned configuration:

**Architecture**:
- **Storage**: Elasticsearch indices (`config-projects`, `config-workflows`, `config-agents`)
- **Caching**: Redis write-through cache for fast access
- **Versioning**: Each update creates new document version
- **Search**: Full-text search across all configurations

```python
class ConfigurationService:
    def __init__(self, config_store: IConfigStore):
        self.config_store = config_store  # ElasticsearchConfigStore + RedisCache

    async def get_workflow(self, project: str) -> WorkflowConfig:
        """Get workflow config (from cache or Elasticsearch)."""
        return await self.config_store.get_workflow_config(project)

    async def update_agent_prompt(self,
                                  agent_id: str,
                                  prompt: str,
                                  updated_by: str) -> None:
        """
        Update agent prompt (creates new version).

        Flow:
        1. Write to Elasticsearch (versioned)
        2. Update Redis cache
        3. Broadcast cache invalidation
        """
        config = await self.config_store.get_agent_config(agent_id)
        config.prompt_template = prompt
        config.updated_by = updated_by
        await self.config_store.save_agent_config(config)

    async def search_configurations(self, query: str) -> List[Dict]:
        """Full-text search across all configurations."""
        return await self.config_store.search_configs(query)
```

### Web-Based Configuration UI
```python
# REST API for configuration with versioning and history
@router.post("/api/workflows/{workflow_id}/stages")
async def add_workflow_stage(
    workflow_id: str,
    stage: StageConfig,
    config_service: ConfigurationService
):
    """Add stage to workflow (creates new version)."""
    workflow = await config_service.get_workflow(workflow_id)
    workflow.add_stage(stage)
    await config_service.save_workflow(workflow)
    return {"status": "success", "version": workflow.version}

@router.get("/api/configurations/search")
async def search_configurations(
    query: str,
    config_service: ConfigurationService
):
    """Full-text search across all configurations."""
    results = await config_service.search_configurations(query)
    return {"results": results}

@router.get("/api/workflows/{workflow_id}/history")
async def get_workflow_history(
    workflow_id: str,
    config_service: ConfigurationService
):
    """Get configuration change history."""
    history = await config_service.get_config_history(workflow_id)
    return {"history": history}
```

## Simulation Mode Features

### 1. Time Manipulation
```python
class SimulationClock(IClock):
    def __init__(self, speed_multiplier: float = 1.0):
        self.speed_multiplier = speed_multiplier
        self.current_time = datetime.now()
    
    def now(self) -> datetime:
        return self.current_time
    
    def advance(self, seconds: float):
        self.current_time += timedelta(seconds=seconds * self.speed_multiplier)
```

### 2. Deterministic Responses
```python
class MockLLMProvider(ILLMProvider):
    def __init__(self, responses: Dict[str, str]):
        self.responses = responses
        self.call_count = 0
    
    async def execute_prompt(self, prompt: str, context: Dict, callback):
        # Return predetermined response based on prompt hash
        response_key = self.hash_prompt(prompt)
        response = self.responses.get(response_key, "Default response")
        
        # Simulate streaming
        for chunk in response.split():
            await callback(chunk)
            await asyncio.sleep(0.01)  # Simulate delay
        
        return ExecutionResult(response)
```

### 3. Event Replay
```python
class EventReplayer:
    def __init__(self, event_store: IEventStore):
        self.event_store = event_store
    
    async def replay_from(self, 
                         timestamp: datetime,
                         until: datetime = None):
        events = await self.event_store.get_events(
            from_time=timestamp,
            to_time=until
        )
        
        for event in events:
            await self.process_event(event)
```

## Extensibility Points

### 1. Plugin Architecture for Ticket Systems
```python
class TicketSystemRegistry:
    def __init__(self):
        self.adapters = {}
    
    def register(self, name: str, adapter_class: Type[ITicketSystem]):
        self.adapters[name] = adapter_class
    
    def create(self, name: str, config: Dict) -> ITicketSystem:
        adapter_class = self.adapters[name]
        return adapter_class(**config)

# Register adapters
registry = TicketSystemRegistry()
registry.register("github", GitHubTicketAdapter)
registry.register("jira", JiraTicketAdapter)
registry.register("markdown", MarkdownTicketAdapter)
```

### 2. Plugin Architecture for LLM Providers
```python
registry.register("claude", ClaudeCodeAdapter)
registry.register("aider", AiderAdapter)
registry.register("gpt4", GPT4Adapter)
```

## Migration Strategy

### Phase 1: Core Domain Extraction
1. Extract pure business logic into domain models
2. Create port interfaces for external dependencies
3. Wrap existing code in adapter implementations

### Phase 2: Event Sourcing Implementation
1. Add event store alongside existing state management
2. Emit events for all state changes
3. Build event replay capability

### Phase 3: Mock Adapter Development
1. Create in-memory implementations for all ports
2. Build simulation test scenarios
3. Validate against production behavior

### Phase 4: Configuration Migration
1. Build Elasticsearch indices for configuration storage
2. Create web UI for configuration management with search
3. Migrate from YAML files to Elasticsearch
4. Deploy Redis for configuration caching

### Phase 5: Full Integration
1. Replace existing orchestrator with new hexagonal core
2. Run in parallel mode for validation
3. Deploy Elasticsearch + Redis infrastructure
4. Complete cutover once stable

## Benefits of This Architecture

1. **Testability**: Every component can be tested in isolation with mock dependencies
2. **Simulation Mode**: Full end-to-end testing without external services
3. **Observability**: Event sourcing provides complete audit trail and replay capability
4. **Extensibility**: New ticket systems and LLM providers plug in easily
5. **Configuration**: Web-based UI with Elasticsearch storage (versioned, searchable) replaces YAML files
6. **Maintainability**: Clear boundaries and single responsibilities
7. **Performance**: Redis buffering/caching optimizes both writes and reads
8. **Debugging**: Event replay allows reproducing any issue
9. **Search**: Full-text search across events, logs, and configurations
10. **Scalability**: Elasticsearch + Redis architecture scales horizontally

This architecture provides the foundation for a highly testable, observable, and extensible system that can run in full simulation mode for testing while maintaining clean separation of concerns.