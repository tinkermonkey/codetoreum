"""Mock branch resolution adapter for testing and simulation.

This module provides a deterministic mock implementation of IBranchResolutionService
that enables testing branch resolution logic without external dependencies.
"""

import asyncio
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from codetoreum.adapters.secondary.mock_event_emitter import MockEventEmitter
from codetoreum.domain.events.branch_events import (
    BranchResolutionCreatedEvent,
    BranchResolvedEvent,
    BranchReusedEvent,
)
from codetoreum.domain.value_objects import BranchResolution
from codetoreum.ports.output.branch_resolution_service import IBranchResolutionService

if TYPE_CHECKING:
    from codetoreum.infrastructure.simulation.simulation_clock import SimulationClock


class MockBranchResolutionAdapter(MockEventEmitter, IBranchResolutionService):
    """Mock branch resolution adapter for testing.

    Provides configurable branch resolution decisions for simulation and unit tests.
    Default behavior returns action="create" with resolution_strategy="new" to preserve
    backward compatibility with existing tests.

    Configured responses are keyed by (project_id, issue_id) tuple. When a resolution
    is requested for a project/issue pair that has been pre-configured, the adapter
    returns that configured result. Otherwise, it returns the default result.

    The adapter emits two events on each resolve_branch() call:
    1. BranchResolvedEvent - Primary audit event (always emitted)
    2. BranchReusedEvent when action is "reuse", or BranchResolutionCreatedEvent
       when action is "create"

    Example:
        # Setup
        adapter = MockBranchResolutionAdapter()

        # Configure for specific project/issue
        resolution = BranchResolution(
            action="reuse",
            branch_name="feature/issue-123-fix",
            confidence=0.95,
            reason="Exact match found",
            resolution_strategy="exact_match"
        )
        adapter.configure_resolution("proj-1", "123", resolution)

        # Call resolve_branch
        result = await adapter.resolve_branch("proj-1", "123", {}, "/workspace/my-repo")
        assert result.action == "reuse"
        assert result.branch_name == "feature/issue-123-fix"

        # Subscribe to events
        events = []
        adapter.on("branch.resolved", events.append)
        await adapter.resolve_branch("proj-1", "123", {}, "/workspace/my-repo")
        assert len(events) == 1
    """

    def __init__(self, clock: "SimulationClock | None" = None) -> None:
        """Initialize the mock branch resolution adapter.

        Args:
            clock: Optional SimulationClock for deterministic time in tests.
                   If provided, event timestamps use simulation clock.
        """
        super().__init__()
        self._clock = clock
        self._lock = asyncio.Lock()

        # Configured resolutions: (project_id, issue_id) -> BranchResolution
        self._configured_resolutions: dict[tuple[str, str], BranchResolution] = {}

        # Exception to raise on next resolve_branch call (for testing fallback behavior)
        self._exception_to_raise: Exception | None = None

        # Default resolution for unconfigured cases
        self._default_resolution = BranchResolution(
            action="create",
            branch_name="feature/default-branch",
            confidence=1.0,
            reason="Default resolution (no pre-configured result)",
            resolution_strategy="new",
            parent_issue_id=None,
        )

    def configure_resolution(self, project_id: str, issue_id: str, resolution: BranchResolution) -> None:
        """Configure resolution for a specific project/issue pair.

        Args:
            project_id: Project identifier
            issue_id: Issue/work item identifier
            resolution: BranchResolution to return for this pair

        Raises:
            ValueError: If project_id or issue_id is empty
        """
        if not project_id or not project_id.strip():
            msg = "project_id cannot be empty"
            raise ValueError(msg)
        if not issue_id or not issue_id.strip():
            msg = "issue_id cannot be empty"
            raise ValueError(msg)

        self._configured_resolutions[(project_id, issue_id)] = resolution

    async def resolve_branch(
        self,
        project_id: str,
        issue_id: str,
        issue_metadata: Mapping[str, Any],
        repo_path: str,
    ) -> BranchResolution:
        """Resolve branch for a work item.

        Returns pre-configured resolution if available, otherwise returns default.
        Emits BranchResolvedEvent and appropriate outcome event (BranchReusedEvent
        or BranchResolutionCreatedEvent).

        Args:
            project_id: Project identifier
            issue_id: Issue/work item identifier
            issue_metadata: Issue metadata (unused in mock)
            repo_path: Local repository path (unused in mock, but required by interface)

        Returns:
            BranchResolution with action and branch details

        Raises:
            ValueError: If project_id or issue_id is empty
            Exception: Any exception configured via configure_to_raise()
        """
        if not project_id or not project_id.strip():
            msg = "project_id cannot be empty"
            raise ValueError(msg)
        if not issue_id or not issue_id.strip():
            msg = "issue_id cannot be empty"
            raise ValueError(msg)

        # Check if we should raise an exception (for testing fallback behavior)
        async with self._lock:
            if self._exception_to_raise is not None:
                exc = self._exception_to_raise
                self._exception_to_raise = None  # Clear after raising
                raise exc

        # Get configured or default resolution
        async with self._lock:
            resolution = self._configured_resolutions.get((project_id, issue_id), self._default_resolution)

        # Get timestamp
        now = self._clock.now() if self._clock else datetime.now(UTC)
        timestamp = now.isoformat()

        # Emit events - let all exceptions propagate immediately in test code
        # This ensures tests fail loudly if event dataclass signatures change
        # (rather than silently passing with suppressed exceptions)

        # Emit primary audit event
        resolved_event = BranchResolvedEvent(
            type="branch.resolved",
            timestamp=timestamp,
            source="mock_branch_resolution",
            project_id=project_id,
            issue_id=issue_id,
            action=resolution.action,
            branch_name=resolution.branch_name,
            confidence=resolution.confidence,
            reason=resolution.reason,
            parent_issue_id=resolution.parent_issue_id,
            resolution_strategy=resolution.resolution_strategy,
        )
        self.emit(resolved_event)

        # Emit outcome-specific event
        if resolution.action == "reuse":
            outcome_event = BranchReusedEvent(
                type="branch.reused",
                timestamp=timestamp,
                source="mock_branch_resolution",
                project_id=project_id,
                issue_id=issue_id,
                branch_name=resolution.branch_name,
                confidence=resolution.confidence,
                reason=resolution.reason,
                parent_issue_id=resolution.parent_issue_id,
                resolution_strategy=resolution.resolution_strategy,
            )
        else:
            # action == "create"
            outcome_event = BranchResolutionCreatedEvent(
                type="branch.created",
                timestamp=timestamp,
                source="mock_branch_resolution",
                project_id=project_id,
                issue_id=issue_id,
                branch_name=resolution.branch_name,
                confidence=resolution.confidence,
                reason=resolution.reason,
                parent_issue_id=resolution.parent_issue_id,
                resolution_strategy=resolution.resolution_strategy,
            )

        self.emit(outcome_event)

        return resolution

    # =========================================================================
    # Test Helper Methods
    # =========================================================================

    def clear_configurations(self) -> None:
        """Clear all configured resolutions."""
        self._configured_resolutions.clear()

    def set_default_resolution(self, resolution: BranchResolution) -> None:
        """Set the default resolution for unconfigured cases.

        Args:
            resolution: BranchResolution to use as default
        """
        self._default_resolution = resolution

    def configure_to_raise(self, exception: Exception) -> None:
        """Configure the adapter to raise an exception on next resolve_branch call.

        Used to test fallback behavior when the resolution service fails.

        Args:
            exception: Exception to raise on next resolve_branch() call
        """
        self._exception_to_raise = exception

    def get_configured_count(self) -> int:
        """Get count of configured resolutions.

        Returns:
            Number of configured (project_id, issue_id) pairs
        """
        return len(self._configured_resolutions)
