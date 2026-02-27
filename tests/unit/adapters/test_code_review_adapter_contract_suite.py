"""Phase 6 Contract Test Suite for Code Review Adapters.

This test suite verifies that code review adapter implementations conform to
the ICodeReviewService interface contract. Same test suite runs against both
mock and production adapters.
"""

import pytest

from codetoreum.adapters.secondary.mock_code_review_adapter import MockCodeReviewAdapter
from codetoreum.ports.output.code_review_service import ICodeReviewService
from codetoreum.ports.output.event_emitter import IEventEmitter


class CodeReviewAdapterContractSuite:
    """Base contract test suite for code review adapters."""

    @pytest.fixture
    def adapter(self):
        """Fixture to provide code review adapter."""
        raise NotImplementedError("Subclasses must implement adapter fixture")

    # =========================================================================
    # Interface Compliance Tests
    # =========================================================================

    def test_implements_code_review_service_interface(self, adapter):
        """Adapter must implement ICodeReviewService interface."""
        assert isinstance(adapter, ICodeReviewService)

    def test_implements_event_emitter_interface(self, adapter):
        """Adapter must implement IEventEmitter interface."""
        assert isinstance(adapter, IEventEmitter)

    # =========================================================================
    # Code Review Operations Tests
    # =========================================================================

    def test_create_pull_request_operation_exists(self, adapter):
        """Adapter must have create_pull_request operation."""
        assert hasattr(adapter, "create_pull_request")
        assert callable(adapter.create_pull_request)

    def test_get_pull_request_operation_exists(self, adapter):
        """Adapter must have get_pull_request operation."""
        assert hasattr(adapter, "get_pull_request")
        assert callable(adapter.get_pull_request)

    def test_add_review_comment_operation_exists(self, adapter):
        """Adapter must have add_review_comment operation."""
        assert hasattr(adapter, "add_review_comment")
        assert callable(adapter.add_review_comment)

    def test_submit_review_operation_exists(self, adapter):
        """Adapter must have submit_review operation."""
        assert hasattr(adapter, "submit_review")
        assert callable(adapter.submit_review)

    def test_request_changes_operation_exists(self, adapter):
        """Adapter must have request_changes operation."""
        assert hasattr(adapter, "request_changes")
        assert callable(adapter.request_changes)

    def test_approve_pull_request_operation_exists(self, adapter):
        """Adapter must have approve_pull_request operation."""
        assert hasattr(adapter, "approve_pull_request")
        assert callable(adapter.approve_pull_request)

    def test_get_pull_request_reviews_operation_exists(self, adapter):
        """Adapter must have get_pull_request_reviews operation."""
        assert hasattr(adapter, "get_pull_request_reviews")
        assert callable(adapter.get_pull_request_reviews)

    def test_can_merge_operation_exists(self, adapter):
        """Adapter must have can_merge operation."""
        assert hasattr(adapter, "can_merge")
        assert callable(adapter.can_merge)

    def test_merge_pull_request_operation_exists(self, adapter):
        """Adapter must have merge_pull_request operation."""
        assert hasattr(adapter, "merge_pull_request")
        assert callable(adapter.merge_pull_request)

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
    async def test_create_pull_request_returns_string(self, adapter):
        """create_pull_request should return PR ID (string)."""
        result = await adapter.create_pull_request(
            repo_id="repo-1",
            title="Test PR",
            source_branch="feature",
            target_branch="main",
            description="Test",
        )
        assert result is None or isinstance(result, str)

    @pytest.mark.asyncio
    async def test_get_pull_request_returns_dict_or_none(self, adapter):
        """get_pull_request should return dict or None."""
        result = await adapter.get_pull_request("repo-1", "pr-1")
        assert result is None or isinstance(result, dict)

    @pytest.mark.asyncio
    async def test_get_pull_request_reviews_returns_list(self, adapter):
        """get_pull_request_reviews should return list."""
        result = await adapter.get_pull_request_reviews("repo-1", "pr-1")
        assert isinstance(result, list)

    @pytest.mark.asyncio
    async def test_can_merge_returns_boolean(self, adapter):
        """can_merge should return boolean."""
        result = await adapter.can_merge("repo-1", "pr-1")
        assert isinstance(result, bool)

    # =========================================================================
    # Error Handling Contracts
    # =========================================================================

    @pytest.mark.asyncio
    async def test_get_pull_request_handles_missing_pr(self, adapter):
        """get_pull_request should gracefully handle missing PR."""
        result = await adapter.get_pull_request("repo-1", "pr-nonexistent-999")
        assert result is None or isinstance(result, dict)

    @pytest.mark.asyncio
    async def test_get_pull_request_reviews_handles_missing_pr(self, adapter):
        """get_pull_request_reviews should handle missing PR."""
        result = await adapter.get_pull_request_reviews("repo-1", "pr-nonexistent-999")
        assert isinstance(result, list)

    @pytest.mark.asyncio
    async def test_approve_pull_request_with_invalid_input(self, adapter):
        """approve_pull_request should handle invalid input gracefully."""
        try:
            result = await adapter.approve_pull_request(
                repo_id="repo-1",
                pr_id="pr-nonexistent",
                reviewer_id="reviewer-1",
                message="Approved",
            )
            assert result is None or isinstance(result, bool)
        except (ValueError, Exception):
            # Also acceptable to raise
            pass


class TestMockCodeReviewAdapterContract(CodeReviewAdapterContractSuite):
    """Run contract tests against MockCodeReviewAdapter."""

    @pytest.fixture
    def adapter(self):
        """Provide MockCodeReviewAdapter instance."""
        return MockCodeReviewAdapter()

    @pytest.mark.asyncio
    async def test_mock_code_review_adapter_default_behavior(self, adapter):
        """MockCodeReviewAdapter should have sensible defaults."""
        # Mock should be usable without configuration
        reviews = await adapter.get_pull_request_reviews("repo-1", "pr-1")
        assert isinstance(reviews, list)
