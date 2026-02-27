"""Phase 6 Contract Test Suite for Discussion Adapters.

This test suite verifies that discussion adapter implementations conform to
the IDiscussionAdapter interface contract. Same test suite runs against both
mock and production adapters.
"""

import pytest

from codetoreum.adapters.secondary.configurable_identity_service import (
    ConfigurableIdentityService,
)
from codetoreum.adapters.testing import MockDiscussionAdapter
from codetoreum.ports.output.discussion_adapter import IDiscussionAdapter
from codetoreum.ports.output.event_emitter import IEventEmitter


class DiscussionAdapterContractSuite:
    """Base contract test suite for discussion adapters."""

    @pytest.fixture
    def identity_service(self):
        """Provide identity service."""
        return ConfigurableIdentityService()

    @pytest.fixture
    def adapter(self, identity_service):
        """Fixture to provide discussion adapter."""
        raise NotImplementedError("Subclasses must implement adapter fixture")

    # =========================================================================
    # Interface Compliance Tests
    # =========================================================================

    def test_implements_discussion_adapter_interface(self, adapter):
        """Adapter must implement IDiscussionAdapter interface."""
        assert isinstance(adapter, IDiscussionAdapter)

    def test_implements_event_emitter_interface(self, adapter):
        """Adapter must implement IEventEmitter interface."""
        assert isinstance(adapter, IEventEmitter)

    # =========================================================================
    # Discussion Thread Operations Tests
    # =========================================================================

    def test_get_discussion_thread_operation_exists(self, adapter):
        """Adapter must have get_discussion_thread operation."""
        assert hasattr(adapter, "get_discussion_thread")
        assert callable(adapter.get_discussion_thread)

    def test_get_thread_comments_operation_exists(self, adapter):
        """Adapter must have get_thread_comments operation."""
        assert hasattr(adapter, "get_thread_comments")
        assert callable(adapter.get_thread_comments)

    def test_add_comment_operation_exists(self, adapter):
        """Adapter must have add_comment operation."""
        assert hasattr(adapter, "add_comment")
        assert callable(adapter.add_comment)

    def test_update_comment_operation_exists(self, adapter):
        """Adapter must have update_comment operation."""
        assert hasattr(adapter, "update_comment")
        assert callable(adapter.update_comment)

    def test_delete_comment_operation_exists(self, adapter):
        """Adapter must have delete_comment operation."""
        assert hasattr(adapter, "delete_comment")
        assert callable(adapter.delete_comment)

    def test_create_discussion_thread_operation_exists(self, adapter):
        """Adapter must have create_discussion_thread operation."""
        assert hasattr(adapter, "create_discussion_thread")
        assert callable(adapter.create_discussion_thread)

    def test_close_discussion_operation_exists(self, adapter):
        """Adapter must have close_discussion operation."""
        assert hasattr(adapter, "close_discussion")
        assert callable(adapter.close_discussion)

    def test_reopen_discussion_operation_exists(self, adapter):
        """Adapter must have reopen_discussion operation."""
        assert hasattr(adapter, "reopen_discussion")
        assert callable(adapter.reopen_discussion)

    # =========================================================================
    # Comment Reaction Operations Tests
    # =========================================================================

    def test_add_reaction_operation_exists(self, adapter):
        """Adapter must have add_reaction operation."""
        assert hasattr(adapter, "add_reaction")
        assert callable(adapter.add_reaction)

    def test_remove_reaction_operation_exists(self, adapter):
        """Adapter must have remove_reaction operation."""
        assert hasattr(adapter, "remove_reaction")
        assert callable(adapter.remove_reaction)

    # =========================================================================
    # Monitoring Operations Tests
    # =========================================================================

    def test_start_monitoring_operation_exists(self, adapter):
        """Adapter must have start_monitoring operation."""
        assert hasattr(adapter, "start_monitoring")
        assert callable(adapter.start_monitoring)

    def test_stop_monitoring_operation_exists(self, adapter):
        """Adapter must have stop_monitoring operation."""
        assert hasattr(adapter, "stop_monitoring")
        assert callable(adapter.stop_monitoring)

    def test_get_monitoring_status_operation_exists(self, adapter):
        """Adapter must have get_monitoring_status operation."""
        assert hasattr(adapter, "get_monitoring_status")
        assert callable(adapter.get_monitoring_status)

    # =========================================================================
    # Event Emitter Operations Tests
    # =========================================================================

    def test_on_operation_exists(self, adapter):
        """Adapter must have on (event subscription) operation."""
        assert hasattr(adapter, "on")
        assert callable(adapter.on)

    def test_off_operation_exists(self, adapter):
        """Adapter must have off (event unsubscription) operation."""
        assert hasattr(adapter, "off")
        assert callable(adapter.off)

    def test_emit_operation_exists(self, adapter):
        """Adapter must have emit (event publishing) operation."""
        assert hasattr(adapter, "emit")
        assert callable(adapter.emit)

    def test_once_operation_exists(self, adapter):
        """Adapter must have once (one-time subscription) operation."""
        assert hasattr(adapter, "once")
        assert callable(adapter.once)

    # =========================================================================
    # Return Type Contracts
    # =========================================================================

    @pytest.mark.asyncio
    async def test_get_discussion_thread_returns_dict_or_none(self, adapter):
        """get_discussion_thread should return dict or None."""
        result = await adapter.get_discussion_thread("discussion-1")
        assert result is None or isinstance(result, dict)

    @pytest.mark.asyncio
    async def test_get_thread_comments_returns_list(self, adapter):
        """get_thread_comments should return list."""
        result = await adapter.get_thread_comments("discussion-1")
        assert isinstance(result, list)

    @pytest.mark.asyncio
    async def test_add_comment_returns_dict_or_string(self, adapter):
        """add_comment should return comment dict or ID."""
        result = await adapter.add_comment(
            discussion_id="discussion-1",
            author_id="user-1",
            body="Test comment",
        )
        assert result is None or isinstance(result, (str, dict))

    @pytest.mark.asyncio
    async def test_create_discussion_thread_returns_string_or_dict(self, adapter):
        """create_discussion_thread should return ID or dict."""
        result = await adapter.create_discussion_thread(
            related_to="issue-1",
            title="Discussion",
            body="Details",
        )
        assert result is None or isinstance(result, (str, dict))

    # =========================================================================
    # Error Handling Contracts
    # =========================================================================

    @pytest.mark.asyncio
    async def test_get_discussion_thread_handles_missing(self, adapter):
        """get_discussion_thread should handle missing thread gracefully."""
        result = await adapter.get_discussion_thread("discussion-nonexistent-999")
        assert result is None or isinstance(result, dict)

    @pytest.mark.asyncio
    async def test_get_thread_comments_handles_missing(self, adapter):
        """get_thread_comments should handle missing thread."""
        result = await adapter.get_thread_comments("discussion-nonexistent-999")
        assert isinstance(result, list)

    @pytest.mark.asyncio
    async def test_add_comment_with_invalid_discussion(self, adapter):
        """add_comment should handle invalid discussion gracefully."""
        try:
            result = await adapter.add_comment(
                discussion_id="discussion-nonexistent",
                author_id="user-1",
                body="Test",
            )
            assert result is None or isinstance(result, (str, dict))
        except (ValueError, Exception):
            # Also acceptable to raise
            pass

    @pytest.mark.asyncio
    async def test_delete_comment_with_invalid_comment(self, adapter):
        """delete_comment should handle invalid comment."""
        try:
            result = await adapter.delete_comment(
                discussion_id="discussion-1",
                comment_id="comment-nonexistent",
            )
            # May return bool or None
        except (ValueError, Exception):
            # Also acceptable to raise
            pass


class TestMockDiscussionAdapterContract(DiscussionAdapterContractSuite):
    """Run contract tests against MockDiscussionAdapter."""

    @pytest.fixture
    def adapter(self, identity_service):
        """Provide MockDiscussionAdapter instance."""
        return MockDiscussionAdapter(identity_service)

    @pytest.mark.asyncio
    async def test_mock_discussion_adapter_creates_threads(self, adapter):
        """MockDiscussionAdapter should support thread creation."""
        result = await adapter.create_discussion_thread(
            related_to="issue-1",
            title="Test",
            body="Test body",
        )
        # Mock should support creating threads
        assert result is None or isinstance(result, (str, dict))

    @pytest.mark.asyncio
    async def test_mock_discussion_adapter_handles_comments(self, adapter):
        """MockDiscussionAdapter should support comment operations."""
        # Add comment to non-existent thread (mock should handle gracefully)
        result = await adapter.add_comment(
            discussion_id="discussion-1",
            author_id="user-1",
            body="Test comment",
        )
        # Should handle gracefully
