---
required_sections:
  - "## Contents"
  - "## Adapter Organization"
  - "## Port-to-Adapter Mapping"
  - "## Key Design Principles"
  - "## Documentation Standards"
applies_to: "documentation/architecture/adapters/README.md"
---

# Adapters Tier

The adapters tier contains concrete implementations of port interfaces. Adapters translate between the Codetoreum domain model and external systems, handling vendor-specific details, API integration, error handling, and resilience patterns.

## Contents

### [Production Adapters](./production/) - External System Integration

Implementations connecting to real external systems used in production:

- **github-board-adapter.md** - GitHub Projects v2 board management (IBoardService)
- **github-ticket-adapter.md** - GitHub Issues for work item management (ITicketSystem)
- **github-code-review-adapter.md** - GitHub PRs for code review workflows (ICodeReviewService)
- **docker-container-adapter.md** - Docker for containerized agent execution (IContainer)
- **claude-code-adapter.md** - Claude Code CLI for autonomous coding agent operations (ICodingAgent; replaces the historical ILLMProvider)
- **git-repository-adapter.md** - Git operations and version control (IRepository)
- **infrastructure-adapters.md** - Event stores, config storage, metrics, and messaging

### [Simulation Adapters](../../implementations/simulation/adapters.md) - Testing Implementations

Mock and in-memory adapters for deterministic testing without external dependencies:

- **36 Testing Adapters**: Mock implementations of all output ports
- **18 Input Port Adapters**: Mock HTTP endpoint wrappers
- **Helper Classes**: Data structures for test state tracking

## Adapter Organization

```
src/codetoreum/adapters/
├── primary/                        # Inbound adapters
│   ├── input_port_adapters/       # HTTP endpoints for input ports
│   │   ├── mock/                  # Mock implementations (18 adapters)
│   │   └── ...
│   └── fastapi_app.py             # FastAPI application
├── secondary/                      # Outbound adapters
│   ├── github_*.py                # GitHub integrations (6 adapters)
│   ├── docker_*.py                # Docker integrations (2 adapters)
│   ├── claude_code/                # Coding agent adapter (ICodingAgent)
│   │   ├── adapter.py
│   │   ├── strategies/
│   │   ├── stream_parser.py
│   │   └── prompt_renderer.py
│   ├── git_repository_adapter.py # Version control
│   ├── elasticsearch_*.py         # Event store and config (2 adapters)
│   ├── prometheus_*.py            # Metrics collection
│   ├── redis_*.py                 # Message broker
│   └── ...                        # Other infrastructure
└── testing/                        # Testing-only adapters (36 adapters)
    ├── in_memory_*.py             # In-memory backing stores
    ├── mock_*.py                  # Mock external systems
    ├── fake_*.py                  # Fake implementations
    └── ...
```

## Port-to-Adapter Mapping

### Core System Ports
| Port Interface | Production Adapter | Simulation Adapter |
|---|---|---|
| `ITicketSystem` | GitHubTicketAdapter | InMemoryTicketAdapter |
| `ICodingAgent` | ClaudeCodeAdapter | MockClaudeCodeAdapter |
| `IPromptBuilder` | DefaultPromptBuilder | DefaultPromptBuilder (same impl; deterministic given inputs) |
| `IContainer` | DockerContainerAdapter | FakeContainerAdapter |
| `IRepository` | GitRepositoryAdapter | InMemoryRepositoryAdapter |
| `IEventStore` | ElasticsearchEventStore | InMemoryEventStore |
| `IConfigStore` | ElasticsearchConfigStorage | InMemoryConfigStore |

> `IStorage` is retired with the coding-agent port redesign. The simulation `InMemoryStorageAdapter` and production `MinioStorageAdapter` are removed; agent output flows through `CodingAgent*` events instead.

### Board & Work Coordination Ports
| Port Interface | Production Adapter | Simulation Adapter |
|---|---|---|
| `IBoardService` | GitHubBoardAdapter | MockBoardAdapter |
| `IWorkItemService` | GitHubTicketAdapter | MockWorkItemService |
| `IDiscussionAdapter` | GitHubDiscussionAdapter | MockDiscussionAdapter |

### Code Review Ports
| Port Interface | Production Adapter | Simulation Adapter |
|---|---|---|
| `ICodeReviewService` | GitHubCodeReviewAdapter | InMemoryCodeReviewAdapter |

### Infrastructure Services Ports
| Port Interface | Production Adapter | Simulation Adapter |
|---|---|---|
| `IMetrics` | PrometheusMetricsAdapter | InMemoryMetricsAdapter |
| `INotifier` | (Configurable) | MockNotifierAdapter |
| `IEventEmitter` | RedisPubSubAdapter | CapturingMockEventEmitter |
| `IMessageBroker` | RedisPubSubAdapter | InMemoryMessageBroker |

### Lifecycle Services Ports
| Port Interface | Production Adapter | Simulation Adapter |
|---|---|---|
| `IAgentContainerRecoveryService` | DockerContainerRecoveryAdapter | MockContainerRecoveryAdapter |
| `IRepairCycle` | ProductionRepairCycleAdapter | MockRepairCycleAdapter |
| `ICIPipelineService` | GitHubCIPipelineAdapter | MockCIPipelineAdapter |

## Key Design Principles

### 1. Separation of Concerns
Each adapter implements one or more closely related port interfaces. Complex interactions (e.g., GitHub integrations) are split into focused adapters:
- **GitHubBoardAdapter**: Projects v2 board management only
- **GitHubTicketAdapter**: Issues for work item CRUD and tracking
- **GitHubCodeReviewAdapter**: Pull requests and code review workflows
- **GitHubDiscussionAdapter**: Comments and discussions

### 2. Resilience as Infrastructure Concern
Individual adapters remain pure—resilience patterns are applied via decorator wrappers:

```python
# Adapter: pure implementation
board_service = GitHubBoardAdapter(graphql_client)

# Infrastructure: resilience wrapper
resilient_board = ResilientBoardServiceDecorator(
    board_service,
    circuit_breaker_threshold=5,
    rate_limit=60_per_minute,
    timeout_seconds=30
)
```

This separation allows:
- Swapping resilience patterns without changing adapters
- Testing adapters in isolation or with different resilience strategies
- Consistent error handling across all external integrations

### 3. Port Consistency
All adapters implementing the same port follow the same interface contract:
- Method signatures match exactly
- Exception types are consistent (port-standard exceptions)
- Behavior semantics are identical
- Error handling follows the same patterns

### 4. Configuration Externalization
Adapters accept configuration via constructor injection:

```python
class GitHubBoardAdapter(IBoardService):
    def __init__(
        self,
        ticket_adapter: GitHubTicketAdapter,
        graphql_client: GitHubGraphQLClient,
        webhook_enabled: bool = True,
    ):
        ...
```

Configuration sources:
- Environment variables for credentials and tokens
- Database (ConfigStore) for application settings
- Constructor parameters for wiring-time decisions
- Runtime configuration via port methods

### 5. Error Handling Consistency
All adapters translate external errors to port-standard exceptions:

```python
try:
    result = self._github_api.create_issue(...)
except GitHubAPIError as e:
    if e.status_code == 401:
        raise AuthenticationError(...) from e
    elif e.status_code == 404:
        raise ResourceNotFoundError(...) from e
    else:
        raise ExternalServiceError(...) from e
```

Standard port exceptions:
- `AuthenticationError`: Invalid credentials or token
- `AuthorizationError`: Insufficient permissions
- `ResourceNotFoundError`: Item doesn't exist
- `ValidationError`: Invalid input
- `ExternalServiceError`: Service unavailable or error
- `RateLimitError`: Rate limit exceeded
- `TimeoutError`: Operation timed out

## Documentation Standards

All production adapter documentation follows the [Adapter Template](../../templates/adapter-template.md) with these required sections:

1. **Purpose** - What port(s) it implements, external system, why it exists
2. **Implementation Strategy** - How it fulfills port contracts, API calls, data translation
3. **Configuration** - Required parameters, environment variables, defaults
4. **Error Handling** - Error scenarios and recovery strategies
5. **Testing** - Unit tests, integration tests, mock strategy
6. **Source** - File path, class name, related files
7. **Diagram** - Mermaid diagram showing adapter, port, and external system

## Adapter Lifecycle

### Initialization
1. Adapters are instantiated during bootstrap (production or simulation)
2. Configuration is injected via constructor
3. Credentials are loaded from environment or secure store
4. Optional connection validation (e.g., GitHub API token check)

### Operation
1. Application services call adapters through port interfaces
2. Adapters translate domain models to external system formats
3. External system calls are made with proper error handling
4. Results are translated back to domain types
5. Domain events are emitted if state changed

### Error Recovery
1. Transient errors (timeout, rate limit) trigger retries
2. Persistent errors (auth, not found) fail fast
3. Circuit breakers activate after threshold of consecutive failures
4. All errors are logged with full context (event_id, correlation_id, error details)

## Testing Strategy

### Unit Tests
- Adapter tested in isolation with mocked external API
- Verify correct API calls for given inputs
- Verify correct error handling and translations
- Verify configuration parameter handling

### Contract Tests
- Adapter tested against port interface contract
- Verify method signatures and return types
- Verify exception types match port contract
- Shared test suite runs against all adapters implementing same port

### Integration Tests
- Adapter tested with real external system (staging)
- Verify end-to-end workflows
- Verify authentication and authorization
- Verify error recovery and resilience

### Simulation Tests
- Adapter wrapped in mock variant for deterministic testing
- Verify application logic with simulated external systems
- Fast feedback (10-100x faster than real systems)
- Complete audit trail via event sourcing

## Cross-References

### Related Documentation
- [Ports: Output](../ports/output/) - Port interface specifications
- [Simulation Adapters](../../implementations/simulation/adapters.md) - Mock adapter reference
- [Bootstrap Wiring](../../implementations/production-bootstrap.md) - Production adapter wiring
- [Infrastructure](../infrastructure/) - Resilience patterns, observability, event bus

### Source Code
- Production adapters: `src/codetoreum/adapters/secondary/`
- Input port adapters: `src/codetoreum/adapters/primary/input_port_adapters/`
- Testing adapters: `src/codetoreum/adapters/testing/`
- Bootstrap wiring: `src/codetoreum/infrastructure/bootstrap.py`

---

**Total Adapter Count**:
- **Production Adapters**: 15+ implementations connecting to external systems
- **Simulation Adapters**: 54 mock and in-memory implementations
- **Total**: 70+ adapters across production and testing
