# Implementation Notes: Hybrid Mode Support

## Status: Partial Implementation Required

The **Hybrid Mode Configuration Guide** references adapter factory methods that don't fully exist yet. This document tracks what needs to be implemented.

## What Exists ✅

### Adapter Registries
- ✅ `TicketSystemRegistry` - Complete
- ✅ `LLMProviderRegistry` - Complete
- ✅ `ContainerRegistry` - Complete
- ✅ `RepositoryRegistry` - Complete
- ✅ `EventStoreRegistry` - Complete
- ✅ `StorageRegistry` - Complete (but no factory method)

### Factory Methods
- ✅ `create_ticket_system()` - Complete
- ✅ `create_llm_provider()` - Complete
- ✅ `create_container()` - Complete
- ✅ `create_repository()` - Complete
- ✅ `create_event_store()` - Complete

### Testing Adapters
- ✅ `InMemoryTicketAdapter`
- ✅ `MockLLMAdapter`
- ✅ `FakeContainerAdapter`
- ✅ `InMemoryRepositoryAdapter`
- ✅ `InMemoryEventStore`
- ✅ `InMemoryMetricsAdapter`
- ✅ `InMemoryStorageAdapter`
- ✅ `MockNotifierAdapter`
- ✅ `InMemoryConfigStore`

## What's Missing ❌

### 1. Missing Registries

Need to add to `src/codetoreum/infrastructure/adapters/registries.py`:

```python
class MetricsRegistry(AdapterRegistry[IMetrics]):
    """Registry for metrics adapters."""

    def __init__(self):
        super().__init__(
            interface_class=IMetrics,
            registry_name="MetricsRegistry"
        )


class NotifierRegistry(AdapterRegistry[INotifier]):
    """Registry for notifier adapters."""

    def __init__(self):
        super().__init__(
            interface_class=INotifier,
            registry_name="NotifierRegistry"
        )


class ConfigStoreRegistry(AdapterRegistry[IConfigStore]):
    """Registry for config store adapters."""

    def __init__(self):
        super().__init__(
            interface_class=IConfigStore,
            registry_name="ConfigStoreRegistry"
        )
```

### 2. Missing Factory Methods

Need to add to `src/codetoreum/infrastructure/adapters/factory.py`:

#### Initialize Registries in `__init__`

```python
def __init__(self, config: Optional[AdapterFactoryConfig] = None):
    # ... existing code ...

    # Add new registries
    self._storage_registry = StorageRegistry()
    self._metrics_registry = MetricsRegistry()
    self._notifier_registry = NotifierRegistry()
    self._config_store_registry = ConfigStoreRegistry()
```

#### Register Default Adapters in `_register_default_adapters`

```python
def _register_default_adapters(self) -> None:
    # ... existing registrations ...

    # Storage Adapters
    self._storage_registry.register(
        name="local",
        adapter_type=LocalStorageAdapter,
        description="Local filesystem storage",
        version="1.0.0",
        tags=["production", "local"],
        set_as_default=True
    )
    self._storage_registry.register(
        name="in_memory",
        adapter_type=InMemoryStorageAdapter,
        description="In-memory storage for testing",
        version="1.0.0",
        tags=["testing", "simulation", "mock"]
    )

    # Metrics Adapters
    self._metrics_registry.register(
        name="in_memory",
        adapter_type=InMemoryMetricsAdapter,
        description="In-memory metrics for testing",
        version="1.0.0",
        tags=["testing", "simulation", "mock"],
        set_as_default=True
    )
    # TODO: Add ElasticsearchMetricsAdapter when implemented
    # self._metrics_registry.register(
    #     name="elasticsearch",
    #     adapter_type=ElasticsearchMetricsAdapter,
    #     ...
    # )

    # Notifier Adapters
    self._notifier_registry.register(
        name="mock",
        adapter_type=MockNotifierAdapter,
        description="Mock notifier for testing",
        version="1.0.0",
        tags=["testing", "simulation", "mock"],
        set_as_default=True
    )
    # TODO: Add EmailNotifierAdapter when implemented
    # self._notifier_registry.register(
    #     name="email",
    #     adapter_type=EmailNotifierAdapter,
    #     ...
    # )

    # Config Store Adapters
    self._config_store_registry.register(
        name="in_memory",
        adapter_type=InMemoryConfigStore,
        description="In-memory config store for testing",
        version="1.0.0",
        tags=["testing", "simulation", "mock"],
        set_as_default=True
    )
    # TODO: Add ElasticsearchConfigStore when implemented
    # self._config_store_registry.register(
    #     name="elasticsearch",
    #     adapter_type=ElasticsearchConfigStore,
    #     ...
    # )
```

#### Add Registry Properties

```python
@property
def storage_registry(self) -> StorageRegistry:
    """Get the storage registry."""
    return self._storage_registry

@property
def metrics_registry(self) -> MetricsRegistry:
    """Get the metrics registry."""
    return self._metrics_registry

@property
def notifier_registry(self) -> NotifierRegistry:
    """Get the notifier registry."""
    return self._notifier_registry

@property
def config_store_registry(self) -> ConfigStoreRegistry:
    """Get the config store registry."""
    return self._config_store_registry
```

#### Add Creation Methods

```python
def create_storage(
    self,
    adapter_name: Optional[str] = None,
    **kwargs
) -> IStorage:
    """Create a storage adapter instance."""
    if adapter_name is None:
        adapter_name = self._storage_registry.get_default_name()
        if adapter_name is None:
            raise ValueError("No default storage adapter configured")

    logger.info(f"Creating storage adapter: {adapter_name}")
    adapter = self._storage_registry.create_instance(adapter_name, **kwargs)

    # No resilience applied to storage (similar to event store)
    return adapter


def create_metrics(
    self,
    adapter_name: Optional[str] = None,
    **kwargs
) -> IMetrics:
    """Create a metrics adapter instance."""
    if adapter_name is None:
        adapter_name = self._metrics_registry.get_default_name()
        if adapter_name is None:
            raise ValueError("No default metrics adapter configured")

    logger.info(f"Creating metrics adapter: {adapter_name}")
    adapter = self._metrics_registry.create_instance(adapter_name, **kwargs)

    # No resilience applied to metrics (internal infrastructure)
    return adapter


def create_notifier(
    self,
    adapter_name: Optional[str] = None,
    resilience_config: Optional[ServiceResilienceConfig] = None,
    **kwargs
) -> INotifier:
    """Create a notifier adapter instance."""
    if adapter_name is None:
        adapter_name = self._notifier_registry.get_default_name()
        if adapter_name is None:
            raise ValueError("No default notifier adapter configured")

    logger.info(f"Creating notifier adapter: {adapter_name}")
    adapter = self._notifier_registry.create_instance(adapter_name, **kwargs)

    # Apply resilience if enabled (notifiers are external)
    if self._config.enable_resilience and adapter_name != 'mock':
        # TODO: Add NOTIFIER_RESILIENCE_CONFIG
        # adapter = self._resilience_factory.create_resilient_notifier(
        #     adapter, service_config=...
        # )
        pass

    return adapter


def create_config_store(
    self,
    adapter_name: Optional[str] = None,
    **kwargs
) -> IConfigStore:
    """Create a config store adapter instance."""
    if adapter_name is None:
        adapter_name = self._config_store_registry.get_default_name()
        if adapter_name is None:
            raise ValueError("No default config store adapter configured")

    logger.info(f"Creating config store adapter: {adapter_name}")
    adapter = self._config_store_registry.create_instance(adapter_name, **kwargs)

    # No resilience applied to config store (internal infrastructure)
    return adapter
```

### 3. Missing Imports

Add to `src/codetoreum/infrastructure/adapters/factory.py`:

```python
from codetoreum.ports.output.storage import IStorage
from codetoreum.ports.output.metrics import IMetrics
from codetoreum.ports.output.notifier import INotifier
from codetoreum.ports.output.config_store import IConfigStore

from codetoreum.infrastructure.adapters.registries import (
    # ... existing imports ...
    StorageRegistry,
    MetricsRegistry,
    NotifierRegistry,
    ConfigStoreRegistry
)

from codetoreum.adapters.testing import (
    # ... existing imports ...
    InMemoryStorageAdapter,
    InMemoryMetricsAdapter,
    MockNotifierAdapter,
    InMemoryConfigStore
)
```

### 4. Missing Production Adapters

These need to be implemented:

#### Storage Adapter
- ✅ `InMemoryStorageAdapter` - Exists
- ❌ `LocalStorageAdapter` - **Needs implementation**
- ❌ `S3StorageAdapter` - Optional (future)

**Location**: `src/codetoreum/adapters/secondary/local_storage_adapter.py`

#### Metrics Adapter
- ✅ `InMemoryMetricsAdapter` - Exists
- ❌ `ElasticsearchMetricsAdapter` - **Needs implementation**
- ❌ `PrometheusMetricsAdapter` - Optional (future)

**Location**: `src/codetoreum/adapters/secondary/elasticsearch_metrics_adapter.py`

#### Notifier Adapter
- ✅ `MockNotifierAdapter` - Exists
- ❌ `EmailNotifierAdapter` - **Needs implementation**
- ❌ `SlackNotifierAdapter` - Optional (future)

**Location**: `src/codetoreum/adapters/secondary/email_notifier_adapter.py`

#### Config Store Adapter
- ✅ `InMemoryConfigStore` - Exists
- ❌ `ElasticsearchConfigStore` - **May already exist** (check `adapters/secondary/`)
- ❌ `PostgresConfigStore` - Optional (future)

**Location**: Check if already exists, otherwise implement

### 5. Configuration Module

The guide references `src/codetoreum/infrastructure/config/adapter_config.py` which doesn't exist yet.

**Create**: `src/codetoreum/infrastructure/config/`
- `__init__.py`
- `adapter_config.py` (full code provided in hybrid mode guide)

## Implementation Priority

### Phase 1: Critical (Required for Hybrid Mode)

1. ✅ Create `infrastructure/config/adapter_config.py` module
   - `AdapterMode` enum
   - `AdapterSelectionConfig` class
   - `create_adapters_from_config()` function

2. ✅ Add missing registries to `registries.py`:
   - `MetricsRegistry`
   - `NotifierRegistry`
   - `ConfigStoreRegistry`

3. ✅ Add factory methods to `factory.py`:
   - `create_storage()`
   - `create_metrics()`
   - `create_notifier()`
   - `create_config_store()`

4. ✅ Update `_register_default_adapters()` to register in-memory versions

### Phase 2: Production Adapters (Can use mocks initially)

5. ⏳ Implement `LocalStorageAdapter` (or verify it exists)
6. ⏳ Implement/verify `ElasticsearchMetricsAdapter`
7. ⏳ Implement `EmailNotifierAdapter`
8. ⏳ Verify `ElasticsearchConfigStore` exists

### Phase 3: Testing & Validation

9. ⏳ Write integration tests for hybrid modes
10. ⏳ Test each predefined mode from the guide
11. ⏳ Validate adapter swapping works correctly

## Workaround for Immediate Use

Until the factory methods are implemented, you can manually create adapters:

```python
# Temporary workaround
from codetoreum.adapters.testing import (
    InMemoryStorageAdapter,
    InMemoryMetricsAdapter,
    MockNotifierAdapter,
    InMemoryConfigStore
)

# Manually create adapters that aren't in factory yet
storage = InMemoryStorageAdapter()
metrics = InMemoryMetricsAdapter()
notifier = MockNotifierAdapter()
config_store = InMemoryConfigStore()

# Use factory for adapters that exist
factory = AdapterFactory()
ticket_system = factory.create_ticket_system(adapter_name='in_memory')
llm_provider = factory.create_llm_provider(adapter_name='mock')
container = factory.create_container(adapter_name='fake')
repository = factory.create_repository(adapter_name='in_memory')
event_store = factory.create_event_store(adapter_name='in_memory')
```

## Estimated Implementation Time

- **Phase 1** (Critical): ~2 days
  - Config module: 4 hours
  - Registries: 2 hours
  - Factory methods: 4 hours
  - Testing: 4 hours

- **Phase 2** (Production adapters): ~3-5 days
  - LocalStorageAdapter: 1 day
  - ElasticsearchMetricsAdapter: 1-2 days
  - EmailNotifierAdapter: 1-2 days

- **Phase 3** (Testing): ~2 days
  - Integration tests: 1 day
  - Mode validation: 1 day

**Total**: ~7-9 days

## Questions for Verification

Before implementing, check:

1. ❓ Does `LocalStorageAdapter` already exist in `adapters/secondary/`?
2. ❓ Does `ElasticsearchConfigStore` already exist?
3. ❓ Are there existing metrics adapters in `adapters/secondary/`?
4. ❓ Are there existing notifier adapters?

**Action**: Run comprehensive search:

```bash
find src/codetoreum/adapters -name "*storage*" -o -name "*metrics*" -o -name "*notifier*" -o -name "*config*"
```

## Next Steps

1. Search for existing production adapters (above)
2. Implement Phase 1 (critical factory infrastructure)
3. Test with simulation mode + hybrid modes
4. Implement Phase 2 (production adapters) as needed
5. Update hybrid mode guide with any corrections

---

**Status**: Ready for implementation. The guide is complete but requires the factory infrastructure to be built out.
