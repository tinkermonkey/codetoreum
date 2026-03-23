"""Backwards-compatibility shim for MockCodeReviewAdapter.

The canonical implementation is InMemoryCodeReviewAdapter in adapters/testing/.
This module re-exports it under the old name for backwards compatibility.
"""

# Re-export the canonical testing adapter under the old name
from codetoreum.adapters.testing.in_memory_code_review_adapter import (
    InMemoryCodeReviewAdapter as MockCodeReviewAdapter,
)

__all__ = ["MockCodeReviewAdapter"]
