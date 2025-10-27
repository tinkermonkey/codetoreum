"""Comment domain model for Codetoreum."""

from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from codetoreum.domain.types import CommentId, UserId, WorkItemId


@dataclass
class Comment:
    """Represents a comment on a work item.

    Attributes:
        id: Unique identifier for the comment
        work_item_id: ID of the work item this comment belongs to
        author_id: ID of the user who created the comment
        body: Text content of the comment
        created_at: When the comment was created
        updated_at: When the comment was last updated
        parent_id: ID of parent comment (for threaded discussions)
    """

    id: CommentId
    work_item_id: WorkItemId
    author_id: UserId
    body: str
    created_at: datetime
    updated_at: Optional[datetime] = None
    parent_id: Optional[CommentId] = None
