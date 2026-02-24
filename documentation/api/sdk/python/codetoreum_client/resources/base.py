"""
Base resource class for all API resource clients.

This module provides the base Resource class that all API resource clients
inherit from, ensuring consistent initialization and client access patterns.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from ..client import CodetoreumClient


class Resource:
    """
    Base class for all API resource clients.

    Provides common initialization and client reference for resource-specific
    API clients (e.g., WorkItemsResource, AgentsResource).

    Attributes:
        client: Reference to the CodetoreumClient instance
    """

    def __init__(self, client: CodetoreumClient) -> None:
        """
        Initialize a resource client.

        Args:
            client: The CodetoreumClient instance to use for requests
        """
        self.client = client
