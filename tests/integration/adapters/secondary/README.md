# Secondary Adapter Integration Tests

This directory contains integration tests for the production secondary adapters in Phase 2.4.

## Adapters Tested

### 1. GitHubTicketAdapter
Tests for GitHub Issues integration via GitHub REST API.

**Requirements:**
- `GITHUB_TOKEN` environment variable with valid GitHub personal access token
- `GITHUB_TEST_ORG` environment variable (optional, defaults to "test-org")
- `GITHUB_TEST_REPO` environment variable (optional, defaults to "test-repo")
- Test repository must exist and token must have appropriate permissions

**Test Coverage:**
- Get work item by ID
- List work items with filters
- Search work items
- Create and update work items
- Add and retrieve comments
- Webhook registration/unregistration
- Error handling (not found, invalid input)

### 2. ClaudeCodeAdapter
Tests for Claude Code CLI integration.

**Requirements:**
- `ANTHROPIC_API_KEY` environment variable with valid Anthropic API key
- Claude CLI installed and available in PATH
- Internet connection for API calls

**Test Coverage:**
- Configuration validation
- Simple prompt execution
- Streaming execution
- Conversation management
- Model information retrieval
- Token counting
- Error handling (authentication, CLI not found)

### 3. DockerContainerAdapter
Tests for Docker container operations.

**Requirements:**
- Docker daemon running
- Docker CLI installed
- User has permissions to run Docker commands
- Internet connection for pulling images

**Test Coverage:**
- Run simple commands
- Environment variables
- Volume mounts
- Streaming logs
- Container lifecycle (create, start, stop, remove)
- Exec in running container
- List and inspect containers
- Image operations (pull, exists check)
- Error handling (image not found, container not running)

### 4. GitRepositoryAdapter
Tests for Git repository operations.

**Requirements:**
- Git CLI installed and available in PATH
- Filesystem permissions for temporary directories

**Test Coverage:**
- Clone repository
- Create and checkout branches
- Commit workflow
- Commit info and history
- Merge branches
- Diff between refs
- File content retrieval
- Remote management
- Error handling (invalid paths, conflicts)

## Running Tests

### Run All Integration Tests
```bash
pytest tests/integration/adapters/secondary/ -v
```

### Run Specific Adapter Tests
```bash
# GitHub adapter
pytest tests/integration/adapters/secondary/test_github_ticket_adapter.py -v

# Claude Code adapter
pytest tests/integration/adapters/secondary/test_claude_code_adapter.py -v

# Docker adapter
pytest tests/integration/adapters/secondary/test_docker_container_adapter.py -v

# Git adapter
pytest tests/integration/adapters/secondary/test_git_repository_adapter.py -v
```

### Run with Coverage
```bash
pytest tests/integration/adapters/secondary/ --cov=codetoreum.adapters.secondary --cov-report=html
```

### Skip Tests Requiring External Services
Integration tests automatically skip if required environment variables or dependencies are not available.

```bash
# Run without GitHub (tests will skip)
unset GITHUB_TOKEN
pytest tests/integration/adapters/secondary/test_github_ticket_adapter.py -v

# Run without Claude API (tests will skip)
unset ANTHROPIC_API_KEY
pytest tests/integration/adapters/secondary/test_claude_code_adapter.py -v
```

## Test Markers

All tests in this directory are marked with `@pytest.mark.integration`.

To run only integration tests:
```bash
pytest -m integration
```

To exclude integration tests:
```bash
pytest -m "not integration"
```

## Environment Setup

### Example .env File
```bash
# GitHub
GITHUB_TOKEN=ghp_your_token_here
GITHUB_TEST_ORG=your-org
GITHUB_TEST_REPO=your-test-repo

# Anthropic
ANTHROPIC_API_KEY=sk-ant-your-key-here

# Docker (usually no config needed if Docker is running)

# Git (usually no config needed)
```

### Docker Setup
```bash
# Start Docker daemon
sudo systemctl start docker

# Add user to docker group (Linux)
sudo usermod -aG docker $USER
newgrp docker

# Verify Docker is working
docker run hello-world
```

### Claude CLI Setup
```bash
# Install Claude CLI (if not already installed)
npm install -g @anthropic-ai/claude-code

# Verify installation
claude --version
```

## CI/CD Considerations

These integration tests can be run in CI/CD pipelines with appropriate setup:

1. **GitHub Actions**: Use secrets for API keys, enable Docker service
2. **GitLab CI**: Use protected variables, docker:dind service
3. **Jenkins**: Configure credentials, Docker plugin

Example GitHub Actions workflow:
```yaml
name: Integration Tests

on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest

    services:
      docker:
        image: docker:dind

    steps:
      - uses: actions/checkout@v2

      - name: Set up Python
        uses: actions/setup-python@v2
        with:
          python-version: '3.11'

      - name: Install dependencies
        run: |
          pip install -r requirements.txt
          pip install pytest pytest-asyncio

      - name: Run integration tests
        env:
          GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
          ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }}
        run: |
          pytest tests/integration/adapters/secondary/ -v
```

## Troubleshooting

### Tests Skip Unexpectedly
- Check that required environment variables are set
- Verify external services (Docker, Git, Claude CLI) are installed
- Ensure network connectivity for API calls

### Docker Tests Fail
- Verify Docker daemon is running: `docker ps`
- Check Docker permissions: `docker run hello-world`
- Pull required images manually: `docker pull alpine:latest`

### GitHub Tests Fail
- Verify token has correct permissions (repo scope)
- Check rate limiting: GitHub allows 5000 requests/hour
- Ensure test repository exists and is accessible

### Claude Tests Fail
- Verify API key is valid and has credits
- Check Claude CLI installation: `claude --version`
- Ensure network can reach api.anthropic.com

### Git Tests Fail
- Verify Git is installed: `git --version`
- Check filesystem permissions
- Ensure temp directory is writable

## Performance Notes

- Integration tests are slower than unit tests (seconds vs milliseconds)
- GitHub API has rate limits (5000 req/hour authenticated)
- Docker operations may require image pulls (can take minutes on first run)
- Claude API calls cost tokens (consider cost when running frequently)
- Git operations on large repos may be slow

## Best Practices

1. **Run integration tests separately** from unit tests in CI/CD
2. **Cache dependencies** (Docker images, pip packages)
3. **Use test-specific resources** (dedicated test repository, test API keys)
4. **Clean up resources** (containers, temp files) even if tests fail
5. **Monitor costs** for API-based tests (Claude, GitHub)
6. **Set reasonable timeouts** to prevent hanging tests

## Further Reading

- [GitHub REST API Documentation](https://docs.github.com/en/rest)
- [Anthropic Claude API Documentation](https://docs.anthropic.com/)
- [Docker SDK for Python](https://docker-py.readthedocs.io/)
- [GitPython Documentation](https://gitpython.readthedocs.io/)
