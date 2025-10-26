# Agent Interaction Command Input Port Design

## Purpose

The Agent Interaction Command Port enables human users to interact with agents during workflow execution, including asking questions, providing feedback, approving/rejecting work, and requesting revisions.

## Port Interface

```python
from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, List
from dataclasses import dataclass
from enum import Enum

class InteractionType(Enum):
    """Type of agent interaction"""
    QUESTION = "question"
    FEEDBACK = "feedback"
    APPROVAL = "approval"
    REJECTION = "rejection"
    REVISION_REQUEST = "revision_request"

@dataclass
class AskQuestionCommand:
    """Command to ask an agent a question"""
    project_name: str
    work_item_id: str
    agent_name: str
    question: str
    conversation_id: Optional[str] = None  # For threaded conversations
    user_id: str = None  # Who asked the question

@dataclass
class ProvideFeedbackCommand:
    """Command to provide feedback on agent output"""
    project_name: str
    work_item_id: str
    agent_name: str
    agent_execution_id: str  # Specific execution to provide feedback on
    feedback: str
    feedback_type: str = "general"  # general, technical, process
    user_id: str = None

@dataclass
class ApproveWorkCommand:
    """Command to approve agent's work"""
    project_name: str
    work_item_id: str
    agent_name: str
    agent_execution_id: str
    approval_note: Optional[str] = None
    auto_advance: bool = True  # Move to next stage?
    user_id: str = None

@dataclass
class RejectWorkCommand:
    """Command to reject agent's work"""
    project_name: str
    work_item_id: str
    agent_name: str
    agent_execution_id: str
    rejection_reason: str
    required_changes: List[str]  # Specific changes needed
    user_id: str = None

@dataclass
class RequestRevisionCommand:
    """Command to request revision of agent's work"""
    project_name: str
    work_item_id: str
    agent_name: str
    agent_execution_id: str
    revision_instructions: str
    specific_issues: List[Dict[str, str]]  # [{title, description}]
    user_id: str = None

@dataclass
class InteractionResult:
    """Result of agent interaction command"""
    success: bool
    interaction_id: str
    agent_response_id: Optional[str] = None  # If agent responded immediately
    queued_for_response: bool = False  # If agent will respond async
    message: str = ""
    errors: Optional[List[str]] = None

class IAgentInteractionCommandPort(ABC):
    """Input port for agent interaction commands"""

    @abstractmethod
    async def ask_question(
        self,
        command: AskQuestionCommand
    ) -> InteractionResult:
        """
        Asks an agent a question about their work.

        Creates a conversational interaction where the agent
        will respond to the question in context of current work.

        Args:
            command: Question command with context

        Returns:
            Result with interaction ID and response status

        Raises:
            ProjectNotFoundError: If project doesn't exist
            WorkItemNotFoundError: If work item doesn't exist
            AgentNotActiveError: If agent not currently working on item
        """
        pass

    @abstractmethod
    async def provide_feedback(
        self,
        command: ProvideFeedbackCommand
    ) -> InteractionResult:
        """
        Provides feedback on agent's output.

        Feedback can be general comments or specific issues.
        Agent may or may not need to respond depending on feedback type.

        Args:
            command: Feedback command with details

        Returns:
            Result with interaction ID

        Raises:
            ProjectNotFoundError: If project doesn't exist
            ExecutionNotFoundError: If agent execution doesn't exist
        """
        pass

    @abstractmethod
    async def approve_work(
        self,
        command: ApproveWorkCommand
    ) -> InteractionResult:
        """
        Approves agent's work output.

        Marks the work as approved and optionally advances
        workflow to next stage.

        Args:
            command: Approval command with details

        Returns:
            Result with interaction ID and next stage info

        Raises:
            ProjectNotFoundError: If project doesn't exist
            ExecutionNotFoundError: If agent execution doesn't exist
            WorkAlreadyApprovedError: If already approved
        """
        pass

    @abstractmethod
    async def reject_work(
        self,
        command: RejectWorkCommand
    ) -> InteractionResult:
        """
        Rejects agent's work output.

        Marks work as rejected and queues agent for rework
        with specified changes.

        Args:
            command: Rejection command with required changes

        Returns:
            Result with interaction ID and rework task info

        Raises:
            ProjectNotFoundError: If project doesn't exist
            ExecutionNotFoundError: If agent execution doesn't exist
        """
        pass

    @abstractmethod
    async def request_revision(
        self,
        command: RequestRevisionCommand
    ) -> InteractionResult:
        """
        Requests revision of agent's work.

        Similar to rejection but for minor changes.
        Agent will revise work based on specific issues.

        Args:
            command: Revision request with specific issues

        Returns:
            Result with interaction ID and revision task info

        Raises:
            ProjectNotFoundError: If project doesn't exist
            ExecutionNotFoundError: If agent execution doesn't exist
        """
        pass
```

## Interaction Modes

### 1. Conversational Mode (Questions)

**Flow**:
```
Human asks question
    ↓
Create ConversationSession
    ↓
Queue agent for response (question mode)
    ↓
Agent responds in context
    ↓
Store in conversation history
    ↓
Await next question or exit
```

**Session Management**:
```python
@dataclass
class ConversationSession:
    """Represents a human-agent conversation"""
    session_id: str
    project: str
    work_item_id: str
    agent_name: str
    started_at: datetime
    status: str  # active, paused, completed
    turn_count: int
    history: List[ConversationTurn]
    initial_stage: str  # To detect column changes

@dataclass
class ConversationTurn:
    """Single turn in conversation"""
    role: str  # human, agent
    author: str
    content: str
    timestamp: datetime
    content_files: Optional[List[str]] = None  # Context file references
```

**Session Lifecycle**:
```python
class ConversationSessionManager:
    """Manages conversation sessions"""

    async def start_session(
        self,
        project: str,
        work_item_id: str,
        agent_name: str,
        initial_question: str,
        user_id: str
    ) -> ConversationSession:
        """Creates new conversation session"""
        session = ConversationSession(
            session_id=generate_id(),
            project=project,
            work_item_id=work_item_id,
            agent_name=agent_name,
            started_at=utc_now(),
            status="active",
            turn_count=1,
            history=[
                ConversationTurn(
                    role="human",
                    author=user_id,
                    content=initial_question,
                    timestamp=utc_now()
                )
            ],
            initial_stage=await self.get_current_stage(work_item_id)
        )

        # Store session
        await self.session_repository.save(session)

        return session

    async def add_turn(
        self,
        session_id: str,
        role: str,
        author: str,
        content: str,
        content_files: Optional[List[str]] = None
    ):
        """Adds turn to conversation"""
        session = await self.session_repository.get(session_id)

        turn = ConversationTurn(
            role=role,
            author=author,
            content=content,
            timestamp=utc_now(),
            content_files=content_files
        )

        session.history.append(turn)
        session.turn_count += 1

        await self.session_repository.save(session)

    async def should_end_session(
        self,
        session_id: str
    ) -> bool:
        """Checks if session should end"""
        session = await self.session_repository.get(session_id)

        # End if work item moved to different stage
        current_stage = await self.get_current_stage(session.work_item_id)
        if current_stage != session.initial_stage:
            return True

        # End if no activity for 24 hours
        last_turn = session.history[-1]
        if (utc_now() - last_turn.timestamp).total_seconds() > 86400:
            return True

        return False
```

### 2. Feedback Mode

**Flow**:
```
Human provides feedback
    ↓
Store feedback on AgentExecution
    ↓
Determine if agent needs to respond
    ↓
If response needed:
    Queue agent for feedback mode
    ↓
Agent addresses feedback
```

**Feedback Routing**:
```python
class FeedbackRouter:
    """Routes feedback to appropriate handler"""

    async def route_feedback(
        self,
        command: ProvideFeedbackCommand
    ) -> FeedbackAction:
        """
        Determines what to do with feedback.

        Returns:
            Action to take (record_only, queue_agent, start_revision)
        """
        # Analyze feedback content
        analysis = await self.analyze_feedback(command.feedback)

        if analysis.is_question:
            # Start conversational mode
            return FeedbackAction.START_CONVERSATION

        if analysis.requires_changes:
            # Queue agent for revision
            return FeedbackAction.QUEUE_REVISION

        if analysis.is_informational:
            # Just record, no action
            return FeedbackAction.RECORD_ONLY

        # Default: record and notify agent
        return FeedbackAction.RECORD_AND_NOTIFY
```

### 3. Review Mode (Approval/Rejection)

**Flow**:
```
Human reviews agent output
    ↓
Approve or Reject
    ↓
If Approved:
    Mark execution as approved
    Auto-advance to next stage (if configured)
    ↓
If Rejected:
    Mark execution as rejected
    Queue agent for rework with required changes
```

**Review Decision Recording**:
```python
@dataclass
class ReviewDecision:
    """Human review decision on agent work"""
    decision_id: str
    project: str
    work_item_id: str
    agent_execution_id: str
    reviewer: str
    decision: str  # approved, rejected, needs_revision
    decision_time: datetime
    notes: Optional[str]
    required_changes: Optional[List[str]]
    approval_level: str  # informal, formal, final

class ReviewDecisionService:
    """Records and processes review decisions"""

    async def record_approval(
        self,
        command: ApproveWorkCommand
    ) -> ReviewDecision:
        """Records approval decision"""
        decision = ReviewDecision(
            decision_id=generate_id(),
            project=command.project_name,
            work_item_id=command.work_item_id,
            agent_execution_id=command.agent_execution_id,
            reviewer=command.user_id,
            decision="approved",
            decision_time=utc_now(),
            notes=command.approval_note,
            approval_level="formal"
        )

        # Store decision
        await self.decision_repository.save(decision)

        # Update agent execution
        execution = await self.execution_repository.get(
            command.agent_execution_id
        )
        execution.mark_approved(decision.decision_id, command.user_id)
        await self.execution_repository.save(execution)

        # Auto-advance if configured
        if command.auto_advance:
            await self.advance_workflow(command.work_item_id)

        return decision
```

## Context File References for Interactions

**Design Change**: Interactions can reference large context via files

```python
class InteractionContextBuilder:
    """Builds context for agent interactions"""

    async def build_question_context(
        self,
        command: AskQuestionCommand,
        session: ConversationSession
    ) -> Dict[str, Any]:
        """
        Builds context for question-mode agent execution.

        Uses file references for:
        - Original work item description
        - Agent's previous output
        - Full conversation history
        - Any attached files from user
        """
        context_dir = Path(f"/context/conversations/{session.session_id}")
        context_dir.mkdir(parents=True, exist_ok=True)

        # Write conversation history to file
        history_file = context_dir / "conversation_history.md"
        history_content = self.format_conversation_history(session.history)
        history_file.write_text(history_content)

        # Write current question to file
        question_file = context_dir / "current_question.md"
        question_file.write_text(command.question)

        return {
            'work_item_id': command.work_item_id,
            'agent_name': command.agent_name,
            'conversation_id': session.session_id,
            'turn_count': session.turn_count,

            # File references instead of inline content
            'context_files': {
                'conversation_history': str(history_file),
                'current_question': str(question_file),
                'original_work': f"/context/{command.work_item_id}/work_item.md"
            },

            # Metadata
            'interaction_mode': 'question',
            'user_id': command.user_id
        }

    async def build_revision_context(
        self,
        command: RequestRevisionCommand
    ) -> Dict[str, Any]:
        """
        Builds context for revision-mode agent execution.

        Uses file references for:
        - Original requirements
        - Previous agent output
        - Specific issues to address
        - Reviewer feedback
        """
        context_dir = Path(
            f"/context/revisions/{command.agent_execution_id}"
        )
        context_dir.mkdir(parents=True, exist_ok=True)

        # Get previous output
        execution = await self.execution_repository.get(
            command.agent_execution_id
        )

        # Write previous output to file
        previous_output_file = context_dir / "previous_output.md"
        previous_output_file.write_text(execution.output)

        # Write revision instructions to file
        instructions_file = context_dir / "revision_instructions.md"
        instructions_content = self.format_revision_instructions(
            command.revision_instructions,
            command.specific_issues
        )
        instructions_file.write_text(instructions_content)

        return {
            'work_item_id': command.work_item_id,
            'agent_name': command.agent_name,
            'original_execution_id': command.agent_execution_id,

            # File references
            'context_files': {
                'previous_output': str(previous_output_file),
                'revision_instructions': str(instructions_file),
                'original_work': f"/context/{command.work_item_id}/work_item.md"
            },

            # Metadata
            'interaction_mode': 'revision',
            'revision_iteration': execution.revision_count + 1,
            'user_id': command.user_id
        }
```

## Adapter Implementations

### REST API Adapter
```python
class AgentInteractionRESTAdapter(IAgentInteractionCommandPort):
    """REST API adapter for agent interactions"""

    def __init__(
        self,
        interaction_service: IAgentInteractionService,
        session_manager: ConversationSessionManager,
        event_bus: IEventBus
    ):
        self.interaction_service = interaction_service
        self.session_manager = session_manager
        self.event_bus = event_bus

    async def ask_question(
        self,
        command: AskQuestionCommand
    ) -> InteractionResult:
        """Ask question via REST API"""

        # Get or create conversation session
        if command.conversation_id:
            session = await self.session_manager.get_session(
                command.conversation_id
            )
        else:
            session = await self.session_manager.start_session(
                command.project_name,
                command.work_item_id,
                command.agent_name,
                command.question,
                command.user_id
            )

        # Queue agent for response
        response_task = await self.interaction_service.queue_agent_response(
            session=session,
            question=command.question,
            user_id=command.user_id
        )

        # Emit event
        await self.event_bus.publish(
            QuestionAskedEvent(
                interaction_id=session.session_id,
                project=command.project_name,
                work_item_id=command.work_item_id,
                agent_name=command.agent_name,
                user_id=command.user_id
            )
        )

        return InteractionResult(
            success=True,
            interaction_id=session.session_id,
            queued_for_response=True,
            message=f"Question queued for {command.agent_name}"
        )
```

### GitHub Comment Adapter
```python
class AgentInteractionGitHubAdapter(IAgentInteractionCommandPort):
    """GitHub comment adapter for agent interactions"""

    def __init__(
        self,
        interaction_service: IAgentInteractionService,
        github_service: IGitHubService
    ):
        self.interaction_service = interaction_service
        self.github_service = github_service

    async def ask_question(
        self,
        command: AskQuestionCommand
    ) -> InteractionResult:
        """
        Ask question via GitHub comment.

        Triggered when user comments on agent's output in GitHub issue.
        """

        # Detect if this is a threaded reply to agent comment
        agent_comment_id = await self.github_service.find_agent_comment(
            command.work_item_id,
            command.agent_name
        )

        # Create conversation session
        session = await self.session_manager.start_session(
            command.project_name,
            command.work_item_id,
            command.agent_name,
            command.question,
            command.user_id
        )

        # Queue agent response
        response_task = await self.interaction_service.queue_agent_response(
            session=session,
            question=command.question,
            user_id=command.user_id,
            reply_to_comment_id=agent_comment_id
        )

        return InteractionResult(
            success=True,
            interaction_id=session.session_id,
            queued_for_response=True,
            message="Question will be answered in GitHub thread"
        )
```

## Observability

### Events Emitted
```python
@dataclass
class QuestionAskedEvent(DomainEvent):
    """Human asked agent a question"""
    interaction_id: str
    project: str
    work_item_id: str
    agent_name: str
    user_id: str

@dataclass
class FeedbackProvidedEvent(DomainEvent):
    """Human provided feedback on agent work"""
    interaction_id: str
    project: str
    agent_execution_id: str
    feedback_type: str
    user_id: str

@dataclass
class WorkApprovedEvent(DomainEvent):
    """Human approved agent work"""
    interaction_id: str
    project: str
    agent_execution_id: str
    reviewer: str
    auto_advanced: bool

@dataclass
class WorkRejectedEvent(DomainEvent):
    """Human rejected agent work"""
    interaction_id: str
    project: str
    agent_execution_id: str
    reviewer: str
    required_changes_count: int

@dataclass
class RevisionRequestedEvent(DomainEvent):
    """Human requested revision of agent work"""
    interaction_id: str
    project: str
    agent_execution_id: str
    issues_count: int
    user_id: str
```

## Security

### Authorization
```python
class InteractionAuthorizer:
    """Authorizes agent interactions"""

    def can_ask_question(
        self,
        user: User,
        project: str
    ) -> bool:
        """Check if user can ask questions"""
        # Any project member can ask questions
        return user.is_member_of(project)

    def can_approve_work(
        self,
        user: User,
        project: str
    ) -> bool:
        """Check if user can approve work"""
        # Requires reviewer role
        return user.has_role(project, "reviewer")

    def can_reject_work(
        self,
        user: User,
        project: str
    ) -> bool:
        """Check if user can reject work"""
        # Requires reviewer role
        return user.has_role(project, "reviewer")
```

## Testing Strategy

### Unit Tests
- Command validation
- Context file building
- Session management
- Feedback routing logic

### Integration Tests
- End-to-end conversation flow
- Approval/rejection workflow
- Event emission

### Simulation Tests
- Mock interactions
- Simulated conversations
- Review cycles

## Dependencies

- `IAgentInteractionService`: Process interactions
- `ConversationSessionManager`: Manage conversations
- `IAgentExecutionRepository`: Access execution data
- `IEventBus`: Publish events
- `IGitHubService`: GitHub integration
