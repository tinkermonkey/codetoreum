# Hybrid Mode Configuration Guide

## Overview

This guide explains how to **gradually migrate from simulation mode to production** by mixing mock/in-memory adapters with real external service adapters. This allows you to:

- Test specific components in isolation with real infrastructure
- Debug integration issues one service at a time
- Reduce external dependencies while still testing critical paths
- Build confidence before full production deployment

## Architecture Support

The hexagonal architecture + adapter factory design **natively supports hybrid modes**:

```python
# Each adapter can be independently configured
factory = AdapterFactory(config=AdapterFactoryConfig(
    operation_mode=OperationMode.HYBRID  # Custom mode
))

# Mix and match adapters
ticket_system = factory.create_ticket_system(adapter_name='in_memory')  # Mock
llm_provider = factory.create_llm_provider(adapter_name='claude_code')  # Real
container = factory.create_container(adapter_name='docker')             # Real
repository = factory.create_repository(adapter_name='in_memory')        # Mock
```

This gives you **fine-grained control** over which components are real vs simulated.

---

## Common Hybrid Configurations

### 1. **Local Development Mode**

**Use Case**: Developing new features without external API costs

**Configuration**:
- ✅ Real: Docker (containers)
- ✅ Real: Redis (event store, caching)
- ❌ Mock: GitHub (tickets)
- ❌ Mock: Claude API (LLM)
- ❌ Mock: Git repositories
- ❌ Mock: Notifications

**Why**: You can test containerized execution locally without consuming GitHub API quota or Claude API credits.

**Setup**:
```python
# config/local_dev.py
ADAPTER_CONFIG = {
    'ticket_system': 'in_memory',
    'llm_provider': 'mock',
    'container': 'docker',          # Real Docker
    'repository': 'in_memory',
    'event_store': 'redis',         # Real Redis
    'metrics': 'in_memory',
    'storage': 'in_memory',
    'notifier': 'mock',
    'config_store': 'redis'         # Real Redis
}
```

**Docker Compose**:
```yaml
# docker-compose.local.yml
version: '3.8'
services:
  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"

  codetoreum:
    build: .
    environment:
      - ADAPTER_TICKET_SYSTEM=in_memory
      - ADAPTER_LLM_PROVIDER=mock
      - ADAPTER_CONTAINER=docker
      - ADAPTER_EVENT_STORE=redis
      - REDIS_HOST=redis
    volumes:
      - /var/run/docker.sock:/var/run/docker.sock
    depends_on:
      - redis
```

**Run**:
```bash
docker-compose -f docker-compose.local.yml up
```

---

### 2. **LLM Integration Testing Mode**

**Use Case**: Testing real LLM integration without GitHub or container overhead

**Configuration**:
- ✅ Real: Claude API (LLM)
- ✅ Real: Redis (for realistic event buffering)
- ❌ Mock: GitHub (tickets)
- ❌ Mock: Docker (fast fake containers)
- ❌ Mock: Everything else

**Why**: Test LLM prompts, response parsing, token usage without spinning up containers or consuming GitHub API quota.

**Setup**:
```python
ADAPTER_CONFIG = {
    'ticket_system': 'in_memory',
    'llm_provider': 'claude_code',  # Real Claude
    'container': 'fake',
    'repository': 'in_memory',
    'event_store': 'redis',         # Real Redis
    'metrics': 'in_memory',
    'storage': 'in_memory',
    'notifier': 'mock',
    'config_store': 'in_memory'
}
```

**Environment Variables**:
```bash
export CLAUDE_API_KEY="your-api-key"
export ADAPTER_LLM_PROVIDER=claude_code
export ADAPTER_CONTAINER=fake
export ADAPTER_TICKET_SYSTEM=in_memory
```

**Benefits**:
- Test real LLM behavior
- Measure actual token usage and costs
- Validate prompt engineering
- No container startup time (instant execution)

---

### 3. **GitHub Integration Testing Mode**

**Use Case**: Testing GitHub webhook handling, issue sync, PR creation without LLM costs

**Configuration**:
- ✅ Real: GitHub (tickets)
- ✅ Real: Git (repositories)
- ✅ Real: Redis
- ❌ Mock: Claude API (LLM)
- ❌ Mock: Docker (containers)
- ❌ Mock: Everything else

**Why**: Validate GitHub integration, webhook parsing, issue updates without consuming LLM credits.

**Setup**:
```python
ADAPTER_CONFIG = {
    'ticket_system': 'github',      # Real GitHub
    'llm_provider': 'mock',
    'container': 'fake',
    'repository': 'git',            # Real Git
    'event_store': 'redis',
    'metrics': 'in_memory',
    'storage': 'in_memory',
    'notifier': 'mock',
    'config_store': 'redis'
}
```

**Environment Variables**:
```bash
export GITHUB_TOKEN="ghp_..."
export GITHUB_REPO_OWNER="your-org"
export GITHUB_REPO_NAME="your-repo"
export ADAPTER_TICKET_SYSTEM=github
export ADAPTER_REPOSITORY=git
export ADAPTER_LLM_PROVIDER=mock
```

**Benefits**:
- Test real GitHub webhook flow
- Validate issue/PR synchronization
- Test GitHub API error handling
- No LLM costs

---

### 4. **Container Integration Testing Mode**

**Use Case**: Testing real Docker container execution with controlled inputs

**Configuration**:
- ✅ Real: Docker (containers)
- ✅ Real: Git (repositories) - for realistic workspace setup
- ✅ Real: Storage (local filesystem)
- ❌ Mock: GitHub (tickets)
- ❌ Mock: Claude API (LLM)
- ❌ Mock: Everything else

**Why**: Validate containerization, volume mounting, security constraints without external API dependencies.

**Setup**:
```python
ADAPTER_CONFIG = {
    'ticket_system': 'in_memory',
    'llm_provider': 'mock',
    'container': 'docker',          # Real Docker
    'repository': 'git',            # Real Git
    'event_store': 'in_memory',
    'metrics': 'in_memory',
    'storage': 'local',             # Real local storage
    'notifier': 'mock',
    'config_store': 'in_memory'
}
```

**Benefits**:
- Test real container security constraints
- Validate volume mounting
- Test container resource limits
- Verify file system isolation

---

### 5. **Full Observability Mode**

**Use Case**: Testing complete observability stack (metrics, events, logs) with real infrastructure

**Configuration**:
- ✅ Real: Redis (event store)
- ✅ Real: Elasticsearch (metrics, logs, config)
- ❌ Mock: GitHub, Claude, Docker
- ❌ Mock: Everything else

**Why**: Validate observability pipeline, event sourcing, metrics aggregation without external API costs.

**Setup**:
```python
ADAPTER_CONFIG = {
    'ticket_system': 'in_memory',
    'llm_provider': 'mock',
    'container': 'fake',
    'repository': 'in_memory',
    'event_store': 'redis',         # Real Redis
    'metrics': 'elasticsearch',     # Real Elasticsearch
    'storage': 'in_memory',
    'notifier': 'mock',
    'config_store': 'elasticsearch' # Real Elasticsearch
}
```

**Docker Compose**:
```yaml
version: '3.8'
services:
  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"

  elasticsearch:
    image: elasticsearch:8.11.0
    environment:
      - discovery.type=single-node
      - xpack.security.enabled=false
    ports:
      - "9200:9200"

  codetoreum:
    build: .
    environment:
      - ADAPTER_EVENT_STORE=redis
      - ADAPTER_METRICS=elasticsearch
      - ADAPTER_CONFIG_STORE=elasticsearch
      - REDIS_HOST=redis
      - ELASTICSEARCH_HOST=elasticsearch
    depends_on:
      - redis
      - elasticsearch
```

**Benefits**:
- Test event sourcing at scale
- Validate metrics collection and querying
- Test configuration storage and search
- Verify observability dashboard integration

---

### 6. **Staging Mode** (Almost Production)

**Use Case**: Pre-production testing with real infrastructure but controlled data

**Configuration**:
- ✅ Real: GitHub (test organization/repo)
- ✅ Real: Claude API (with rate limits)
- ✅ Real: Docker
- ✅ Real: Git
- ✅ Real: Redis
- ✅ Real: Elasticsearch
- ❌ Mock: Notifications (prevent spam)

**Setup**:
```python
ADAPTER_CONFIG = {
    'ticket_system': 'github',
    'llm_provider': 'claude_code',
    'container': 'docker',
    'repository': 'git',
    'event_store': 'redis',
    'metrics': 'elasticsearch',
    'storage': 'local',
    'notifier': 'mock',             # Still mock to avoid spam
    'config_store': 'elasticsearch'
}
```

**Benefits**:
- Full end-to-end testing
- Production-like environment
- Real cost/performance metrics
- Safe for testing failures

---

## Implementation: Environment-Based Configuration

### Configuration Module (`src/codetoreum/infrastructure/config/adapter_config.py`)

```python
"""Environment-based adapter configuration."""

import os
from enum import Enum
from typing import Dict, Optional
from dataclasses import dataclass


class AdapterMode(Enum):
    """Predefined adapter configuration modes."""
    SIMULATION = "simulation"      # All mock
    LOCAL_DEV = "local_dev"        # Docker + Redis, rest mock
    LLM_TESTING = "llm_testing"    # Real LLM, rest mock
    GITHUB_TESTING = "github_testing"  # Real GitHub, rest mock
    CONTAINER_TESTING = "container_testing"  # Real Docker, rest mock
    OBSERVABILITY = "observability"  # Real Redis + ES, rest mock
    STAGING = "staging"            # Almost all real
    PRODUCTION = "production"      # All real


@dataclass
class AdapterSelectionConfig:
    """Configuration specifying which adapter to use for each port."""

    ticket_system: str = 'in_memory'
    llm_provider: str = 'mock'
    container: str = 'fake'
    repository: str = 'in_memory'
    event_store: str = 'in_memory'
    metrics: str = 'in_memory'
    storage: str = 'in_memory'
    notifier: str = 'mock'
    config_store: str = 'in_memory'

    @classmethod
    def from_mode(cls, mode: AdapterMode) -> 'AdapterSelectionConfig':
        """Create configuration from predefined mode."""

        MODES = {
            AdapterMode.SIMULATION: cls(
                ticket_system='in_memory',
                llm_provider='mock',
                container='fake',
                repository='in_memory',
                event_store='in_memory',
                metrics='in_memory',
                storage='in_memory',
                notifier='mock',
                config_store='in_memory'
            ),

            AdapterMode.LOCAL_DEV: cls(
                ticket_system='in_memory',
                llm_provider='mock',
                container='docker',          # Real
                repository='in_memory',
                event_store='redis',         # Real
                metrics='in_memory',
                storage='in_memory',
                notifier='mock',
                config_store='redis'         # Real
            ),

            AdapterMode.LLM_TESTING: cls(
                ticket_system='in_memory',
                llm_provider='claude_code',  # Real
                container='fake',
                repository='in_memory',
                event_store='redis',         # Real
                metrics='in_memory',
                storage='in_memory',
                notifier='mock',
                config_store='in_memory'
            ),

            AdapterMode.GITHUB_TESTING: cls(
                ticket_system='github',      # Real
                llm_provider='mock',
                container='fake',
                repository='git',            # Real
                event_store='redis',         # Real
                metrics='in_memory',
                storage='in_memory',
                notifier='mock',
                config_store='redis'
            ),

            AdapterMode.CONTAINER_TESTING: cls(
                ticket_system='in_memory',
                llm_provider='mock',
                container='docker',          # Real
                repository='git',            # Real
                event_store='in_memory',
                metrics='in_memory',
                storage='local',             # Real
                notifier='mock',
                config_store='in_memory'
            ),

            AdapterMode.OBSERVABILITY: cls(
                ticket_system='in_memory',
                llm_provider='mock',
                container='fake',
                repository='in_memory',
                event_store='redis',         # Real
                metrics='elasticsearch',     # Real
                storage='in_memory',
                notifier='mock',
                config_store='elasticsearch' # Real
            ),

            AdapterMode.STAGING: cls(
                ticket_system='github',
                llm_provider='claude_code',
                container='docker',
                repository='git',
                event_store='redis',
                metrics='elasticsearch',
                storage='local',
                notifier='mock',             # Still mock
                config_store='elasticsearch'
            ),

            AdapterMode.PRODUCTION: cls(
                ticket_system='github',
                llm_provider='claude_code',
                container='docker',
                repository='git',
                event_store='redis',
                metrics='elasticsearch',
                storage='local',
                notifier='email',            # Real
                config_store='elasticsearch'
            )
        }

        return MODES[mode]

    @classmethod
    def from_environment(cls) -> 'AdapterSelectionConfig':
        """Create configuration from environment variables."""

        # Check for mode override
        mode_str = os.getenv('CODETOREUM_MODE')
        if mode_str:
            try:
                mode = AdapterMode(mode_str)
                return cls.from_mode(mode)
            except ValueError:
                pass

        # Individual adapter overrides
        return cls(
            ticket_system=os.getenv('ADAPTER_TICKET_SYSTEM', 'in_memory'),
            llm_provider=os.getenv('ADAPTER_LLM_PROVIDER', 'mock'),
            container=os.getenv('ADAPTER_CONTAINER', 'fake'),
            repository=os.getenv('ADAPTER_REPOSITORY', 'in_memory'),
            event_store=os.getenv('ADAPTER_EVENT_STORE', 'in_memory'),
            metrics=os.getenv('ADAPTER_METRICS', 'in_memory'),
            storage=os.getenv('ADAPTER_STORAGE', 'in_memory'),
            notifier=os.getenv('ADAPTER_NOTIFIER', 'mock'),
            config_store=os.getenv('ADAPTER_CONFIG_STORE', 'in_memory')
        )


def create_adapters_from_config(
    config: AdapterSelectionConfig,
    factory: 'AdapterFactory'
) -> Dict[str, Any]:
    """
    Create all adapters based on configuration.

    Args:
        config: Adapter selection configuration
        factory: Adapter factory instance

    Returns:
        Dictionary of created adapters
    """
    adapters = {}

    # Create ticket system
    adapters['ticket_system'] = factory.create_ticket_system(
        adapter_name=config.ticket_system
    )

    # Create LLM provider
    adapters['llm_provider'] = factory.create_llm_provider(
        adapter_name=config.llm_provider
    )

    # Create container
    adapters['container'] = factory.create_container(
        adapter_name=config.container
    )

    # Create repository
    adapters['repository'] = factory.create_repository(
        adapter_name=config.repository
    )

    # Create event store
    adapters['event_store'] = factory.create_event_store(
        adapter_name=config.event_store
    )

    # Create metrics (need to add to factory)
    adapters['metrics'] = factory.create_metrics(
        adapter_name=config.metrics
    )

    # Create storage
    adapters['storage'] = factory.create_storage(
        adapter_name=config.storage
    )

    # Create notifier
    adapters['notifier'] = factory.create_notifier(
        adapter_name=config.notifier
    )

    # Create config store
    adapters['config_store'] = factory.create_config_store(
        adapter_name=config.config_store
    )

    return adapters
```

---

## Usage Examples

### Example 1: Start in Local Dev Mode

```bash
# Set mode via environment
export CODETOREUM_MODE=local_dev

# Or set individual adapters
export ADAPTER_CONTAINER=docker
export ADAPTER_EVENT_STORE=redis
export ADAPTER_CONFIG_STORE=redis

# Start server
python -m codetoreum.cli.server
```

### Example 2: Run Tests in LLM Testing Mode

```python
# tests/integration/test_llm_integration.py

import pytest
from codetoreum.infrastructure.config import (
    AdapterMode,
    AdapterSelectionConfig,
    create_adapters_from_config
)
from codetoreum.infrastructure.adapters import AdapterFactory


@pytest.fixture
async def llm_testing_adapters():
    """Set up adapters for LLM integration testing."""

    config = AdapterSelectionConfig.from_mode(AdapterMode.LLM_TESTING)
    factory = AdapterFactory()

    adapters = create_adapters_from_config(config, factory)

    yield adapters

    # Cleanup
    await adapters['event_store'].clear()


@pytest.mark.integration
@pytest.mark.llm
async def test_real_claude_api_integration(llm_testing_adapters):
    """Test with real Claude API."""

    llm = llm_testing_adapters['llm_provider']

    # This will make a real API call
    response = await llm.generate_response(
        conversation_id="test-1",
        prompt="Write a hello world function in Python"
    )

    assert "def" in response
    assert "hello" in response.lower()

    # Verify event was stored in Redis
    events = await llm_testing_adapters['event_store'].get_events(
        aggregate_type='AgentExecution'
    )
    assert len(events) > 0
```

### Example 3: Pytest with Mode Selection

```python
# conftest.py

import pytest
import os


def pytest_addoption(parser):
    """Add command-line options for adapter mode."""
    parser.addoption(
        "--adapter-mode",
        action="store",
        default="simulation",
        choices=[
            "simulation",
            "local_dev",
            "llm_testing",
            "github_testing",
            "container_testing",
            "observability"
        ],
        help="Adapter mode for testing"
    )


@pytest.fixture(scope="session", autouse=True)
def configure_adapter_mode(request):
    """Configure adapter mode from pytest option."""
    mode = request.config.getoption("--adapter-mode")
    os.environ['CODETOREUM_MODE'] = mode
    yield
    # Cleanup
    os.environ.pop('CODETOREUM_MODE', None)
```

**Run tests**:
```bash
# Simulation mode (default)
pytest

# LLM testing mode
pytest --adapter-mode=llm_testing

# Container testing mode
pytest --adapter-mode=container_testing -m container
```

---

## Migration Checklist: Simulation → Production

Use this checklist to gradually migrate from simulation to production:

### Phase 1: Local Infrastructure (Week 1)

- [ ] Set up Redis locally via Docker Compose
- [ ] Configure `event_store: redis`
- [ ] Configure `config_store: redis`
- [ ] Run simulation tests against Redis
- [ ] Verify event persistence and replay
- [ ] Verify configuration caching

**Validation**:
```bash
# Start Redis
docker-compose up redis

# Run tests
ADAPTER_EVENT_STORE=redis ADAPTER_CONFIG_STORE=redis pytest

# Inspect Redis data
redis-cli
> KEYS codetoreum:events:*
> KEYS codetoreum:config:*
```

### Phase 2: Container Runtime (Week 2)

- [ ] Ensure Docker daemon is running
- [ ] Configure `container: docker`
- [ ] Run container integration tests
- [ ] Verify workspace mounting
- [ ] Verify container security constraints
- [ ] Test container cleanup on failure

**Validation**:
```bash
# Run container tests
ADAPTER_CONTAINER=docker pytest tests/integration/adapters/secondary/test_docker_container_adapter.py

# Monitor containers
docker ps -a | grep codetoreum

# Check volumes
docker volume ls | grep codetoreum
```

### Phase 3: Git Repository (Week 2)

- [ ] Set up test Git repository
- [ ] Configure `repository: git`
- [ ] Run repository integration tests
- [ ] Verify clone, commit, push operations
- [ ] Test git credential handling

**Validation**:
```bash
# Run repository tests
ADAPTER_REPOSITORY=git pytest tests/integration/adapters/secondary/test_git_repository_adapter.py

# Inspect test repo
cd /tmp/codetoreum-workspaces
ls -la
```

### Phase 4: Observability Stack (Week 3)

- [ ] Set up Elasticsearch via Docker Compose
- [ ] Configure `metrics: elasticsearch`
- [ ] Run metrics integration tests
- [ ] Verify metrics indexing and querying
- [ ] Test metrics dashboard integration

**Validation**:
```bash
# Start Elasticsearch
docker-compose up elasticsearch

# Run metrics tests
ADAPTER_METRICS=elasticsearch pytest tests/integration/infrastructure/

# Query metrics
curl http://localhost:9200/codetoreum-metrics/_search?pretty
```

### Phase 5: GitHub Integration (Week 4)

- [ ] Create test GitHub organization/repository
- [ ] Generate GitHub token with appropriate permissions
- [ ] Configure `ticket_system: github`
- [ ] Run GitHub integration tests
- [ ] Verify webhook handling
- [ ] Test issue/PR synchronization

**Validation**:
```bash
# Set credentials
export GITHUB_TOKEN="ghp_..."
export GITHUB_REPO_OWNER="test-org"
export GITHUB_REPO_NAME="test-repo"

# Run GitHub tests
ADAPTER_TICKET_SYSTEM=github pytest tests/integration/adapters/secondary/test_github_ticket_adapter.py

# Verify webhook endpoint
ngrok http 8000
# Configure webhook in GitHub settings
```

### Phase 6: LLM Integration (Week 5)

- [ ] Obtain Claude API key
- [ ] Set up Claude Code CLI
- [ ] Configure `llm_provider: claude_code`
- [ ] Run LLM integration tests (costly!)
- [ ] Verify prompt engineering
- [ ] Monitor token usage and costs

**Validation**:
```bash
# Set credentials
export CLAUDE_API_KEY="sk-..."

# Run LLM tests (use sparingly - costs money!)
ADAPTER_LLM_PROVIDER=claude_code pytest tests/integration/adapters/secondary/test_claude_code_adapter.py -k "single_response"

# Check token usage
# (via Claude dashboard)
```

### Phase 7: Staging Environment (Week 6)

- [ ] Set up staging infrastructure (Redis, ES, etc.)
- [ ] Configure staging mode
- [ ] Run full E2E tests in staging
- [ ] Verify all integrations work together
- [ ] Test error handling and recovery

**Validation**:
```bash
# Start staging
CODETOREUM_MODE=staging docker-compose -f docker-compose.staging.yml up

# Run E2E tests
pytest tests/simulation/e2e/ --adapter-mode=staging

# Monitor metrics
curl http://staging.example.com/api/metrics
```

### Phase 8: Production Deployment (Week 7+)

- [ ] Set up production infrastructure
- [ ] Configure production secrets/credentials
- [ ] Configure `notifier: email` (or Slack)
- [ ] Deploy to production environment
- [ ] Run smoke tests
- [ ] Set up monitoring and alerting

**Validation**:
```bash
# Production deployment
CODETOREUM_MODE=production docker-compose -f docker-compose.prod.yml up -d

# Smoke tests
curl https://codetoreum.example.com/health
curl https://codetoreum.example.com/api/metrics

# Monitor logs
docker-compose logs -f codetoreum
```

---

## Troubleshooting Hybrid Modes

### Problem: "Adapter not found" error

**Cause**: Adapter name doesn't match registry

**Solution**:
```python
# Check registered adapters
factory = AdapterFactory()
print(factory.ticket_system_registry.list_adapters())
print(factory.llm_provider_registry.list_adapters())

# Use exact name from registry
adapters = create_adapters_from_config(config, factory)
```

### Problem: Real adapter fails in tests

**Cause**: Missing credentials or infrastructure

**Solution**:
```bash
# Check environment variables
echo $GITHUB_TOKEN
echo $CLAUDE_API_KEY
echo $REDIS_HOST

# Check infrastructure
docker ps | grep redis
docker ps | grep elasticsearch

# Fall back to mock for that component
export ADAPTER_TICKET_SYSTEM=in_memory  # Instead of 'github'
```

### Problem: Tests are slow with real adapters

**Cause**: Real external calls vs instant mocks

**Solution**:
```python
# Use pytest markers to separate fast/slow tests
@pytest.mark.slow
@pytest.mark.requires_docker
async def test_real_container_execution():
    # ...

# Run only fast tests by default
pytest -m "not slow"

# Run slow tests explicitly
pytest -m slow --adapter-mode=container_testing
```

### Problem: Hybrid mode configuration is verbose

**Cause**: Need to set many environment variables

**Solution**:
```bash
# Use .env file
# .env.local_dev
CODETOREUM_MODE=local_dev
REDIS_HOST=localhost
REDIS_PORT=6379

# Load with direnv or dotenv
pip install python-dotenv

# In code
from dotenv import load_dotenv
load_dotenv('.env.local_dev')
```

---

## Best Practices

### 1. **Start with Simulation, Add Real Components Incrementally**

Don't jump straight to production mode. Add one real component at a time:
```
Simulation → + Redis → + Docker → + Git → + Elasticsearch → + GitHub → + Claude → Production
```

### 2. **Use Mode Presets for Common Scenarios**

Don't configure individual adapters manually. Use predefined modes:
```bash
# Good
export CODETOREUM_MODE=llm_testing

# Avoid (unless you need custom config)
export ADAPTER_TICKET_SYSTEM=in_memory
export ADAPTER_LLM_PROVIDER=claude_code
export ADAPTER_CONTAINER=fake
# ... 6 more lines
```

### 3. **Tag Tests with Required Adapters**

```python
@pytest.mark.requires_docker
@pytest.mark.requires_redis
async def test_container_with_events():
    # ...
```

Run tests based on available infrastructure:
```bash
# Local machine with Docker
pytest -m "not requires_github and not requires_claude"

# CI environment with all infrastructure
pytest
```

### 4. **Use Docker Compose Profiles for Infrastructure**

```yaml
# docker-compose.yml
version: '3.8'
services:
  redis:
    image: redis:7-alpine
    profiles: ["local", "staging", "prod"]

  elasticsearch:
    image: elasticsearch:8.11.0
    profiles: ["staging", "prod"]

  postgres:
    image: postgres:15-alpine
    profiles: ["prod"]
```

**Start subset**:
```bash
# Just Redis
docker-compose --profile local up

# Redis + Elasticsearch
docker-compose --profile staging up
```

### 5. **Document Adapter Requirements**

```python
# In each test file
"""
Adapter Requirements:
- ticket_system: in_memory
- llm_provider: claude_code (REAL - costs money!)
- container: fake
- event_store: redis (Docker required)

Run with:
    CODETOREUM_MODE=llm_testing pytest tests/integration/test_llm.py
"""
```

### 6. **Create Adapter Compatibility Matrix**

| Test Suite | Ticket | LLM | Container | Repo | Events | Metrics |
|------------|--------|-----|-----------|------|--------|---------|
| Unit Tests | N/A | N/A | N/A | N/A | N/A | N/A |
| Simulation | Mock | Mock | Fake | Mock | InMem | InMem |
| Local Dev | Mock | Mock | **Docker** | Mock | **Redis** | InMem |
| LLM Tests | Mock | **Claude** | Fake | Mock | **Redis** | InMem |
| GitHub Tests | **GitHub** | Mock | Fake | **Git** | **Redis** | InMem |
| Staging | **GitHub** | **Claude** | **Docker** | **Git** | **Redis** | **ES** |
| Production | **GitHub** | **Claude** | **Docker** | **Git** | **Redis** | **ES** |

---

## Summary

The hybrid mode approach allows you to:

1. ✅ **Incrementally adopt real components** without big-bang migration
2. ✅ **Test in isolation** (e.g., just LLM integration)
3. ✅ **Reduce costs** (mock expensive APIs during development)
4. ✅ **Speed up CI/CD** (fast tests with mocks, slow tests on-demand)
5. ✅ **Debug effectively** (isolate issues to specific adapters)

**Key Takeaway**: The hexagonal architecture + adapter factory gives you a **spectrum of testing modes** from full simulation to full production, with many useful hybrid points in between.

Start with simulation, gradually add real components, and build confidence at each step!
