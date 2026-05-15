# ============================================================================
# Orchestrator Dockerfile
# ============================================================================
# Container image for the Codetoreum orchestrator process
# - Manages workflow execution and agent scheduling
# - Connects to Docker daemon (via socket mounting)
# - Executes as non-root user via docker group membership (not sudo)

FROM python:3.11-slim

# Build argument for host docker group GID
# Linux: run `getent group docker | cut -d: -f3` to get the GID; typically 984
# macOS: use 0 (Docker group is root)
ARG DOCKER_GID=984

# Set working directory
WORKDIR /workspace

# ============================================================================
# Stage 1: System Dependencies
# ============================================================================
RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    curl \
    postgresql-client \
    redis-tools \
    netcat-traditional \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

# ============================================================================
# Stage 2: Python Dependencies
# ============================================================================
# Copy dependency manifests
COPY pyproject.toml poetry.lock* requirements.txt* ./

# Install Poetry
RUN pip install --no-cache-dir poetry

# Configure Poetry to not create virtualenv (container is isolated)
ENV POETRY_NO_INTERACTION=1 \
    POETRY_VIRTUALENVS_CREATE=false \
    POETRY_CACHE_DIR=/tmp/poetry_cache

# Install dependencies
RUN if [ -f poetry.lock ]; then \
        poetry install --no-root; \
    elif [ -f requirements.txt ]; then \
        pip install --no-cache-dir -r requirements.txt; \
    fi

# Install codetoreum in editable mode
RUN mkdir -p src/codetoreum && \
    touch src/codetoreum/__init__.py README.md && \
    pip install --no-cache-dir --no-deps -e .

# ============================================================================
# Stage 3: Docker Group Setup (Non-Root Docker Access)
# ============================================================================
# Create docker group matching host GID
# Add orchestrator user to docker group (not root)
RUN if [ "${DOCKER_GID}" = "0" ]; then \
        useradd -m -u 1000 -G root orchestrator; \
    else \
        groupadd -g ${DOCKER_GID} docker || true && \
        useradd -m -u 1000 -G docker orchestrator; \
    fi

# ============================================================================
# Stage 4: Ownership
# ============================================================================
RUN chown -R orchestrator:orchestrator /workspace

# ============================================================================
# Stage 5: Health Check
# ============================================================================
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# ============================================================================
# Stage 6: Runtime Configuration
# ============================================================================
# Set up environment
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH=/home/orchestrator/.local/bin:$PATH

# Create necessary directories with correct ownership
RUN mkdir -p /tmp/codetoreum/workspaces && \
    chown -R orchestrator:orchestrator /tmp/codetoreum

# ============================================================================
# Stage 7: Switch to Non-Root User
# ============================================================================
USER orchestrator

# ============================================================================
# Default entrypoint and command
# ============================================================================
CMD ["python", "-m", "codetoreum.cli.main"]
