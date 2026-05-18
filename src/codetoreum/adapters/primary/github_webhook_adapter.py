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

from codetoreum.domain.events.adapter_events import now_iso
from codetoreum.domain.events.board_events import WorkItemColumnChangedEvent
from codetoreum.domain.events.discussion_events import Comment, CommentContext, CommentNeedsResponseEvent
from codetoreum.domain.events.review_events import ReviewStatusChangedEvent
from codetoreum.infrastructure.error_ids import ErrorRegistry
from codetoreum.infrastructure.event_bus import EventBus
from codetoreum.infrastructure.observability.instrumentation import (
    instrument_async_function,
)
from codetoreum.ports.input.issue_intake import IIssueIntakePort, IssueOpenedCommand
from codetoreum.ports.input.workflow_command import IWorkflowCommandPort
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
        issue_intake_port: IIssueIntakePort | None = None,
    ):
        """
        Initialize adapter with dependencies.

        Args:
            workflow_command_port: Port for workflow commands
            event_bus: Event bus for publishing events
            config_service: Configuration service
            logger: Logging service
            idempotency_cache_size: Maximum size of idempotency cache (bounded, with LRU eviction)
            issue_intake_port: Optional issue intake port for handling opened issues
        """
        self.workflow_port = workflow_command_port
        self.event_bus = event_bus
        self.config = config_service
        self.logger = logger
        self.issue_intake_port = issue_intake_port
        self._idempotency_cache_size = idempotency_cache_size

        # Event handlers by GitHub event type
        # Note: issue_comment, pull_request, and discussion_comment handlers were implemented in issue #888.
        # The issues handler (_handle_issues_event) was pre-existing and handles opened issues.
        # The discussion_comment event type (not "discussion") carries comment payloads for discussion comments.
        self.handlers: dict[str, Callable] = {
            "project_card": self._handle_project_card_event,
            "issues": self._handle_issues_event,
            "issue_comment": self._handle_issue_comment_event,
            "pull_request": self._handle_pull_request_event,
            "discussion_comment": self._handle_discussion_event,
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
                "Webhook secret not configured for project %s; " "signature verification cannot proceed",
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
            "discussion_comment": self._validate_discussion_payload,
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
        return "action" in payload and "discussion" in payload and "comment" in payload

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
                message=f"Event type {event.event_type} ignored",
                commands_created=[],
            )

        # Handle event (project_id already resolved, avoid re-lookup)
        commands = await handler(event, project_id)

        return WebhookProcessingResult(
            success=True,
            message=f"Processed {event.event_type} event",
            commands_created=[cmd for cmd in commands],
        )

    @instrument_async_function(
        name="github.webhook.handle_project_card",
        attributes={"service": "github_webhook", "event_type": "project_card"},
    )
    async def _handle_project_card_event(self, event: WebhookEvent, project: str) -> list[str]:
        """
        Handle project_card event (card movement).

        Emits WorkItemColumnChangedEvent when a card moves to a new column.
        The event is processed by BoardColumnEventHandler for workflow automation.

        Args:
            event: Webhook event
            project: Project name (project_id in domain)

        Returns:
            List of created event IDs
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

        # Resolve column_id to column_name
        # The column_id is a numeric GitHub Projects column identifier that must be resolved
        # to a column name that matches the board workflow template.
        column_name = await self._resolve_column_id_to_name(project, column_id)
        if not column_name:
            self.logger.warning(
                "Could not resolve column_id %s for project %s; card movement will not trigger automation",
                column_id,
                project,
                extra={
                    "error_id": ErrorRegistry.ERR_WEBHOOK_COLUMN_RESOLUTION_FAILED,
                    "project_id": project,
                    "column_id": column_id,
                    "work_item_id": work_item_id,
                },
            )
            return []

        # Get previous column name if available
        previous_column_id = (
            payload.get("changes", {}).get("column_id", {}).get("from")
            if payload.get("changes", {}).get("column_id", {}).get("from")
            else None
        )
        previous_column_name = None
        if previous_column_id:
            previous_column_name = await self._resolve_column_id_to_name(project, previous_column_id)

        # Create and emit WorkItemColumnChangedEvent
        try:
            domain_event = WorkItemColumnChangedEvent(
                type="workitem.column_changed",
                timestamp=now_iso(),
                source="github",
                work_item_id=work_item_id,
                project_id=project,
                board_id=project,  # Using project as board_id (GitHub Projects are per-repository)
                from_column=previous_column_name,
                to_column=column_name,
                moved_by="human",  # Card moved by human via GitHub UI
            )
        except ValueError as e:
            self.logger.warning("Failed to create WorkItemColumnChangedEvent: %s", str(e), exc_info=True)
            return []

        # Publish event to event bus
        try:
            await self.event_bus.publish(domain_event)
            self.logger.info(
                "Emitted WorkItemColumnChangedEvent for work_item %s: %s -> %s",
                work_item_id,
                previous_column_name,
                column_name,
            )
            return [domain_event.event_id]
        except Exception as e:
            self.logger.error(
                "Failed to publish WorkItemColumnChangedEvent: %s",
                str(e),
                exc_info=True,
                extra={"error_id": ErrorRegistry.ERR_INTERNAL_ERROR},
            )
            return []

    @instrument_async_function(
        name="github.webhook.handle_issues",
        attributes={"service": "github_webhook", "event_type": "issues"},
    )
    async def _handle_issues_event(self, event: WebhookEvent, project: str) -> list[str]:
        """
        Handle issues event (issue created/updated).

        When an issue is opened, delegates to the issue intake port to place it
        in the initial column on a board, which triggers a WorkItemColumnChangedEvent
        for orchestration.

        Args:
            event: Webhook event
            project: Project name

        Returns:
            List of created work item IDs
        """
        # Add issue context to span
        span = self._get_span()
        if span:
            span.set_attribute("github.project", project)
            if "action" in event.payload:
                span.set_attribute("github.action", event.payload["action"])

        payload = event.payload
        action = payload.get("action")

        # Only handle 'opened' action
        if action != "opened":
            return []

        # Extract issue information
        issue = payload.get("issue", {})
        issue_number = str(issue.get("number", ""))
        issue_title = issue.get("title")
        issue_url = issue.get("html_url")

        if not issue_number:
            self.logger.warning("Could not extract issue number from payload")
            return []

        # If issue intake port not available, we can't process the issue
        if not self.issue_intake_port:
            self.logger.warning("Issue intake port not injected; cannot place opened issue %s on board", issue_number)
            return []

        # Delegate to issue intake service via input port
        command = IssueOpenedCommand(
            project_id=project,
            issue_number=issue_number,
            issue_title=issue_title,
            issue_url=issue_url,
        )

        try:
            result = await self.issue_intake_port.on_issue_opened(command)

            if result.success:
                return [result.work_item_id]
            self.logger.warning("Failed to intake issue %s: %s", issue_number, result.message)
            return []
        except Exception as e:
            self.logger.error(
                "Failed to open issue %s: %s",
                issue_number,
                str(e),
                exc_info=True,
                extra={"error_id": ErrorRegistry.ERR_INTERNAL_ERROR},
            )
            return []

    @instrument_async_function(
        name="github.webhook.handle_issue_comment",
        attributes={"service": "github_webhook", "event_type": "issue_comment"},
    )
    async def _handle_issue_comment_event(self, event: WebhookEvent, project: str) -> list[str]:
        """
        Handle issue_comment event (comments requiring agent response).

        When a comment is created on an issue, emits CommentNeedsResponseEvent
        to trigger the conversational loop orchestrator to generate a response.

        Args:
            event: Webhook event
            project: Project name

        Returns:
            List of created event IDs
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

        payload = event.payload
        action = payload.get("action")

        # Only handle 'created' action
        if action != "created":
            return []

        # Extract issue and comment information
        issue = payload.get("issue", {})
        comment = payload.get("comment", {})
        issue_number = str(issue.get("number", ""))

        if not issue_number or not comment:
            self.logger.warning("Could not extract issue number or comment from payload")
            return []

        # Build Comment object from GitHub comment data
        try:
            comment_obj = Comment(
                id=str(comment.get("id", "")),
                author=comment.get("user", {}).get("login", "unknown"),
                body=comment.get("body", ""),
                created_at=comment.get("created_at", datetime.now(UTC).isoformat()),
                is_bot=comment.get("user", {}).get("type") == "Bot",
            )
        except ValueError as e:
            self.logger.warning("Failed to create Comment object: %s", str(e), exc_info=True)
            return []

        # Skip bot-authored comments to prevent infinite feedback loops
        if comment_obj.is_bot:
            return []

        # Create CommentNeedsResponseEvent with context
        try:
            domain_event = CommentNeedsResponseEvent(
                type="comment.needs_response",
                timestamp=now_iso(),
                source="github",
                work_item_id=issue_number,
                project_id=project,
                comment=comment_obj,
                context=CommentContext.for_initial_request(),
            )
        except ValueError as e:
            self.logger.warning("Failed to create CommentNeedsResponseEvent: %s", str(e), exc_info=True)
            return []

        # Emit event to event bus
        try:
            await self.event_bus.publish(domain_event)
            self.logger.info(
                "Emitted CommentNeedsResponseEvent for issue %s comment %s",
                issue_number,
                comment_obj.id,
            )
            return [domain_event.event_id]
        except Exception as e:
            self.logger.error(
                "Failed to publish CommentNeedsResponseEvent: %s",
                str(e),
                exc_info=True,
                extra={"error_id": ErrorRegistry.ERR_INTERNAL_ERROR},
            )
            return []

    @instrument_async_function(
        name="github.webhook.handle_pull_request",
        attributes={"service": "github_webhook", "event_type": "pull_request"},
    )
    async def _handle_pull_request_event(self, event: WebhookEvent, project: str) -> list[str]:
        """
        Handle pull_request event (review status tracking).

        When a PR is opened, closed, merged, or reviewed, emits ReviewStatusChangedEvent
        to track code review lifecycle changes.

        Args:
            event: Webhook event
            project: Project name

        Returns:
            List of created event IDs
        """
        # Add PR context to span
        span = self._get_span()
        if span:
            span.set_attribute("github.project", project)
            if "action" in event.payload:
                span.set_attribute("github.action", event.payload["action"])
            if "number" in event.payload:
                span.set_attribute("github.pr_number", event.payload["number"])

        payload = event.payload
        action = payload.get("action")
        pr = payload.get("pull_request", {})
        pr_number = str(pr.get("number", ""))

        if not pr_number:
            self.logger.warning("Could not extract PR number from payload")
            return []

        # Map GitHub PR action to review status
        # Relevant actions: opened, closed, reopened, synchronize, ready_for_review, converted_to_draft
        # We focus on status-change actions
        status_mapping = {
            "opened": "open",
            "reopened": "open",
            "closed": "closed",
            "ready_for_review": "open",
            "converted_to_draft": "open",
        }

        if action not in status_mapping:
            # Ignore other actions (e.g., "synchronize" which is for new commits)
            return []

        new_status = status_mapping[action]

        # Determine previous status for state transitions
        # Note: GitHub doesn't always provide previous_status, so we infer from current state
        pr_merged = pr.get("merged", False)

        # Infer previous status based on action
        # When PR is reopened, previous status is closed (you can only reopen a closed PR)
        # For other status changes, default to open
        if action == "reopened":
            previous_status = "closed"
        else:
            previous_status = "open"

        # Handle merged status override (only when closed AND merged)
        if action == "closed" and pr_merged:
            new_status = "merged"

        # Extract reviewer info - use the person who performed the action (sender)
        # For opened events, there is no reviewer yet; for other actions, use the actor
        if action == "opened":
            reviewer = None
        else:
            reviewer = payload.get("sender", {}).get("login")

        # Create ReviewStatusChangedEvent
        try:
            domain_event = ReviewStatusChangedEvent(
                type="review.status_changed",
                timestamp=now_iso(),
                source="github",
                review_id=pr_number,
                work_item_id=pr_number,  # Link PR to work item with same number
                project_id=project,
                previous_status=previous_status,
                new_status=new_status,
                reviewer=reviewer,
            )
        except ValueError as e:
            self.logger.warning("Failed to create ReviewStatusChangedEvent: %s", str(e), exc_info=True)
            return []

        # Emit event to event bus
        try:
            await self.event_bus.publish(domain_event)
            self.logger.info(
                "Emitted ReviewStatusChangedEvent for PR %s: %s → %s",
                pr_number,
                previous_status,
                new_status,
            )
            return [domain_event.event_id]
        except Exception as e:
            self.logger.error(
                "Failed to publish ReviewStatusChangedEvent: %s",
                str(e),
                exc_info=True,
                extra={"error_id": ErrorRegistry.ERR_INTERNAL_ERROR},
            )
            return []

    @instrument_async_function(
        name="github.webhook.handle_discussion_comment",
        attributes={"service": "github_webhook", "event_type": "discussion_comment"},
    )
    async def _handle_discussion_event(self, event: WebhookEvent, project: str) -> list[str]:
        """
        Handle discussion_comment event (comments on discussions requiring agent response).

        When a comment is created on a discussion, emits CommentNeedsResponseEvent
        to trigger the conversational loop orchestrator to generate a response.

        GitHub delivers discussion comments via the 'discussion_comment' event type,
        which has the comment data at the top level of the payload.

        Args:
            event: Webhook event
            project: Project name

        Returns:
            List of created event IDs
        """
        # Add discussion context to span
        span = self._get_span()
        if span:
            span.set_attribute("github.project", project)
            if "action" in event.payload:
                span.set_attribute("github.action", event.payload["action"])

        payload = event.payload
        action = payload.get("action")
        discussion = payload.get("discussion", {})
        discussion_number = str(discussion.get("number", ""))

        if not discussion_number:
            self.logger.warning("Could not extract discussion number from payload")
            return []

        # Only handle 'created' action (for new discussion or new comments)
        if action != "created":
            return []

        # Extract comment information from discussion
        # Note: Discussion webhook includes comment data if action is on a comment
        comment_data = payload.get("comment")
        if not comment_data:
            # Action on discussion itself (e.g., discussion created), skip
            self.logger.debug("Ignoring discussion event action '%s' without comment data", action)
            return []

        # Build Comment object from GitHub discussion comment data
        try:
            comment_obj = Comment(
                id=str(comment_data.get("id", "")),
                author=comment_data.get("user", {}).get("login", "unknown"),
                body=comment_data.get("body", ""),
                created_at=comment_data.get("created_at", datetime.now(UTC).isoformat()),
                is_bot=comment_data.get("user", {}).get("type") == "Bot",
            )
        except ValueError as e:
            self.logger.warning("Failed to create Comment object from discussion: %s", str(e), exc_info=True)
            return []

        # Skip bot-authored comments to prevent infinite feedback loops
        if comment_obj.is_bot:
            return []

        # Create CommentNeedsResponseEvent
        try:
            domain_event = CommentNeedsResponseEvent(
                type="comment.needs_response",
                timestamp=now_iso(),
                source="github",
                work_item_id=discussion_number,
                project_id=project,
                comment=comment_obj,
                context=CommentContext.for_initial_request(),
            )
        except ValueError as e:
            self.logger.warning("Failed to create CommentNeedsResponseEvent: %s", str(e), exc_info=True)
            return []

        # Emit event to event bus
        try:
            await self.event_bus.publish(domain_event)
            self.logger.info(
                "Emitted CommentNeedsResponseEvent for discussion %s comment %s",
                discussion_number,
                comment_obj.id,
            )
            return [domain_event.event_id]
        except Exception as e:
            self.logger.error(
                "Failed to publish CommentNeedsResponseEvent from discussion: %s",
                str(e),
                exc_info=True,
                extra={"error_id": ErrorRegistry.ERR_INTERNAL_ERROR},
            )
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

    async def _resolve_column_id_to_name(self, project_id: str, column_id: int) -> str | None:
        """
        Resolve GitHub Projects column ID to column name.

        Attempts to resolve the numeric column ID to a human-readable column name
        using the project configuration's board column mapping. The mapping should be
        stored in the project configuration metadata.

        Args:
            project_id: Project ID
            column_id: GitHub Projects numeric column ID

        Returns:
            Column name string, or None if mapping not found or resolution fails
        """
        if column_id is None:
            return None

        try:
            project_config = await self.config.get_project_config(project_id)
            if not project_config:
                self.logger.warning("Project config not found for %s", project_id)
                return None

            # Try to find column mapping in project metadata
            # Expected format: metadata.board_columns = {column_id: "column_name", ...}
            board_columns = project_config.metadata.get("board_columns", {})
            column_name = board_columns.get(str(column_id))

            if column_name:
                return column_name

            # If mapping not found, log warning but don't fail hard
            self.logger.warning(
                "Column ID mapping not found for column_id=%s in project %s. "
                "Please configure board_columns mapping in project configuration metadata.",
                column_id,
                project_id,
                extra={
                    "error_id": ErrorRegistry.ERR_WEBHOOK_COLUMN_MAPPING_NOT_FOUND,
                    "project_id": project_id,
                    "column_id": column_id,
                },
            )
            return None

        except Exception as e:
            self.logger.error(
                "Error resolving column ID %s for project %s: %s",
                column_id,
                project_id,
                str(e),
                exc_info=True,
                extra={
                    "error_id": ErrorRegistry.ERR_WEBHOOK_COLUMN_RESOLUTION_ERROR,
                    "project_id": project_id,
                    "column_id": column_id,
                },
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
