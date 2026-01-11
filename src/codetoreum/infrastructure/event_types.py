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
