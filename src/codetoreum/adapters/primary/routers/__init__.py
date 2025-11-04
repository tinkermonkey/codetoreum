"""
Primary Adapter Routers

This package contains FastAPI routers for various REST API endpoints.
"""

from codetoreum.adapters.primary.routers.work_items import create_work_items_router

__all__ = ["create_work_items_router"]
