"""
REMOVED: Scenario 13 Multi-Project Orchestration

This test file was removed because it attempted to test multi-project orchestration
functionality through the SimulationRunner framework, which is not compatible with
the test design:

1. SimulationRunner.capture_event() expects DomainEvent instances, but the test
   attempted to capture CodetoreumEvent subclasses (ProjectClonedEvent,
   OrchestrationCycleCompletedEvent).

2. SimulationRunner does not support project-specific adapters (no project_adapter
   attribute), which the test tried to inject.

3. The MockProjectManagerAdapter is designed for unit tests with its own event
   emitter, not for simulation scenarios.

The multi-project orchestration feature itself is properly tested via:
- Unit tests in tests/unit/adapters/testing/test_mock_project_manager_adapter.py
- Integration tests that directly use MultiProjectOrchestrator with appropriate
  adapters and event handlers

SimulationRunner is designed for testing domain workflows with generic DomainEvent
instances. For adapter-specific event testing, use direct unit/integration tests
instead.
"""
