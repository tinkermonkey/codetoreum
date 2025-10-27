# Codetoreum - Quick Start Guide

## Prerequisites

- Python 3.11 or higher
- Git
- Docker (for containerized agent execution)

## Installation

### 1. Clone the Repository

```bash
git clone <repository-url>
cd codetoreum
```

### 2. Install Poetry (if not already installed)

Poetry is already installed in this environment. If you need to install it elsewhere:

```bash
curl -sSL https://install.python-poetry.org | python3 -
```

Add Poetry to your PATH:
```bash
export PATH="/home/orchestrator/.local/bin:$PATH"
```

### 3. Install Dependencies

```bash
# Using Poetry directly
poetry install

# Or using Makefile
make install
```

### 4. Set Up Pre-commit Hooks (Optional but Recommended)

```bash
poetry run pre-commit install
```

## Verify Installation

```bash
# Run all tests
make test

# Run linters
make lint

# Run type checker
make type-check

# Run full validation
make validate
```

Expected output:
- ✅ All tests passing (3/3)
- ✅ Ruff linting passed
- ✅ MyPy type checking passed

## Common Commands

### Development Workflow

```bash
# Activate Poetry shell (recommended for development)
poetry shell

# Run tests
make test

# Run specific test category
make test-unit
make test-integration
make test-simulation

# Run tests with coverage report
make test-cov

# Format code
make format

# Lint code
make lint

# Lint with auto-fix
make lint-fix

# Type check
make type-check

# Run all validation checks
make validate

# Clean generated files
make clean
```

### Running the Application

```bash
# Development server (with auto-reload)
make dev

# Production server
make run
```

### Docker Commands

```bash
# Start Docker services
make docker-up

# Stop Docker services
make docker-down

# View Docker logs
make docker-logs

# Rebuild Docker images
make docker-rebuild
```

### Documentation

```bash
# Build documentation
make docs

# Serve documentation locally
make docs-serve
```

## Project Structure

```
codetoreum/
├── src/codetoreum/          # Main package
│   ├── domain/              # Core business logic
│   ├── application/         # Application services
│   ├── ports/              # Port interfaces
│   │   ├── input/          # Inbound ports
│   │   └── output/         # Outbound ports
│   ├── adapters/           # Adapter implementations
│   │   ├── primary/        # Inbound adapters
│   │   └── secondary/      # Outbound adapters
│   └── infrastructure/     # Cross-cutting concerns
├── tests/                  # Test suite
│   ├── unit/              # Unit tests
│   ├── integration/       # Integration tests
│   └── simulation/        # Simulation tests
└── documentation/         # Design documentation
```

## Configuration

### Environment Variables

Copy the example environment file and customize:

```bash
cp .env.example .env
```

Edit `.env` with your configuration:
- Database connection
- Redis connection
- Docker settings
- GitHub credentials
- Claude API key

### Key Environment Variables

```bash
# Application
APP_ENV=development
DEBUG=true

# Database
DATABASE_URL=postgresql://user:password@localhost:5432/codetoreum

# Redis
REDIS_URL=redis://localhost:6379/0

# GitHub
GITHUB_APP_ID=your_app_id
GITHUB_PRIVATE_KEY_PATH=/path/to/key.pem

# Claude API
ANTHROPIC_API_KEY=your_api_key
```

## Testing

### Test Categories

Tests are organized with pytest markers:

```bash
# Run all unit tests
pytest -m unit

# Run all integration tests
pytest -m integration

# Run all simulation tests
pytest -m simulation

# Run slow tests
pytest -m slow

# Run contract tests
pytest -m contract
```

### Writing Tests

Example unit test:

```python
import pytest

@pytest.mark.unit
def test_work_item_creation():
    work_item = WorkItem(
        id="issue-1",
        title="Test Issue",
        status=WorkItemStatus.PENDING
    )
    assert work_item.id == "issue-1"
    assert work_item.status == WorkItemStatus.PENDING
```

Example async test:

```python
import pytest

@pytest.mark.unit
@pytest.mark.asyncio
async def test_async_operation():
    result = await some_async_function()
    assert result is not None
```

## Code Quality

### Linting

The project uses Ruff for linting:

```bash
# Check for issues
poetry run ruff check src/ tests/

# Auto-fix issues
poetry run ruff check --fix src/ tests/
```

### Formatting

The project uses Black for formatting:

```bash
# Check formatting
poetry run black --check src/ tests/

# Format code
poetry run black src/ tests/
```

### Type Checking

The project uses MyPy for type checking:

```bash
# Type check
poetry run mypy src/
```

## Getting Help

```bash
# Show all available make commands
make help

# Check Poetry version
poetry --version

# Check Python version
python --version

# Check installed packages
poetry show
```

## Troubleshooting

### Poetry not found

Add Poetry to your PATH:
```bash
export PATH="/home/orchestrator/.local/bin:$PATH"
```

### Tests failing

Ensure dependencies are installed:
```bash
poetry install
```

### Coverage warnings

Coverage warnings about "no data collected" are expected when there's no implementation code yet. This will resolve as you implement domain models and application logic.

### Pre-commit hooks failing

Run pre-commit manually to see specific issues:
```bash
poetry run pre-commit run --all-files
```

## Next Steps

1. **Review Design Documentation**: See `documentation/01_design/` for detailed specifications
2. **Implement Domain Models**: Start with Phase 1.2 - Domain Model Implementation
3. **Write Tests First**: Follow TDD approach for new features
4. **Check Architecture Compliance**: Ensure clean separation of concerns

## Resources

- **Architecture Guide**: `documentation/01_design/02_high_level_arch.md`
- **Implementation Plan**: `documentation/01_design/03_implementation_plan.md`
- **Setup Summary**: `SETUP_SUMMARY.md`
- **Project README**: `README.md`

---

**Need Help?** Check the documentation or run `make help` for available commands.
