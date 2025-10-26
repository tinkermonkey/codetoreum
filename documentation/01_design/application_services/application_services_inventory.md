# Application Services Inventory

This document provides a comprehensive inventory of all application services in the redesigned Codetoreum system. Application services orchestrate domain objects and coordinate infrastructure operations to fulfill business use cases.

## Core Orchestration Services

### 1. Workflow Orchestrator
**Purpose**: Orchestrates complete workflows from card movement to agent completion, coordinating task creation, agent selection, and progression through pipeline stages.

**Key Responsibilities**:
- Handle card movement events from GitHub Projects
- Determine agent routing based on workflow configuration
- Coordinate pipeline stage progression
- Manage workflow lifecycle from start to completion

### 2. Agent Scheduler
**Purpose**: Schedules and manages agent execution timing, priorities, and resource allocation.

**Key Responsibilities**:
- Queue management for agent tasks
- Priority-based task scheduling
- Resource availability checking
- Rate limiting and throttling

### 3. Pipeline Manager
**Purpose**: Manages pipeline execution, stage coordination, and state checkpointing.

**Key Responsibilities**:
- Execute pipeline stages sequentially
- Manage pipeline state and checkpoints
- Handle stage failures and recovery
- Coordinate stage dependencies

## Execution Services

### 4. Agent Executor
**Purpose**: Centralized service for all agent executions, ensuring consistent observability, workspace management, and output handling.

**Key Responsibilities**:
- Execute agents with guaranteed event emission
- Manage Claude Code streaming integration
- Coordinate workspace preparation and finalization
- Post agent output to GitHub
- Track execution outcomes

### 5. Claude Integration Service
**Purpose**: Manages integration with Claude Code CLI, routing execution between Docker and local modes.

**Key Responsibilities**:
- Execute Claude Code with prompts
- Parse and stream Claude output
- Manage MCP server configuration
- Handle session continuity

### 6. Docker Agent Runner
**Purpose**: Manages Docker container lifecycle for agent executions.

**Key Responsibilities**:
- Create and configure agent containers
- Mount volumes (project, SSH, git config)
- Stream container logs
- Handle container recovery and cleanup

## Workspace Services

### 7. Workspace Router
**Purpose**: Routes work items to appropriate workspace types (issues, discussions, hybrid) based on configuration and agent capabilities.

**Key Responsibilities**:
- Determine workspace type for each task
- Select discussion categories
- Route based on agent capabilities
- Apply workspace-specific rules

### 8. Issues Workspace Manager
**Purpose**: Manages Git-based workspace operations for issue workflows.

**Key Responsibilities**:
- Feature branch management (create, checkout, reuse)
- Git operations (commit, push, rebase)
- Merge conflict detection and handling
- Parent/sub-issue hierarchical branches

### 9. Discussions Workspace Manager
**Purpose**: Manages discussion-based workspace operations for non-Git workflows.

**Key Responsibilities**:
- Discussion lifecycle management
- Discussion ID tracking
- Category management
- Discussion-specific operations

### 10. Feature Branch Manager
**Purpose**: Manages feature branch lifecycle, naming conventions, and branch reuse logic.

**Key Responsibilities**:
- Detect existing branches
- Generate branch names following conventions
- Track parent/sub-issue relationships
- Calculate branch reuse confidence

### 11. Git Workflow Manager
**Purpose**: Executes Git operations including branches, commits, and pull requests.

**Key Responsibilities**:
- Execute Git commands
- Manage branch operations
- Create commits with standardized messages
- Create pull requests via gh CLI

## Review and Feedback Services

### 12. Review Service
**Purpose**: Orchestrates maker-checker review cycles with iteration tracking and escalation logic.

**Key Responsibilities**:
- Start and manage review cycles
- Execute maker-checker iterations
- Track review outcomes
- Handle escalation to human reviewers

### 13. Review Parser
**Purpose**: Parses reviewer output into structured review data.

**Key Responsibilities**:
- Extract approval status
- Parse issue lists
- Structure feedback data
- Identify severity levels

### 14. Feedback Manager
**Purpose**: Tracks feedback on agent outputs and routes feedback to appropriate agents.

**Key Responsibilities**:
- Detect user comments and reactions
- Route feedback to revision tasks
- Prevent duplicate feedback processing
- Track feedback timestamps

### 15. Human Feedback Loop Service
**Purpose**: Manages human-in-the-loop interactions including questions, answers, and escalations.

**Key Responsibilities**:
- Route questions to agents
- Manage conversation threading
- Handle escalation scenarios
- Track conversation state

### 16. Review Filter Manager
**Purpose**: Manages pattern-based issue suppression and learning from human feedback.

**Key Responsibilities**:
- Store and apply review filters
- Pattern-based issue suppression
- Learning from human feedback
- Agent-specific and global filters

## GitHub Integration Services

### 17. GitHub Project Manager
**Purpose**: Manages GitHub Projects v2 boards including reconciliation, columns, and labels.

**Key Responsibilities**:
- Reconcile project boards with configuration
- Create and update columns
- Manage labels
- Discover and track boards

### 18. Project Monitor
**Purpose**: Continuously monitors GitHub boards for card movements and changes.

**Key Responsibilities**:
- Poll project boards (30-second interval)
- Detect card movements
- Create tasks from card changes
- Track last-known column states

### 19. GitHub Integration Service
**Purpose**: Handles GitHub API operations for issues, discussions, comments, and labels.

**Key Responsibilities**:
- Post agent output (workspace-aware)
- Create and manage comments
- Manage discussions
- Update labels and metadata

### 20. GitHub Discussions Service
**Purpose**: Specialized service for GitHub Discussions CRUD operations.

**Key Responsibilities**:
- Create and manage discussions
- Handle discussion comments
- Manage categories
- Execute GraphQL queries

## Task Management Services

### 21. Task Queue Manager
**Purpose**: Manages task queue with priority-based ordering and Redis-backed persistence.

**Key Responsibilities**:
- Enqueue tasks with priority
- Dequeue highest-priority tasks
- Persist queue to Redis
- Backup queue to JSON

### 22. Work Execution State Tracker
**Purpose**: Tracks in-progress executions and prevents duplicate work.

**Key Responsibilities**:
- Mark work as in-progress
- Mark work as completed/failed
- Cleanup stuck states
- Prevent duplicate task execution

### 23. Conversational Session State Manager
**Purpose**: Manages conversational threads and session persistence.

**Key Responsibilities**:
- Track conversational sessions
- Store thread history
- Detect column exits
- Manage session lifecycle

## Observability Services

### 24. Event Processor
**Purpose**: Processes and routes observability events throughout the system.

**Key Responsibilities**:
- Event streaming to Redis
- Elasticsearch indexing
- Event history management
- Real-time pub/sub

### 25. Decision Event Emitter
**Purpose**: Convenience wrapper for emitting structured decision events.

**Key Responsibilities**:
- Emit decision events with consistent structure
- High-level decision abstractions
- Categorize decisions (routing, feedback, progression, etc.)
- Track decision reasoning

### 26. Metrics Collector
**Purpose**: Collects and indexes task execution and quality metrics.

**Key Responsibilities**:
- Collect task metrics (duration, success/failure)
- Collect quality metrics (scores)
- Index to Elasticsearch
- JSON backup

### 27. Health Monitor
**Purpose**: Monitors system health and component availability.

**Key Responsibilities**:
- Check Redis connectivity
- Check GitHub API access
- Check Docker availability
- Check Elasticsearch connectivity
- Persist health status to Redis

## Pipeline Support Services

### 28. Pipeline Progression Service
**Purpose**: Manages issue movement between columns and workflow rule enforcement.

**Key Responsibilities**:
- Move issues between columns
- Determine next stage
- Check auto-advancement rules
- Enforce workflow rules

### 29. Pipeline Run Manager
**Purpose**: Tracks pipeline run lifecycle and active runs.

**Key Responsibilities**:
- Start and complete pipeline runs
- Track active runs
- Generate run IDs
- Index run history to Elasticsearch
- Cleanup stale runs

### 30. Repair Cycle Service
**Purpose**: Orchestrates test-driven repair cycles with iterative fixing.

**Key Responsibilities**:
- Execute repair cycles in containers
- Run tests and detect failures
- Coordinate agent fixes
- Track iteration counts
- Manage checkpoints

### 31. Repair Cycle Runner
**Purpose**: Manages containerized repair cycle execution with recovery.

**Key Responsibilities**:
- Create and manage repair containers
- Execute tests in containers
- Persist checkpoints to Redis
- Recover containers on restart
- Cleanup completed cycles

## Configuration Services

### 32. Configuration Manager
**Purpose**: Central service for loading and accessing all configuration.

**Key Responsibilities**:
- Load foundation configurations (agents, pipelines, workflows, MCP)
- Load project configurations
- Provide configuration access methods
- Validate configuration consistency

### 33. State Manager
**Purpose**: Manages GitHub state persistence and synchronization tracking.

**Key Responsibilities**:
- Save and load GitHub state
- Track board and column IDs
- Detect configuration changes
- Manage synchronization timestamps

### 34. Dev Container State Manager
**Purpose**: Tracks Docker image verification status for projects.

**Key Responsibilities**:
- Track image verification status (UNVERIFIED, IN_PROGRESS, VERIFIED, BLOCKED)
- Check image existence
- Update build state
- Persist state to files

## Infrastructure Services

### 35. Project Workspace Manager
**Purpose**: Manages project directory initialization and workspace paths.

**Key Responsibilities**:
- Initialize all project workspaces
- Clone or update repositories
- Provide project directory paths
- Manage workspace structure

### 36. Auto Commit Service
**Purpose**: Automatically commits changes after agent work with standardized messages.

**Key Responsibilities**:
- Detect file changes
- Generate commit messages
- Execute git commits
- Apply standardized formatting

### 37. Agent Container Recovery Service
**Purpose**: Recovers or cleans up containers on system restart.

**Key Responsibilities**:
- Assess container states on startup
- Recover running containers with Redis keys
- Kill orphaned containers
- Remove stopped containers

### 38. Scheduled Tasks Service
**Purpose**: Executes periodic maintenance and background tasks.

**Key Responsibilities**:
- Schedule periodic cleanups
- Prune old events
- Execute health checks
- Manage background jobs

## Pattern Detection Services

### 39. Pattern Detection Service
**Purpose**: Detects patterns in logs and events using Elasticsearch.

**Key Responsibilities**:
- Pattern matching on logs/events
- Anomaly detection
- Trend analysis
- Pattern persistence

### 40. Pattern Ingestion Service
**Purpose**: Ingests logs and events for pattern analysis.

**Key Responsibilities**:
- Pre-process and normalize data
- Index management
- Batch ingestion
- Data enrichment

### 41. Pattern Analysis Service
**Purpose**: Analyzes detected patterns for insights.

**Key Responsibilities**:
- Trend analysis
- Root cause analysis
- Pattern correlation
- Historical analysis

### 42. Pattern GitHub Integration
**Purpose**: Links detected patterns to GitHub issues.

**Key Responsibilities**:
- Create issues for patterns
- Annotate PRs with patterns
- Track pattern occurrences
- Link to incidents

### 43. Pattern Alerting Service
**Purpose**: Generates alerts for critical patterns.

**Key Responsibilities**:
- Alert on critical patterns
- Route notifications
- Throttle alerts
- Manage alert rules

## Support Services

### 44. Circuit Breaker Service
**Purpose**: Provides fault tolerance and automatic recovery for service calls.

**Key Responsibilities**:
- Track failure rates
- Open circuits on threshold
- Implement half-open recovery
- Provide fallback mechanisms

### 45. Claude Token Scheduler
**Purpose**: Rate limits Claude API calls using token bucket algorithm.

**Key Responsibilities**:
- Implement token bucket algorithm
- Schedule API requests
- Enforce rate limits
- Track token usage

### 46. Claude Code Failure Handler
**Purpose**: Detects and handles Claude Code crashes and errors.

**Key Responsibilities**:
- Detect crashes from logs
- Parse error messages
- Implement recovery strategies
- Emit failure events

## Summary

**Total Application Services**: 46

**Service Categories**:
- Core Orchestration: 3 services
- Execution: 3 services
- Workspace: 5 services
- Review and Feedback: 5 services
- GitHub Integration: 4 services
- Task Management: 3 services
- Observability: 4 services
- Pipeline Support: 4 services
- Configuration: 3 services
- Infrastructure: 4 services
- Pattern Detection: 5 services
- Support: 3 services

These application services coordinate domain objects and infrastructure to implement the complete business logic of the Codetoreum system.
