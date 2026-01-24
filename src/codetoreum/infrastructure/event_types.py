"""
Event type constants for the event bus.

Centralizes event type names to prevent typos and enable refactoring.
"""


class EventTypes:
    """Event type constants used throughout the system."""

    # Board events
    WORKITEM_COLUMN_CHANGED = "workitem.column_changed"
    BOARD_RECONCILED = "board.reconciled"

    # Discussion events
    COMMENT_NEEDS_RESPONSE = "comment.needs_response"
    COMMENT_POSTED = "comment.posted"

    # Lock events
    LOCK_ACQUIRED = "lock.acquired"
    LOCK_RELEASED = "lock.released"
    LOCK_STALE_DETECTED = "lock.stale_detected"

    # Review events
    REVIEW_STATUS_CHANGED = "review.status_changed"
    REVIEW_COMMENT_ADDED = "review.comment_added"

    # Repair cycle events
    REPAIR_CYCLE_STARTED = "repair_cycle.started"
    REPAIR_CYCLE_TEST_EXECUTION_STARTED = "repair_cycle.test_execution_started"
    REPAIR_CYCLE_TEST_EXECUTION_COMPLETED = "repair_cycle.test_execution_completed"
    REPAIR_CYCLE_TEST_CYCLE_COMPLETED = "repair_cycle.test_cycle_completed"
    REPAIR_CYCLE_FILE_FIX_STARTED = "repair_cycle.file_fix_started"
    REPAIR_CYCLE_FILE_FIX_COMPLETED = "repair_cycle.file_fix_completed"
    REPAIR_CYCLE_WARNING_REVIEW_STARTED = "repair_cycle.warning_review_started"
    REPAIR_CYCLE_WARNING_REVIEW_COMPLETED = "repair_cycle.warning_review_completed"
    REPAIR_CYCLE_FAST_FAIL = "repair_cycle.fast_fail"
    REPAIR_CYCLE_RESUMED = "repair_cycle.resumed"
    REPAIR_CYCLE_CHECKPOINT_FAILED = "repair_cycle.checkpoint_failed"
    REPAIR_CYCLE_METRICS_BACKEND_FAILED = "repair_cycle.metrics_backend_failed"
    REPAIR_CYCLE_COMPLETED = "repair_cycle.completed"
