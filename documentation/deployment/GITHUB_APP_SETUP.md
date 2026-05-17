# GitHub App Setup for Codetoreum

This guide documents how to set up GitHub authentication for Codetoreum in production.

## Overview

Codetoreum requires GitHub integration to:
- Manage issues and pull requests
- Update project boards
- Access code repositories
- Retrieve CI/CD pipeline status

You can authenticate with either:
1. **Personal Access Token (PAT)** — Simpler setup, best for single-user or small teams
2. **GitHub App** — Recommended for organizations, better security and permissions control

## Option 1: Personal Access Token (PAT)

### Prerequisites
- GitHub account with write access to the target organization/repositories

### Steps

1. **Create a Personal Access Token**
   - Go to https://github.com/settings/tokens
   - Click "Generate new token" → "Generate new token (classic)"
   - Name: `codetoreum-prod` (or similar)
   - Expiration: Set to no expiration or 1 year (plan for rotation)
   - Select required scopes:
     - ✓ `repo` — Full control of private repositories
     - ✓ `read:project` — Read access to GitHub Projects
     - ✓ `read:org` — Read organization data
     - ✓ `read:user` — Read user profile data
   - **Do NOT select**: `admin:repo_hook` (webhook management) — not required for MVP

2. **Configure Codetoreum**
   - Copy the token value
   - Add to `.env.production`:
     ```bash
     GITHUB_TOKEN=ghs_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
     GITHUB_ORG=your-organization-name
     ```

3. **Validate**
   ```bash
   python -m codetoreum.cli.validate_credentials
   ```

### Security Considerations
- **Store securely**: Use a secrets manager (e.g., AWS Secrets Manager, HashiCorp Vault) in production
- **Rotation**: Rotate the token every 90 days
- **Scoping**: The token grants access to all repositories in the organization
- **Audit**: GitHub logs all PAT access to the organization

## Option 2: GitHub App (Recommended for Organizations)

GitHub Apps provide finer-grained permission control and better security isolation compared to Personal Access Tokens.

### Prerequisites
- GitHub organization owner or admin access to organization settings
- Ability to install apps in the organization

### Steps

#### Step 1: Create a GitHub App

1. Go to https://github.com/organizations/{your-org}/settings/apps/new
2. Fill in the app details:
   - **App name**: `Codetoreum` (or `codetoreum-prod`)
   - **Homepage URL**: `https://codetoreum.example.com` (your deployment URL)
   - **Webhook URL**: `https://codetoreum.example.com/webhooks/github` (can be configured later)
   - **Webhook active**: ✓ (enable but webhook integration is post-MVP)

3. **Permissions** — Select required permissions:
   - **Repository Permissions**:
     - Contents: `Read & write` (for repository operations)
     - Issues: `Read & write` (for issue management)
     - Pull requests: `Read & write` (for PR handling)
     - Commit statuses: `Read & write` (for CI/CD integration)
   - **Organization Permissions**:
     - Members: `Read-only` (for team access)
     - Projects: `Read & write` (for board management)

4. **Events** — Subscribe to webhook events (post-MVP concern):
   - Leave unchecked for now
   - Will be configured in Phase #855 (webhook integration)

5. **Install App**
   - Click "Create GitHub App"
   - On the app page, click "Install App"
   - Select organization
   - Select repositories (choose specific repos or all)
   - Authorize

#### Step 2: Configure Codetoreum

1. **Get App Credentials**
   - Go to your app settings page: https://github.com/organizations/{your-org}/settings/apps/codetoreum
   - Note the **App ID** (e.g., `123456`)
   - Under "Private keys", click "Generate a private key"
   - Save the `.pem` file securely

2. **Set Environment Variables**
   - Store the private key file securely (e.g., `/etc/codetoreum/github-app.pem`)
   - Add to `.env.production`:
     ```bash
     GITHUB_APP_ID=123456
     GITHUB_PRIVATE_KEY_PATH=/etc/codetoreum/github-app.pem
     GITHUB_INSTALLATION_ID=99999999
     GITHUB_ORG=your-organization-name
     ```

3. **Get Installation ID**
   - If not known, Codetoreum will attempt to discover it from the app installation
   - Or find it in: GitHub App settings → Installations → {your-org} → View

3. **Validate**
   ```bash
   python -m codetoreum.cli.validate_credentials
   ```

### Security Considerations
- **Private Key**: Store the `.pem` file securely (not in Git, use secrets manager)
- **Permissions**: GitHub Apps use fine-grained permissions (no access to unselected repositories)
- **Rotation**: Private key can be regenerated at any time without downtime
- **Audit**: All GitHub App actions are audited in organization settings
- **Least Privilege**: Only grant permissions actually used by Codetoreum

## Validation

After setup, validate your GitHub configuration:

```bash
# Check credentials are set
python -m codetoreum.cli.validate_credentials

# Expected output for successful configuration:
# ✓ PASSED ADAPTERS:
# ├─ ticket (GitHubTicketAdapter)
# ├─ board (GitHubBoardAdapter)
# ├─ code_review (GitHubCodeReviewAdapter)
# └─ ...
```

## Troubleshooting

### "GITHUB_TOKEN not set or invalid"
- Verify token is in `.env.production` with `GITHUB_TOKEN=` prefix
- Check token has not expired
- Verify token has required scopes (`repo`, `read:project`, `read:org`)

### "Repository access denied"
- For PAT: Ensure token scopes include `repo` (full repository access)
- For App: Install app in repositories (or "All repositories" option)
- For Organization: Ensure user has write access to target repositories

### "GitHub App authentication failed"
- Verify `GITHUB_APP_ID` is correct
- Verify `GITHUB_PRIVATE_KEY_PATH` points to valid `.pem` file
- Verify `GITHUB_INSTALLATION_ID` matches your organization's installation

## Migration: PAT to GitHub App

If initially deploying with a PAT and want to migrate to a GitHub App:

1. Create GitHub App (see Step 1 above)
2. Install the app in your repositories
3. Update `.env.production`:
   ```bash
   # Remove (or comment out):
   # GITHUB_TOKEN=...

   # Add:
   GITHUB_APP_ID=...
   GITHUB_PRIVATE_KEY_PATH=...
   GITHUB_INSTALLATION_ID=...
   ```
4. Validate: `python -m codetoreum.cli.validate_credentials`
5. Restart Codetoreum

## References

- GitHub Personal Access Tokens: https://github.com/settings/tokens
- Creating GitHub Apps: https://docs.github.com/en/apps/creating-github-apps/creating-a-github-app
- GitHub App Permissions: https://docs.github.com/en/apps/creating-github-apps/managing-github-apps/choosing-permissions-for-a-github-app
- Installing GitHub Apps: https://docs.github.com/en/apps/using-github-apps/installing-an-app-in-your-organization

## Related Configuration

For complete production setup, also configure:
- **Docker**: `DOCKER_HOST` (container runtime)
- **Claude Code**: `CLAUDE_CODE_OAUTH_TOKEN` (AI agent)
- **Redis** (optional): `REDIS_URL` (caching and event persistence)
- **Elasticsearch** (optional): `ELASTICSEARCH_URL` (advanced event store)

See `.env.production.example` for complete configuration guide.
