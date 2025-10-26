# GitHub Webhook Input Port Design

## Purpose

The GitHub Webhook Port receives and processes webhook events from GitHub, translating them into domain commands that trigger workflow executions.

## Port Interface

```python
from abc import ABC, abstractmethod
from typing import Dict, Any, Optional
from dataclasses import dataclass

@dataclass
class WebhookEvent:
    """Represents a GitHub webhook event"""
    event_type: str  # 'push', 'pull_request', 'issues', 'project_card'
    delivery_id: str  # Unique webhook delivery ID
    signature: str  # HMAC signature for verification
    payload: Dict[str, Any]  # Raw webhook payload
    timestamp: datetime

@dataclass
class WebhookProcessingResult:
    """Result of processing a webhook"""
    success: bool
    message: str
    commands_created: List[str]  # IDs of commands created
    errors: Optional[List[str]] = None

class IGitHubWebhookPort(ABC):
    """Input port for GitHub webhooks"""

    @abstractmethod
    async def receive_webhook(
        self,
        event: WebhookEvent
    ) -> WebhookProcessingResult:
        """
        Receives and processes a GitHub webhook event.

        Args:
            event: The webhook event to process

        Returns:
            Result of webhook processing including any commands created

        Raises:
            WebhookVerificationError: If signature verification fails
            WebhookProcessingError: If event processing fails
        """
        pass

    @abstractmethod
    async def verify_signature(
        self,
        payload: bytes,
        signature: str
    ) -> bool:
        """
        Verifies the webhook signature using the shared secret.

        Args:
            payload: Raw request payload
            signature: HMAC signature from GitHub

        Returns:
            True if signature is valid, False otherwise
        """
        pass
```

## Supported GitHub Events

### 1. Project Card Events
**Trigger**: Card moved between columns on GitHub Project board

**Event Payload Structure**:
```json
{
  "action": "moved",
  "project_card": {
    "id": 12345,
    "note": null,
    "content_url": "https://api.github.com/repos/org/repo/issues/123"
  },
  "changes": {
    "column_id": {
      "from": 67890
    }
  },
  "project_card": {
    "column_id": 11111
  },
  "repository": {
    "name": "repo",
    "full_name": "org/repo"
  }
}
```

**Port Processing**:
1. Extract issue/PR number from content_url
2. Determine source and destination columns
3. Identify project and pipeline
4. Create WorkflowCommand to start appropriate agent
5. Emit domain event: CardMovedEvent

**Domain Command Generated**:
```python
StartWorkflowCommand(
    project_name="project-name",
    work_item_id="123",
    pipeline_name="dev-pipeline",
    stage_name="requirements-analysis",
    trigger=TriggerType.CARD_MOVEMENT,
    context={
        'previous_column': 'Backlog',
        'current_column': 'Requirements Analysis',
        'board_name': 'Development'
    }
)
```

### 2. Issue Events
**Trigger**: Issue created, updated, or commented

**Event Payload Structure**:
```json
{
  "action": "opened",
  "issue": {
    "number": 123,
    "title": "Feature request",
    "body": "Description...",
    "labels": [{"name": "enhancement"}],
    "user": {"login": "username"}
  },
  "repository": {
    "name": "repo",
    "full_name": "org/repo"
  }
}
```

**Port Processing**:
1. Determine if this is a new work item or update
2. Check for agent questions/feedback
3. Identify relevant project configuration
4. Create appropriate command based on action

**Domain Commands Generated**:
- For "opened": `CreateWorkItemCommand`
- For "comment": `ProvideAgentFeedbackCommand` (if comment is on agent output)

### 3. Pull Request Events
**Trigger**: PR opened, updated, or reviewed

**Event Payload Structure**:
```json
{
  "action": "opened",
  "pull_request": {
    "number": 456,
    "title": "Add feature X",
    "body": "Implementation of...",
    "base": {"ref": "main"},
    "head": {"ref": "feature/issue-123"}
  },
  "repository": {
    "name": "repo",
    "full_name": "org/repo"
  }
}
```

**Port Processing**:
1. Extract PR details
2. Link to originating issue if present
3. Determine review workflow stage
4. Create review command

**Domain Command Generated**:
```python
StartReviewWorkflowCommand(
    project_name="project-name",
    pull_request_number="456",
    source_branch="feature/issue-123",
    target_branch="main"
)
```

### 4. Discussion Events
**Trigger**: Discussion created or commented

**Event Payload Structure**:
```json
{
  "action": "created",
  "discussion": {
    "id": "D_kwDOABCDEF01",
    "number": 789,
    "title": "Architecture decision",
    "body": "Should we use...",
    "category": {"name": "Q&A"}
  },
  "repository": {
    "name": "repo",
    "full_name": "org/repo"
  }
}
```

**Port Processing**:
1. Identify workspace type (discussions)
2. Determine appropriate agent based on category
3. Create workflow command for discussion-based work

## Input Validation

### Signature Verification
```python
def verify_signature(payload: bytes, signature: str) -> bool:
    """
    Verifies GitHub webhook signature using HMAC-SHA256.

    Expected signature format: 'sha256=<hexdigest>'
    """
    secret = get_webhook_secret()  # From configuration
    expected = hmac.new(
        secret.encode(),
        payload,
        hashlib.sha256
    ).hexdigest()

    provided = signature.replace('sha256=', '')
    return hmac.compare_digest(expected, provided)
```

### Payload Validation
```python
class WebhookPayloadValidator:
    """Validates webhook payload structure"""

    def validate_project_card_event(self, payload: Dict) -> ValidationResult:
        """Validates project card event payload"""
        required_fields = [
            'action',
            'project_card.content_url',
            'project_card.column_id',
            'repository.full_name'
        ]
        # Check all required fields present
        # Validate data types
        # Verify column IDs exist in configuration

    def validate_issue_event(self, payload: Dict) -> ValidationResult:
        """Validates issue event payload"""
        required_fields = [
            'action',
            'issue.number',
            'issue.title',
            'repository.full_name'
        ]
        # Validation logic...
```

## Event Routing Logic

### Project Identification
```python
def identify_project(repository_full_name: str) -> Optional[str]:
    """
    Maps GitHub repository to internal project name.

    Args:
        repository_full_name: GitHub repo in 'org/repo' format

    Returns:
        Internal project name or None if not found
    """
    # Query configuration for matching repository
    # Return configured project name
```

### Column to Stage Mapping
```python
def map_column_to_stage(
    project: str,
    board_name: str,
    column_name: str
) -> Optional[StageInfo]:
    """
    Maps GitHub project board column to pipeline stage.

    Returns:
        StageInfo containing pipeline, stage, and agent details
    """
    # Load project configuration
    # Find matching pipeline by board name
    # Find workflow column definition
    # Return stage and agent info
```

### Trigger Classification
```python
def classify_trigger(
    event_type: str,
    action: str,
    payload: Dict
) -> TriggerType:
    """
    Classifies webhook event into internal trigger type.

    Returns:
        TriggerType enum value
    """
    if event_type == 'project_card' and action == 'moved':
        return TriggerType.CARD_MOVEMENT
    elif event_type == 'issues' and action == 'opened':
        return TriggerType.WORK_ITEM_CREATED
    elif event_type == 'issue_comment':
        # Check if comment is on agent output
        if is_agent_feedback(payload):
            return TriggerType.AGENT_FEEDBACK
        return TriggerType.HUMAN_COMMENT
    # ... more classifications
```

## Error Handling

### Error Types
```python
class WebhookError(Exception):
    """Base class for webhook errors"""
    pass

class WebhookVerificationError(WebhookError):
    """Raised when signature verification fails"""
    pass

class WebhookProcessingError(WebhookError):
    """Raised when event processing fails"""
    pass

class UnknownProjectError(WebhookError):
    """Raised when repository is not configured"""
    pass

class InvalidPayloadError(WebhookError):
    """Raised when payload is malformed"""
    pass
```

### Error Response
```python
@dataclass
class ErrorResponse:
    """Response for webhook errors"""
    status_code: int
    error_type: str
    message: str
    details: Optional[Dict[str, Any]] = None

# Example responses:
# 401 Unauthorized - Signature verification failed
# 400 Bad Request - Invalid payload structure
# 404 Not Found - Project not configured
# 500 Internal Server Error - Processing failed
```

## Adapter Implementation

### HTTP Webhook Adapter
```python
class GitHubWebhookHTTPAdapter(IGitHubWebhookPort):
    """HTTP adapter for GitHub webhooks (FastAPI/Flask)"""

    def __init__(
        self,
        workflow_service: IWorkflowService,
        config_service: IConfigurationService,
        event_bus: IEventBus
    ):
        self.workflow_service = workflow_service
        self.config_service = config_service
        self.event_bus = event_bus

    async def receive_webhook(
        self,
        event: WebhookEvent
    ) -> WebhookProcessingResult:
        """Process webhook and create domain commands"""

        # 1. Verify signature
        if not await self.verify_signature(event.payload, event.signature):
            raise WebhookVerificationError("Invalid signature")

        # 2. Validate payload
        validator = WebhookPayloadValidator()
        validation = validator.validate(event.event_type, event.payload)
        if not validation.valid:
            raise InvalidPayloadError(validation.errors)

        # 3. Identify project
        repo = event.payload['repository']['full_name']
        project = self.identify_project(repo)
        if not project:
            raise UnknownProjectError(f"Repository {repo} not configured")

        # 4. Route event to appropriate handler
        handler = self.get_handler(event.event_type)
        commands = await handler.handle(event, project)

        # 5. Execute commands via application service
        results = []
        for cmd in commands:
            result = await self.workflow_service.execute_command(cmd)
            results.append(result.command_id)

        # 6. Emit domain event
        await self.event_bus.publish(
            WebhookProcessedEvent(
                event_id=event.delivery_id,
                event_type=event.event_type,
                project=project,
                commands_created=results
            )
        )

        return WebhookProcessingResult(
            success=True,
            message=f"Processed {event.event_type} event",
            commands_created=results
        )
```

## Simulation/Test Implementation

### Mock Webhook Adapter
```python
class MockGitHubWebhookPort(IGitHubWebhookPort):
    """Mock implementation for testing"""

    def __init__(self):
        self.received_events: List[WebhookEvent] = []
        self.verification_result = True

    async def receive_webhook(
        self,
        event: WebhookEvent
    ) -> WebhookProcessingResult:
        """Store event and return canned response"""
        self.received_events.append(event)

        return WebhookProcessingResult(
            success=True,
            message="Mock processing successful",
            commands_created=["mock-cmd-123"]
        )

    async def verify_signature(
        self,
        payload: bytes,
        signature: str
    ) -> bool:
        """Return configured verification result"""
        return self.verification_result

    def simulate_card_move(
        self,
        project: str,
        issue_number: int,
        from_column: str,
        to_column: str
    ):
        """Helper to simulate card movement"""
        event = WebhookEvent(
            event_type='project_card',
            delivery_id=str(uuid.uuid4()),
            signature='sha256=valid',
            payload={
                'action': 'moved',
                'project_card': {
                    'content_url': f'https://api.github.com/repos/org/{project}/issues/{issue_number}'
                },
                'changes': {'column_id': {'from': 1}},
                'repository': {'full_name': f'org/{project}'}
            },
            timestamp=datetime.utcnow()
        )
        return self.receive_webhook(event)
```

## Configuration

### Webhook Configuration
```yaml
# Project configuration
projects:
  my-project:
    github:
      org: "myorg"
      repo: "myrepo"
      webhook:
        secret: "${GITHUB_WEBHOOK_SECRET}"
        events:
          - project_card
          - issues
          - issue_comment
          - pull_request
          - discussion

    # Column to stage mappings
    pipelines:
      - board_name: "Development"
        workflow: "dev_workflow"
        columns:
          - name: "Requirements Analysis"
            agent: "business_analyst"
          - name: "Implementation"
            agent: "senior_software_engineer"
```

## Observability

### Events Emitted
```python
# When webhook received
WebhookReceivedEvent(
    delivery_id=str,
    event_type=str,
    repository=str,
    timestamp=datetime
)

# When webhook processed
WebhookProcessedEvent(
    delivery_id=str,
    event_type=str,
    project=str,
    commands_created=List[str],
    processing_time_ms=float
)

# When webhook fails
WebhookFailedEvent(
    delivery_id=str,
    event_type=str,
    error_type=str,
    error_message=str
)
```

### Metrics
- Webhooks received (count, by event type)
- Webhooks processed successfully (count, duration)
- Webhooks failed (count, by error type)
- Signature verification failures (count)
- Unknown repositories (count)

## Security Considerations

### Authentication
- All webhooks MUST have valid HMAC signature
- Webhook secret stored securely (environment variable)
- Signature comparison uses timing-safe comparison

### Authorization
- Only configured repositories accepted
- Project configuration determines allowed actions
- Rate limiting applied per repository

### Input Sanitization
- All payload data validated before use
- No execution of user-provided code
- SQL injection prevention (parameterized queries)
- XSS prevention (output encoding)

## Dependencies

### Domain Services
- `IWorkflowService`: Execute workflow commands
- `IConfigurationService`: Load project configuration
- `IEventBus`: Publish domain events

### Infrastructure
- HTTP server (FastAPI/Flask)
- HMAC library for signature verification
- JSON parser for payload processing

## Testing Strategy

### Unit Tests
- Signature verification logic
- Payload validation
- Event routing classification
- Error handling

### Integration Tests
- End-to-end webhook processing
- Command creation verification
- Event emission verification

### Simulation Tests
- Mock webhook events
- Verify correct commands created
- Test all supported event types

## Migration Notes

### From Legacy System
The legacy system uses:
- `ProjectMonitor.monitor_projects()` - Polls GitHub API every 30 seconds
- Redis tracking of `last_column:{project}:{issue_number}`

The new design:
- Uses push-based webhooks (no polling)
- Events processed in real-time
- No Redis state needed for change detection
- More efficient and responsive
