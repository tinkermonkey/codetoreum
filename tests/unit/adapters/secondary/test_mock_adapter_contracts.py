"""Contract tests verifying mock adapters implement port interfaces.

These tests ensure mock adapters satisfy the port interface contracts,
enabling them to be used as drop-in replacements for production adapters
in tests and simulation.
"""

import pytest

from codetoreum.adapters.secondary.configurable_identity_service import (
    ConfigurableIdentityService,
)
from codetoreum.adapters.secondary.in_memory_queue_lock_service import (
    InMemoryLockService,
)
from codetoreum.adapters.secondary.mock_code_review_adapter import MockCodeReviewAdapter
from codetoreum.adapters.testing import MockDiscussionAdapter
from codetoreum.adapters.testing.mock_board_adapter import MockBoardAdapter
from codetoreum.application.pipeline_lock_service import (
    IPipelineLockService,
    IQueuedPipelineLockService,
)
from codetoreum.ports.output.board_service import IBoardService
from codetoreum.ports.output.code_review_service import ICodeReviewService
from codetoreum.ports.output.discussion_adapter import IDiscussionAdapter
from codetoreum.ports.output.event_emitter import IEventEmitter
from codetoreum.ports.output.identity_service import IIdentityService


class TestMockBoardAdapterContract:
    """Verify MockBoardAdapter satisfies IBoardService contract."""

    def test_is_event_emitter(self):
        """MockBoardAdapter should be an IEventEmitter."""
        adapter = MockBoardAdapter()
        assert isinstance(adapter, IEventEmitter)

    def test_is_board_service(self):
        """MockBoardAdapter should be an IBoardService."""
        adapter = MockBoardAdapter()
        assert isinstance(adapter, IBoardService)

    def test_implements_board_operations(self):
        """MockBoardAdapter should implement all board operations."""
        adapter = MockBoardAdapter()
        assert hasattr(adapter, "get_board")
        assert hasattr(adapter, "get_columns")
        assert hasattr(adapter, "get_items_in_column")
        assert hasattr(adapter, "get_item_position")
        assert hasattr(adapter, "move_item_to_column")
        assert hasattr(adapter, "reconcile_board")

    def test_implements_monitoring_operations(self):
        """MockBoardAdapter should implement monitoring operations."""
        adapter = MockBoardAdapter()
        assert hasattr(adapter, "start_monitoring")
        assert hasattr(adapter, "stop_monitoring")
        assert hasattr(adapter, "get_monitoring_status")

    def test_implements_event_emitter_operations(self):
        """MockBoardAdapter should implement IEventEmitter operations."""
        adapter = MockBoardAdapter()
        assert hasattr(adapter, "on")
        assert hasattr(adapter, "off")
        assert hasattr(adapter, "emit")
        assert hasattr(adapter, "once")


class TestMockDiscussionAdapterContract:
    """Verify MockDiscussionAdapter satisfies IDiscussionAdapter contract."""

    def test_is_event_emitter(self):
        """MockDiscussionAdapter should be an IEventEmitter."""
        adapter = MockDiscussionAdapter(ConfigurableIdentityService())
        assert isinstance(adapter, IEventEmitter)

    def test_is_discussion_adapter(self):
        """MockDiscussionAdapter should be an IDiscussionAdapter."""
        adapter = MockDiscussionAdapter(ConfigurableIdentityService())
        assert isinstance(adapter, IDiscussionAdapter)

    def test_implements_discussion_operations(self):
        """MockDiscussionAdapter should implement all discussion operations."""
        adapter = MockDiscussionAdapter(ConfigurableIdentityService())
        assert hasattr(adapter, "get_thread")
        assert hasattr(adapter, "add_comment")
        assert hasattr(adapter, "start_monitoring")
        assert hasattr(adapter, "stop_monitoring")

    def test_implements_event_emitter_operations(self):
        """MockDiscussionAdapter should implement IEventEmitter operations."""
        adapter = MockDiscussionAdapter(ConfigurableIdentityService())
        assert hasattr(adapter, "on")
        assert hasattr(adapter, "off")
        assert hasattr(adapter, "emit")


class TestMockCodeReviewAdapterContract:
    """Verify MockCodeReviewAdapter satisfies ICodeReviewService contract."""

    def test_is_event_emitter(self):
        """MockCodeReviewAdapter should be an IEventEmitter."""
        adapter = MockCodeReviewAdapter()
        assert isinstance(adapter, IEventEmitter)

    def test_is_code_review_service(self):
        """MockCodeReviewAdapter should be an ICodeReviewService."""
        adapter = MockCodeReviewAdapter()
        assert isinstance(adapter, ICodeReviewService)

    def test_implements_code_review_operations(self):
        """MockCodeReviewAdapter should implement all code review operations."""
        adapter = MockCodeReviewAdapter()
        assert hasattr(adapter, "get_review_for_work_item")
        assert hasattr(adapter, "get_review_status")
        assert hasattr(adapter, "get_review_comments")
        assert hasattr(adapter, "request_changes")
        assert hasattr(adapter, "approve")

    def test_implements_monitoring_operations(self):
        """MockCodeReviewAdapter should implement monitoring operations."""
        adapter = MockCodeReviewAdapter()
        assert hasattr(adapter, "start_monitoring")
        assert hasattr(adapter, "stop_monitoring")
        assert hasattr(adapter, "get_monitoring_status")

    def test_implements_event_emitter_operations(self):
        """MockCodeReviewAdapter should implement IEventEmitter operations."""
        adapter = MockCodeReviewAdapter()
        assert hasattr(adapter, "on")
        assert hasattr(adapter, "off")
        assert hasattr(adapter, "emit")


class TestConfigurableIdentityServiceContract:
    """Verify ConfigurableIdentityService satisfies IIdentityService contract."""

    def test_is_identity_service(self):
        """ConfigurableIdentityService should be an IIdentityService."""
        service = ConfigurableIdentityService()
        assert isinstance(service, IIdentityService)

    def test_implements_identity_operations(self):
        """ConfigurableIdentityService should implement all identity operations."""
        service = ConfigurableIdentityService()
        assert hasattr(service, "is_bot_user")
        assert hasattr(service, "get_bot_username")
        assert hasattr(service, "get_human_users")
        assert hasattr(service, "configure")

    def test_does_not_emit_events(self):
        """ConfigurableIdentityService should NOT implement IEventEmitter."""
        service = ConfigurableIdentityService()
        assert not isinstance(service, IEventEmitter)


class TestEventEmitterContract:
    """Verify MockEventEmitter satisfies IEventEmitter contract."""

    def test_is_event_emitter(self):
        """MockEventEmitter should be an IEventEmitter."""
        from codetoreum.adapters.secondary.mock_event_emitter import (
            MockEventEmitter,
        )

        emitter = MockEventEmitter()
        assert isinstance(emitter, IEventEmitter)

    def test_implements_all_operations(self):
        """MockEventEmitter should implement all IEventEmitter operations."""
        from codetoreum.adapters.secondary.mock_event_emitter import (
            MockEventEmitter,
        )

        emitter = MockEventEmitter()
        assert hasattr(emitter, "on")
        assert hasattr(emitter, "off")
        assert hasattr(emitter, "emit")
        assert hasattr(emitter, "once")


class TestInMemoryLockServiceContract:
    """Verify InMemoryLockService satisfies IPipelineLockService/IQueuedPipelineLockService contract."""

    def test_is_pipeline_lock_service(self):
        """InMemoryLockService should be an IPipelineLockService (application-layer alias)."""
        service = InMemoryLockService()
        assert isinstance(service, IPipelineLockService)

    def test_is_queued_pipeline_lock_service(self):
        """InMemoryLockService should be an IQueuedPipelineLockService."""
        service = InMemoryLockService()
        assert isinstance(service, IQueuedPipelineLockService)

    def test_implements_query_operations(self):
        """InMemoryLockService should implement query operations."""
        service = InMemoryLockService()
        assert hasattr(service, "get_queue_state")
        assert hasattr(service, "get_all_lock_states")

    def test_implements_command_operations(self):
        """InMemoryLockService should implement command operations."""
        service = InMemoryLockService()
        assert hasattr(service, "try_acquire_lock")
        assert hasattr(service, "release_lock")

    def test_implements_queue_operations(self):
        """InMemoryLockService should implement IQueuedPipelineLockService operations."""
        service = InMemoryLockService()
        # IQueuedPipelineLockService methods
        assert hasattr(service, "get_queue_state")
        assert hasattr(service, "update_queue_positions")

    def test_implements_test_helper_operations(self):
        """InMemoryLockService should implement test helper operations."""
        service = InMemoryLockService()
        assert hasattr(service, "set_lock_acquired_at")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
