# Codetoreum Deployment Documentation

This directory contains deployment guides and operational procedures for running Codetoreum in production.

## Pre-Deployment Checklist

Before deploying Codetoreum to production, follow these guides:

1. **[GITHUB_APP_SETUP.md](./GITHUB_APP_SETUP.md)** — Configure GitHub authentication
   - Personal Access Token (PAT) setup
   - GitHub App setup (recommended for organizations)
   - Validation and troubleshooting

2. **Credential Validation** — Verify all credentials are configured correctly
   ```bash
   python -m codetoreum.cli.validate_credentials
   ```
   This script validates:
   - GitHub token or app credentials
   - Claude Code OAuth token
   - Docker daemon connectivity
   - Git availability
   - All critical adapters

## Configuration Files

- `.env.production.example` — Example production configuration with all required variables documented

## Critical Credentials for MVP

The following credentials are **required** for production deployment:

### GitHub Integration
- **GITHUB_TOKEN** — Personal access token with `repo`, `read:project`, `read:org` scopes
  - OR use GitHub App: `GITHUB_APP_ID`, `GITHUB_PRIVATE_KEY_PATH`, `GITHUB_INSTALLATION_ID`
- **GITHUB_ORG** — Target organization name

### Claude Code (AI Agent)
- **CLAUDE_CODE_OAUTH_TOKEN** — OAuth token for Claude Code authentication (NOT an API key)

### Docker Runtime
- **DOCKER_HOST** — Docker daemon socket path (typically `unix:///var/run/docker.sock`)
- **AGENT_WORKSPACE_BASE** — Base directory for agent container workspaces

### Security
- **CODETOREUM_SECRET_KEY** — Persistent JWT secret for authentication (must not change between restarts)
- **CODETOREUM_ENV** — Set to `production`

### Git (for repository operations)
- **GIT_USER** — Git user for commit operations
- **GIT_EMAIL** — Git email for commit operations

## Optional Infrastructure

These are optional but recommended for production:

- **REDIS_URL** — Redis connection for caching and event persistence
- **ELASTICSEARCH_URL** — Elasticsearch for advanced event store features
- **SIGNOZ_API_KEY** — Signoz for distributed tracing and observability

## Deployment Phases

Codetoreum is deployed in phases, each adding more capabilities:

- **Credential Infrastructure** — Credential documentation and validation
- **Core Orchestration** — Workflow execution and orchestration
- **Container-based Agents** — Containerized agent execution
- **Advanced Features** — Review cycles, repair cycles, multi-project support

## Monitoring and Observability

Production deployments should be configured with:

- **Distributed Tracing** — Signoz/Jaeger via OpenTelemetry
- **Metrics** — Prometheus for performance monitoring
- **Logging** — Structured logging with correlation IDs
- **Health Checks** — `/health` endpoint monitoring

## Troubleshooting

If credential validation fails:

1. Check environment variables are set: `env | grep -E "GITHUB|CLAUDE|DOCKER|CODETOREUM"`
2. Verify token scopes and permissions
3. Test individual services:
   - GitHub: `curl -H "Authorization: token $GITHUB_TOKEN" https://api.github.com/user`
   - Docker: `docker ps` or `docker info`
   - Claude Code: `claude --version`
4. Check logs in `/var/log/codetoreum/` for detailed error messages

## References

- [GitHub Authentication Setup](./GITHUB_APP_SETUP.md)
- [Production Configuration](../.env.production.example)
- [Credential Validation Script](../../src/codetoreum/cli/validate_credentials.py)
