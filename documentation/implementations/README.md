# Implementations Tier

The implementations tier documents concrete implementations that fulfill the architecture tier contracts. An implementation provides adapters for all ports and demonstrates the architecture in action.

## What is an Implementation?

An implementation is a complete, working configuration of adapters that together satisfy all output ports. For example:

- **Simulation Implementation**: Uses mock adapters to simulate the entire system in-memory. Used for testing, development, and scenario testing.
- **Production Implementation**: Uses real adapters for GitHub, Docker, Claude Code, etc. See [production-bootstrap.md](./production-bootstrap.md) for the wiring sequence and validation run.

Each implementation includes:
- A bootstrap function that instantiates and wires all adapters
- Configuration for system behavior
- Adapter-to-port mappings
- Integration tests demonstrating the implementation's capabilities

## Contents

### [simulation/](./simulation/)
**The Simulation System — Complete Mock Implementation**

The simulation system is a full, working implementation of Codetoreum using mock adapters and in-memory services. It is NOT a test harness — it exercises the complete architecture with real domain logic and business rules. It enables:

- Fast, deterministic testing without external dependencies
- Scenario-based testing with time manipulation
- Complete audit trail through event sourcing
- Reproducible behavior for debugging and analysis

**Documentation Files**:
- **[overview.md](./simulation/overview.md)** — Simulation as complete port contract implementation, time control, determinism
- **[adapters.md](./simulation/adapters.md)** — All 58 adapters (38 testing + 2 secondary + 18 input mock) mapped to port interfaces with file paths
- **[bootstrap-wiring.md](./simulation/bootstrap-wiring.md)** — 6-phase bootstrap sequence with Level 4 Mermaid wiring diagram
- **[scenarios.md](./simulation/scenarios.md)** — All 10 scenario directories with YAML files, format guide, and execution instructions

## How to Add a New Implementation

To create a new implementation (e.g., production, staging, cloud-hosted):

1. **Choose Adapters**: For each output port, select or create an adapter
   - Production adapters: Real external systems
   - Secondary adapters: Vendor-specific implementations
   - Testing adapters: Mocks for development

2. **Create Bootstrap Function**: Wire adapters together in `bootstrap.py`
   ```python
   async def create_production_app():
       # Instantiate all adapters — production implementations of the same
       # port interfaces used by the simulation (ITicketSystem, IContainer, etc.)
       ticket_adapter = GitHubTicketAdapter(github_token=...)
       container_adapter = DockerContainerAdapter(docker_host=...)
       # Resolve the ICodingAgent slot (DEF-015 D3) — the production
       # ClaudeCodeAdapter is constructed inside resolve_coding_agent()
       # along with its containerized + host strategies and is wrapped by
       # ResilientCodingAgentDecorator.
       coding_agent = resolver.resolve_coding_agent(
           prompt_builder=DefaultPromptBuilder(),
           container=container_adapter,
           ...,
       )
       # (plus all remaining output port adapters)

       # Wire them to the application
       return create_app(ticket_adapter, container_adapter, coding_agent, ...)
   ```

3. **Document the Implementation**: Create a directory in `implementations/` with:
   - `overview.md` — Purpose and design decisions
   - `adapters.md` — List of chosen adapters and rationale
   - `bootstrap-wiring.md` — Wiring diagram and configuration
   - Configuration files — environment, secrets, scaling

4. **Test the Implementation**: Create integration tests that exercise key workflows

5. **Update [Architecture Documentation](../architecture/)**: If the implementation reveals gaps or changes to ports, update architecture tier documentation

## Implementation vs. Architecture

- **Architecture Tier**: Abstract, implementation-agnostic
  - Defines contracts (ports) for all external interactions
  - Describes domain models and services
  - Technology-neutral (no specific GitHub, Docker, etc.)

- **Implementations Tier**: Concrete, specific technology choices
  - Selects and adapters for each port
  - Wires them together
  - Makes technology decisions (GitHub vs. Jira, Docker vs. Kubernetes, etc.)

Architecture remains stable while implementations can be added or evolved. A new implementation doesn't require architecture changes — only adapter selection and wiring.

## Available and Planned Implementations

- **Simulation** — ✅ Complete mock implementation with in-memory services
- **Production** — Real GitHub, Docker, Claude Code, and external services
- **Staging** (Planned) — Real systems with test GitHub organization
- **Cloud-Hosted** (Planned) — Kubernetes-based deployment with cloud storage

## Documentation Standards

Each implementation follows the pattern:
- `overview.md` — Describes what this implementation is and why
- `adapters.md` — Lists all adapters, their source files, and rationale
- `bootstrap-wiring.md` — Shows how adapters are wired and configuration
- Mermaid diagrams for wiring and architecture
- Links back to architecture tier documentation

See `../templates/implementation-template.md` for required sections and structure.
