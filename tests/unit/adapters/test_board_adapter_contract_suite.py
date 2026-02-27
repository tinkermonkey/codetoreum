"""Phase 6 Contract Test Suite for Board Adapters.

This test suite verifies that board adapter implementations (both mock and production)
conform to the IBoardService interface contract. The same test suite is run against
both mock and production adapters to ensure behavior consistency.

Test Pattern:
- Use a fixture to provide the adapter instance
- Test methods verify both interface implementation and behavioral contracts
- Both MockBoardAdapter and production adapters must pass identical test suites
"""

import pytest

from codetoreum.adapters.testing.mock_board_adapter import MockBoardAdapter
from codetoreum.ports.output.board_service import IBoardService
from codetoreum.ports.output.event_emitter import IEventEmitter


class BoardAdapterContractSuite:
    """Base contract test suite for board adapters.

    This suite is parameterized to run against multiple adapter implementations.
    """

    @pytest.fixture
    def adapter(self):
        """Fixture to provide board adapter (to be overridden by subclasses)."""
        raise NotImplementedError("Subclasses must implement adapter fixture")

    # =========================================================================
    # Interface Compliance Tests
    # =========================================================================

    def test_implements_board_service_interface(self, adapter):
        """Adapter must implement IBoardService interface."""
        assert isinstance(adapter, IBoardService)

    def test_implements_event_emitter_interface(self, adapter):
        """Adapter must implement IEventEmitter interface."""
        assert isinstance(adapter, IEventEmitter)

    # =========================================================================
    # Board Service Operations Tests
    # =========================================================================

    @pytest.mark.asyncio
    async def test_get_board_operation_exists(self, adapter):
        """Adapter must have get_board operation."""
        assert hasattr(adapter, "get_board")
        assert callable(adapter.get_board)

    @pytest.mark.asyncio
    async def test_get_columns_operation_exists(self, adapter):
        """Adapter must have get_columns operation."""
        assert hasattr(adapter, "get_columns")
        assert callable(adapter.get_columns)

    @pytest.mark.asyncio
    async def test_get_items_in_column_operation_exists(self, adapter):
        """Adapter must have get_items_in_column operation."""
        assert hasattr(adapter, "get_items_in_column")
        assert callable(adapter.get_items_in_column)

    @pytest.mark.asyncio
    async def test_get_item_position_operation_exists(self, adapter):
        """Adapter must have get_item_position operation."""
        assert hasattr(adapter, "get_item_position")
        assert callable(adapter.get_item_position)

    @pytest.mark.asyncio
    async def test_move_item_to_column_operation_exists(self, adapter):
        """Adapter must have move_item_to_column operation."""
        assert hasattr(adapter, "move_item_to_column")
        assert callable(adapter.move_item_to_column)

    @pytest.mark.asyncio
    async def test_reconcile_board_operation_exists(self, adapter):
        """Adapter must have reconcile_board operation."""
        assert hasattr(adapter, "reconcile_board")
        assert callable(adapter.reconcile_board)

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
    async def test_get_board_returns_dict_or_none(self, adapter):
        """get_board should return dict or None."""
        result = await adapter.get_board("test-board")
        assert result is None or isinstance(result, dict)

    @pytest.mark.asyncio
    async def test_get_columns_returns_list(self, adapter):
        """get_columns should return list."""
        result = await adapter.get_columns("test-board")
        assert isinstance(result, list)

    @pytest.mark.asyncio
    async def test_get_items_in_column_returns_list(self, adapter):
        """get_items_in_column should return list."""
        result = await adapter.get_items_in_column("test-board", "column-1")
        assert isinstance(result, list)

    @pytest.mark.asyncio
    async def test_get_item_position_returns_dict_or_none(self, adapter):
        """get_item_position should return dict or None."""
        result = await adapter.get_item_position("test-board", "item-1")
        assert result is None or isinstance(result, dict)

    @pytest.mark.asyncio
    async def test_reconcile_board_returns_dict(self, adapter):
        """reconcile_board should return dict."""
        result = await adapter.reconcile_board("test-board")
        assert isinstance(result, dict)

    # =========================================================================
    # Error Handling Contracts
    # =========================================================================

    @pytest.mark.asyncio
    async def test_get_board_handles_missing_board(self, adapter):
        """get_board should gracefully handle missing board."""
        # Should not raise, but may return None
        result = await adapter.get_board("nonexistent-board-999")
        # Implementation may return None or empty dict, but shouldn't raise

    @pytest.mark.asyncio
    async def test_get_columns_handles_missing_board(self, adapter):
        """get_columns should handle missing board gracefully."""
        # Should not raise, returns empty list
        result = await adapter.get_columns("nonexistent-board-999")
        assert isinstance(result, list)

    @pytest.mark.asyncio
    async def test_move_item_to_column_with_invalid_inputs(self, adapter):
        """move_item_to_column should handle invalid inputs."""
        # Should handle gracefully (implementation specific)
        # May raise ValueError or return False, but shouldn't crash
        try:
            result = await adapter.move_item_to_column(
                "test-board", "item-1", "nonexistent-column"
            )
            # If it returns, should be boolean
            assert isinstance(result, bool)
        except ValueError:
            # Also acceptable to raise ValueError
            pass


class TestMockBoardAdapterContract(BoardAdapterContractSuite):
    """Run contract tests against MockBoardAdapter."""

    @pytest.fixture
    def adapter(self):
        """Provide MockBoardAdapter instance."""
        return MockBoardAdapter()

    @pytest.mark.asyncio
    async def test_mock_board_adapter_reflects_configuration(self, adapter):
        """MockBoardAdapter should reflect configured boards."""
        # Mock should support configuration
        assert hasattr(adapter, "_boards") or hasattr(adapter, "_configured")
