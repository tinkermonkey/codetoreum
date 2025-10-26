# Decision Events Design

## Overview

Decision events capture all strategic decision points in the Codetoreum system. Unlike agent lifecycle events that track execution, decision events explain **why** things happen - which agent was selected, why feedback was processed a certain way, when to escalate, etc.

Decision events are critical for:
- Understanding system behavior
- Debugging unexpected routing
- Building explainable AI systems
- Analytics on decision patterns
- Compliance and audit trails

## Decision Event Categories

Decision events are organized into 8 categories based on the type of decision being made:

1. **Routing Decisions** - Agent and workspace selection
2. **Feedback Decisions** - How to handle user feedback
3. **Progression Decisions** - Status and stage transitions
4. **Review Cycle Decisions** - Maker-checker workflow decisions
5. **Conversational Loop Decisions** - Q&A conversation management
6. **Error Handling Decisions** - Error recovery strategies
7. **Task Management Decisions** - Task queuing and prioritization
8. **Branch Management Decisions** - Git branch operations

## Standardized Decision Event Structure

All decision events follow this standardized structure:

```python
{
    'timestamp': str,              # ISO 8601 UTC timestamp
    'event_id': str,               # UUID
    'event_type': str,             # Event type name
    'agent': str,                  # Agent involved
    'task_id': str,                # Task identifier
    'project': str,                # Project name
    'pipeline_run_id': str,        # Pipeline run ID
    'data': {
        # Standard decision fields
        'decision_category': str,  # Category (routing, feedback, etc.)
        'issue_number': int,       # Work item number
        'board': str,              # Board/pipeline name
        'workspace_type': str,     # Workspace type

        # Decision-specific fields
        'inputs': Dict[str, Any],     # Inputs to decision
        'decision': Dict[str, Any],   # The decision made
        'reason': str,                # Human-readable explanation
        'reasoning_data': Dict,       # Structured reasoning
    }
}
```

## Category 1: Routing Decisions

Routing decisions determine which agent handles work and in what workspace.

### agent_routing_decision

**Purpose**: Explains why a specific agent was selected for a work item.

**Emitted By**: `ProjectMonitor._create_task_from_card()`

**When Emitted**: When card moves to new column and agent is selected

**Event Structure**:
```python
{
    'data': {
        'decision_category': 'routing',
        'issue_number': 123,
        'board': 'Development',
        'workspace_type': 'issues',

        'inputs': {
            'current_column': 'Implementation',
            'previous_column': 'Design',
            'issue_labels': ['feature', 'priority:high'],
            'available_agents': ['senior_software_engineer', 'junior_developer']
        },

        'decision': {
            'selected_agent': 'senior_software_engineer',
            'alternatives_considered': ['junior_developer'],
            'confidence': 0.95
        },

        'reason': 'Selected senior_software_engineer based on Implementation column mapping in workflow configuration',

        'reasoning_data': {
            'selection_method': 'workflow_config',  # 'workflow_config' | 'label_based' | 'escalation'
            'config_source': 'workflows.yaml',
            'fallback_used': False
        }
    }
}
```

**Key Decision Factors**:
- Workflow column mapping (primary)
- Issue labels (secondary)
- Previous stage output requirements
- Agent availability and circuit breaker state

---

### workspace_routing_decision

**Purpose**: Explains why a specific workspace type was selected (issues, discussions, or hybrid).

**Emitted By**: `WorkspaceRouter.determine_workspace_type()`

**When Emitted**: When determining workspace for new work item or stage

**Event Structure**:
```python
{
    'data': {
        'decision_category': 'routing',
        'issue_number': 123,
        'board': 'Planning',

        'inputs': {
            'pipeline_config': 'discussions',  # From config
            'agent': 'business_analyst',
            'stage': 'requirements_analysis',
            'agent_makes_code_changes': False
        },

        'decision': {
            'workspace_type': 'discussions',
            'category_id': 'DIC_kwDOABCDEF01',
            'category_name': 'Requirements'
        },

        'reason': 'Selected discussions workspace: pipeline configured for discussions, agent does not require git access',

        'reasoning_data': {
            'selection_priority': [
                'pipeline_config',      # Explicit config wins
                'agent_requirements',   # Agent needs git?
                'stage_requirements'    # Stage needs git?
            ],
            'override_used': False
        }
    }
}
```

**Key Decision Factors**:
- Pipeline workspace configuration
- Agent requirements (requires git for code changes)
- Stage requirements (review stages may use different workspace)

---

## Category 2: Feedback Decisions

Feedback decisions determine how user feedback on agent output is processed.

### feedback_detected

**Purpose**: Records that user feedback was detected on agent output.

**Emitted By**: `FeedbackManager.detect_feedback()`

**When Emitted**: When new comment, label, or reaction detected after agent completion

**Event Structure**:
```python
{
    'data': {
        'decision_category': 'feedback',
        'issue_number': 123,
        'board': 'Development',
        'workspace_type': 'issues',

        'inputs': {
            'feedback_type': 'comment',  # 'comment' | 'label' | 'reaction' | 'status_change'
            'feedback_author': 'user123',
            'feedback_timestamp': '2025-10-26T11:00:00Z',
            'last_agent_comment_timestamp': '2025-10-26T10:36:00Z',
            'active_conversation_session': True
        },

        'decision': {
            'feedback_classification': 'question',  # 'question' | 'approval' | 'change_request' | 'escalation'
            'should_process': True,
            'processing_method': 'conversational_loop'  # 'conversational_loop' | 'revision' | 'ignore'
        },

        'reason': 'Question detected in comment: processing via conversational loop',

        'reasoning_data': {
            'question_indicators': [
                'Contains question mark',
                'Starts with interrogative',
                'Requests clarification'
            ],
            'feedback_text_preview': 'Can you explain section 2 in more detail?'
        }
    }
}
```

**Key Decision Factors**:
- Feedback timing (how soon after agent output)
- Feedback content (question vs approval vs change request)
- Active conversation session exists
- Feedback author (human vs bot)

---

### feedback_ignored

**Purpose**: Records that feedback was detected but intentionally ignored with explanation.

**Emitted By**: `FeedbackManager.detect_feedback()`

**When Emitted**: When feedback is detected but processing rules determine it should be ignored

**Event Structure**:
```python
{
    'data': {
        'decision_category': 'feedback',
        'issue_number': 123,
        'board': 'Development',

        'inputs': {
            'feedback_type': 'comment',
            'feedback_author': 'github-actions[bot]',
            'feedback_timestamp': '2025-10-26T11:00:00Z'
        },

        'decision': {
            'should_process': False,
            'ignore_reason': 'bot_author'  # 'bot_author' | 'too_old' | 'column_changed' | 'duplicate'
        },

        'reason': 'Ignoring feedback from bot account github-actions[bot]',

        'reasoning_data': {
            'bot_patterns': ['[bot]', 'dependabot', 'renovate'],
            'author_matched_pattern': '[bot]'
        }
    }
}
```

**Ignore Reasons**:
- `bot_author`: Feedback from automated account
- `too_old`: Feedback more than 24 hours after agent output
- `column_changed`: Work item moved to different column
- `duplicate`: Already processed this feedback

---

## Category 3: Progression Decisions

Progression decisions track movement through workflow stages and statuses.

### status_progression

**Purpose**: Records when work item moves between statuses/columns with context.

**Emitted By**: `PipelineProgression.move_issue_to_column()`

**When Emitted**: After card successfully moved on GitHub board

**Event Structure**:
```python
{
    'data': {
        'decision_category': 'progression',
        'issue_number': 123,
        'board': 'Development',

        'inputs': {
            'current_column': 'In Progress',
            'trigger': 'review_approved',  # 'review_approved' | 'manual' | 'auto_advance'
            'review_outcome': 'approved',
            'auto_advance_enabled': True
        },

        'decision': {
            'next_column': 'Testing',
            'next_agent': 'qa_engineer',
            'auto_advanced': True
        },

        'reason': 'Auto-advancing to Testing after review approval',

        'reasoning_data': {
            'progression_rule': 'auto_advance_on_approval',
            'workflow_path': ['Requirements', 'Design', 'In Progress', 'Testing'],
            'current_position': 2
        }
    }
}
```

**Key Decision Factors**:
- Auto-advance configuration
- Review outcome (if from review cycle)
- Workflow progression rules
- Manual override

---

## Category 4: Review Cycle Decisions

Review cycle decisions manage the maker-checker workflow.

### review_cycle_decision

**Purpose**: Records state changes in maker-checker review cycle.

**Emitted By**: `ReviewCycleService.execute_iteration()`

**When Emitted**: At each state transition in review cycle

**Event Structure**:
```python
{
    'data': {
        'decision_category': 'review_cycle',
        'issue_number': 123,
        'board': 'Development',

        'inputs': {
            'iteration': 2,
            'max_iterations': 3,
            'review_outcome': 'changes_requested',  # 'approved' | 'changes_requested'
            'issues_found': 3,
            'maker_agent': 'senior_software_engineer',
            'reviewer_agent': 'code_reviewer'
        },

        'decision': {
            'state': 'maker_selected',  # 'maker_selected' | 'reviewer_selected' | 'approved' | 'escalate'
            'next_agent': 'senior_software_engineer',
            'next_action': 'revision'  # 'revision' | 'review' | 'complete' | 'escalate'
        },

        'reason': 'Reviewer requested changes in iteration 2: queuing maker agent for revision',

        'reasoning_data': {
            'review_issues': [
                {'title': 'Missing error handling', 'severity': 'high'},
                {'title': 'Inconsistent naming', 'severity': 'medium'},
                {'title': 'Missing tests', 'severity': 'high'}
            ],
            'iterations_remaining': 1,
            'will_escalate_if_not_approved': True
        }
    }
}
```

**Review Cycle States**:
- `maker_selected`: Maker agent queued for initial work or revision
- `reviewer_selected`: Reviewer agent queued
- `approved`: Review cycle completed successfully
- `escalate`: Maximum iterations reached, human review needed

---

## Category 5: Conversational Loop Decisions

Conversational loop decisions manage threaded Q&A conversations.

### conversational_loop_started

**Purpose**: Records start of threaded conversation session.

**Emitted By**: `ConversationalSessionState.start_session()`

**When Emitted**: After agent completes and conversation monitoring begins

**Event Structure**:
```python
{
    'data': {
        'decision_category': 'conversational_loop',
        'issue_number': 123,
        'board': 'Planning',

        'inputs': {
            'agent': 'business_analyst',
            'column': 'Requirements Analysis',
            'initial_output_comment_id': 'IC_kwDOABCDEF01'
        },

        'decision': {
            'session_id': 'conv_session_123_1729945800',
            'timeout': 86400,  # 24 hours
            'exit_trigger': 'column_change'  # Exit when column changes
        },

        'reason': 'Starting conversational session after business_analyst completion',

        'reasoning_data': {
            'conversation_mode': 'threaded',
            'agent_supports_qa': True,
            'initial_column': 'Requirements Analysis'
        }
    }
}
```

**Key Decision Factors**:
- Agent completed successfully
- Agent supports conversational mode
- No active conversation session exists
- Workspace supports threading (discussions or issues with threaded comments)

---

## Category 6: Error Handling Decisions

Error handling decisions track retry, circuit breaker, and recovery strategies.

### circuit_breaker_opened

**Purpose**: Records when circuit breaker opens due to repeated failures.

**Emitted By**: `CircuitBreaker.record_failure()`

**When Emitted**: When failure threshold exceeded

**Event Structure**:
```python
{
    'data': {
        'decision_category': 'error_handling',
        'issue_number': 123,
        'board': 'Development',

        'inputs': {
            'agent': 'senior_software_engineer',
            'recent_failures': 5,
            'failure_threshold': 3,
            'failure_window': 300,  # 5 minutes
            'last_errors': [
                'TimeoutError: Claude call exceeded timeout',
                'TimeoutError: Claude call exceeded timeout',
                'TimeoutError: Claude call exceeded timeout'
            ]
        },

        'decision': {
            'state': 'open',  # Circuit breaker now open
            'cooldown_seconds': 300,  # 5 minutes
            'alternative_action': 'queue_human_review'
        },

        'reason': 'Circuit breaker opened: 5 consecutive failures in 5 minutes',

        'reasoning_data': {
            'failure_pattern': 'consistent_timeout',
            'probable_cause': 'claude_api_issues',
            'automatic_recovery': True,
            'recovery_time': '2025-10-26T11:10:00Z'
        }
    }
}
```

**Key Decision Factors**:
- Failure count in time window
- Error type patterns
- Agent-specific vs system-wide issue
- Recovery strategy

---

## Category 7: Task Management Decisions

Task management decisions track task queuing, prioritization, and scheduling.

### task_queued

**Purpose**: Records when task is added to queue with priority reasoning.

**Emitted By**: `TaskQueue.enqueue()`

**When Emitted**: After task is added to Redis sorted set

**Event Structure**:
```python
{
    'data': {
        'decision_category': 'task_management',
        'issue_number': 123,
        'board': 'Development',

        'inputs': {
            'agent': 'senior_software_engineer',
            'trigger': 'card_movement',
            'current_queue_size': 12,
            'requested_priority': 'MEDIUM'
        },

        'decision': {
            'assigned_priority': 'HIGH',  # May differ from requested
            'queue_position': 3,  # Approximate
            'priority_boost_applied': True,
            'priority_boost_reason': 'blocked_by_dependency'
        },

        'reason': 'Queued with HIGH priority: blocking other work items',

        'reasoning_data': {
            'priority_factors': [
                {'factor': 'dependency_blocker', 'weight': 0.4},
                {'factor': 'issue_age', 'weight': 0.3},
                {'factor': 'explicit_label', 'weight': 0.3}
            ],
            'estimated_wait_time_seconds': 600
        }
    }
}
```

**Key Decision Factors**:
- Explicit priority labels
- Dependency relationships
- Issue age
- Pipeline stage urgency

---

## Category 8: Branch Management Decisions

Branch management decisions track git branch operations and strategies.

### branch_reused

**Purpose**: Records when existing branch is reused instead of creating new.

**Emitted By**: `FeatureBranchManager.get_or_create_branch()`

**When Emitted**: When existing branch found with sufficient confidence

**Event Structure**:
```python
{
    'data': {
        'decision_category': 'branch_management',
        'issue_number': 123,
        'board': 'Development',

        'inputs': {
            'issue_number': 123,
            'parent_issue': 120,
            'search_patterns': [
                'feature/issue-123',
                'feature/issue-120/sub-123'
            ],
            'found_branches': [
                {
                    'name': 'feature/issue-120/sub-123',
                    'last_commit': '2025-10-25T14:30:00Z',
                    'commits_behind_main': 5
                }
            ]
        },

        'decision': {
            'reuse_branch': True,
            'branch_name': 'feature/issue-120/sub-123',
            'confidence': 0.95,
            'sync_with_main': True  # Will rebase
        },

        'reason': 'Reusing existing branch feature/issue-120/sub-123 with high confidence (0.95)',

        'reasoning_data': {
            'match_method': 'parent_sub_pattern',
            'confidence_factors': [
                {'factor': 'exact_sub_issue_match', 'confidence': 0.95},
                {'factor': 'recent_activity', 'confidence': 0.85}
            ],
            'alternative_was_create_new': True
        }
    }
}
```

**Key Decision Factors**:
- Branch name pattern matching
- Issue parent/child relationships
- Branch recency and activity
- Confidence threshold (0.8+)

---

### branch_conflict_detected

**Purpose**: Records when merge conflict detected during branch sync.

**Emitted By**: `IssuesWorkspaceContext._handle_merge_conflicts()`

**When Emitted**: After git pull --rebase fails with conflicts

**Event Structure**:
```python
{
    'data': {
        'decision_category': 'branch_management',
        'issue_number': 123,
        'board': 'Development',

        'inputs': {
            'branch_name': 'feature/issue-123',
            'commits_behind_main': 12,
            'attempted_operation': 'rebase'
        },

        'decision': {
            'abort_rebase': True,
            'notify_human': True,
            'agent_can_proceed': False,
            'recovery_action': 'manual_resolution_required'
        },

        'reason': 'Merge conflict detected: manual resolution required before agent can proceed',

        'reasoning_data': {
            'conflicting_files': [
                'src/main.py',
                'tests/test_main.py'
            ],
            'conflict_markers_count': 8,
            'automatic_resolution_attempted': False,
            'escalation_label': 'needs-merge-resolution'
        }
    }
}
```

**Key Decision Factors**:
- Conflict complexity (number of files, markers)
- Automatic resolution capability
- Risk of incorrect resolution
- Human intervention availability

---

## Event Consumption Patterns

### Real-Time Decision Monitoring

```python
# Web UI displays decision reasoning
redis.subscribe('orchestrator:agent_events')

for message in redis.listen():
    event = json.loads(message['data'])

    if event.get('data', {}).get('decision_category') == 'routing':
        ui.show_decision_card(
            title=f"Agent Selected: {event['data']['decision']['selected_agent']}",
            reason=event['data']['reason'],
            alternatives=event['data']['decision']['alternatives_considered']
        )
```

### Decision Analytics

```python
# Query Elasticsearch for routing patterns
es.search(
    index='decision-events-*',
    body={
        'query': {
            'bool': {
                'must': [
                    {'term': {'data.decision_category': 'routing'}},
                    {'range': {'timestamp': {'gte': 'now-30d'}}}
                ]
            }
        },
        'aggs': {
            'by_agent': {
                'terms': {
                    'field': 'data.decision.selected_agent',
                    'size': 20
                }
            },
            'by_selection_method': {
                'terms': {
                    'field': 'data.reasoning_data.selection_method'
                }
            }
        }
    }
)
```

### Audit Trail

```python
# Reconstruct decision history for issue
decisions = es.search(
    index='decision-events-*',
    body={
        'query': {
            'term': {'data.issue_number': 123}
        },
        'sort': [{'timestamp': 'asc'}]
    }
)

for decision in decisions['hits']['hits']:
    print(f"{decision['_source']['timestamp']}: {decision['_source']['data']['reason']}")
```

## Decision Explainability

All decision events must include:

1. **Inputs**: What information was available for the decision
2. **Decision**: What was decided and what alternatives were considered
3. **Reason**: Human-readable explanation (one sentence)
4. **Reasoning Data**: Structured data explaining the decision logic

This ensures decisions are:
- **Traceable**: Can reconstruct why decision was made
- **Auditable**: Can verify decision followed rules
- **Explainable**: Can communicate to humans
- **Debuggable**: Can identify incorrect decisions

## Testing Decision Events

```python
def test_agent_routing_decision():
    # Setup
    task_context = {
        'issue_number': 123,
        'board': 'Development',
        'column': 'Implementation'
    }

    # Execute
    agent = select_agent_for_column(task_context)

    # Verify decision event emitted
    decision_event = obs_mock.emit.call_args_list[-1]

    assert decision_event['data']['decision_category'] == 'routing'
    assert decision_event['data']['decision']['selected_agent'] == 'senior_software_engineer'
    assert 'reason' in decision_event['data']
    assert 'reasoning_data' in decision_event['data']

    # Verify reasoning is sound
    reasoning = decision_event['data']['reasoning_data']
    assert reasoning['selection_method'] in ['workflow_config', 'label_based', 'escalation']
```

## Migration from Legacy System

### Changes from Legacy
1. **Standardized structure**: All decision events now follow same structure
2. **New field**: `decision_category` for grouping
3. **Enhanced reasoning**: `reasoning_data` provides structured explanation
4. **Alternatives tracking**: `alternatives_considered` shows what was evaluated

### Backward Compatibility
- Event type names unchanged where possible
- Distribution channels unchanged
- Legacy consumers can ignore new fields

## Related Documentation

- **Agent Lifecycle Events**: [agent_lifecycle_events_design.md](./agent_lifecycle_events_design.md)
- **Pipeline Events**: [pipeline_events_design.md](./pipeline_events_design.md)
- **System Architecture**: [../02_high_level_arch.md](../02_high_level_arch.md)

## Summary

Decision events provide comprehensive explainability for all strategic decisions in Codetoreum. These events enable:

- **Transparency**: Understand why system behaves as it does
- **Debugging**: Identify incorrect routing or processing
- **Analytics**: Discover decision patterns and optimization opportunities
- **Audit**: Compliance and audit trail requirements
- **Trust**: Users can see and understand system reasoning

The standardized decision event structure ensures consistent capture of inputs, decisions, reasoning, and alternatives across all decision categories.
