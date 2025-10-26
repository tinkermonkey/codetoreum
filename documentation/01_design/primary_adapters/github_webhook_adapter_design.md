# GitHub Webhook Adapter Design

## Purpose

The GitHub Webhook Adapter is a primary adapter that receives webhook events from GitHub and translates them into domain commands. It replaces the legacy polling-based `ProjectMonitor` with a more efficient push-based event system.

## Architecture Position

```
┌──────────────┐
│   GitHub     │
│   (External) │
└──────┬───────┘
       │ HTTPS POST
       │ Webhook Event
       ▼
┌──────────────────────────┐
│  GitHub Webhook Adapter  │ ← Primary Adapter
│  (HTTP Endpoint)         │
└──────┬───────────────────┘
       │
       ▼
┌──────────────────────────┐
│     Input Ports          │
│  - WorkflowCommandPort   │
│  - AgentCommandPort      │
│  - EventStreamPort       │
└──────┬───────────────────┘
       │
       ▼
┌──────────────────────────┐
│  Application Services    │
└──────────────────────────┘
```

## Responsibilities

### Primary Responsibilities
1. **Webhook Reception**: Accept HTTP POST requests from GitHub
2. **Signature Verification**: Validate HMAC-SHA256 signatures
3. **Payload Validation**: Verify webhook payload structure
4. **Project Identification**: Map GitHub repository to internal project
5. **Event Translation**: Convert GitHub events to domain commands
6. **Command Execution**: Invoke appropriate input ports
7. **Event Publishing**: Emit domain events for observability

### Non-Responsibilities
- Workflow execution (handled by application services)
- Business logic (handled by domain layer)
- External API calls to GitHub (handled by output adapters)
- Data persistence (handled by infrastructure)

## Interface Design

### External Interface (HTTP)

**Endpoint**: `POST /webhooks/github`

**Headers**:
```http
X-GitHub-Delivery: <unique-delivery-id>
X-GitHub-Event: <event-type>
X-Hub-Signature-256: sha256=<hmac-signature>
Content-Type: application/json
```

**Request Body**: JSON payload (varies by event type)

**Response**:
```http
HTTP/1.1 202 Accepted
Content-Type: application/json

{
  "status": "accepted",
  "delivery_id": "12345-67890",
  "message": "Webhook processed successfully",
  "commands_created": ["cmd-123", "cmd-456"]
}
```

### Port Interface (Domain)

```python
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Dict, Any, List, Optional
from datetime import datetime

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

class IGitHubWebhookPort(ABC):
    """Port interface for GitHub webhook processing"""

    @abstractmethod
    async def receive_webhook(
        self,
        event: WebhookEvent
    ) -> WebhookProcessingResult:
        """
        Process GitHub webhook event and create domain commands.

        Args:
            event: Webhook event to process

        Returns:
            Processing result with created command IDs

        Raises:
            WebhookVerificationError: Invalid signature
            WebhookProcessingError: Processing failed
            UnknownProjectError: Repository not configured
        """
        pass

    @abstractmethod
    async def verify_signature(
        self,
        payload: bytes,
        signature: str
    ) -> bool:
        """
        Verify webhook signature using HMAC-SHA256.

        Args:
            payload: Raw request body
            signature: X-Hub-Signature-256 header value

        Returns:
            True if signature is valid
        """
        pass
```

## Implementation Design

### Class Structure

```python
from fastapi import FastAPI, Request, HTTPException, Header
from typing import Optional
import hmac
import hashlib

class GitHubWebhookAdapter:
    """
    FastAPI-based GitHub webhook adapter.

    Receives webhook events from GitHub and translates them
    into domain commands via input ports.
    """

    def __init__(
        self,
        workflow_command_port: IWorkflowCommandPort,
        agent_command_port: IAgentCommandPort,
        event_stream_port: IEventStreamPort,
        config_service: IConfigurationService,
        logger: ILogger
    ):
        """
        Initialize adapter with dependencies.

        Args:
            workflow_command_port: Port for workflow commands
            agent_command_port: Port for agent commands
            event_stream_port: Port for event publishing
            config_service: Configuration service
            logger: Logging service
        """
        self.workflow_port = workflow_command_port
        self.agent_port = agent_command_port
        self.event_port = event_stream_port
        self.config = config_service
        self.logger = logger

        # Event handlers by GitHub event type
        self.handlers = {
            'project_card': self._handle_project_card_event,
            'issues': self._handle_issues_event,
            'issue_comment': self._handle_issue_comment_event,
            'pull_request': self._handle_pull_request_event,
            'discussion': self._handle_discussion_event
        }

    async def receive_webhook(
        self,
        request: Request,
        x_github_delivery: str = Header(...),
        x_github_event: str = Header(...),
        x_hub_signature_256: str = Header(...)
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
                repository=payload.get('repository', {}).get('full_name', '')
            )

            # 3. Verify signature
            if not await self.verify_signature(payload_bytes, x_hub_signature_256):
                raise WebhookVerificationError("Invalid signature")

            # 4. Validate payload
            if not self._validate_payload(event):
                raise InvalidPayloadError("Malformed payload")

            # 5. Process event
            result = await self._process_event(event)

            # 6. Calculate metrics
            processing_time = (time.time() - start_time) * 1000
            result.processing_time_ms = processing_time

            # 7. Emit observability event
            await self.event_port.publish(WebhookProcessedEvent(
                delivery_id=event.delivery_id,
                event_type=event.event_type,
                repository=event.repository,
                commands_created=result.commands_created,
                processing_time_ms=processing_time
            ))

            # 8. Return success response
            return {
                "status": "accepted",
                "delivery_id": event.delivery_id,
                "message": result.message,
                "commands_created": result.commands_created
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
            await self.event_port.publish(WebhookFailedEvent(
                delivery_id=x_github_delivery,
                error_type=type(e).__name__,
                error_message=str(e)
            ))
            raise HTTPException(status_code=500, detail="Internal error")

    async def verify_signature(
        self,
        payload: bytes,
        signature: str
    ) -> bool:
        """
        Verify HMAC-SHA256 signature from GitHub.

        Args:
            payload: Raw request body bytes
            signature: X-Hub-Signature-256 header (format: 'sha256=<hex>')

        Returns:
            True if signature matches
        """
        # Get webhook secret from configuration
        secret = self.config.get_webhook_secret()
        if not secret:
            self.logger.error("Webhook secret not configured")
            return False

        # Compute expected signature
        expected = hmac.new(
            key=secret.encode('utf-8'),
            msg=payload,
            digestmod=hashlib.sha256
        ).hexdigest()

        # Extract provided signature (remove 'sha256=' prefix)
        provided = signature.replace('sha256=', '')

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
        if 'repository' not in payload:
            return False

        # Event-specific validation
        validators = {
            'project_card': self._validate_project_card_payload,
            'issues': self._validate_issues_payload,
            'issue_comment': self._validate_issue_comment_payload,
            'pull_request': self._validate_pull_request_payload,
            'discussion': self._validate_discussion_payload
        }

        validator = validators.get(event.event_type)
        if validator:
            return validator(payload)

        # Unknown event type - consider valid (ignore)
        return True

    async def _process_event(
        self,
        event: WebhookEvent
    ) -> WebhookProcessingResult:
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
                commands_created=[]
            )

        # Identify project
        project = await self._identify_project(event.repository)
        if not project:
            raise UnknownProjectError(f"Repository {event.repository} not configured")

        # Handle event
        commands = await handler(event, project)

        return WebhookProcessingResult(
            success=True,
            message=f"Processed {event.event_type} event",
            commands_created=[cmd.command_id for cmd in commands]
        )

    async def _handle_project_card_event(
        self,
        event: WebhookEvent,
        project: str
    ) -> List[Command]:
        """
        Handle project_card event (card movement).

        Args:
            event: Webhook event
            project: Project name

        Returns:
            List of created commands
        """
        payload = event.payload
        action = payload.get('action')

        # Only handle 'moved' action
        if action != 'moved':
            return []

        # Extract card details
        card = payload['project_card']
        content_url = card.get('content_url', '')
        column_id = card.get('column_id')

        # Extract issue/PR number from content URL
        work_item_id = self._extract_work_item_id(content_url)
        if not work_item_id:
            self.logger.warning(f"Could not extract work item ID from {content_url}")
            return []

        # Map column ID to stage
        stage_info = await self._map_column_to_stage(project, column_id)
        if not stage_info:
            self.logger.warning(f"Column {column_id} not mapped for project {project}")
            return []

        # Create workflow command
        command = StartWorkflowCommand(
            project_name=project,
            work_item_id=work_item_id,
            pipeline_name=stage_info.pipeline_name,
            stage_name=stage_info.stage_name,
            trigger=TriggerType.CARD_MOVEMENT,
            context={
                'board_name': stage_info.board_name,
                'column_name': stage_info.column_name,
                'previous_column_id': payload.get('changes', {}).get('column_id', {}).get('from'),
                'delivery_id': event.delivery_id
            }
        )

        # Execute command via port
        result = await self.workflow_port.start_workflow(command)

        return [command]

    async def _handle_issue_comment_event(
        self,
        event: WebhookEvent,
        project: str
    ) -> List[Command]:
        """
        Handle issue_comment event (agent feedback).

        Args:
            event: Webhook event
            project: Project name

        Returns:
            List of created commands
        """
        payload = event.payload
        action = payload.get('action')

        # Only handle 'created' action
        if action != 'created':
            return []

        issue = payload['issue']
        comment = payload['comment']

        # Check if this is feedback on agent output
        if not await self._is_agent_feedback(project, issue['number'], comment):
            return []

        # Create agent feedback command
        command = ProvideAgentFeedbackCommand(
            project_name=project,
            work_item_id=str(issue['number']),
            feedback_text=comment['body'],
            feedback_author=comment['user']['login'],
            comment_id=str(comment['id']),
            trigger=TriggerType.AGENT_FEEDBACK
        )

        # Execute command via port
        result = await self.agent_port.provide_feedback(command)

        return [command]

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
            repo_full_name = f"{project_config.github.org}/{project_config.github.repo}"
            if repo_full_name == repository:
                return project
        return None

    async def _map_column_to_stage(
        self,
        project: str,
        column_id: int
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
        for board, board_data in state.get('boards', {}).items():
            for col_name, col_id in board_data.get('columns', {}).items():
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
                            agent_name=col.agent
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

        parts = content_url.split('/')
        if len(parts) < 2:
            return None

        try:
            return parts[-1]  # Last part is the number
        except (IndexError, ValueError):
            return None

    async def _is_agent_feedback(
        self,
        project: str,
        issue_number: int,
        comment: Dict
    ) -> bool:
        """
        Determine if comment is feedback on agent output.

        Args:
            project: Project name
            issue_number: Issue number
            comment: Comment payload

        Returns:
            True if this is agent feedback
        """
        # Check if comment is in reply to an agent comment
        # (This requires additional GitHub API call or session state check)
        # For now, simplified logic:

        # Check conversational session state
        session = await self.agent_port.get_active_session(project, issue_number)
        if session and session.status == 'active':
            # There's an active conversation - this is likely feedback
            return True

        return False

# Supporting data classes
@dataclass
class StageInfo:
    """Information about a pipeline stage"""
    pipeline_name: str
    board_name: str
    stage_name: str
    column_name: str
    agent_name: str
```

## Configuration

### Webhook Configuration
```yaml
# In project configuration
projects:
  my-project:
    github:
      org: "myorg"
      repo: "myrepo"
      webhook:
        secret: "${GITHUB_WEBHOOK_SECRET}"  # From environment
        events:
          - project_card
          - issues
          - issue_comment
          - pull_request
          - discussion
```

### GitHub Webhook Setup
```bash
# Setup webhook in GitHub repository settings:
# Payload URL: https://your-domain.com/webhooks/github
# Content type: application/json
# Secret: <your-webhook-secret>
# Events:
#   - Project cards
#   - Issues
#   - Issue comments
#   - Pull requests
#   - Discussions
```

## Error Handling

### Error Types
```python
class WebhookError(Exception):
    """Base webhook error"""
    pass

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
```

### Error Responses
```json
{
  "error": {
    "type": "WebhookVerificationError",
    "message": "Invalid HMAC signature",
    "delivery_id": "12345-67890",
    "timestamp": "2025-10-26T12:00:00Z"
  }
}
```

## Testing Strategy

### Unit Tests
```python
import pytest
from unittest.mock import Mock, AsyncMock

class TestGitHubWebhookAdapter:
    def setup_method(self):
        self.workflow_port = Mock(IWorkflowCommandPort)
        self.agent_port = Mock(IAgentCommandPort)
        self.event_port = Mock(IEventStreamPort)
        self.config = Mock(IConfigurationService)
        self.logger = Mock(ILogger)

        self.adapter = GitHubWebhookAdapter(
            self.workflow_port,
            self.agent_port,
            self.event_port,
            self.config,
            self.logger
        )

    @pytest.mark.asyncio
    async def test_verify_signature_valid(self):
        """Test HMAC signature verification with valid signature"""
        payload = b'{"test": "data"}'
        secret = "my-secret"
        expected_sig = hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()

        self.config.get_webhook_secret.return_value = secret

        result = await self.adapter.verify_signature(
            payload,
            f"sha256={expected_sig}"
        )

        assert result is True

    @pytest.mark.asyncio
    async def test_verify_signature_invalid(self):
        """Test HMAC signature verification with invalid signature"""
        payload = b'{"test": "data"}'
        self.config.get_webhook_secret.return_value = "my-secret"

        result = await self.adapter.verify_signature(
            payload,
            "sha256=invalid"
        )

        assert result is False

    @pytest.mark.asyncio
    async def test_handle_project_card_moved(self):
        """Test handling project card moved event"""
        event = WebhookEvent(
            delivery_id="test-123",
            event_type="project_card",
            payload={
                "action": "moved",
                "project_card": {
                    "content_url": "https://api.github.com/repos/org/repo/issues/123",
                    "column_id": 456
                },
                "repository": {"full_name": "org/repo"}
            },
            signature="sha256=valid",
            timestamp=datetime.utcnow(),
            repository="org/repo"
        )

        # Mock project identification
        self.config.list_projects = AsyncMock(return_value=["my-project"])
        # Mock column mapping
        # Mock command execution

        result = await self.adapter._process_event(event)

        assert result.success
        assert len(result.commands_created) == 1
```

### Integration Tests
```python
@pytest.mark.integration
class TestGitHubWebhookIntegration:
    @pytest.mark.asyncio
    async def test_end_to_end_webhook_processing(self):
        """Test complete webhook processing flow"""
        # Use real (in-memory) port implementations
        workflow_port = InMemoryWorkflowCommandPort()
        agent_port = InMemoryAgentCommandPort()
        event_port = InMemoryEventStreamPort()
        config = InMemoryConfigurationService()

        adapter = GitHubWebhookAdapter(
            workflow_port,
            agent_port,
            event_port,
            config,
            create_logger()
        )

        # Send webhook
        payload = create_test_webhook_payload("project_card", "moved")
        result = await adapter.receive_webhook(payload)

        # Verify command created
        assert len(workflow_port.commands) == 1
        # Verify event published
        assert len(event_port.events) == 1
```

## Observability

### Metrics
```python
# Prometheus-style metrics
webhook_requests_total = Counter(
    'webhook_requests_total',
    'Total webhook requests received',
    ['event_type', 'status']
)

webhook_processing_duration_seconds = Histogram(
    'webhook_processing_duration_seconds',
    'Webhook processing duration',
    ['event_type']
)

webhook_signature_failures_total = Counter(
    'webhook_signature_failures_total',
    'Signature verification failures'
)
```

### Events
```python
@dataclass
class WebhookReceivedEvent(DomainEvent):
    """Webhook received"""
    delivery_id: str
    event_type: str
    repository: str

@dataclass
class WebhookProcessedEvent(DomainEvent):
    """Webhook processed successfully"""
    delivery_id: str
    event_type: str
    repository: str
    commands_created: List[str]
    processing_time_ms: float

@dataclass
class WebhookFailedEvent(DomainEvent):
    """Webhook processing failed"""
    delivery_id: str
    event_type: str
    error_type: str
    error_message: str
```

## Security Considerations

### HMAC Signature Verification
- Always verify webhook signatures
- Use timing-safe comparison (`hmac.compare_digest`)
- Store webhook secret securely (environment variable)
- Rotate secrets periodically

### Input Validation
- Validate all payload fields before use
- Sanitize string inputs
- Limit payload size (prevent DoS)
- Rate limit by delivery ID/IP

### Error Information Disclosure
- Don't expose internal errors in responses
- Log detailed errors internally
- Return generic error messages externally

## Performance Considerations

### Webhook Processing
- Async/await for non-blocking I/O
- Process webhooks concurrently
- Return 202 Accepted immediately
- Actual processing happens asynchronously

### Caching
- Cache project configurations
- Cache column mappings
- Cache webhook secrets
- Invalidate on configuration changes

### Rate Limiting
- Implement per-repository rate limits
- Use token bucket algorithm
- Reject excessive requests with 429

## Migration from Legacy System

### Legacy Component
- `ProjectMonitor` - Polls GitHub API every 30 seconds
- Redis key: `last_column:{project}:{issue_number}`

### Migration Strategy
1. **Phase 1**: Deploy webhook adapter alongside legacy polling
2. **Phase 2**: Configure GitHub webhooks
3. **Phase 3**: Monitor webhook reliability for 1 week
4. **Phase 4**: Disable polling once webhooks proven stable
5. **Phase 5**: Remove legacy ProjectMonitor code

### Backward Compatibility
- Both systems can run simultaneously
- Webhooks take precedence when available
- Fallback to polling if webhooks fail
- Gradual rollout per project

## Deployment

### Infrastructure Requirements
- HTTP server (FastAPI/Flask)
- Public HTTPS endpoint
- Valid SSL certificate
- Webhook secret storage (env vars)

### GitHub Configuration
```bash
# Using GitHub CLI
gh api \
  --method POST \
  -H "Accept: application/vnd.github+json" \
  /repos/OWNER/REPO/hooks \
  -f name='web' \
  -f config[url]='https://your-domain.com/webhooks/github' \
  -f config[content_type]='json' \
  -f config[secret]='<your-secret>' \
  -F config[insecure_ssl]=0 \
  -f events[]='project_card' \
  -f events[]='issues' \
  -f events[]='issue_comment'
```

## Summary

The GitHub Webhook Adapter provides:
- **Real-time workflow triggering** (replaces 30-second polling)
- **HMAC signature verification** for security
- **Event translation** to domain commands
- **Observability** through metrics and events
- **Testability** through port abstractions
- **Performance** through async processing

This adapter is a critical entry point for the redesigned system, enabling push-based event processing instead of inefficient polling.
