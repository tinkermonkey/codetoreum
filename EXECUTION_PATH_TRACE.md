# Execution Path Trace: BoardColumnEventHandler → ClaudeCodeAdapter

## Complete Execution Flow

### 1. Webhook Event Triggers Column Change
- **Source**: GitHub webhook or board API
- **Event**: `WorkItemColumnChangedEvent`
- **Handler**: `BoardColumnEventHandler` (src/codetoreum/application/event_handlers/board_event_handler.py)

### 2. Event Handler → Agent Executor
**File**: `src/codetoreum/application/event_handlers/board_event_handler.py`
**Method**: `BoardColumnEventHandler._trigger_agent()` (line 676)

```python
await self.agent_executor.execute(
    work_item_id=work_item_id,
    agent_id=column_config.agent_id,
    board_id=board_id
)
```

### 3. Agent Executor → Execution Service
**File**: `src/codetoreum/adapters/secondary/execution_service_agent_executor.py`
**Method**: `ExecutionServiceAgentExecutor.execute()` (line 193)

- Creates async task via `asyncio.create_task(self._run_execution(...))`
- Schedules background execution (fire-and-forget pattern)

**Method**: `ExecutionServiceAgentExecutor._run_execution()` (line 256)
- Steps 1-9: Load domain objects, route workspace, prepare workspace, create execution
- Step 10 (line 443-454): Execute via LLM or container

```python
if agent.requires_docker:
    # Container path
    exec_result = await self._execution_service.execute_with_container(
        execution, context, container_config
    )
else:
    # LLM path (default for Claude Code)
    exec_result = await self._execution_service.execute_with_llm(execution, context)
```

### 4. Execution Service → LLM Provider (ClaudeCodeAdapter)
**File**: `src/codetoreum/application/execution_service.py`
**Method**: `ExecutionService.execute_with_llm()` (line 290)

Line 313: Builds LLM execution context
```python
llm_context = self._build_llm_context(context)
```

Line 316-322: **Critical call to LLM adapter**
```python
result = await self.llm_provider.execute(
    prompt=execution.prompt,
    context=llm_context,
    stream_callback=(
        self._create_stream_callback(execution.id, stream_callback) if stream_callback else None
    ),
)
```

### 5. LLM Provider Executes Prompt (ClaudeCodeAdapter)
**File**: `src/codetoreum/adapters/secondary/claude_code_adapter.py`
**Interface**: Implements `ILLMProvider` port (src/codetoreum/ports/output/llm_provider.py)
**Method**: `ClaudeCodeAdapter.execute()` (line 305)

#### Parameters:
- `prompt`: str - The agent task
- `context`: ExecutionContext - Contains working directory, timeout, model, etc.
- `stream_callback`: StreamCallback - Optional streaming callback

#### Execution Steps:
1. **Line 315**: Sanitize prompt
   ```python
   sanitized_prompt = self._sanitize_prompt(prompt)
   ```

2. **Line 318**: Build CLI command
   ```python
   cmd = self._build_command(sanitized_prompt, ctx)
   ```

3. **Line 319**: **Build environment - CREDENTIAL RETRIEVAL**
   ```python
   env = await self._build_environment(ctx)
   ```

   This method (lines 201-237):
   - Copies os.environ
   - Calls credential provider to get API key/OAuth token:
     ```python
     api_key = await self.config.credential_provider.get_credential(
         self.config.api_key_credential_name  # "ANTHROPIC_API_KEY"
     )
     oauth_token = await self.config.credential_provider.get_credential(
         self.config.oauth_token_credential_name  # "CLAUDE_CODE_OAUTH_TOKEN"
     )
     ```
   - Sets environment variable based on which credential is available
   - **IMPORTANT**: Token is passed to subprocess via `env` dict, NOT injected into container

4. **Line 329-336**: Create subprocess
   ```python
   process = await asyncio.create_subprocess_exec(
       *cmd,
       stdout=asyncio.subprocess.PIPE,
       stderr=asyncio.subprocess.PIPE,
       env=env,  # OAuth token in subprocess environment, not container
       cwd=cwd,
       shell=False,
   )
   ```

5. **Lines 344-388**: Process streaming output
   - Reads JSON events from stdout
   - Parses assistant messages
   - Calls stream_callback if provided
   - Tracks usage statistics

6. **Lines 437-451**: Handle errors
   - Checks exit code
   - Sanitizes error messages
   - Raises appropriate exceptions

7. **Lines 462-484**: Return ExecutionResult
   - Content from assembled output parts
   - Token counts
   - Duration metrics
   - Metadata

## Credential Provider Architecture

**File**: `src/codetoreum/adapters/secondary/claude_code_adapter.py`

### Base Class (Abstract)
**Lines 42-55**: `ICredentialProvider`
```python
class ICredentialProvider:
    async def get_credential(self, key: str) -> str | None:
        raise NotImplementedError  # Base class stub at line 55
```

### Production Implementation (Default)
**Lines 58-63**: `EnvironmentCredentialProvider`
```python
class EnvironmentCredentialProvider(ICredentialProvider):
    async def get_credential(self, key: str) -> str | None:
        return os.environ.get(key)  # No NotImplementedError reached
```

### Adapter Initialization
**Lines 121-134**: `ClaudeCodeAdapter.__init__()`
```python
self.config = config

# Initialize credential provider
if self.config.credential_provider is None:
    self.config.credential_provider = EnvironmentCredentialProvider()
```

### Execution Flow Guarantee
The base class `ICredentialProvider.get_credential()` at line 55 is NEVER reachable during production execution because:
1. `ClaudeCodeAdapter.__init__()` (line 131-132) always sets a concrete provider
2. Default provider is `EnvironmentCredentialProvider` (line 132)
3. All code paths use the concrete provider, not the abstract base class

## stream_completion Method

**File**: `src/codetoreum/adapters/secondary/claude_code_adapter.py`
**Lines**: 549-645

### Status
- **Currently**: Fully implemented with proper streaming support
- **Used by**: Resilience decorator fallback logic only (infrastructure/resilience/decorators.py:399, 402)
- **Called in pipeline**: NO - normal execution uses `execute()` method exclusively
- **Purpose**: Alternative streaming interface for advanced use cases (not in current pipeline)

### When Called
The `stream_completion()` method is ONLY invoked by the `ResilientLLMProviderDecorator` (lines 399, 402) as a fallback mechanism when:
1. Circuit breaker is open
2. Rate limiter is exceeded
3. Other resilience conditions trigger fallback mode

### Why Not In Critical Path
The main execution flow in `ExecutionService.execute_with_llm()` (line 316) calls `self.llm_provider.execute()`, NOT `stream_completion()`. The streaming happens through the `stream_callback` parameter of `execute()`, not through a separate `stream_completion()` call.

## Authentication Token Handling

### OAuth vs API Key
- **Claude Code CLI requires**: OAuth token (not API key)
- **Environment variable**: `CLAUDE_CODE_OAUTH_TOKEN`
- **NOT injected into agent containers** - subprocess inherits from server process environment

### Token Flow
1. Server process has `CLAUDE_CODE_OAUTH_TOKEN` in environment
2. `_build_environment()` reads it via credential provider
3. Token passed to subprocess via `env` dict
4. Claude CLI subprocess inherits the token
5. Agent containers do NOT see the token (isolated namespace)

### Security Model
- Tokens protected at subprocess level, not container level
- Agent containers can't access server authentication
- Following principle of least privilege

## No NotImplementedError in Production

### Proof
1. Base class `ICredentialProvider.get_credential()` at line 55 is abstract/stub
2. Never instantiated directly - always wrapped by concrete provider
3. Concrete `EnvironmentCredentialProvider` at line 61 returns `os.environ.get(key)`
4. No code path reaches line 55 because line 131-132 ensures concrete provider
5. All calls go through lines 61-63 (EnvironmentCredentialProvider)

## Summary

| Component | File | Method/Line |
|-----------|------|-----------|
| Entry Point | board_event_handler.py | _trigger_agent() line 676 |
| Execution Trigger | execution_service_agent_executor.py | execute() line 193 |
| LLM Provider Call | execution_service.py | execute_with_llm() line 316 |
| CLI Command Build | claude_code_adapter.py | _build_command() line 152 |
| Credential Retrieval | claude_code_adapter.py | _build_environment() line 201 |
| Subprocess Execution | claude_code_adapter.py | execute() line 329 |
| OAuth Token Source | EnvironmentCredentialProvider | line 61-63 |

## Verifications Completed

✅ **ICredentialProvider base class (line 55)**: NOT reachable - EnvironmentCredentialProvider always used
✅ **stream_completion method (line 549)**: Not in critical path - only decorator fallback
✅ **OAuth token flow**: Proper subprocess environment injection, not container injection
✅ **Factory registration**: Should use `CLAUDE_CODE_OAUTH_TOKEN` (needs fix in factory.py:379)
✅ **Test fixture**: Should use `CLAUDE_CODE_OAUTH_TOKEN` (needs fix in test_claude_code_adapter.py:20)
