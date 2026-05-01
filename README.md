# Codetoreum - AI Agent Orchestration Platform

Codetoreum is an AI agent orchestration platform that automates software development workflows using specialized AI agents. The system integrates with GitHub for work item management and uses Claude Code for agent execution in containerized environments.

## Overview

This project implements a **Gen 2 Hexagonal Architecture** with event sourcing, designed for:
- **Testability**: Full end-to-end testing without external services via simulation mode
- **Observability**: Event sourcing provides complete audit trail
- **Extensibility**: Plugin architecture for ticket systems and LLM providers
- **Ease of Configuration**: Web-based UI with database storage

## Architecture

The system follows **Hexagonal Architecture** (Ports and Adapters) with clear separation of concerns:

```
┌─────────────────────────────────────────────────────────┐
│                    Primary Adapters                     │
│          (Web API, CLI, WebSocket, Webhooks)           │
└─────────────────────┬───────────────────────────────────┘
                      │
┌─────────────────────▼───────────────────────────────────┐
│                    Input Ports                          │
│    (IWorkflowService, IExecutionService, etc.)         │
└─────────────────────┬───────────────────────────────────┘
                      │
┌─────────────────────▼───────────────────────────────────┐
│               Application Services                      │
│  (WorkflowOrchestrator, AgentScheduler, etc.)          │
└─────────────────────┬───────────────────────────────────┘
                      │
┌─────────────────────▼───────────────────────────────────┐
│                  Domain Models                          │
│  (WorkItem, Agent, Workflow, PipelineStage, etc.)      │
└─────────────────────┬───────────────────────────────────┘
                      │
┌─────────────────────▼───────────────────────────────────┐
│                   Output Ports                          │
│  (ITicketSystem, ILLMProvider, IContainer, etc.)       │
└─────────────────────┬───────────────────────────────────┘
                      │
┌─────────────────────▼───────────────────────────────────┐
│                 Secondary Adapters                      │
│  (GitHubAdapter, ClaudeCodeAdapter, DockerAdapter)     │
└─────────────────────────────────────────────────────────┘
```

## Project Structure

```
codetoreum/
├── src/
│   ├── domain/              # Core business logic (pure, no dependencies)
│   ├── application/         # Application services (orchestration)
│   ├── ports/              # Port interfaces (contracts)
│   │   ├── input/          # Inbound port interfaces
│   │   └── output/         # Outbound port interfaces
│   ├── adapters/           # Adapter implementations
│   │   ├── primary/        # Inbound adapters (API, CLI, webhooks)
│   │   └── secondary/      # Outbound adapters (GitHub, Docker, LLM)
│   └── infrastructure/     # Cross-cutting concerns (logging, events, resilience)
├── tests/
│   ├── unit/               # Unit tests (domain models)
│   ├── integration/        # Integration tests (with mock adapters)
│   └── simulation/         # Full workflow simulation tests
├── docs/                   # Additional documentation
└── documentation/          # Design documentation
    ├── architecture/       # Gen 2 architecture specifications
    ├── implementations/    # Implementation guides and production bootstrap
    └── templates/          # Documentation templates
```

## Quick Start

### Prerequisites

- Python 3.11+
- Poetry (dependency management)
- Docker (for containerized agent execution)

### Installation

1. **Clone the repository**:
   ```bash
   git clone <repository-url>
   cd codetoreum
   ```

2. **Install dependencies**:
   ```bash
   poetry install
   ```

3. **Set up pre-commit hooks**:
   ```bash
   poetry run pre-commit install
   ```

4. **Run tests**:
   ```bash
   poetry run pytest
   ```

### Configuration

1. **Copy environment configuration**:
   ```bash
   cp .env.example .env
   ```

2. **Configure environment variables**:

   Edit `.env` and set the required values:

   **IMPORTANT for Production**: Generate a secure secret key for JWT authentication:
   ```bash
   python -c 'import secrets; print(secrets.token_urlsafe(64))'
   ```

   Then set in your `.env` file:
   ```bash
   CODETOREUM_SECRET_KEY=<generated-secret-key>
   CODETOREUM_ENV=production
   ```

   Without a persistent secret key in production, all JWT tokens will be invalidated on server restart.

### Development Setup

1. **Activate virtual environment**:
   ```bash
   poetry shell
   ```

2. **Run linters**:
   ```bash
   # Format code
   poetry run black .

   # Lint with ruff
   poetry run ruff check .

   # Type check with mypy
   poetry run mypy src/
   ```

3. **Run tests with coverage**:
   ```bash
   poetry run pytest --cov=src --cov-report=html
   ```

## Development Workflow

### Code Quality Standards

- **Domain Layer**: 100% test coverage required
- **Application Layer**: 90% test coverage target
- **Overall Project**: 80% minimum coverage

### Linting and Formatting

This project uses:
- **Black**: Code formatting (line length: 100)
- **Ruff**: Fast Python linter with multiple rule sets
- **MyPy**: Static type checking
- **Pre-commit**: Automated checks before commits

All tools are configured in `pyproject.toml`.

### Testing

```bash
# Run all tests
poetry run pytest

# Run specific test categories
poetry run pytest -m unit
poetry run pytest -m integration
poetry run pytest -m simulation

# Run with coverage report
poetry run pytest --cov=src --cov-report=term-missing

# Run tests in watch mode
poetry run pytest-watch
```

### Test Markers

- `@pytest.mark.unit`: Unit tests for isolated components
- `@pytest.mark.integration`: Integration tests with external dependencies
- `@pytest.mark.simulation`: Full workflow simulation tests
- `@pytest.mark.slow`: Tests that take significant time
- `@pytest.mark.contract`: Contract tests for adapter implementations

## Key Design Principles

### 1. Hexagonal Architecture
- **Domain layer** contains pure business logic with no external dependencies
- All external interactions go through **port interfaces**
- **Adapters** are swappable implementations

### 2. Event Sourcing
- All state changes emit domain events
- Complete audit trail for debugging and replay
- Event store using Elasticsearch + Redis

### 3. Testability
- **Simulation mode** allows full end-to-end testing without external services
- Mock adapters for ticket systems, LLMs, containers
- Time manipulation for fast-forwarding simulations

### 4. Security Model
Containerized agents have:
- ✅ Internet access
- ✅ Mounted project files (read/write or read-only)
- ✅ Project-level environment variables
- ❌ No git credentials or SSH keys
- ❌ No GitHub credentials
- ❌ No Docker socket access

**Implication**: The orchestrator handles all git operations (clone, commit, push).

## Documentation

See `documentation/` for complete architecture and implementation documentation:

- **Architecture Documentation**: `documentation/architecture/overview.md` - Complete system design
- **Domain Models**: `documentation/architecture/domain/models.md` - Domain model specifications
- **Port Specifications**: `documentation/architecture/ports/` - Input and output port interfaces
- **Production Bootstrap**: `documentation/implementations/production-bootstrap.md` - Production bootstrap wiring guide
- **Simulation Framework**: `documentation/implementations/simulation/` - Simulation and testing documentation

## Technology Stack

- **Language**: Python 3.11+
- **Web Framework**: FastAPI
- **ORM**: SQLAlchemy
- **Databases**: PostgreSQL (config), Redis (event store)
- **Container Runtime**: Docker
- **Testing**: pytest, pytest-asyncio, testcontainers
- **Linting**: ruff, black, mypy
- **Dependency Management**: Poetry

## Contributing

1. Create a feature branch
2. Write tests first (TDD approach)
3. Implement functionality
4. Ensure all tests pass and coverage meets standards
5. Run linters and formatters
6. Submit pull request

## License

[To be determined]

## Contact

For questions or issues, please refer to the project documentation or open an issue.

---

*Generated with Claude Code - AI-assisted development platform*
