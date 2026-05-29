# IAgentLauncher and ILLMTextProvider — The ILLMProvider Split

**Status**: Decision implemented (D3, breadth-axis Phase D)
**Date**: 2026-05-29
**Driver**: `/home/austinsand/.claude/plans/bootstrap-breadth-axis-implementation.md` §D3
**Strategic context**: `/home/austinsand/.claude/plans/consider-the-bootstrap-effort-woolly-donut.md` § Port-shape fixes

## Why the split

`ClaudeCodeAdapter` — the sole production implementation of the historical
`ILLMProvider` port — is an **autonomous-agent launcher**, not a prompt→text
LLM wrapper. It invokes `claude --print` (Claude Code's headless mode) as a
subprocess inside a workspace; Claude Code then runs its full agentic loop
inside that subprocess: reading files, editing code, executing bash,
making multi-step decisions. `ExecutionContext.working_directory` aims the
agent at the target codebase. From Codetoreum's perspective the subprocess
is synchronous (we `await` its completion); within the subprocess Claude
Code operates autonomously.

A direct Anthropic API adapter or OpenAI API adapter — both reasonable
breadth-axis targets — would *also* satisfy the historical `ILLMProvider`
port, but with meaningfully different semantics:

- **Lifecycle**: API HTTP request vs. subprocess fork-exec-wait.
- **Error categories**: API rate limits, HTTP 5xx, content filter,
  context-length-exceeded vs. subprocess timeout, non-zero exit, SIGKILL.
- **Token accounting**: API exposes a counting endpoint (Anthropic
  `messages.count_tokens`, OpenAI tiktoken); subprocess only sees stdout
  fragments and has to approximate.
- **Cancellation**: API call cancel vs. SIGTERM-then-SIGKILL with D-state
  fallback handling.
- **`working_directory`**: Required for subprocess (it's where the agent
  reads/writes); irrelevant for prompt→text APIs.
- **Conversation management**: Subprocess emulates locally (replays history
  into the next invocation); API may have server-side conversation state
  (OpenAI Assistants) or stateless message-history (Anthropic Messages).

Templating the historical `ILLMProvider` to a second adapter — say, an
Anthropic API adapter — would import all of this ambiguity. Worse: the
second adapter would silently choose semantics for each method, and the
choice would only be visible by reading the implementation.

## What the split looks like

Three options were considered (see plan §D3):

- **A. Single port, two implementation patterns.** Keep `ILLMProvider`,
  accept that some methods behave differently across implementations. Cheapest
  to ship, leaves the ambiguity intact.
- **B. Two sibling ports.** Introduce `IAgentLauncher` and
  `ILLMTextProvider`; `ILLMProvider` becomes a deprecated alias.
- **C. Hierarchy.** `ILLMTextProvider` (base) extended by `IAgentLauncher`.
  Implies subprocess-launchers are a strict superset of text-providers, which
  is false (a launcher's `count_tokens` is *less* exact than a text
  provider's; the relationship isn't refinement).

**Chosen: Option B.** Two sibling ports, each honest about its semantics.

## Port mapping

### `IAgentLauncher` (`src/codetoreum/ports/output/agent_launcher.py`)

Models subprocess-based autonomous-agent CLIs. Today: Claude Code. Future:
Aider, Cursor CLI, OpenAI Codex CLI.

Methods (signatures identical to the historical `ILLMProvider`, semantics
clarified):

| Method | Semantic for an agent launcher |
|---|---|
| `execute(prompt, context, stream_callback)` | Launches the agent subprocess in `context.working_directory`; awaits its completion; returns the agent's final summary. |
| `execute_with_tools(prompt, tools, context, ...)` | Same as `execute`; tool definitions are typically informational (CLI agents use MCP servers, not direct tool args). |
| `stream_completion(prompt, context)` | Streams chunks of the agent's interleaved output (assistant text segments between tool calls), not raw tokens. |
| `create_conversation(system_prompt, parameters)` | Returns a locally-generated identifier; history replayed on subsequent calls. |
| `continue_conversation(conversation_id, message, ...)` | Prepends history to the prompt; re-invokes the subprocess. |
| `get_model_info()` | Hard-coded per CLI (e.g. Claude Code → Claude Sonnet 4.5). |
| `list_available_models()` | Hard-coded list of CLI-supported models. |
| `count_tokens(text, model)` | Approximate (e.g. ~4 chars/token). |
| `get_usage_stats(since)` | Launcher-tracked (parsed from subprocess logs/output). |

Error categories: `PromptTooLongError`, `RateLimitError`, `AuthenticationError`
(propagated from the underlying provider), `ExternalServiceError` (subprocess
lifecycle failures), `UnsupportedFeatureError`, `ConversationNotFoundError`.

### `ILLMTextProvider` (`src/codetoreum/ports/output/llm_text_provider.py`)

Models prompt→text LLM APIs. No production adapter today — established for
the breadth-axis Phase G work (Anthropic API, OpenAI API, AWS Bedrock,
GCP Vertex AI).

Method signatures match `IAgentLauncher` but the semantic contract differs:

| Method | Semantic for a text provider |
|---|---|
| `execute(prompt, context, stream_callback)` | Single prompt→completion HTTP request; returns the model's completion. |
| `execute_with_tools(prompt, tools, context, ...)` | Tool definitions passed directly to the API (Anthropic `tools=…`, OpenAI `tools=…`). |
| `stream_completion(prompt, context)` | Streams tokens from the API stream. |
| `create_conversation(system_prompt, parameters)` | Returns server-issued ID (OpenAI Assistants) or locally-generated (Anthropic stateless). |
| `continue_conversation(conversation_id, message, ...)` | Posts a new message to the conversation; provider may manage history server-side. |
| `get_model_info()` | Reflects the configured default model from API metadata. |
| `list_available_models()` | Queries the provider's model-listing endpoint (`models.list()`). |
| `count_tokens(text, model)` | Exact, via provider tokenizer (`messages.count_tokens`, `tiktoken`). |
| `get_usage_stats(since)` | Ideally from the provider's billing API. |

Error categories: same as `IAgentLauncher` but HTTP-shaped — rate-limit,
authentication, model-not-found, content-filter, context-length-exceeded.

### `ILLMProvider` (deprecated alias)

`ILLMProvider` is now an alias of `IAgentLauncher`, exported from both
`codetoreum.ports.output` (the package) and
`codetoreum.ports.output.llm_provider` (the historical deep import path,
provided via module `__getattr__` to avoid a circular import). The alias
exists so the ~100 existing references continue to compile and run; new
code should import `IAgentLauncher` or `ILLMTextProvider` directly.

The alias points at `IAgentLauncher` rather than `ILLMTextProvider` because
the only production implementation (`ClaudeCodeAdapter`) is an
autonomous-agent launcher.

## How to choose between them when implementing a new adapter

| Adapter | Port |
|---|---|
| Claude Code subprocess (today) | `IAgentLauncher` |
| Aider subprocess | `IAgentLauncher` |
| Cursor CLI subprocess | `IAgentLauncher` |
| OpenAI Codex CLI subprocess | `IAgentLauncher` |
| Direct Anthropic API (`anthropic` SDK) | `ILLMTextProvider` |
| Direct OpenAI API (`openai` SDK) | `ILLMTextProvider` |
| AWS Bedrock | `ILLMTextProvider` |
| GCP Vertex AI | `ILLMTextProvider` |
| Local llama.cpp / Ollama | `ILLMTextProvider` |
| MockLLMAdapter (test fixture) | `IAgentLauncher` (it mocks the production execution path, which is agent-launcher-shaped) |

The deciding question: **"Does this adapter run an external process inside a
workspace that does its own agentic loop?"** If yes → `IAgentLauncher`. If
the adapter's `execute` is a single HTTP request to a remote completion API
→ `ILLMTextProvider`.

## What did *not* change

- The data types (`ExecutionContext`, `ExecutionResult`, `ModelInfo`,
  `StreamChunk`, `StreamCallback`, `ToolDefinition`, `ToolCall`, `UsageStats`)
  remain in `codetoreum.ports.output.llm_provider`. Both new ports import them
  from there. Splitting the data types into their own module would be useful
  but is a separate refactor.
- `ClaudeCodeAdapter` behavior is unchanged. Only its declared base class
  changes (`ILLMProvider` → `IAgentLauncher`).
- `MockLLMAdapter` behavior is unchanged. Its declared base class changes
  (`ILLMProvider` → `IAgentLauncher`). It is not split into two mocks; a
  separate `MockLLMTextProvider` will be added when the first
  `ILLMTextProvider` production adapter ships in Phase G.
- `ResilientLLMProviderDecorator` is now declared as wrapping
  `IAgentLauncher`; the underlying resilience patterns
  (`infrastructure/resilience/decorators.py`) are unchanged.
- The `AgentLLMFactory` type alias points at `IAgentLauncher` (was
  `ILLMProvider`). Type-equivalent via the alias.
- `AdapterResolver.resolve_llm()` is renamed `resolve_agent_launcher()`;
  return type is `IAgentLauncher`. The `_factory.create_llm_provider()`
  method is unchanged for now (factory-level rename is a small future cleanup
  — single method, well-contained).

## What is *not yet* done (and why)

- **No production `ILLMTextProvider` adapter yet.** The port is established;
  the first implementation (likely `AnthropicAPIAdapter`) lands in
  breadth-axis Phase G. See `bootstrap-breadth-axis-implementation.md` §G1.
- **No `MockLLMTextProvider` yet.** Will be added alongside the first
  production text-provider adapter.
- **`core-system.md` still describes the historical `ILLMProvider`.** That
  doc will be re-organized when `ILLMProvider` is finally removed (post-Phase
  G, once all call sites have migrated to the explicit names).
- **DR model not updated.** The Documentation Robotics model
  (`documentation-robotics/model/`) still lists `ILLMProvider` as an
  application interface. Updating it is a separate `/dr-sync` workflow.

## File summary

New files:

- `src/codetoreum/ports/output/agent_launcher.py` — `IAgentLauncher` ABC.
- `src/codetoreum/ports/output/llm_text_provider.py` — `ILLMTextProvider` ABC.
- `documentation/architecture/ports/output/agent-launcher.md` — this doc.

Modified files:

- `src/codetoreum/ports/output/llm_provider.py` — `ILLMProvider` ABC removed;
  data types retained; module-level `__getattr__` provides the lazy alias to
  `IAgentLauncher` so deep-import call sites continue to work.
- `src/codetoreum/ports/output/__init__.py` — exports `IAgentLauncher`,
  `ILLMTextProvider`, and the deprecated `ILLMProvider` alias.
- `src/codetoreum/ports/__init__.py` — re-exports the new symbols.
- `src/codetoreum/adapters/secondary/claude_code_adapter.py` — explicit
  `IAgentLauncher` inheritance.
- `src/codetoreum/adapters/testing/mock_llm_adapter.py` — explicit
  `IAgentLauncher` inheritance.
- `src/codetoreum/infrastructure/resilience/decorators.py` —
  `ResilientLLMProviderDecorator` now wraps `IAgentLauncher`.
- `src/codetoreum/infrastructure/adapters/resolver.py` — `resolve_llm`
  renamed to `resolve_agent_launcher`; return type is `IAgentLauncher`.
- `src/codetoreum/cli/validate_credentials.py` — updated call to
  `resolve_agent_launcher`.
- `tests/unit/infrastructure/adapters/test_adapter_resolver.py` — test
  renamed and updated.
