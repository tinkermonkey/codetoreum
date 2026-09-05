# End-to-End Tests for Codetoreum

This directory contains end-to-end (E2E) tests that verify Codetoreum functionality against real infrastructure, including GitHub.

## Conversational Loop Production Wiring Test

**File**: `test_conversational_loop_production_e2e.py`

**Purpose**: Verify the complete conversational loop flow with production GitHub wiring.

**What it tests**:
1. ✅ GitHubDiscussionAdapter connects to real GitHub API with valid credentials
2. ✅ CommentNeedsResponseEvent is emitted when a human comment is detected
3. ✅ ConversationalLoopOrchestrator.handle_comment_event() processes the event correctly
4. ✅ Coding agent generates a response
5. ✅ Response is posted to real GitHub via adapter.add_comment()
6. ✅ Posted comment is visible on the real GitHub discussion/issue
7. ✅ Event trail and session state are properly persisted for audit trail

**Event Path Verified**:
```
Human Comment on GitHub
        ↓
GitHubDiscussionAdapter.get_thread() detects it
        ↓
CommentNeedsResponseEvent emitted
        ↓
ConversationalLoopOrchestrator.handle_comment_event()
        ↓
ICodingAgent.execute() generates response
        ↓
GitHubDiscussionAdapter.add_comment() posts response
        ↓
Response visible on real GitHub
        ↓
AgentResponsePostedEvent logged to event store
        ↓
Session state persisted with checkpoint
```

## Setup

### Prerequisites

1. **GitHub Account & Token**:
   - Create a personal access token at https://github.com/settings/tokens
   - Required scopes: `repo` (for issues/discussions)
   - Save the token securely

2. **Test Repository**:
   - Create a throwaway GitHub repository (or use an existing test repo)
   - Must allow discussions or have issues enabled
   - Note the repo in format `organization/repository`

3. **Work Item (Issue or Discussion)**:
   - Create a GitHub issue or discussion in the test repository
   - Note the issue/discussion number
   - This is where the test will post comments

### Environment Configuration

Set these environment variables before running the test:

```bash
# GitHub personal access token (requires repo scope)
export GITHUB_TOKEN=ghp_your_token_here

# Test repository (format: org/repo)
export GITHUB_TEST_REPO=my-org/test-conversational-repo

# Issue or discussion number on the test repo
export GITHUB_TEST_WORK_ITEM_ID=123
```

## Running the Test

### Basic Run (Verbose Output)

```bash
# Single test class
python -m pytest tests/e2e/test_conversational_loop_production_e2e.py::TestConversationalLoopProductionE2E -v -s

# Single specific test
python -m pytest tests/e2e/test_conversational_loop_production_e2e.py::TestConversationalLoopProductionE2E::test_conversational_loop_posts_to_real_github -v -s

# All E2E tests
python -m pytest tests/e2e/ -v -s
```

### With Environment Variables

```bash
GITHUB_TOKEN=ghp_... \
GITHUB_TEST_REPO=my-org/test-repo \
GITHUB_TEST_WORK_ITEM_ID=123 \
python -m pytest tests/e2e/test_conversational_loop_production_e2e.py -v -s
```

### Expected Output

On successful run, you'll see:

```
[E2E Test] Starting conversational loop verification with GitHub my-org/test-repo, work item 123
[E2E Test] ✓ Conversational loop initialized, session ID: conv_session_123_1234567890
[E2E Test] ✓ GitHub discussion monitoring started for work item 123
[E2E Test] Created test comment (ID: e2e-test-1234567890) to trigger agent response
[E2E Test] CommentNeedsResponseEvent created, triggering CLO.handle_comment_event()
[E2E Test] ✓ Comment event handled by orchestrator
[E2E Test] ✓ Coding agent invoked (execution ID: exec-abc123)
[E2E Test] Fetching GitHub discussion thread to verify response...
[E2E Test] ✓ GitHub discussion thread retrieved with N comments
[E2E Test] ✓ Bot response found in discussion (author: codetoreum-e2e-test, ID: comment-id-123)
[E2E Test] ✓ Bot response content verified
[E2E Test] ✓ Session state persisted with checkpoint: e2e-test-1234567890
[E2E Test] ✅ End-to-end verification complete!
```

## Test Cases

### 1. `test_conversational_loop_posts_to_real_github`

**Primary E2E test**: Full conversational loop flow

**Verification steps**:
1. Initializes conversational loop for work item
2. Starts monitoring GitHub discussion
3. Creates test comment to simulate human input
4. Emits CommentNeedsResponseEvent
5. Orchestrator handles event and invokes coding agent
6. Agent generates response
7. Response posted to GitHub via add_comment()
8. Fetches thread and verifies comment is visible
9. Validates session state persisted correctly
10. Cleans up session

**Accepts**: ✅ All verification steps complete, comment visible on GitHub

**Rejects**: ❌ Any step fails, comment not visible, or event path broken

### 2. `test_conversational_loop_event_trail`

**Audit trail verification**: Captures complete event sequence

**Logged events**:
1. CommentNeedsResponseEvent (adapter detection)
2. AgentExecutionStarted (orchestrator invocation)
3. AgentResponsePosted (adapter posting)
4. SessionStateUpdated (checkpoint persistence)

**Output**: JSON event trail showing each step with timestamp

## Troubleshooting

### "GITHUB_TOKEN not set"
- Verify token is exported in current shell: `echo $GITHUB_TOKEN`
- Check token hasn't expired at https://github.com/settings/tokens
- Verify token has `repo` scope

### "401 Unauthorized" / "403 Forbidden"
- Token may lack required scopes
- Create new token with `repo` scope
- Test token works: `curl -H "Authorization: token $GITHUB_TOKEN" https://api.github.com/user`

### "Work item not found"
- Verify work item ID exists in repository
- For issues: Go to repo/issues/123
- For discussions: Go to repo/discussions (check if discussions enabled)
- Ensure ID is numeric without `#` prefix

### "Cannot post comment"
- Verify repository allows write access with your token
- Test with: `curl -X POST -H "Authorization: token $GITHUB_TOKEN" ...`
- Check rate limits: `curl -H "Authorization: token $GITHUB_TOKEN" https://api.github.com/rate_limit`

### "Comment never posted"
- Check GitHub API rate limits (429 errors)
- Verify adapter is actually calling add_comment() in logs
- Check if bot is blocked or rate-limited

## CI/CD Considerations

**By default, E2E tests are NOT run in CI** because:
- They require valid GitHub credentials
- They consume GitHub API quota
- They require external infrastructure
- They should only run on demand with explicit setup

**To enable in CI**:
1. Set secrets: `GITHUB_TOKEN`, `GITHUB_TEST_REPO`, `GITHUB_TEST_WORK_ITEM_ID`
2. Add pytest marker: `pytest -m "e2e" tests/`
3. Consider rate-limiting and quota management

## Acceptance Criteria (Issue #943 Phase 4)

This E2E test fulfills all acceptance criteria:

- [x] A conversational-loop scenario runs against production wiring
- [x] Posts a visible comment to a real GitHub discussion/issue thread
- [x] Full event path confirmed:
  - [x] `CommentNeedsResponseEvent` emitted by adapter
  - [x] Event reaches `CLO.handle_comment_event`
  - [x] CLO posts reply via `discussion_adapter.add_comment()`
  - [x] Comment visible on real GitHub thread
- [x] Verification evidence captured in logs and event trail
- [x] No regression in simulation-based tests (existing tests still pass)
- [x] Code reviewed and follows CLAUDE.md guidelines

## Future Enhancements

- Multi-turn dialogue verification (agent responds, human replies, agent responds again)
- Rate limiting and resilience decorator testing
- Error recovery scenarios
- Performance benchmarking
- Real Claude Code invocation (not mock) for ultimate verification
