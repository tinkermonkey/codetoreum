# Port Interface Contract Tests

This directory contains abstract contract test classes that verify all implementations of port interfaces conform to their contracts.

## Overview

Each port interface (e.g., `IBoardService`, `IPipelineLockService`) has a corresponding contract test class (e.g., `TestBoardServiceContract`). These tests are abstract base classes that define the expected behavior of any implementation.

## How to Use

To test a concrete implementation of a port interface:

1. Create a concrete test class that inherits from the contract test class
2. Implement the abstract factory method to create your implementation
3. Run pytest - it will execute all contract tests against your implementation

### Example: Testing a Mock BoardService

```python
# tests/unit/adapters/mock_board_service_test.py

from codetoreum.adapters.mock.board_service import MockBoardService
from tests.unit.ports.output.test_board_service_contract import TestBoardServiceContract


class TestMockBoardService(TestBoardServiceContract):
    """Verify MockBoardService conforms to IBoardService contract."""

    async def create_service(self) -> IBoardService:
        return MockBoardService()

    async def setup_test_board(self, service, project_id, board_id):
        # Set up test data specific to your implementation
        return await service.get_board(project_id, board_id)
```

## Contract Test Classes

### TestEventEmitterContract
- **Location**: `test_event_emitter_contract.py`
- **Tests**: `IEventEmitter` interface
- **Coverage**: Event subscription, handler invocation, unsubscription, one-time handlers
- **Required Methods**: `create_emitter()`

### TestMonitoredServiceContract
- **Location**: `test_monitored_service_contract.py`
- **Tests**: `IMonitoredService` interface
- **Coverage**: Monitoring lifecycle, state transitions, configuration
- **Required Methods**: `create_service()`

### TestBoardServiceContract
- **Location**: `test_board_service_contract.py`
- **Tests**: `IBoardService` interface
- **Coverage**: Board queries, column management, item movement, reconciliation
- **Required Methods**: `create_service()`, `setup_test_board()`

### TestPipelineLockServiceContract
- **Location**: `test_pipeline_lock_service_contract.py`
- **Tests**: `IPipelineLockService` interface
- **Coverage**: Lock acquisition, release, querying, conflict handling
- **Required Methods**: `create_service()`

### TestDiscussionAdapterContract
- **Location**: `test_discussion_adapter_contract.py`
- **Tests**: `IDiscussionAdapter` interface
- **Coverage**: Comment posting, thread retrieval, monitoring, independence
- **Required Methods**: `create_adapter()`

## Benefits

1. **Consistency**: All implementations of a port interface behave consistently
2. **Early Detection**: Incompatibilities with the interface are caught immediately
3. **Documentation**: Tests serve as executable documentation of interface contracts
4. **Regression Prevention**: Changes that break the contract are caught by CI/CD

## Key Principles

- **Port Independence**: Contract tests don't depend on specific implementations
- **Extensibility**: Concrete test classes can add implementation-specific tests
- **Clarity**: Each test is focused and documents one aspect of the contract
- **Async Compatibility**: All tests are async-aware using pytest-asyncio

## Adding New Port Interfaces

When adding a new port interface:

1. Create a contract test class in `test_<interface>_contract.py`
2. Make it inherit from `ABC` to prevent direct instantiation
3. Add `@abstractmethod` for factory methods implementations must provide
4. Add test methods for all interface behaviors
5. Document expected exceptions and special cases

## Running Tests

Run all contract tests:
```bash
pytest tests/unit/ports/output/
```

Run specific contract tests:
```bash
pytest tests/unit/ports/output/test_board_service_contract.py
```

Run tests for a specific implementation:
```bash
pytest tests/unit/adapters/mock/test_board_service.py
```
