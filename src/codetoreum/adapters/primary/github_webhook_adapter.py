"""
GitHub Webhook Adapter

This module implements the primary adapter for receiving GitHub webhook events
and translating them into domain commands.
"""

import hashlib
import hmac
import logging
import time
from collections import OrderedDict
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from fastapi import Header, HTTPException, Request

try:
    from opentelemetry import trace
except ImportError:
    trace = None

from codetoreum.infrastructure.error_ids import ErrorRegistry
from codetoreum.infrastructure.event_bus import EventBus
from codetoreum.infrastructure.observability.instrumentation import (
    instrument_async_function,
)
from codetoreum.ports.input.workflow_command import (
    IWorkflowCommandPort,
    StartWorkflowCommand,
    TriggerType,
)
from codetoreum.ports.output.board_service import IBoardService
from codetoreum.ports.output.config_store import IConfigStore

# Type aliases for missing interfaces
IEventBus = EventBus
IConfigurationService = IConfigStore
ILogger = logging.Logger

logger = logging.getLogger(__name__)


# ============================================================================
# Data Classes
# ============================================================================


@dataclass
class WebhookEvent:
    """Domain representation of webhook event"""

    delivery_id: str
    event_type: str
    payload: dict[str, Any]
    signature: str
    timestamp: datetime
    repository: str


@dataclass
class WebhookProcessingResult:
    """Result of webhook processing"""

    success: bool
    message: str
    commands_created: list[str]
    errors: list[str] | None = None
    processing_time_ms: float = 0.0


@dataclass
class StageInfo:
    """Information about a pipeline stage"""

    pipeline_name: str
    board_name: str
    stage_name: str
    column_name: str
    agent_name: str


# ============================================================================
# Custom Exceptions
# ============================================================================


class WebhookError(Exception):
    """Base webhook error"""

    http_status = 500


class WebhookVerificationError(WebhookError):
    """Signature verification failed"""

    http_status = 401


class InvalidPayloadError(WebhookError):
    """Payload structure invalid"""

    http_status = 400


class UnknownProjectError(WebhookError):
    """Repository not configured"""

    http_status = 404


class WebhookProcessingError(WebhookError):
    """Event processing failed"""

    http_status = 500


# ============================================================================
# GitHub Webhook Adapter
# ============================================================================


class GitHubWebhookAdapter:
    """
    FastAPI-based GitHub webhook adapter.

    Receives webhook events from GitHub and translates them
    into domain commands via input ports.
    """

    # Idempotency cache configuration
    _DEFAULT_CACHE_SIZE = 1000
    _DEFAULT_EVICTION_THRESHOLD = 0.9  # Evict when at 90% capacity

    @staticmethod
    def _get_span():
        """Get current span if OpenTelemetry is available, otherwise return None."""
        if trace is None:
            return None
        try:
            return trace.get_current_span()
        except Exception as e:
            logger.debug("Failed to get current span: %s", str(e), exc_info=True)
            return None

    def __init__(
        self,
        workflow_command_port: IWorkflowCommandPort,
        event_bus: IEventBus,
        config_service: IConfigurationService,
        logger: ILogger,
        idempotency_cache_size: int = _DEFAULT_CACHE_SIZE,
        board_service: IBoardService | None = None,
    ):
        """
        Initialize adapter with dependencies.

        Args:
            workflow_command_port: Port for workflow commands
            event_bus: Event bus for publishing events
            config_service: Configuration service
            logger: Logging service
            idempotency_cache_size: Maximum size of idempotency cache (bounded, with LRU eviction)
            board_service: Optional board service for column-to-stage mapping
        """
        self.workflow_port = workflow_command_port
        self.event_bus = event_bus
        self.config = config_service
        self.logger = logger
        self.board_service = board_service
        self._idempotency_cache_size = idempotency_cache_size

        # Event handlers by GitHub event type
        self.handlers: dict[str, Callable] = {
            "project_card": self._handle_project_card_event,
            "issues": self._handle_issues_event,
            "issue_comment": self._handle_issue_comment_event,
            "pull_request": self._handle_pull_request_event,
            "discussion": self._handle_discussion_event,
        }

        # Track processed delivery IDs for idempotency (bounded cache with FIFO eviction)
        # OrderedDict maintains insertion order; popitem(last=False) removes oldest entry
        self._processed_deliveries: OrderedDict[str, WebhookProcessingResult] = OrderedDict()

    def _evict_old_entries_if_needed(self) -> None:
        """
        Evict oldest entries from idempotency cache if it exceeds the threshold.

        Uses FIFO (First In, First Out) eviction strategy based on insertion order.
        When cache size exceeds 90% of max capacity, removes the oldest 10% of entries.
        """
        cache_size = len(self._processed_deliveries)
        threshold = int(self._idempotency_cache_size * self._DEFAULT_EVICTION_THRESHOLD)

        if cache_size >= threshold:
            # Evict 10% of cache size (at least 1 entry)
            evict_count = max(1, self._idempotency_cache_size // 10)

            # Remove oldest entries (FIFO - pop from left)
            for _ in range(evict_count):
                self._processed_deliveries.popitem(last=False)

            # Single batched log instead of per-entry logging
            self.logger.debug("Evicted %d oldest entries from webhook idempotency cache", evict_count)

    @instrument_async_function(name="github.webhook.receive", attributes={"service": "github_webhook"})
    async def receive_webhook(
        self,
        request: Request,
        x_github_delivery: str = Header(...),
        x_github_event: str = Header(...),
        x_hub_signature_256: str = Header(...),
    ) -> dict[str, Any]:
        """
        FastAPI endpoint handler for webhook reception.

        Creates a span named "github.webhook.receive" with service attribute.
        Span attributes are populated with:
        - github.delivery_id: Unique GitHub delivery ID
        - github.event_type: GitHub event type (e.g., 'push', 'pull_request')

        Args:
            request: FastAPI request object
            x_github_delivery: Unique delivery ID header
            x_github_event: Event type header
            x_hub_signature_256: HMAC signature header

        Returns:
            JSON response with processing result

        Raises:
            HTTPException: On verification or processing failure
        """
        # Add webhook-specific attributes to span
        span = self._get_span()
        if span:
            span.set_attribute("github.delivery_id", x_github_delivery)
            span.set_attribute("github.event_type", x_github_event)
        start_time = time.time()

        try:
            # Check for idempotency - if already processed, return cached result
            if x_github_delivery in self._processed_deliveries:
                cached_result = self._processed_deliveries[x_github_delivery]
                self.logger.info("Webhook %s already processed, returning cached result", x_github_delivery)
                return {
                    "status": "accepted",
                    "delivery_id": x_github_delivery,
                    "message": cached_result.message + " (cached)",
                    "commands_created": cached_result.commands_created,
                }

            # 1. Read raw payload
            payload_bytes = await request.body()
            payload = await request.json()

            # 2. Create webhook event
            event = WebhookEvent(
                delivery_id=x_github_delivery,
                event_type=x_github_event,
                payload=payload,
                signature=x_hub_signature_256,
                timestamp=datetime.now(UTC),
                repository=payload.get("repository", {}).get("full_name", ""),
            )

            # 3. Identify project early (before signature verification)
            project_id = await self._identify_project(event.repository)
            if not project_id:
                msg = f"Repository {event.repository} not configured"
                raise UnknownProjectError(msg)

            # 4. Verify signature (pass project_id to avoid re-lookup)
            if not await self._verify_signature(payload_bytes, x_hub_signature_256, project_id):
                msg = "Invalid HMAC signature"
                raise WebhookVerificationError(msg)

            # 5. Validate payload
            if not self._validate_payload(event):
                msg = "Malformed payload structure"
                raise InvalidPayloadError(msg)

            # 6. Process event (pass project_id to avoid re-lookup)
            result = await self._process_event(event, project_id)

            # 7. Calculate metrics
            processing_time = (time.time() - start_time) * 1000
            result.processing_time_ms = processing_time

            # 8. Cache result for idempotency (with bounded cache and eviction)
            self._evict_old_entries_if_needed()
            self._processed_deliveries[x_github_delivery] = result

            # 9. Emit observability event
            self.logger.info("Webhook %s processed successfully in %.2fms", x_github_delivery, processing_time)

            # 10. Return success response
            return {
                "status": "accepted",
                "delivery_id": event.delivery_id,
                "message": result.message,
                "commands_created": result.commands_created,
            }

        except WebhookVerificationError as e:
            self.logger.warning("Webhook verification failed: %s", str(e), exc_info=True)
            raise HTTPException(status_code=401, detail=str(e)) from e

        except UnknownProjectError as e:
            self.logger.warning("Unknown project: %s", str(e), exc_info=True)
            raise HTTPException(status_code=404, detail=str(e)) from e

        except InvalidPayloadError as e:
            self.logger.error(
                f"Invalid payload: {e}",
                exc_info=True,
                extra={"error_id": ErrorRegistry.ERR_INVALID_INPUT},
            )
            raise HTTPException(status_code=400, detail=str(e)) from e

        except Exception as e:
            self.logger.error(
                f"Webhook processing failed: {e}",
                exc_info=True,
                extra={"error_id": ErrorRegistry.ERR_INTERNAL_ERROR},
            )
            raise HTTPException(status_code=500, detail="Internal error") from e

    async def _verify_signature(self, payload: bytes, signature: str, project_id: str) -> bool:
        """
        Verify HMAC-SHA256 signature from GitHub.

        Args:
            payload: Raw request body bytes
            signature: X-Hub-Signature-256 header (format: 'sha256=<hex>')
            project_id: Project identifier (already resolved before signature verification)

        Returns:
            True if signature matches
        """
        # Get project config to retrieve webhook secret from metadata
        try:
            project_config = await self.config.get_project_config(project_id)
        except Exception as e:
            self.logger.warning(
                "Could not load project config for %s: %s",
                project_id,
                str(e),
                exc_info=True,
            )
            return False

        secret = project_config.metadata.get("webhook_secret")
        if not secret:
            self.logger.warning(
                "Webhook secret not configured for project %s; "
                "signature verification cannot proceed",
                project_id,
            )
            return False

        # Compute expected signature
        expected = hmac.new(key=secret.encode("utf-8"), msg=payload, digestmod=hashlib.sha256).hexdigest()

        # Extract provided signature (remove 'sha256=' prefix)
        provided = signature.replace("sha256=", "")

        # Timing-safe comparison
        return hmac.compare_digest(expected, provided)

    def _validate_payload(self, event: WebhookEvent) -> bool:
        """
        Validate webhook payload structure.

        Args:
            event: Webhook event to validate

        Returns:
            True if payload is valid
        """
        payload = event.payload

        # Common validation
        if "repository" not in payload:
            return False

        # Event-specific validation
        validators = {
            "project_card": self._validate_project_card_payload,
            "issues": self._validate_issues_payload,
            "issue_comment": self._validate_issue_comment_payload,
            "pull_request": self._validate_pull_request_payload,
            "discussion": self._validate_discussion_payload,
        }

        validator = validators.get(event.event_type)
        if validator:
            return validator(payload)

        # Unknown event type - consider valid (ignore)
        return True

    def _validate_project_card_payload(self, payload: dict[str, Any]) -> bool:
        """Validate project_card event payload"""
        return "action" in payload and "project_card" in payload

    def _validate_issues_payload(self, payload: dict[str, Any]) -> bool:
        """Validate issues event payload"""
        return "action" in payload and "issue" in payload

    def _validate_issue_comment_payload(self, payload: dict[str, Any]) -> bool:
        """Validate issue_comment event payload"""
        return "action" in payload and "issue" in payload and "comment" in payload

    def _validate_pull_request_payload(self, payload: dict[str, Any]) -> bool:
        """Validate pull_request event payload"""
        return "action" in payload and "pull_request" in payload

    def _validate_discussion_payload(self, payload: dict[str, Any]) -> bool:
        """Validate discussion event payload"""
        return "action" in payload and "discussion" in payload

    @instrument_async_function(name="github.webhook.process_event", attributes={"service": "github_webhook"})
    async def _process_event(self, event: WebhookEvent, project_id: str) -> WebhookProcessingResult:
        """
        Process webhook event and create commands.

        Args:
            event: Webhook event to process
            project_id: Project identifier (resolved before signature verification)

        Returns:
            Processing result
        """
        # Add event details to span
        span = self._get_span()
        if span:
            span.set_attribute("github.event_type", event.event_type)
            span.set_attribute("github.delivery_id", event.delivery_id)
            span.set_attribute("github.repository", event.repository)
        # Get event handler
        handler = self.handlers.get(event.event_type)
        if not handler:
            # Unsupported event type - ignore gracefully
            return WebhookProcessingResult(
                success=True,
                message="Event type %s ignored" % event.event_type,
                commands_created=[],
            )

        # Handle event (project_id already resolved, avoid re-lookup)
        commands = await handler(event, project_id)

        return WebhookProcessingResult(
            success=True,
            message="Processed %s event" % event.event_type,
            commands_created=[cmd for cmd in commands],
        )

    @instrument_async_function(
        name="github.webhook.handle_project_card",
        attributes={"service": "github_webhook", "event_type": "project_card"},
    )
    async def _handle_project_card_event(self, event: WebhookEvent, project: str) -> list[str]:
        """
        Handle project_card event (card movement).

        Args:
            event: Webhook event
            project: Project name

        Returns:
            List of created command IDs
        """
        # Add project card context to span
        span = self._get_span()
        if span:
            span.set_attribute("github.project", project)
            if "action" in event.payload:
                span.set_attribute("github.action", event.payload["action"])
        payload = event.payload
        action = payload.get("action")

        # Only handle 'moved' action
        if action != "moved":
            return []

        # Extract card details
        card = payload["project_card"]
        content_url = card.get("content_url", "")
        column_id = card.get("column_id")

        # Extract issue/PR number from content URL
        work_item_id = self._extract_work_item_id(content_url)
        if not work_item_id:
            self.logger.warning("Could not extract work item ID from %s", content_url)
            return []

        # Map column ID to stage
        stage_info = await self._map_column_to_stage(project, column_id)
        if not stage_info:
            self.logger.warning("Column %s not mapped for project %s", column_id, project)
            return []

        # Create workflow command
        command = StartWorkflowCommand(
            project_name=project,
            work_item_id=work_item_id,
            pipeline_name=stage_info.pipeline_name,
            stage_name=stage_info.stage_name,
            trigger=TriggerType.CARD_MOVEMENT,
            context={
                "board_name": stage_info.board_name,
                "column_name": stage_info.column_name,
                "previous_column_id": payload.get("changes", {}).get("column_id", {}).get("from"),
                "delivery_id": event.delivery_id,
            },
        )

        # Execute command via port
        result = await self.workflow_port.start_workflow(command)

        return [result.workflow_run_id]

    @instrument_async_function(
        name="github.webhook.handle_issues",
        attributes={"service": "github_webhook", "event_type": "issues"},
    )
    async def _handle_issues_event(self, event: WebhookEvent, project: str) -> list[str]:
        """
        Handle issues event (issue created/updated).

        Args:
            event: Webhook event
            project: Project name

        Returns:
            List of created command IDs
        """
        # Add issue context to span
        span = self._get_span()
        if span:
            span.set_attribute("github.project", project)
            if "action" in event.payload:
                span.set_attribute("github.action", event.payload["action"])
        # Placeholder for future implementation
        return []

    @instrument_async_function(
        name="github.webhook.handle_issue_comment",
        attributes={"service": "github_webhook", "event_type": "issue_comment"},
    )
    async def _handle_issue_comment_event(self, event: WebhookEvent, project: str) -> list[str]:
        """
        Handle issue_comment event (agent feedback).

        Args:
            event: Webhook event
            project: Project name

        Returns:
            List of created command IDs
        """
        # Add issue comment context to span
        span = self._get_span()
        if span:
            span.set_attribute("github.project", project)
            if "action" in event.payload:
                span.set_attribute("github.action", event.payload["action"])
            if "issue" in event.payload and "number" in event.payload["issue"]:
                span.set_attribute("github.issue_number", event.payload["issue"]["number"])
            if "comment" in event.payload and "id" in event.payload["comment"]:
                span.set_attribute("github.comment_id", event.payload["comment"]["id"])
        # Placeholder for future implementation
        return []

    @instrument_async_function(
        name="github.webhook.handle_pull_request",
        attributes={"service": "github_webhook", "event_type": "pull_request"},
    )
    async def _handle_pull_request_event(self, event: WebhookEvent, project: str) -> list[str]:
        """
        Handle pull_request event.

        Args:
            event: Webhook event
            project: Project name

        Returns:
            List of created command IDs
        """
        # Add PR context to span
        span = self._get_span()
        if span:
            span.set_attribute("github.project", project)
            if "action" in event.payload:
                span.set_attribute("github.action", event.payload["action"])
            if "number" in event.payload:
                span.set_attribute("github.pr_number", event.payload["number"])
        # Placeholder for future implementation
        return []

    @instrument_async_function(
        name="github.webhook.handle_discussion",
        attributes={"service": "github_webhook", "event_type": "discussion"},
    )
    async def _handle_discussion_event(self, event: WebhookEvent, project: str) -> list[str]:
        """
        Handle discussion event.

        Args:
            event: Webhook event
            project: Project name

        Returns:
            List of created command IDs
        """
        # Add discussion context to span
        span = self._get_span()
        if span:
            span.set_attribute("github.project", project)
            if "action" in event.payload:
                span.set_attribute("github.action", event.payload["action"])
        # Placeholder for future implementation
        return []

    async def _identify_project(self, repository: str) -> str | None:
        """
        Map GitHub repository to internal project name.

        Args:
            repository: GitHub repository (format: 'org/repo')

        Returns:
            Project name or None
        """
        projects = await self.config.list_projects()
        for project_config in projects:
            repo_full_name = f"{project_config.github_org}/{project_config.github_repo}"
            if repo_full_name == repository:
                return project_config.id
        return None

    async def _map_column_to_stage(self, project: str, column_id: int) -> StageInfo | None:
        """
        Map GitHub project column ID to pipeline stage.

        Maps GitHub project card column ID to a workflow stage by:
        1. Querying IBoardService to find the column name by ID
        2. Looking up the workflow template to find the agent for that column

        Args:
            project: Project name (ID)
            column_id: GitHub column ID

        Returns:
            Stage information or None if mapping cannot be completed

        Note:
            Requires board_service to be injected. If not available, returns None.
            TODO #370: Implement board ID resolution from GitHub project card events
        """
        if not self.board_service:
            self.logger.warning(
                "Board service not injected; column ID to stage mapping not available "
                "for project %s column %s",
                project,
                column_id,
            )
            return None

        try:
            # TODO #370: Get board ID from project configuration or GitHub event
            # For now, we cannot reliably map GitHub project IDs to our board IDs
            # without additional configuration or the board_id in the webhook event
            self.logger.warning(
                "Column ID to stage mapping requires board_id resolution; "
                "not implemented for project %s column %s. "
                "See #370 for tracking.",
                project,
                column_id,
            )
            return None
        except Exception as e:
            self.logger.warning(
                "Error mapping column %s to stage for project %s: %s",
                column_id,
                project,
                str(e),
                exc_info=True,
            )
            return None

    def _extract_work_item_id(self, content_url: str) -> str | None:
        """
        Extract issue/PR number from GitHub API URL.

        Args:
            content_url: GitHub API URL (e.g., '.../issues/123')

        Returns:
            Work item ID (issue/PR number) or None
        """
        # URL format: https://api.github.com/repos/org/repo/issues/123
        # or: https://api.github.com/repos/org/repo/pulls/456
        if not content_url:
            return None

        parts = content_url.split("/")
        if len(parts) < 2:
            return None

        try:
            return parts[-1]  # Last part is the number
        except (IndexError, ValueError):
            return None
