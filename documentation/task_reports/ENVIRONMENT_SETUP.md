# Codetoreum Development Environment Setup

This document describes the development environment setup for the Codetoreum project, including Docker configuration and validation procedures.

## Overview

The Codetoreum agent runs in a containerized environment built on the `clauditoreum-orchestrator` base image. The environment includes:

- **Claude CLI** - AI agent interface (v2.0.27)
- **Git** - Version control (v2.47.3)
- **GitHub CLI** - GitHub API interaction (v2.82.1)
- **Python 3.11** - Runtime environment
- **Build tools** - GCC, make, and PostgreSQL development libraries
- **Python dependencies** - FastAPI, SQLAlchemy, Redis, Docker SDK, and more

## Files Created/Modified

### 1. Dockerfile.agent

Location: `/workspace/codetoreum/Dockerfile.agent`

The Dockerfile follows the hexagonal architecture pattern and implements these key principles:

- **Builds the environment, not the source code** - Source code is mounted at runtime
- **Pre-installs dependencies** - Speeds up agent startup time
- **Minimal ownership changes** - Only changes ownership of installed packages, not source code
- **Verification layer** - Ensures all critical CLIs are present

Key features:
- Based on `clauditoreum-orchestrator:latest` which includes Claude, Git, and GitHub CLIs
- Installs build-essential and libpq-dev for PostgreSQL support
- Pre-installs Python dependencies from requirements.txt
- Runs verification checks for all critical tools
- Uses non-root user (`orchestrator`) for runtime

### 2. requirements.txt

Location: `/workspace/codetoreum/requirements.txt`

Python dependencies aligned with the Gen 2 architecture implementation plan:

**Web Framework:**
- FastAPI >= 0.104.0
- uvicorn[standard] >= 0.24.0
- pydantic >= 2.5.0

**Database & ORM:**
- SQLAlchemy >= 2.0.0
- alembic >= 1.12.0
- asyncpg >= 0.29.0
- psycopg2-binary >= 2.9.9

**Event Store & Cache:**
- redis >= 5.0.0
- hiredis >= 2.2.3

**Background Tasks:**
- celery >= 5.3.4
- httpx >= 0.25.0

**Git & Container Operations:**
- gitpython >= 3.1.40
- docker >= 6.1.0

**Testing:**
- pytest >= 7.4.3
- pytest-asyncio >= 0.21.1
- pytest-cov >= 4.1.0
- testcontainers >= 3.7.1

**Code Quality:**
- ruff >= 0.1.6
- mypy >= 1.7.0
- black >= 23.11.0

**Monitoring:**
- opentelemetry-api >= 1.21.0
- opentelemetry-sdk >= 1.21.0
- prometheus-client >= 0.19.0

**Additional:**
- boto3 >= 1.29.0 (AWS S3)
- PyGithub >= 2.1.1 (GitHub API)
- typer >= 0.9.0 (CLI framework)

### 3. .dockerignore

Location: `/workspace/codetoreum/.dockerignore`

Optimizes Docker build context by excluding:
- Git directories (.git, .github)
- Python cache files (__pycache__, *.pyc)
- Virtual environments (venv, env)
- IDE files (.vscode, .idea)
- Build artifacts (build/, dist/)
- Logs and temporary files

This reduces build context from potentially hundreds of MB to <10MB, significantly speeding up builds.

### 4. validate_environment.py

Location: `/workspace/codetoreum/validate_environment.py`

Automated validation script that tests:
- Critical CLI tools (Claude, Git, GitHub CLI)
- Python environment (Python 3.11, pip)
- Core Python dependencies (FastAPI, SQLAlchemy, etc.)
- Build tools (GCC, make)

## Building the Image

```bash
docker build -f /workspace/codetoreum/Dockerfile.agent -t codetoreum-agent:latest /workspace/codetoreum
```

Build time: ~40-60 seconds (depending on network speed for package downloads)

## Validation

### Automated Validation

Run the validation script:

```bash
python3 /workspace/codetoreum/validate_environment.py
```

Expected output:
```
======================================================================
Codetoreum Agent Environment Validation
======================================================================

Testing: Claude CLI availability... ✓ PASS - /usr/local/bin/claude
Testing: Claude CLI version... ✓ PASS - 2.0.27 (Claude Code)
Testing: Git CLI availability... ✓ PASS - /usr/bin/git
Testing: Git CLI version... ✓ PASS - git version 2.47.3
Testing: GitHub CLI availability... ✓ PASS - /usr/bin/gh
Testing: GitHub CLI version... ✓ PASS - gh version 2.82.1 (2025-10-22)
Testing: Python version... ✓ PASS - Python 3.11.14
Testing: pip version... ✓ PASS - pip 24.0 from /usr/local/lib/python3.11/site-packages/pip (python 3.11)
Testing: FastAPI import... ✓ PASS
Testing: SQLAlchemy import... ✓ PASS
Testing: Redis import... ✓ PASS
Testing: Docker SDK import... ✓ PASS
Testing: pytest import... ✓ PASS
Testing: GitPython import... ✓ PASS
Testing: GCC availability... ✓ PASS - /usr/bin/gcc
Testing: make availability... ✓ PASS - /usr/bin/make

======================================================================
Results: 16/16 tests passed
✓ All tests passed! Environment is ready.
```

### Manual Validation

Test individual components:

```bash
# Test Claude CLI
docker run --rm codetoreum-agent:latest claude --version

# Test Git
docker run --rm codetoreum-agent:latest git --version

# Test GitHub CLI
docker run --rm codetoreum-agent:latest gh --version

# Test Python environment
docker run --rm codetoreum-agent:latest python3 --version

# Test Python dependencies
docker run --rm codetoreum-agent:latest python3 -c "import fastapi; print(f'FastAPI {fastapi.__version__}')"
docker run --rm codetoreum-agent:latest python3 -c "import sqlalchemy; print(f'SQLAlchemy {sqlalchemy.__version__}')"
```

## Architecture Pattern Compliance

This implementation follows the Dockerfile.agent architecture pattern:

✅ **Builds environment, not source code** - No `COPY . .` command
✅ **Pre-installs dependencies** - requirements.txt installed during build
✅ **Minimal ownership changes** - Only system packages, not source files
✅ **Verifies critical CLIs** - Claude, Git, and GitHub CLI verified
✅ **Uses .dockerignore** - Optimized build context
✅ **Non-root runtime user** - Runs as `orchestrator` user

## Runtime Usage

The orchestrator will mount the project at runtime:

```bash
docker run --rm \
  -v /workspace/codetoreum:/workspace/codetoreum \
  codetoreum-agent:latest \
  <command>
```

Source code is **not** baked into the image - it's provided at runtime via volume mount.

## Troubleshooting

### Build Failures

**Problem:** Package installation fails
**Solution:** Check network connectivity, verify package versions in requirements.txt

**Problem:** Base image not found
**Solution:** Ensure `clauditoreum-orchestrator:latest` is available

### Validation Failures

**Problem:** Claude CLI not found
**Solution:** Verify base image includes Claude CLI, rebuild from base image

**Problem:** Python import errors
**Solution:** Check requirements.txt installation, verify no syntax errors

## Next Steps

With the environment setup complete, you can proceed with:

1. **Phase 1: Foundation & Core Domain** (see `documentation/01_design/03_implementation_plan.md`)
   - Implement domain models (WorkItem, Agent, AgentExecution, etc.)
   - Set up testing framework
   - Define domain events

2. **Development Workflow**
   - Source code will be mounted at `/workspace/codetoreum`
   - Agents execute in isolated containers
   - All git operations handled by orchestrator

## References

- Implementation Plan: `documentation/01_design/03_implementation_plan.md`
- High-Level Architecture: `documentation/01_design/02_high_level_arch.md`
- Design Changes: `documentation/01_design/01_design_changes.md`
- Project Guide: `CLAUDE.md`
