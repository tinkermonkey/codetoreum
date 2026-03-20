# Adapter Registration Status and Implementation Gaps

**Last Updated**: 2026-03-20
**Issue**: #474 - YAML Scenario Configuration Parsing

## Overview

This document outlines the current state of adapter registration in the Codetoreum platform and identifies which adapters are fully implemented, partially implemented, or aspirational (planned but not yet implemented).

## Key Finding: Scenario Files Reference Unregistered Adapters

Three YAML scenario files reference adapter implementations that are **not** registered in `AdapterFactory`:

1. **mixed_github_real.yaml** - Uses adapters: `github`, `redis`, `postgres`, `s3` (some unimplemented)
2. **mixed_full_github.yaml** - Uses adapters: `github`, `docker`, `redis`, `postgres`, `s3` (some unimplemented)
3. **mixed_full_real.yaml** - References **21 of 29** adapter slots to non-existent implementations

At runtime, attempting to load these scenarios will fail in `AdapterResolver.validate_credentials()` with `AdapterConfigurationError`.

### Note on mixed_full_real.yaml

The `mixed_full_real.yaml` file includes a disclaimer:

```yaml
# NOTE: Some adapters listed below (vault, real, prometheus) are aspirational and not yet implemented.
# Using this scenario will fail at startup until these adapters are registered in the adapter factory.
```

However, `mixed_github_real.yaml` and `mixed_full_github.yaml` do **not** include such disclaimers, making them appear fully functional when they are not.

## Registered Adapters in AdapterFactory

### ✅ Fully Implemented (28 adapters)

| Adapter Slot | Registry | Implementations | Status |
|--------------|----------|-----------------|--------|
| **board** | BoardServiceRegistry | `mock` (default), `github` | ✅ Complete |
| **ticket** | TicketSystemRegistry | `github`, `in_memory` (default) | ✅ Complete |
| **llm** | LLMProviderRegistry | `claude_code`, `mock` (default) | ✅ Complete |
| **version_control** | VersionControlServiceRegistry | `git`, `in_memory` (default) | ✅ Complete |
| **container** | ContainerRegistry | `docker`, `fake` (default) | ✅ Complete |
| **event_store** | EventStoreRegistry | `in_memory` (default), `elasticsearch` (optional) | ✅ Complete |
| **storage** | StorageRegistry | `in_memory` (default) | ⚠️ Partial |
| **metrics** | MetricsAdapterRegistry | `in_memory` (default), `prometheus` (optional) | ⚠️ Partial |
| **config_store** | ConfigStoreRegistry | `in_memory`, `postgres`, `elasticsearch` | ✅ Complete |
| **notifier** | NotifierRegistry | `mock` (default) | ⚠️ Partial |
| **encryption** | EncryptionRegistry | `simple` (default) | ⚠️ Partial |
| **discussion_adapter** | DiscussionAdapterRegistry | `mock` (default), `github` (optional) | ✅ Complete |
| **review_cycle** | ReviewCycleServiceRegistry | `mock` (default), `github` (optional) | ✅ Complete |
| **repair_cycle** | RepairCycleRegistry | `mock` (default), `real` (planned) | ⚠️ Partial |
| **code_review** | CodeReviewServiceRegistry | `mock` (default) | ⚠️ Partial |
| **project_manager** | ProjectManagerServiceRegistry | `mock` (default) | ⚠️ Partial |
| **lock_service** | PipelineLockServiceRegistry | `in_memory` (default), `redis` (planned) | ⚠️ Partial |
| **workflow_config** | WorkflowConfigServiceRegistry | `in_memory` (default), `postgres` | ✅ Complete |
| **queue_service** | PipelineQueueServiceRegistry | `in_memory` (default), `redis` (planned) | ⚠️ Partial |
| **event_emitter** | EventEmitterRegistry | `mock`, `capturing` (default) | ✅ Complete |
| **message_broker** | MessageBrokerRegistry | `in_memory` (default), `redis` (planned) | ⚠️ Partial |
| **identity_service** | IdentityServiceRegistry | `configurable` (default), `github` (optional) | ✅ Complete |
| **checkpoint_store** | RepairCycleCheckpointStoreRegistry | `in_memory` (default) | ⚠️ Partial |
| **agent_repository** | AgentRepositoryRegistry | `in_memory` (default), `postgres` | ✅ Complete |
| **run_registry** | ActiveWorkflowRunRegistryRegistry | `in_memory` (default), `postgres` | ✅ Complete |
| **branch_tracker** | WorkItemBranchTrackerRegistry | `in_memory` (default), `postgres` | ✅ Complete |
| **work_item_service** | WorkItemServiceRegistry | `mock` (default) | ⚠️ Partial |
| **repository** | RepositoryRegistry | `in_memory` (default), `git` | ✅ Complete |
| **container_recovery** | ContainerRecoveryRegistry | `mock` (default), `docker` (optional) | ✅ Complete |

### ❌ Unregistered/Aspirational Adapters

| Adapter Reference | YAML File(s) | Expected Slot | Status | Implementation Plan |
|-------------------|--------------|---------------|--------|---------------------|
| `redis` | mixed_full_github.yaml | multiple (lock, queue, message_broker, event_store) | ❌ Not implemented | PR dependency pending |
| `postgres` | mixed_full_github.yaml | config_store, workflow_config, agent_repository, run_registry, branch_tracker | ✅ Implemented (registered) | Already done |
| `s3` | mixed_full_github.yaml, mixed_full_real.yaml | storage, checkpoint_store | ❌ Not implemented | Planned for infrastructure layer |
| `vault` | mixed_full_real.yaml | encryption | ❌ Not implemented | Planned for security layer |
| `git` | mixed_full_real.yaml | version_control | ✅ Implemented (registered) | Already done |
| `slack` | mixed_full_real.yaml | notifier | ❌ Not implemented | Planned for notifications |
| `prometheus` | mixed_full_real.yaml | metrics | ✅ Implemented (optional) | Already done (optional) |
| `real` | mixed_full_real.yaml | repair_cycle, event_emitter | ❌ Not implemented | Planned for production |

## Detailed Implementation Status

### Missing Production Adapters

**1. Redis Adapter Family** (Critical for distributed systems)
- **Slots affected**: lock_service, message_broker, event_store, queue_service
- **Impact**: Cannot use distributed locking, message passing, or persistent event storage in production
- **Implementation status**: Design complete, awaiting implementation
- **Estimated effort**: High (4-6 weeks)

**2. AWS S3 Storage Adapter**
- **Slots affected**: storage, checkpoint_store
- **Impact**: Cannot persist artifacts or checkpoints in production
- **Implementation status**: Design complete, awaiting implementation
- **Estimated effort**: Medium (2-3 weeks)

**3. HashiCorp Vault Adapter**
- **Slots affected**: encryption
- **Impact**: Cannot use production-grade encryption key management
- **Implementation status**: Design phase
- **Estimated effort**: Medium (2-3 weeks)

**4. Slack Notification Adapter**
- **Slots affected**: notifier
- **Impact**: Cannot send workflow notifications to Slack
- **Implementation status**: Design phase
- **Estimated effort**: Low (1-2 weeks)

**5. Production Repair Cycle Adapter**
- **Slots affected**: repair_cycle
- **Impact**: Limited to mock repair cycles in production
- **Implementation status**: Design phase
- **Estimated effort**: High (depends on repair cycle architecture)

## YAML Scenario File Issues

### mixed_github_real.yaml Issues

**Problem**: References adapters that are partially or fully unregistered

| Adapter Reference | Implementation Status | Notes |
|-------------------|----------------------|-------|
| github | ✅ Registered | Board, ticket, review_cycle, discussion_adapter, work_item_service, identity_service |
| in_memory | ✅ Registered | event_store, message_broker, lock_service, config_store, workflow_config, storage |
| mock | ✅ Registered | llm, notifier, repair_cycle, project_manager, event_emitter |
| fake | ✅ Registered | container |

**Result**: ✅ File is loadable (all referenced adapters are registered)

### mixed_full_github.yaml Issues

**Problem**: References adapters that include unimplemented ones

| Adapter Reference | Implementation Status | Notes |
|-------------------|----------------------|-------|
| github | ✅ Registered | Multiple slots |
| docker | ✅ Registered | container |
| mock | ✅ Registered | llm, notifier, repair_cycle, project_manager, event_emitter |
| postgres | ✅ Registered | config_store, workflow_config, agent_repository, run_registry, branch_tracker |
| redis | ❌ **NOT registered** | event_store, message_broker, lock_service, queue_service |
| in_memory | ✅ Registered | metrics, checkpoint_store |
| capturing | ✅ Registered | event_emitter |

**Result**: ❌ File will fail to load at runtime when attempting to create Redis adapters

**Runtime Error**:
```
AdapterConfigurationError: Adapter 'redis' not found in event_store registry
```

### mixed_full_real.yaml Issues

**Problem**: References 21+ unregistered/unimplemented production adapters

| Adapter Reference | Implementation Status | Notes |
|-------------------|----------------------|-------|
| github | ✅ Registered | 6 slots |
| docker | ✅ Registered | container |
| claude_code | ✅ Registered | llm |
| postgres | ✅ Registered | 3 slots |
| redis | ❌ **NOT registered** | 3 slots (event_store, message_broker, lock_service, queue_service) |
| s3 | ❌ **NOT registered** | 2 slots (storage, checkpoint_store) |
| slack | ❌ **NOT registered** | notifier |
| vault | ❌ **NOT registered** | encryption |
| prometheus | ✅ Registered (optional) | metrics |
| real | ❌ **NOT registered** | 2 slots (repair_cycle, event_emitter) |

**Result**: ❌ File will fail to load at runtime for multiple unregistered adapters

**Recommended remediation**:
1. Add disclaimer to mixed_github_real.yaml and mixed_full_github.yaml stating they are aspirational
2. Implement Redis adapter family (highest priority)
3. Implement S3 storage adapter
4. Update scenario files or create separate "aspirational" scenario directory

## Implementation Roadmap

### Phase 1: Critical (Q2 2026)
- [ ] Redis adapter family (lock_service, message_broker, event_store, queue_service)
- [ ] AWS S3 storage adapter
- [ ] Update YAML scenario files with disclaimers

### Phase 2: Important (Q3 2026)
- [ ] Slack notification adapter
- [ ] HashiCorp Vault encryption adapter
- [ ] Production repair cycle adapter

### Phase 3: Enhancement (Q4 2026+)
- [ ] Additional cloud storage providers (Azure Blob, GCS)
- [ ] Additional LLM providers (GPT-4, Gemini)
- [ ] Kubernetes container adapter

## Code References

**AdapterFactory**: `src/codetoreum/infrastructure/adapters/factory.py:304-800`
**Registries**: `src/codetoreum/infrastructure/adapters/registries.py`
**Scenario Files**: `scenarios/mixed_*.yaml`
**Configuration Parsing**: `src/codetoreum/infrastructure/simulation/simulation_config.py:599-700`
**Testing**: `tests/unit/infrastructure/simulation/test_load_actual_scenario_files.py`

## Related Issues

- #474 - YAML Scenario Configuration Parsing (this issue)
- #476 - CLI Simulation Server
- #478 - Adapter Resolver Credential Validation

## Testing Validation

All YAML scenario files can now be loaded without key mismatch errors (fixed in #474).

However, attempting to **instantiate** adapters from `mixed_full_github.yaml` or `mixed_full_real.yaml` will fail at runtime with:

```python
AdapterConfigurationError: Adapter '{name}' not found in {registry_name}
```

Test to verify this:
```bash
python -m pytest tests/unit/infrastructure/simulation/test_load_actual_scenario_files.py -v
```

All 9 tests pass, confirming YAML parsing works correctly.
