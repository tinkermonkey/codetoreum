# Codetoreum — AI Agent Orchestration Platform

Codetoreum automates software-development workflows with specialized AI agents. It integrates with GitHub for work-item management and runs Claude Code as the coding agent inside containers.

**Architecture docs live in `documentation/architecture/`; implementation/simulation docs in `documentation/implementations/`.** If a task doesn't name a design doc, use `/arch-doc` to find or generate one. Architectural rules are catalogued with stable IDs in `documentation/architecture/invariants.md` (INV-01…21) — that file is canonical; the constraints below summarize the load-bearing ones.

## Architecture: Hexagonal + Event Sourcing

- **Domain** — pure business logic (WorkItem, Agent, AgentExecution, Workflow, PipelineStage, ReviewCycle). NO external dependencies (INV-12).
- **Application** — orchestration services + event handlers.
- **Ports** — `ports/input` (inbound commands/queries/services) and `ports/output` (vendor-agnostic outbound interfaces).
- **Adapters** — `primary/` (FastAPI app, REST routers, webhook), `secondary/` (GitHub, Docker, Claude Code, Redis, Elasticsearch), `testing/` + `primary/input_port_adapters/mock/` (mock/in-memory adapters for simulation).
- **Infrastructure** — cross-cutting: `event_bus.py`, `resilience/`, `observability/`, `simulation/`, `auth/`, `health/`, `http/` (GitHub GraphQL client).

### Event-driven core
- **Domain events** are immutable (frozen dataclasses) with serialization — the audit trail (INV-10: every state change emits one).
- **Event bus** (`infrastructure/event_bus.py`) is in-process pub/sub. When Redis is configured it also `xadd`s every event to a stream for cross-process distribution / audit / replay.
- **Event store** is **Elasticsearch** in production (`ElasticsearchEventStore`) — durable audit trail + replay. (Redis backs the event-bus stream and the distributed pipeline lock, not the event store.)
- **Delivery semantics matter when validating/monitoring.** Some publishes are detached (fire-and-forget) and their handler side effects land seconds *after* the triggering action — e.g. agent completion → lock release / board advance lands ~3–4s after the container exits. Synchronize on the event (or its log line), never on container exit. `EventBus.publish_detached()` + `drain()` close the graceful-shutdown window; crash-window durability is open (see `infrastructure/event-bus.md §6` and `decisions/0001-durable-event-delivery.md`).

### Orchestration is fully event-driven (INV-13)
There are **no application-layer poll loops.** Adapters emit domain events (the GitHub board adapter polls GitHub internally — that polling is private to the adapter and never crosses the hexagonal boundary, INV-19); application handlers react. `WorkItemColumnChangedEvent` triggers workflow evaluation; `AgentExecutionCompletedEvent` triggers auto-progression. `MultiProjectOrchestrator` is an **admin-query service** (project status, enabled-project list) — *not* an orchestration loop. Project lifecycle init (board reconciliation, repo registration) happens once at bootstrap via `ProjectLifecycleService`.

## Key components

**Domain models** — WorkItem (unit of work), Agent (capability-scoped AI agent), AgentExecution (one agent run), Workflow / PipelineStage (multi-stage pipeline + entry conditions), ReviewCycle (maker-checker with feedback).

**Domain events** — ~165 `CodetoreumEvent` subclasses under `domain/events/`. Notable families: `WorkItemColumnChangedEvent`, `BoardReconciledEvent`, `ReviewStatusChangedEvent`, `LockAcquired/ReleasedEvent`, and the **`CodingAgent*` family** (11 per-execution telemetry events in `coding_agent_events.py`: Invoked, Ready, ToolCall, ToolResult, TextOutput, Thinking, RateLimit, ApiRetry, OtlpSpan, TokensUsed, Completed; aggregate id = `execution_id`, stream `coding-agent-<execution_id>`, 14-day retention).

**Application services** (23, in `application/`) — WorkflowOrchestrator, AgentScheduler, ExecutionService (manages execution lifecycle; delegates the actual agent invocation to `ICodingAgent` — it does not build container config, stream logs, parse tokens, or upload artifacts), ReviewService, WorkspaceRouter (returns a logical `WorkspaceContext` value object; the coding-agent adapter translates it to runtime concerns), ConversationalLoopOrchestrator, ContainerRecoveryService, MultiProjectOrchestrator, ProjectLifecycleService, and DefaultPromptBuilder (`application/prompt_building/`, implements `IPromptBuilder` — assembles a vendor-agnostic `StructuredPrompt`; adapters render it to their vendor's format). Event handlers live in `application/event_handlers/` (board, workflow, review, execution, repair-cycle).

**Ports** — input + output interfaces in `ports/`. Output ports include: ITicketSystem, ICodingAgent, IContainer, IVersionControlService, IEventStore, IBoardService, ICodeReviewService, IWorkItemService, IEventEmitter, IIdentityService, IPipelineLockService, IPromptBuilder, IDistributedLock.

> **Coding work runs through `ICodingAgent` + `IPromptBuilder`.** There is no separate LLM-provider, agent-launcher, or storage port — agent output flows through the `CodingAgent*` event family, not a blob store. `ICodingAgent` covers both *what* to invoke and *how* (`InvocationMode.{CONTAINERIZED, HOST, API}`).

> **`ClaudeCodeAdapter` (`adapters/secondary/claude_code/`) implements `ICodingAgent` — it is not a prompt→text API wrapper.** It picks an internal strategy (`strategies/containerized.py` or `strategies/host.py`) from the invocation mode. Containerized launches `claude --print` in a Docker container (`--network bridge`) via `IContainer`; host runs it as a local subprocess. Either way Claude Code runs its **full agentic loop** inside the subprocess (reads files, edits code, runs bash, decides multi-step). The stream parser converts `claude --print --output-format stream-json` into `CodingAgent*` events. Codetoreum `await`s the subprocess (bounded duration) but the agent acts autonomously inside it — bounded duration ≠ bounded capability.

## Infrastructure rules

- **Resilience** (circuit breakers, rate limiting, retries, timeouts) is centralized in `infrastructure/resilience/` and applied via decorators that wrap adapters (e.g. `ResilientBoardServiceDecorator`). **Adapters stay pure — no resilience logic embedded** (INV-11).
- **Observability** — structured logging with context (event_id, project_id, correlation_id), Prometheus metrics, OpenTelemetry/Jaeger tracing, dead-letter queue (`dead_letter_queue.py`), audit logging (`infrastructure/audit/`). No silent failures — all errors logged with `exc_info=True`.

## Agent execution security model
General-purpose containerized agents get: internet, mounted project files, project env vars, MCP servers (artifacts/logging). They get **no** git/SSH credentials, **no** GitHub credentials/app keys, **no** Docker socket. The orchestrator performs all git operations (clone, commit, push) and hands files to the agent.

## Key constraints (MUST FOLLOW — see `invariants.md` for the full catalogue)
- Domain layer has zero external dependencies (INV-12); all external interaction goes through ports.
- All state changes emit an immutable (frozen) domain event (INV-10).
- Application stays fully event-driven — **no application-layer polling loops** (INV-13). Adapter-internal polling stays private to the adapter.
- The board adapter is the single source of truth for a work item's current column (INV-19).
- Coding agents run in isolated containers — agent configs set `invocation.mode: containerized` in production.
- Critical-path adapters + the event store must declare a failure route (`IFailedEventStore`); bootstrap refuses to start otherwise (INV-20).
- Production bootstrap requires exclusive infrastructure — no shared ES/Redis/Docker/GitHub (INV-21). Local dev escape hatch: `CODETOREUM_INFRA_EXCLUSIVITY=skip`.
- Resilience is centralized in infrastructure; adapters stay pure (INV-11).
- Simulation-only routes mount in `SimulationApplicationBootstrap`, never in production `create_app()` (INV-07).
- REST endpoints require `Authorization: Bearer <token>` — `SimpleTokenAuthManager` prints it at startup as `Authentication token: <jwt>` (INV-14).
- Application services implementing output ports MUST explicitly inherit the port ABC — no duck typing or `TYPE_CHECKING`-only imports (INV-09). E.g. `WorkflowOrchestrator(IWorkflowOrchestrator)`.
- Configuration is database-backed (project settings, workflow/agent definitions, env vars).

## Simulation testing
Fast, deterministic, no external services — 10–100× real-time via a simulated clock.
- `infrastructure/simulation/bootstrap.py` (`SimulationBootstrap`) wires mock adapters, input-port adapters, and simulation-only routes.
- `simulation_runner.py` (`SimulationRunner`) runs scenarios and exposes assertion helpers (`assert_event_occurred`, `assert_metric_recorded`, …) and the mock adapters.
- `simulation_config.py` — `create_fast_config()` (100× for tests), `create_realistic_config()` (1×), `from_yaml()`.
- `simulation_clock.py` — `advance(delta)`, `advance_to(time)`, `now()`.
- Mock adapters live in `adapters/testing/` and `adapters/primary/input_port_adapters/mock/` (e.g. MockClaudeCodeAdapter, MockBoardAdapter, MockReviewCycleAdapter, InMemoryEventStore, InMemoryMetricsAdapter).
- Scenario YAML in `scenarios/`; predefined scenarios cover basic workflows, full SDLC (±repair), repair cycles, queue ordering, multi-turn dialogue, container recovery, multi-project, board automation.

```python
@pytest.mark.asyncio
async def test_workflow():
    config = SimulationConfig.create_fast_config("test_name", speed_multiplier=100.0)
    runner = SimulationRunner(config)
    async def scenario(sim):
        await sim.advance_time(timedelta(minutes=5))
        sim.assert_event_occurred("WorkflowStarted")
    result = await runner.run(scenario)
    assert result.success
```

See `tests/simulation/README.md`, `tests/simulation/SCENARIO_FORMAT.md`, and `documentation/implementations/simulation/{adapters,scenarios}.md`.

## Environment & tooling
- **Python 3.11+** (the `.venv/` currently runs 3.12). A virtualenv already exists at `.venv/` — **do NOT create another** (no `venv`/`virtualenv`/`conda`).
- Run Python: `.venv/bin/python`. Run tests: `poetry run pytest` (uses `.venv`). Install: `poetry add <pkg>`.
- Stack: FastAPI, SQLAlchemy, PostgreSQL (config) + Redis (event-bus stream, locks, caching) + Elasticsearch (event store), Docker, pytest/pytest-asyncio/testcontainers, Prometheus/Grafana/Jaeger. LLM: Claude Code CLI (primary), pluggable.

## Working in this repo
- **New features**: review the relevant `documentation/architecture/` doc; check whether domain/ports/adapters need changes; keep the domain pure; write domain tests first (alongside for application); emit events for state changes; validate docs with `/arch-doc`.
- **Debugging**: replay the event store (audit trail); read structured logs by event_id/correlation_id; check adapter behavior and resilience decorators. Remember detached-event timing (above) before concluding something "didn't fire."
- **Refactoring**: ports are contracts (adapters can change freely behind them); keep the domain pure; keep simulation tests green; update docs to match. Docstrings/comments describe the present — `git log` carries history.

## Key documentation
- `documentation/architecture/overview.md`, `invariants.md` (INV catalogue), `decisions/` (ADRs).
- `domain/models.md`, `domain/events.md`; `ports/input/`, `ports/output/`.
- `application-services/services.md`, `application-services/event-handlers.md`.
- `infrastructure/{event-bus,resilience,observability}.md`; `documentation/implementations/production-bootstrap.md`.

## Specialized agents (`.claude/agents/`)
Invoked automatically by context, or name them explicitly.
- **`codetoreum-architect`** — authoritative reviewer for architectural decisions: new adapters/ports/events/services, hexagonal-boundary and resilience-placement compliance, where new logic belongs.
- **`arch-doc`** (`/arch-doc <intent> [target]`) — generate / validate / update / diagram / audit architecture docs. The `arch-doc-validator` skill auto-validates changes under `ports/`, `adapters/`, `domain/events/`, `application/`, `documentation/architecture/`.
- **`dr-architect` / `dr-extractor` / `dr-advisor`** — Documentation Robotics model management, code-to-DR extraction (with source provenance), and layer/modeling guidance. DR edits go through the `dr` CLI, never hand-written YAML.

---
*This project uses Claude Code for AI-assisted development and agent orchestration.*
