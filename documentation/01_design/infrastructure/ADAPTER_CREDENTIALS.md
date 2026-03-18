# Adapter Credentials Reference

This document specifies the environment variables required for each production adapter implementation, how to obtain them, validation procedures, and troubleshooting guidance.

## Quick Reference Table

| Adapter | Implementation | Required Environment Variables | Optional Variables |
|---------|----------------|--------------------------------|-------------------|
| board | GitHubBoardAdapter | GITHUB_TOKEN, GITHUB_ORG | GITHUB_API_URL |
| ticket | GitHubTicketAdapter | GITHUB_TOKEN, GITHUB_REPO | GITHUB_API_URL |
| discussion | GitHubDiscussionAdapter | GITHUB_TOKEN | - |
| review_cycle | GitHubCodeReviewAdapter | GITHUB_TOKEN | - |
| work_item_service | GitHubWorkItemService | GITHUB_TOKEN, GITHUB_REPO | - |
| version_control | *(Planned)* | *(TBD)* | - |
| llm | ClaudeCodeAdapter | CLAUDE_CODE_API_KEY or CLI auth | - |
| container | DockerContainerAdapter | Docker daemon socket | - |
| event_store | RedisEventStore | REDIS_URL or REDIS_HOST + REDIS_PORT | REDIS_PASSWORD |
| message_broker | RedisPubSubAdapter | REDIS_URL or REDIS_HOST + REDIS_PORT | REDIS_PASSWORD |
| lock_service | RedisLockService | REDIS_URL or REDIS_HOST + REDIS_PORT | REDIS_PASSWORD |
| storage | S3StorageAdapter | AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY, AWS_S3_BUCKET | AWS_REGION |
| config_store | DatabaseConfigStore | DATABASE_URL or POSTGRES_* | - |
| workflow_config | DatabaseWorkflowConfigService | DATABASE_URL or POSTGRES_* | - |
| notifier | SlackNotifierAdapter | SLACK_WEBHOOK_URL or SLACK_BOT_TOKEN | - |
| identity_service | GitHubIdentityService | GITHUB_TOKEN, GITHUB_ORG | GITHUB_API_URL |
| metrics | PrometheusMetricsAdapter | PROMETHEUS_URL | - |
| encryption | *(Planned)* | *(TBD)* | - |
| repair_cycle | *(Planned)* | *(TBD)* | - |
| project_manager | *(Planned)* | *(TBD)* | - |
| checkpoint_store | *(Planned)* | *(TBD)* | - |
| agent_repository | *(Planned)* | *(TBD)* | - |
| run_registry | *(Planned)* | *(TBD)* | - |
| branch_tracker | *(Planned)* | *(TBD)* | - |

---

## GitHub Adapters

### Common Prerequisites

All GitHub adapters require a **Personal Access Token (PAT)** or **GitHub App Installation Token**.

#### Obtaining a GitHub Personal Access Token (PAT)

1. Go to GitHub Settings: https://github.com/settings/tokens
2. Click "Generate new token" → "Generate new token (classic)"
3. Give it a descriptive name: "Codetoreum Integration"
4. Select required scopes:
   - `repo` - For repository access (issues, PRs, commits)
   - `project` - For project board access (if using GitHub Projects)
   - `read:org` - For organization access
5. Click "Generate token"
6. **Copy immediately** (you won't see it again)
7. Set environment variable: `export GITHUB_TOKEN="ghp_..."`

#### Token Scopes by Adapter

| Adapter | Scopes Required | Notes |
|---------|-----------------|-------|
| board, ticket, discussion, review_cycle | `repo`, `project` | Project board and issue management |
| work_item_service | `repo` | Work item CRUD operations |
| identity_service | `read:org` | User identification (bot vs. human) |

**Note**: A single PAT with `repo`, `project`, and `read:org` scopes can be reused across all GitHub adapters.

---

### board (GitHubBoardAdapter)

**Purpose**: Manage project board structure (columns, work items, ordering)

**Required Environment Variables:**
```bash
GITHUB_TOKEN="ghp_xxxxxxxxxxxx"  # Personal Access Token with repo, project scopes
GITHUB_ORG="your-org"             # GitHub organization name (e.g., "anthropic")
```

**Optional Environment Variables:**
```bash
GITHUB_API_URL="https://api.github.com"  # For GitHub Enterprise, use custom URL
GITHUB_API_VERSION="2022-11-28"          # GitHub GraphQL API version
```

**Obtaining GITHUB_ORG:**
```bash
# Your organization name (visible in URL: github.com/[ORG]/repo-name)
export GITHUB_ORG="my-organization"
```

**Validation:**
```bash
# Test token validity
curl -H "Authorization: token $GITHUB_TOKEN" https://api.github.com/user

# Test organization access
curl -H "Authorization: token $GITHUB_TOKEN" https://api.github.com/orgs/$GITHUB_ORG
```

**Common Errors:**

| Error | Cause | Solution |
|-------|-------|----------|
| 404 Not Found | Invalid token or org | Verify token is valid and org name is correct |
| 401 Unauthorized | Missing scopes | Regenerate token with `repo` and `project` scopes |
| 403 Forbidden | Insufficient permissions | User must have access to organization |

---

### ticket (GitHubTicketAdapter)

**Purpose**: Issue/ticket lifecycle management

**Required Environment Variables:**
```bash
GITHUB_TOKEN="ghp_xxxxxxxxxxxx"    # Personal Access Token with repo scope
GITHUB_REPO="org/repo-name"        # Repository in org/repo format
```

**Obtaining GITHUB_REPO:**
```bash
# Repository identifier in format org/repo
# Example: "anthropic/codetoreum"
export GITHUB_REPO="my-org/my-repo"
```

**Validation:**
```bash
# Test repository access
curl -H "Authorization: token $GITHUB_TOKEN" \
  https://api.github.com/repos/$GITHUB_REPO
```

**Common Errors:**

| Error | Cause | Solution |
|-------|-------|----------|
| 404 Not Found | Repo doesn't exist or not accessible | Verify org and repo names, ensure PAT has access |
| 422 Unprocessable Entity | Invalid repo format | Use org/repo format exactly |

---

### discussion (GitHubDiscussionAdapter)

**Purpose**: Comment and discussion thread management

**Required Environment Variables:**
```bash
GITHUB_TOKEN="ghp_xxxxxxxxxxxx"  # Personal Access Token with repo scope
```

**Notes:**
- Requires repository or organization context (inherited from board or ticket adapters)
- Discussions API requires `repo` scope

---

### review_cycle (GitHubCodeReviewAdapter)

**Purpose**: Pull request lifecycle and approval management

**Required Environment Variables:**
```bash
GITHUB_TOKEN="ghp_xxxxxxxxxxxx"  # Personal Access Token with repo scope
GITHUB_REPO="org/repo-name"      # Repository in org/repo format (from ticket adapter)
```

**Notes:**
- PR operations require write access to the repository
- Approval operations require reviewer status or admin access
- PAT must have `repo` scope including PR permissions

---

### work_item_service (GitHubWorkItemService)

**Purpose**: Work item CRUD operations and metadata

**Required Environment Variables:**
```bash
GITHUB_TOKEN="ghp_xxxxxxxxxxxx"  # Personal Access Token with repo scope
GITHUB_REPO="org/repo-name"      # Repository in org/repo format
```

---

### identity_service (GitHubIdentityService)

**Purpose**: Bot/human user identification

**Required Environment Variables:**
```bash
GITHUB_TOKEN="ghp_xxxxxxxxxxxx"  # Personal Access Token with read:org scope
GITHUB_ORG="your-org"             # Organization name
```

**Notes:**
- Used to identify whether a user is a bot or human
- Requires read access to organization members
- Usually shares GITHUB_ORG and GITHUB_TOKEN with board adapter

---

## Claude Code Adapter

### llm (ClaudeCodeAdapter)

**Purpose**: LLM provider integration for agent execution

**Authentication Methods:**

#### Option 1: API Key (Recommended for CI/CD)
```bash
CLAUDE_CODE_API_KEY="sk-xxx..."  # Claude Code API key from Anthropic
```

**Obtaining API Key:**
1. Contact Anthropic support or use Anthropic Console
2. Generate API key with appropriate scopes
3. Set environment variable: `export CLAUDE_CODE_API_KEY="sk_..."`

#### Option 2: CLI Authentication (Local Development)
```bash
# Authenticate via Claude Code CLI
claude-code auth login

# Token stored in ~/.claude-code/credentials.json
# ClaudeCodeAdapter will read credentials automatically
```

**Validation:**
```bash
# Test API key validity
curl -H "Authorization: Bearer $CLAUDE_CODE_API_KEY" \
  https://api.codetoreum.com/v1/health
```

**Common Errors:**

| Error | Cause | Solution |
|-------|-------|----------|
| 401 Unauthorized | Invalid or expired API key | Regenerate API key, ensure it's set correctly |
| 403 Forbidden | Insufficient permissions | Check API key scopes |
| Connection refused | Claude Code not running (CLI auth) | Ensure Claude Code CLI is installed and authenticated |

---

## Docker Container Adapter

### container (DockerContainerAdapter)

**Purpose**: Container runtime for isolated agent execution

**Required:**
- Docker daemon running and accessible
- User must have docker socket access

**Environment Variables:**
```bash
DOCKER_HOST="unix:///var/run/docker.sock"  # Default: uses socket
# OR for remote Docker:
DOCKER_HOST="tcp://docker-host:2375"
```

**Setup:**

#### Linux
```bash
# Docker must be installed and running
sudo systemctl start docker

# Add current user to docker group (optional, avoids sudo)
sudo usermod -ag docker $USER
newgrp docker  # Apply group immediately

# Verify access
docker ps
```

#### macOS
```bash
# Docker Desktop must be running
# Verify:
docker ps
```

#### Windows
```bash
# Docker Desktop must be running with WSL2 backend
# Verify:
docker ps
```

**Validation:**
```bash
# Test docker access
docker ps
docker pull ubuntu:20.04
```

**Common Errors:**

| Error | Cause | Solution |
|-------|-------|----------|
| Permission denied | Docker socket not accessible | Run with sudo or add user to docker group |
| Cannot connect to Docker | Docker not running | Start Docker daemon |
| Image not found | Required image not available | Pull image: `docker pull <image>` |

**Security Note**: Containers run with limited privileges:
- ❌ NO docker socket access (cannot create/manage containers)
- ❌ NO git/SSH credentials
- ❌ NO GitHub credentials
- ✅ Mounted project files (read/write or read-only)
- ✅ Project-level environment variables (selected)
- ✅ Internet access
- ✅ MCP server access

---

## Redis Adapters

### event_store, message_broker, lock_service (Redis)

**Purpose**:
- event_store: Domain event persistence and replay
- message_broker: Event pub/sub distribution
- lock_service: Distributed pipeline locking

**Required Environment Variables:**

Option 1: Connection URL
```bash
REDIS_URL="redis://localhost:6379/0"
# OR with authentication:
REDIS_URL="redis://:password@localhost:6379/0"
```

Option 2: Individual Components
```bash
REDIS_HOST="localhost"           # Default: localhost
REDIS_PORT="6379"                # Default: 6379
REDIS_DB="0"                     # Default: 0
REDIS_PASSWORD="secret"          # If authentication enabled
```

**Setup:**

#### Local Development
```bash
# Using Docker
docker run -d -p 6379:6379 redis:7-alpine

# OR native installation
brew install redis  # macOS
sudo apt-get install redis-server  # Ubuntu
```

#### Production
```bash
# Use managed Redis service:
# - AWS ElastiCache
# - Google Cloud Memorystore
# - Azure Cache for Redis
# - Self-hosted Redis cluster

# Set REDIS_URL with connection details
export REDIS_URL="redis://user:password@redis-host:6379/0"
```

**Validation:**
```bash
# Test Redis connection
redis-cli -u "$REDIS_URL" ping
# Should output: PONG

# Check memory usage
redis-cli -u "$REDIS_URL" info memory

# Monitor events (for debugging)
redis-cli -u "$REDIS_URL" MONITOR
```

**Common Errors:**

| Error | Cause | Solution |
|-------|-------|----------|
| Connection refused | Redis not running | Start Redis, verify host/port |
| WRONGPASS | Invalid password | Check REDIS_PASSWORD, verify credentials |
| NOAUTH required | Authentication needed | Set REDIS_PASSWORD or use Redis with auth enabled |
| Timeout | Network unreachable | Verify host/port accessible, check firewall |

**Performance Tuning:**
```bash
# Increase max connections (if needed for high concurrency)
redis-cli CONFIG SET maxclients 10000

# Enable persistence (if durability required)
redis-cli CONFIG SET save "900 1 300 10 60 10000"

# Check event store size
redis-cli --bigkeys -u "$REDIS_URL"
```

---

## Database Adapters

### config_store, workflow_config (Database)

**Purpose**:
- config_store: Configuration persistence
- workflow_config: Workflow definition management

**Required Environment Variables:**

Option 1: PostgreSQL URL
```bash
DATABASE_URL="postgresql://user:password@localhost:5432/codetoreum"
# Example: postgresql://postgres:mypass@db.example.com:5432/codetoreum
```

Option 2: Individual PostgreSQL Components
```bash
POSTGRES_USER="postgres"
POSTGRES_PASSWORD="mypassword"
POSTGRES_HOST="localhost"
POSTGRES_PORT="5432"
POSTGRES_DB="codetoreum"
```

**Setup:**

#### Local Development
```bash
# Using Docker
docker run -d \
  -e POSTGRES_USER=postgres \
  -e POSTGRES_PASSWORD=mypass \
  -e POSTGRES_DB=codetoreum \
  -p 5432:5432 \
  postgres:15-alpine

# Test connection
psql "$DATABASE_URL" -c "SELECT version();"
```

#### Production
```bash
# Use managed database:
# - AWS RDS PostgreSQL
# - Google Cloud SQL
# - Azure Database for PostgreSQL
# - Self-hosted PostgreSQL

export DATABASE_URL="postgresql://user:pass@db-host:5432/codetoreum"
```

**Database Initialization:**
```bash
# The application auto-initializes tables on startup
# But you can pre-initialize if needed:

python -m codetoreum.cli.init-db \
  --database-url "$DATABASE_URL"
```

**Validation:**
```bash
# Test database connection
psql "$DATABASE_URL" -c "SELECT 1;"

# Check existing tables
psql "$DATABASE_URL" -c "\dt"
```

**Common Errors:**

| Error | Cause | Solution |
|-------|-------|----------|
| FATAL: password authentication failed | Wrong credentials | Verify POSTGRES_USER, POSTGRES_PASSWORD |
| FATAL: database "codetoreum" does not exist | Database not created | Create DB: `createdb codetoreum` |
| Connection refused | PostgreSQL not running | Start PostgreSQL service |
| SSL certificate verify failed | SSL required but untrusted | Set `?sslmode=require` in URL, trust certificate |

---

## AWS S3 Adapter

### storage (S3StorageAdapter)

**Purpose**: Artifact storage for code, reports, logs

**Required Environment Variables:**
```bash
AWS_ACCESS_KEY_ID="AKIA..."          # AWS Access Key
AWS_SECRET_ACCESS_KEY="wJalrXUtnFE..." # AWS Secret Key
AWS_S3_BUCKET="codetoreum-artifacts"   # S3 bucket name
```

**Optional Environment Variables:**
```bash
AWS_REGION="us-west-2"                # Default: us-east-1
AWS_S3_KEY_PREFIX="artifacts/"        # Prefix for all uploads
```

**Obtaining AWS Credentials:**

1. Go to AWS IAM Console: https://console.aws.amazon.com/iam/
2. Create new user: "codetoreum-s3-user"
3. Attach policy: `AmazonS3FullAccess` (or restrict to specific bucket)
4. Create access key
5. Copy Access Key ID and Secret Access Key
6. Set environment variables

**Creating S3 Bucket:**
```bash
# Via AWS CLI
aws s3 mb s3://codetoreum-artifacts --region us-west-2

# Or via console: S3 → Create bucket
```

**IAM Policy (Least Privilege):**
```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "s3:GetObject",
        "s3:PutObject",
        "s3:DeleteObject"
      ],
      "Resource": "arn:aws:s3:::codetoreum-artifacts/*"
    },
    {
      "Effect": "Allow",
      "Action": ["s3:ListBucket"],
      "Resource": "arn:aws:s3:::codetoreum-artifacts"
    }
  ]
}
```

**Validation:**
```bash
# Test AWS credentials
aws s3 ls --region "$AWS_REGION"

# Test bucket access
aws s3 ls s3://$AWS_S3_BUCKET/ --region "$AWS_REGION"
```

**Common Errors:**

| Error | Cause | Solution |
|-------|-------|----------|
| InvalidAccessKeyId | Wrong access key | Verify AWS_ACCESS_KEY_ID |
| SignatureDoesNotMatch | Wrong secret key | Verify AWS_SECRET_ACCESS_KEY |
| NoSuchBucket | Bucket doesn't exist | Create bucket or use correct name |
| AccessDenied | Insufficient IAM permissions | Check IAM policy grants s3:GetObject, s3:PutObject |

---

## Slack Notifier Adapter

### notifier (SlackNotifierAdapter)

**Purpose**: Notifications for workflow events

**Required Environment Variables:**

Option 1: Webhook URL
```bash
SLACK_WEBHOOK_URL="https://hooks.slack.com/services/T00000000/B00000000/..."
```

Option 2: Bot Token (Recommended for multiple channels)
```bash
SLACK_BOT_TOKEN="xoxb-..."
```

**Setting Up Slack Webhook:**

1. Go to Slack App Management: https://api.slack.com/apps
2. Create new app (or select existing)
3. Enable "Incoming Webhooks"
4. Add New Webhook to Workspace
5. Select channel (or leave blank for default)
6. Copy Webhook URL
7. Set environment variable: `export SLACK_WEBHOOK_URL="https://hooks.slack.com/..."`

**Setting Up Slack Bot Token:**

1. Go to Slack App Management: https://api.slack.com/apps
2. Create new app (or select existing)
3. Go to "OAuth & Permissions"
4. Add scopes: `chat:write`, `channels:list`, `groups:list`
5. Install app to workspace
6. Copy "Bot User OAuth Token" (starts with `xoxb-`)
7. Set environment variable: `export SLACK_BOT_TOKEN="xoxb_..."`

**Validation:**
```bash
# Test webhook
curl -X POST "$SLACK_WEBHOOK_URL" \
  -H 'Content-Type: application/json' \
  -d '{"text":"Test notification from Codetoreum"}'

# Test bot token (should return 200)
curl -X POST "https://slack.com/api/auth.test" \
  -H "Authorization: Bearer $SLACK_BOT_TOKEN"
```

**Common Errors:**

| Error | Cause | Solution |
|-------|-------|----------|
| 404 Not Found | Invalid webhook URL | Generate new webhook URL, check format |
| No matching URL | Expired webhook | Generate new webhook URL |
| invalid_token | Invalid bot token | Regenerate token, verify it starts with xoxb- |

---

## Prometheus Metrics Adapter

### metrics (PrometheusMetricsAdapter)

**Purpose**: Metrics collection for observability

**Required Environment Variables:**
```bash
PROMETHEUS_URL="http://localhost:9090"  # Prometheus server URL
PROMETHEUS_PUSHGATEWAY_URL="http://localhost:9091"  # Optional: for push mode
```

**Setup:**

#### Local Development
```bash
# Using Docker
docker run -d \
  -p 9090:9090 \
  -v $(pwd)/prometheus.yml:/etc/prometheus/prometheus.yml \
  prom/prometheus:latest
```

#### Configuration (prometheus.yml)
```yaml
global:
  scrape_interval: 15s

scrape_configs:
  - job_name: 'codetoreum'
    static_configs:
      - targets: ['localhost:8000']  # Codetoreum app port
```

**Validation:**
```bash
# Test Prometheus connection
curl http://localhost:9090/api/v1/query?query=up

# Query metrics
curl 'http://localhost:9090/api/v1/query?query=workflow_started_total'
```

---

## Validation at Startup

The application validates all configured adapters at startup:

```python
bootstrap = SimulationApplicationBootstrap(config)
await bootstrap.setup()  # Raises AdapterConfigurationError if credentials missing
```

**Error Message Format:**
```
AdapterConfigurationError: Failed to configure adapter slot "board":
  - Implementation: "github"
  - Missing credentials: GITHUB_TOKEN, GITHUB_ORG
  - Solution: Set environment variables: export GITHUB_TOKEN="..." GITHUB_ORG="..."
```

---

## Credential Management Best Practices

### Development
```bash
# Use .env file (git-ignored)
cat > .env <<EOF
GITHUB_TOKEN=ghp_...
GITHUB_ORG=my-org
REDIS_URL=redis://localhost:6379/0
EOF

# Load in shell
source .env

# Or use direnv
cat > .envrc <<EOF
export $(cat .env | xargs)
EOF
direnv allow
```

### CI/CD
```bash
# Store credentials in:
# - GitHub Secrets (for GitHub Actions)
# - GitLab Variables (for GitLab CI)
# - Jenkins Credentials (for Jenkins)
# - Terraform/Ansible variables

# Example GitHub Actions:
env:
  GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
  REDIS_URL: ${{ secrets.REDIS_URL }}
```

### Production
```bash
# Use secure credential store:
# - AWS Secrets Manager
# - HashiCorp Vault
# - Kubernetes Secrets
# - Azure Key Vault

# Example (AWS):
export GITHUB_TOKEN=$(aws secretsmanager get-secret-value \
  --secret-id codetoreum/github_token \
  --query SecretString --output text)
```

---

## Troubleshooting

### "AdapterConfigurationError: Failed to configure adapter"

1. **Check which adapters are configured:**
   ```bash
   # Print current config
   python -c "from codetoreum.infrastructure.simulation.simulation_config import SimulationConfig; \
     c = SimulationConfig.create_fast_config('test'); \
     import json; print(json.dumps(c.adapters.__dict__, indent=2))"
   ```

2. **Verify all required credentials are set:**
   ```bash
   echo "GITHUB_TOKEN: $GITHUB_TOKEN"
   echo "REDIS_URL: $REDIS_URL"
   echo "AWS_ACCESS_KEY_ID: $AWS_ACCESS_KEY_ID"
   # etc.
   ```

3. **Test each credential:**
   See validation steps in each adapter section above

### "Connection refused" / "Connection timeout"

1. **Verify service is running:**
   - Docker: `docker ps`
   - Redis: `redis-cli ping`
   - PostgreSQL: `psql -c "SELECT 1;"`
   - GitHub: `curl -I https://api.github.com`

2. **Check network connectivity:**
   ```bash
   # Test DNS resolution
   nslookup redis-host.example.com

   # Test port accessibility
   nc -zv redis-host.example.com 6379
   ```

3. **Review firewall rules:**
   - Is the port accessible from application server?
   - Are security groups/network policies configured correctly?

### "Invalid credentials" / "Authentication failed"

1. **Verify credential format:**
   - GitHub token: `ghp_...` (classic) or `github_pat_...` (new)
   - AWS keys: `AKIA...` format
   - API keys: Often base64 encoded, no whitespace

2. **Check token expiration:**
   - GitHub PATs: Check "Expiration" date
   - AWS keys: Keys don't expire, but may be revoked
   - API keys: Check provider's console

3. **Verify scopes/permissions:**
   - GitHub: `repo`, `project`, `read:org`
   - AWS: IAM policy includes required actions
   - Slack: `chat:write`, `channels:list`, etc.

---

## Security Considerations

1. **Never commit credentials to Git:**
   - Use `.gitignore` for `.env` files
   - Store credentials in secure vaults
   - Rotate credentials regularly

2. **Use least privilege:**
   - GitHub: `repo` scope, not `admin:repo_hook`
   - AWS: Restrict to specific S3 bucket
   - Docker: Don't run as root

3. **Encrypt sensitive config:**
   - At rest: Use database encryption, S3 server-side encryption
   - In transit: Use HTTPS, SSL/TLS, encrypted connections
   - At rest in config: Consider `encryption` adapter (when production ready)

4. **Audit credential usage:**
   - Enable CloudTrail (AWS)
   - Check GitHub audit log
   - Review API access logs

---

## See Also

- `documentation/01_design/infrastructure/ADAPTER_PARITY_MATRIX.md` - Complete adapter inventory
- `scenarios/mixed_github_real.yaml` - Example mixed configuration
- `scenarios/mixed_full_real.yaml` - Example full production configuration
