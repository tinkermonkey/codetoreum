"""Tests for error ID infrastructure and categorization."""

import pytest

from codetoreum.infrastructure.error_ids import (
    ErrorCategory,
    ErrorRegistry,
    get_error_id_category,
)


class TestErrorIdCategory:
    """Tests for get_error_id_category function."""

    def test_single_word_prefix_validation(self):
        """Single-word prefixes resolve to their matching ErrorCategory."""
        assert get_error_id_category("ERR_VALIDATION_FAILED") == ErrorCategory.VALIDATION
        assert get_error_id_category("ERR_AUTHENTICATION_FAILED") == ErrorCategory.AUTHENTICATION
        assert get_error_id_category("ERR_AUTHORIZATION_ERROR") == ErrorCategory.AUTHORIZATION
        assert get_error_id_category("ERR_TIMEOUT_ERROR") == ErrorCategory.TIMEOUT
        assert get_error_id_category("ERR_DATABASE_ERROR") == ErrorCategory.DATABASE
        assert get_error_id_category("ERR_CONTAINER_ERROR") == ErrorCategory.CONTAINER
        assert get_error_id_category("ERR_CONFIGURATION_ERROR") == ErrorCategory.CONFIGURATION
        assert get_error_id_category("ERR_HANDLER_REGISTRATION") == ErrorCategory.HANDLER
        assert get_error_id_category("ERR_WORKFLOW_ERROR") == ErrorCategory.WORKFLOW
        assert get_error_id_category("ERR_AGENT_ERROR") == ErrorCategory.AGENT
        assert get_error_id_category("ERR_REPOSITORY_ERROR") == ErrorCategory.REPOSITORY
        assert get_error_id_category("ERR_STORAGE_ERROR") == ErrorCategory.STORAGE
        assert get_error_id_category("ERR_INFRASTRUCTURE_ERROR") == ErrorCategory.INFRASTRUCTURE
        assert get_error_id_category("ERR_METRICS_ERROR") == ErrorCategory.METRICS
        assert get_error_id_category("ERR_AUDIT_ERROR") == ErrorCategory.AUDIT
        assert get_error_id_category("ERR_CONVERSATIONAL_LOOP_ERROR") == ErrorCategory.CONVERSATIONAL
        assert get_error_id_category("ERR_WEBHOOK_COLUMN_RESOLUTION_FAILED") == ErrorCategory.WEBHOOK
        assert get_error_id_category("ERR_DEBUG_MODE_IN_PRODUCTION") == ErrorCategory.DEBUG

    def test_single_word_prefix_scheduler(self):
        """ERR_SCHEDULER_* errors resolve to SCHEDULER category."""
        assert get_error_id_category("ERR_SCHEDULER_AGENT_CONFIG_LOAD_FAILURE") == ErrorCategory.SCHEDULER
        assert get_error_id_category("ERR_SCHEDULER_RATE_LIMIT") == ErrorCategory.SCHEDULER
        assert get_error_id_category("ERR_SCHEDULER_RESOURCE_UNAVAILABLE") == ErrorCategory.SCHEDULER
        assert get_error_id_category("ERR_SCHEDULER_ENQUEUE_FAILURE") == ErrorCategory.SCHEDULER

    def test_single_word_prefix_board(self):
        """ERR_BOARD_* errors resolve to BOARD category."""
        assert get_error_id_category("ERR_BOARD_ERROR") == ErrorCategory.BOARD
        assert get_error_id_category("ERR_BOARD_RECONCILIATION_ERROR") == ErrorCategory.BOARD
        assert get_error_id_category("ERR_BOARD_COLUMN_ERROR") == ErrorCategory.BOARD

    def test_multi_word_exec_chain(self):
        """ERR_EXEC_CHAIN_* errors resolve to EXECUTION category."""
        assert get_error_id_category("ERR_EXEC_CHAIN_NO_ACTIVE_RUN") == ErrorCategory.EXECUTION
        assert get_error_id_category("ERR_EXEC_CHAIN_AGENT_LOAD_FAILURE") == ErrorCategory.EXECUTION
        assert get_error_id_category("ERR_EXEC_CHAIN_EXECUTION_FAILURE") == ErrorCategory.EXECUTION

    def test_multi_word_board_event(self):
        """ERR_BOARD_EVENT_* errors resolve to BOARD category."""
        assert get_error_id_category("ERR_BOARD_EVENT_LEGACY_PAYLOAD_MISSING_KEY") == ErrorCategory.BOARD
        assert get_error_id_category("ERR_BOARD_EVENT_HANDLE_COLUMN_CHANGE_FAILURE") == ErrorCategory.BOARD

    def test_multi_word_external_service(self):
        """ERR_EXTERNAL_SERVICE_* errors resolve to EXTERNAL_SERVICE category."""
        assert get_error_id_category("ERR_EXTERNAL_SERVICE_ERROR") == ErrorCategory.EXTERNAL_SERVICE
        assert get_error_id_category("ERR_EXTERNAL_SERVICE_TIMEOUT") == ErrorCategory.EXTERNAL_SERVICE

    def test_multi_word_event_bus(self):
        """ERR_EVENT_BUS_* errors resolve to EVENT_BUS category."""
        assert get_error_id_category("ERR_EVENT_BUS_ERROR") == ErrorCategory.EVENT_BUS

    def test_multi_word_repair_cycle(self):
        """ERR_REPAIR_CYCLE_* errors resolve to REPAIR_CYCLE category."""
        assert get_error_id_category("ERR_REPAIR_CYCLE_ERROR") == ErrorCategory.REPAIR_CYCLE
        assert get_error_id_category("ERR_REPAIR_CYCLE_STAGE_FAILURE") == ErrorCategory.REPAIR_CYCLE
        assert get_error_id_category("ERR_REPAIR_CYCLE_METRICS_ERROR") == ErrorCategory.REPAIR_CYCLE
        assert get_error_id_category("ERR_REPAIR_CYCLE_CIRCUIT_BREAKER_OPEN") == ErrorCategory.REPAIR_CYCLE

    def test_multi_word_pr_review_cycle(self):
        """ERR_PR_REVIEW_CYCLE_* errors resolve to PR_REVIEW_CYCLE category."""
        assert get_error_id_category("ERR_PR_REVIEW_CYCLE_ERROR") == ErrorCategory.PR_REVIEW_CYCLE
        assert get_error_id_category("ERR_PR_REVIEW_CYCLE_SERVICE_NOT_AVAILABLE") == ErrorCategory.PR_REVIEW_CYCLE
        assert get_error_id_category("ERR_PR_REVIEW_CYCLE_BOARD_SERVICE_ERROR") == ErrorCategory.PR_REVIEW_CYCLE

    def test_longest_match_first_three_word(self):
        """Three-word prefixes are matched before two-word prefixes."""
        # ERR_PR_REVIEW_CYCLE_X should match the 3-word prefix, not just PR
        error_id = "ERR_PR_REVIEW_CYCLE_ERROR"
        assert get_error_id_category(error_id) == ErrorCategory.PR_REVIEW_CYCLE

    def test_unknown_prefix_defaults_to_internal(self):
        """Unknown single-word prefixes default to INTERNAL category."""
        assert get_error_id_category("ERR_UNKNOWN_ERROR") == ErrorCategory.INTERNAL
        assert get_error_id_category("ERR_RANDOM_CATEGORY_SOMETHING") == ErrorCategory.INTERNAL

    def test_invalid_format_no_err_prefix(self):
        """Error IDs must start with ERR_ prefix."""
        with pytest.raises(ValueError, match="Invalid error ID format"):
            get_error_id_category("INVALID_ERROR")

    def test_invalid_format_no_underscore(self):
        """Error IDs must have at least one underscore after ERR_."""
        with pytest.raises(ValueError, match="Invalid error ID format"):
            get_error_id_category("ERR")

    def test_all_registered_error_ids_have_valid_categories(self):
        """All registered error IDs in ErrorRegistry can be categorized."""
        all_error_ids = ErrorRegistry.get_all_error_ids()
        for error_id in all_error_ids:
            # Should not raise and should return a valid category
            category = get_error_id_category(error_id)
            assert isinstance(category, ErrorCategory)

    def test_execution_category_exists(self):
        """EXECUTION category exists in ErrorCategory enum."""
        assert ErrorCategory.EXECUTION in ErrorCategory

    def test_external_service_category_exists(self):
        """EXTERNAL_SERVICE category exists in ErrorCategory enum."""
        assert ErrorCategory.EXTERNAL_SERVICE in ErrorCategory

    def test_event_bus_category_exists(self):
        """EVENT_BUS category exists in ErrorCategory enum."""
        assert ErrorCategory.EVENT_BUS in ErrorCategory

    def test_repair_cycle_category_exists(self):
        """REPAIR_CYCLE category exists in ErrorCategory enum."""
        assert ErrorCategory.REPAIR_CYCLE in ErrorCategory

    def test_pr_review_cycle_category_exists(self):
        """PR_REVIEW_CYCLE category exists in ErrorCategory enum."""
        assert ErrorCategory.PR_REVIEW_CYCLE in ErrorCategory

    def test_scheduler_category_exists(self):
        """SCHEDULER category exists in ErrorCategory enum."""
        assert ErrorCategory.SCHEDULER in ErrorCategory

    def test_board_category_exists(self):
        """BOARD category exists in ErrorCategory enum."""
        assert ErrorCategory.BOARD in ErrorCategory
