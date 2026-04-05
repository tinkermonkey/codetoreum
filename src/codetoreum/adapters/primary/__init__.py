"""
Primary Adapters

This module contains the primary (inbound) adapters for the Codetoreum system.
Primary adapters are entry points that receive external requests and translate
them into domain commands.

Available Adapters:
- GitHubWebhookAdapter: Receives webhook events from GitHub
- RestAPIAdapter: Provides RESTful HTTP API for programmatic access
- WebSocketAdapter: Provides real-time event streaming via WebSocket
"""

from codetoreum.adapters.primary.fastapi_app import create_app, create_development_app
from codetoreum.adapters.primary.factories.production import (
    create_branch_resolution_adapter,
    create_workspace_router_with_branch_resolution,
)
from codetoreum.adapters.primary.github_webhook_adapter import (
    GitHubWebhookAdapter,
    WebhookEvent,
    WebhookProcessingResult,
)
from codetoreum.adapters.primary.rest_api_adapter import RestAPIAdapter
from codetoreum.adapters.primary.websocket_adapter import WebSocketAdapter

__all__ = [
    "GitHubWebhookAdapter",
    "RestAPIAdapter",
    "WebSocketAdapter",
    "WebhookEvent",
    "WebhookProcessingResult",
    "create_app",
    "create_development_app",
    "create_branch_resolution_adapter",
    "create_workspace_router_with_branch_resolution",
]
