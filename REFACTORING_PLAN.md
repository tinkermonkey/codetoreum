# Code Organization Refactoring Plan

## Overview

This document outlines the plan to split large files (500+ lines) into smaller, more maintainable modules.

## Current Structure

```
src/codetoreum/adapters/primary/
├── fastapi_app.py (2005 lines) ❌ TOO LARGE
├── routers/
│   ├── config.py (946 lines) ❌ TOO LARGE
│   ├── agents.py (729 lines) ❌ TOO LARGE
│   └── executions.py (535 lines) ❌ TOO LARGE
```

## Proposed Structure

### 1. fastapi_app.py Refactoring

**Current**: 2005 lines
**Target**: < 200 lines (main app setup only)

```
src/codetoreum/adapters/primary/
├── middleware/
│   ├── __init__.py ✅ CREATED
│   └── security.py ✅ CREATED (security headers middleware)
├── factories/
│   ├── __init__.py ✅ CREATED
│   ├── lifespan.py ✅ CREATED (application lifespan)
│   ├── app_factory.py (main create_app function)
│   └── development.py (create_development_app with mocks)
├── mocks/
│   ├── __init__.py ✅ CREATED
│   ├── mock_ports.py (mock command/query ports)
│   ├── mock_services.py (mock config service, event bus, logger)
│   └── mock_data.py (mock data generators)
└── fastapi_app.py (simplified entry point)
```

### 2. routers/config.py Refactoring

**Current**: 946 lines
**Target**: < 100 lines (router setup only)

```
routers/config/
├── __init__.py (exports create_config_router)
├── projects.py (project config endpoints ~250 lines)
├── agents.py (agent config endpoints ~200 lines)
├── pipelines.py (pipeline config endpoints ~200 lines)
├── environment.py (environment variable endpoints ~150 lines)
└── search.py (config search/audit endpoints ~150 lines)
```

**Endpoint Groups**:
- **projects.py**: GET/PUT /projects/{id}, DELETE /projects/{id}
- **agents.py**: GET/PUT /agents/{project_id}/{agent_name}
- **pipelines.py**: GET/PUT /pipelines/{project_id}/{pipeline_name}
- **environment.py**: POST/DELETE /projects/{id}/env-vars
- **search.py**: POST /search, GET /history

### 3. routers/agents.py Refactoring

**Current**: 729 lines
**Target**: < 100 lines (router setup only)

```
routers/agents/
├── __init__.py (exports create_agents_router)
├── list.py (list/filter/search endpoints ~200 lines)
├── crud.py (create/update/delete ~200 lines)
├── capabilities.py (add/update/remove capabilities ~150 lines)
└── mcp_servers.py (MCP server management ~150 lines)
```

**Endpoint Groups**:
- **list.py**: GET /agents (with filtering/pagination)
- **crud.py**: POST /agents, GET /agents/{id}, PUT /agents/{id}, DELETE /agents/{id}
- **capabilities.py**: POST /agents/{id}/capabilities, PUT /agents/{id}/capabilities/{name}, DELETE /agents/{id}/capabilities/{name}
- **mcp_servers.py**: POST /agents/{id}/mcp-servers, DELETE /agents/{id}/mcp-servers/{name}

### 4. routers/executions.py Refactoring

**Current**: 535 lines
**Target**: < 100 lines (router setup only)

```
routers/executions/
├── __init__.py (exports create_executions_router)
├── list.py (list/filter executions ~150 lines)
├── detail.py (get execution details ~100 lines)
├── control.py (terminate/pause/resume ~150 lines)
└── logs.py (get logs and history ~135 lines)
```

**Endpoint Groups**:
- **list.py**: GET /executions (with filtering/pagination)
- **detail.py**: GET /executions/{id}
- **control.py**: POST /executions/{id}/terminate, POST /executions/{id}/pause, POST /executions/{id}/resume
- **logs.py**: GET /executions/{id}/logs, GET /executions/{id}/history

## Implementation Strategy

### Phase 1: Router Refactoring (Highest Impact) ✅ PRIORITY
1. Split config.py into config/ subdirectory
2. Split agents.py into agents/ subdirectory
3. Split executions.py into executions/ subdirectory
4. Update __init__.py files to re-export create_*_router functions
5. Ensure all imports remain unchanged for external consumers

### Phase 2: FastAPI App Refactoring (Nice to Have)
1. Extract remaining mock classes to mocks/ directory
2. Create factories/app_factory.py with main create_app
3. Create factories/development.py with create_development_app
4. Simplify fastapi_app.py to import and use factories

### Phase 3: Testing & Validation
1. Run unit tests
2. Run integration tests
3. Verify API documentation still generates correctly
4. Check that development mode still works

## Benefits

1. **Maintainability**: Easier to find and modify specific endpoints
2. **Testability**: Each module can be tested independently
3. **Code Review**: Smaller files are easier to review
4. **Onboarding**: New developers can understand structure faster
5. **Modularity**: Clear separation of concerns

## Migration Path

All changes are **backwards compatible**. External imports remain unchanged:

```python
# Still works after refactoring
from codetoreum.adapters.primary.routers.config import create_config_router
from codetoreum.adapters.primary.routers.agents import create_agents_router
from codetoreum.adapters.primary.routers.executions import create_executions_router
```

## Next Steps

1. ✅ Create directory structure
2. ✅ Extract middleware and factories
3. ⏳ Split router files (IN PROGRESS)
4. ⏳ Update imports
5. ⏳ Run tests
6. ⏳ Update documentation

---

**Status**: IN PROGRESS
**Last Updated**: 2025-11-05
**Issue**: #29
