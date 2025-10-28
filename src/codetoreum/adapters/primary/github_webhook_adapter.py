"""
GitHub Webhook Adapter

This module implements the primary adapter for receiving GitHub webhook events
and translating them into domain commands.
"""

import hashlib
import hmac
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional

from fastapi import Header, HTTPException, Request

from codetoreum.domain.events import DomainEvent
from codetoreum.ports.input.workflow_command import (
    IWorkflowCommandPort,
    StartWorkflowCommand,
    TriggerType,
    WorkflowCommandResult,
)


# ============================================================================
# Data Classes
# ============================================================================


@dataclass
class WebhookEvent:
    """Domain representation of webhook event"""

    delivery_id: str
    event_type: str
    payload: Dict[str, Any]
    signature: str
    timestamp: datetime
    repository: str


@dataclass
class WebhookProcessingResult:
    """Result of webhook processing"""

    success: bool
    message: str
    commands_created: List[str]
    errors: Optional[List[str]] = None
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
# Configuration Service Interface
# ============================================================================


class IConfigurationService:
    """Interface for configuration service (temporary until config service is available)"""

    async def get_webhook_secret(self) -> Optional[str]:
        """Get webhook secret for signature verification"""
        raise NotImplementedError

    async def list_projects(self) -> List[str]:
        """List all configured projects"""
        raise NotImplementedError

    async def get_project_config(self, project: str) -> Any:
        """Get project configuration"""
        raise NotImplementedError

    async def load_github_state(self, project: str) -> Optional[Dict[str, Any]]:
        """Load GitHub state (column mappings, etc.)"""
        raise NotImplementedError

    async def get_workflow_template(self, workflow_name: str) -> Any:
        """Get workflow template"""
        raise NotImplementedError


# ============================================================================
# Event Bus Interface
# ============================================================================


class IEventBus:
    """Interface for event bus (temporary until event bus is available)"""

    async def publish(self, event: DomainEvent) -> None:
        """Publish domain event"""
        raise NotImplementedError


# ============================================================================
# Logger Interface
# ============================================================================


class ILogger:
    """Interface for logger"""

    def info(self, message: str) -> None:
        """Log info message"""
        pass

    def warning(self, message: str) -> None:
        """Log warning message"""
        pass

    def error(self, message: str) -> None:
        """Log error message"""
        pass

    def debug(self, message: str) -> None:
        """Log debug message"""
        pass


# ============================================================================
# GitHub Webhook Adapter
# ============================================================================


class GitHubWebhookAdapter:
    """
    FastAPI-based GitHub webhook adapter.

    Receives webhook events from GitHub and translates them
    into domain commands via input ports.
    """

    def __init__(
        self,
        workflow_command_port: IWorkflowCommandPort,
        event_bus: IEventBus,
        config_service: IConfigurationService,
        logger: ILogger,
    ):
        """
        Initialize adapter with dependencies.

        Args:
            workflow_command_port: Port for workflow commands
            event_bus: Event bus for publishing events
            config_service: Configuration service
            logger: Logging service
        """
        self.workflow_port = workflow_command_port
        self.event_bus = event_bus
        self.config = config_service
        self.logger = logger

        # Event handlers by GitHub event type
        self.handlers: Dict[str, Callable] = {
            "project_card": self._handle_project_card_event,
            "issues": self._handle_issues_event,
            "issue_comment": self._handle_issue_comment_event,
            "pull_request": self._handle_pull_request_event,
            "discussion": self._handle_discussion_event,
        }

        # Track processed delivery IDs for idempotency (in-memory for now)
        self._processed_deliveries: Dict[str, WebhookProcessingResult] = {}

    async def receive_webhook(
        self,
        request: Request,
        x_github_delivery: str = Header(...),
        x_github_event: str = Header(...),
        x_hub_signature_256: str = Header(...),
    ) -> Dict[str, Any]:
        """
        FastAPI endpoint handler for webhook reception.

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
        start_time = time.time()

        try:
            # Check for idempotency - if already processed, return cached result
            if x_github_delivery in self._processed_deliveries:
                cached_result = self._processed_deliveries[x_github_delivery]
                self.logger.info(
                    f"Webhook {x_github_delivery} already processed, returning cached result"
                )
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
                timestamp=datetime.utcnow(),
                repository=payload.get("repository", {}).get("full_name", ""),
            )

            # 3. Verify signature
            if not await self.verify_signature(payload_bytes, x_hub_signature_256):
                raise WebhookVerificationError("Invalid HMAC signature")

            # 4. Validate payload
            if not self._validate_payload(event):
                raise InvalidPayloadError("Malformed payload structure")

            # 5. Process event
            result = await self._process_event(event)

            # 6. Calculate metrics
            processing_time = (time.time() - start_time) * 1000
            result.processing_time_ms = processing_time

            # 7. Cache result for idempotency
            self._processed_deliveries[x_github_delivery] = result

            # 8. Emit observability event
            self.logger.info(
                f"Webhook {x_github_delivery} processed successfully in {processing_time:.2f}ms"
            )

            # 9. Return success response
            return {
                "status": "accepted",
                "delivery_id": event.delivery_id,
                "message": result.message,
                "commands_created": result.commands_created,
            }

        except WebhookVerificationError as e:
            self.logger.warning(f"Webhook verification failed: {e}")
            raise HTTPException(status_code=401, detail=str(e))

        except UnknownProjectError as e:
            self.logger.warning(f"Unknown project: {e}")
            raise HTTPException(status_code=404, detail=str(e))

        except InvalidPayloadError as e:
            self.logger.error(f"Invalid payload: {e}")
            raise HTTPException(status_code=400, detail=str(e))

        except Exception as e:
            self.logger.error(f"Webhook processing failed: {e}")
            raise HTTPException(status_code=500, detail="Internal error")

    async def verify_signature(self, payload: bytes, signature: str) -> bool:
        """
        Verify HMAC-SHA256 signature from GitHub.

        Args:
            payload: Raw request body bytes
            signature: X-Hub-Signature-256 header (format: 'sha256=<hex>')

        Returns:
            True if signature matches
        """
        # Get webhook secret from configuration
        secret = await self.config.get_webhook_secret()
        if not secret:
            self.logger.error("Webhook secret not configured")
            return False

        # Compute expected signature
        expected = hmac.new(
            key=secret.encode("utf-8"), msg=payload, digestmod=hashlib.sha256
        ).hexdigest()

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

    def _validate_project_card_payload(self, payload: Dict[str, Any]) -> bool:
        """Validate project_card event payload"""
        return "action" in payload and "project_card" in payload

    def _validate_issues_payload(self, payload: Dict[str, Any]) -> bool:
        """Validate issues event payload"""
        return "action" in payload and "issue" in payload

    def _validate_issue_comment_payload(self, payload: Dict[str, Any]) -> bool:
        """Validate issue_comment event payload"""
        return "action" in payload and "issue" in payload and "comment" in payload

    def _validate_pull_request_payload(self, payload: Dict[str, Any]) -> bool:
        """Validate pull_request event payload"""
        return "action" in payload and "pull_request" in payload

    def _validate_discussion_payload(self, payload: Dict[str, Any]) -> bool:
        """Validate discussion event payload"""
        return "action" in payload and "discussion" in payload

    async def _process_event(self, event: WebhookEvent) -> WebhookProcessingResult:
        """
        Process webhook event and create commands.

        Args:
            event: Webhook event to process

        Returns:
            Processing result
        """
        # Get event handler
        handler = self.handlers.get(event.event_type)
        if not handler:
            # Unsupported event type - ignore gracefully
            return WebhookProcessingResult(
                success=True,
                message=f"Event type {event.event_type} ignored",
                commands_created=[],
            )

        # Identify project
        project = await self._identify_project(event.repository)
        if not project:
            raise UnknownProjectError(
                f"Repository {event.repository} not configured"
            )

        # Handle event
        commands = await handler(event, project)

        return WebhookProcessingResult(
            success=True,
            message=f"Processed {event.event_type} event",
            commands_created=[cmd for cmd in commands],
        )

    async def _handle_project_card_event(
        self, event: WebhookEvent, project: str
    ) -> List[str]:
        """
        Handle project_card event (card movement).

        Args:
            event: Webhook event
            project: Project name

        Returns:
            List of created command IDs
        """
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
            self.logger.warning(f"Could not extract work item ID from {content_url}")
            return []

        # Map column ID to stage
        stage_info = await self._map_column_to_stage(project, column_id)
        if not stage_info:
            self.logger.warning(
                f"Column {column_id} not mapped for project {project}"
            )
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
                "previous_column_id": payload.get("changes", {})
                .get("column_id", {})
                .get("from"),
                "delivery_id": event.delivery_id,
            },
        )

        # Execute command via port
        result = await self.workflow_port.start_workflow(command)

        return [result.workflow_run_id]

    async def _handle_issues_event(
        self, event: WebhookEvent, project: str
    ) -> List[str]:
        """
        Handle issues event (issue created/updated).

        Args:
            event: Webhook event
            project: Project name

        Returns:
            List of created command IDs
        """
        # Placeholder for future implementation
        return []

    async def _handle_issue_comment_event(
        self, event: WebhookEvent, project: str
    ) -> List[str]:
        """
        Handle issue_comment event (agent feedback).

        Args:
            event: Webhook event
            project: Project name

        Returns:
            List of created command IDs
        """
        # Placeholder for future implementation
        return []

    async def _handle_pull_request_event(
        self, event: WebhookEvent, project: str
    ) -> List[str]:
        """
        Handle pull_request event.

        Args:
            event: Webhook event
            project: Project name

        Returns:
            List of created command IDs
        """
        # Placeholder for future implementation
        return []

    async def _handle_discussion_event(
        self, event: WebhookEvent, project: str
    ) -> List[str]:
        """
        Handle discussion event.

        Args:
            event: Webhook event
            project: Project name

        Returns:
            List of created command IDs
        """
        # Placeholder for future implementation
        return []

    async def _identify_project(self, repository: str) -> Optional[str]:
        """
        Map GitHub repository to internal project name.

        Args:
            repository: GitHub repository (format: 'org/repo')

        Returns:
            Project name or None
        """
        projects = await self.config.list_projects()
        for project in projects:
            project_config = await self.config.get_project_config(project)
            # This assumes project_config has github.org and github.repo attributes
            # This will need to be adjusted based on actual config structure
            repo_full_name = f"{project_config.github.org}/{project_config.github.repo}"
            if repo_full_name == repository:
                return project
        return None

    async def _map_column_to_stage(
        self, project: str, column_id: int
    ) -> Optional[StageInfo]:
        """
        Map GitHub project column ID to pipeline stage.

        Args:
            project: Project name
            column_id: GitHub column ID

        Returns:
            Stage information or None
        """
        # Load GitHub state (contains column ID mappings)
        state = await self.config.load_github_state(project)
        if not state:
            return None

        # Find column name by ID
        column_name = None
        board_name = None
        for board, board_data in state.get("boards", {}).items():
            for col_name, col_id in board_data.get("columns", {}).items():
                if col_id == column_id:
                    column_name = col_name
                    board_name = board
                    break

        if not column_name:
            return None

        # Get project configuration
        project_config = await self.config.get_project_config(project)

        # Find pipeline for this board
        for pipeline in project_config.pipelines:
            if pipeline.board_name == board_name:
                # Get workflow template
                workflow = await self.config.get_workflow_template(pipeline.workflow)

                # Find column in workflow
                for col in workflow.columns:
                    if col.name == column_name:
                        return StageInfo(
                            pipeline_name=pipeline.name,
                            board_name=board_name,
                            stage_name=col.name,
                            column_name=col.name,
                            agent_name=col.agent,
                        )

        return None

    def _extract_work_item_id(self, content_url: str) -> Optional[str]:
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
