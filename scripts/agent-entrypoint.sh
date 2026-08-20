#!/bin/bash
# ============================================================================
# Agent Container Entrypoint
# ============================================================================
# Validates the git CLI environment and repairs common DinD mount issues
# before handing off to the requested command.
#
# Problem: In Docker-in-Docker (DinD), file bind mounts from the host
# sometimes appear as directories inside the container. When the orchestrator
# mounts /home/orchestrator/.gitconfig, it can become an empty directory
# instead of a file, which breaks every `git` operation that touches the
# global config.
#
# Solution: Detect the corruption at startup and tell git to skip the
# global config file via GIT_CONFIG_GLOBAL=/dev/null. Git will then use
# /etc/gitconfig (system-level) and GIT_AUTHOR_*/GIT_COMMITTER_* environment
# variables set by the orchestrator. If the mount is removable, remove it;
# if it's a busy mount point, bypass it.
# ============================================================================

set -euo pipefail

GITCONFIG_PATH="/home/orchestrator/.gitconfig"

# --- Fix corrupted .gitconfig (DinD directory-instead-of-file issue) --------
if [ -d "$GITCONFIG_PATH" ]; then
    echo "[agent-entrypoint] WARNING: $GITCONFIG_PATH is a directory (DinD mount corruption)." >&2
    # Try to remove it; if it's a busy mount point, bypass via env var instead
    if ! rm -rf "$GITCONFIG_PATH" 2>/dev/null; then
        echo "[agent-entrypoint] WARNING: Cannot remove (busy mount). Bypassing via GIT_CONFIG_GLOBAL." >&2
        export GIT_CONFIG_GLOBAL=/dev/null
    fi
fi

# If .gitconfig still exists but is not a regular file (e.g. broken symlink,
# or the rm above failed silently), bypass it
if [ -e "$GITCONFIG_PATH" ] && [ ! -f "$GITCONFIG_PATH" ]; then
    echo "[agent-entrypoint] WARNING: $GITCONFIG_PATH is not a regular file. Bypassing via GIT_CONFIG_GLOBAL." >&2
    export GIT_CONFIG_GLOBAL=/dev/null
fi

# --- Validate git CLI -------------------------------------------------------
if ! command -v git >/dev/null 2>&1; then
    echo "[agent-entrypoint] ERROR: git CLI not found in PATH" >&2
    exit 1
fi

# Quick sanity check: can git actually run?
if ! git --version >/dev/null 2>&1; then
    echo "[agent-entrypoint] ERROR: git CLI is present but non-functional" >&2
    exit 1
fi

# --- Validate git identity (via env vars or config) -------------------------
# The orchestrator sets GIT_AUTHOR_NAME/GIT_AUTHOR_EMAIL. If those are missing,
# fall back to whatever is in /etc/gitconfig.
if [ -z "${GIT_AUTHOR_NAME:-}" ] && ! git config user.name >/dev/null 2>&1; then
    echo "[agent-entrypoint] WARNING: No git user.name configured (env or gitconfig)" >&2
fi
if [ -z "${GIT_AUTHOR_EMAIL:-}" ] && ! git config user.email >/dev/null 2>&1; then
    echo "[agent-entrypoint] WARNING: No git user.email configured (env or gitconfig)" >&2
fi

# --- Fix gh CLI multi-account migration issue --------------------------------
# gh CLI v2.40.0+ attempts a one-time migration of its config format to support
# multiple accounts. If stale hosts.yml exists with an expired/invalid token,
# the migration fails with "cowardly refusing to continue with multi account
# migration" and blocks ALL gh commands. Fix: ensure config.yml has version: "1"
# and remove any stale hosts.yml so the migration is never triggered.
GH_CONFIG_DIR="${GH_CONFIG_DIR:-${XDG_CONFIG_HOME:-$HOME/.config}/gh}"
if [ -d "$GH_CONFIG_DIR" ]; then
    # Remove stale hosts.yml that could trigger the migration
    if [ -f "$GH_CONFIG_DIR/hosts.yml" ]; then
        echo "[agent-entrypoint] Clearing stale gh hosts.yml to prevent multi-account migration error." >&2
        rm -f "$GH_CONFIG_DIR/hosts.yml"
    fi
    # Ensure config.yml has version: "1" to mark migration as complete
    if [ -f "$GH_CONFIG_DIR/config.yml" ]; then
        if ! grep -q '^version:' "$GH_CONFIG_DIR/config.yml" 2>/dev/null; then
            echo 'version: "1"' >> "$GH_CONFIG_DIR/config.yml"
            echo "[agent-entrypoint] Added version marker to gh config.yml." >&2
        fi
    fi
else
    # Pre-seed gh config directory with version marker so migration never runs
    mkdir -p "$GH_CONFIG_DIR"
    echo 'version: "1"' > "$GH_CONFIG_DIR/config.yml"
fi

# --- Validate GitHub token permissions --------------------------------------
# Agents need GITHUB_TOKEN with 'actions' scope (or 'actions:read') to query
# GitHub Actions API (e.g. gh run list, gh run view) for CI status verification.
# This is a non-fatal check — the agent can still operate but CI status queries
# will fail at runtime without the correct scope.
if [ -n "${GITHUB_TOKEN:-}" ]; then
    # Use gh to probe the token scopes via a lightweight API call.
    # The X-OAuth-Scopes header in the response tells us what scopes the token has.
    TOKEN_SCOPES=$(gh api -i user 2>/dev/null | grep -i '^x-oauth-scopes:' | cut -d: -f2- | tr -d '[:space:]' || true)
    if [ -n "$TOKEN_SCOPES" ]; then
        # Check if 'actions' scope (or fine-grained equivalent) is present
        if ! echo "$TOKEN_SCOPES" | grep -qi 'actions'; then
            echo "[agent-entrypoint] WARNING: GITHUB_TOKEN is missing 'actions' scope." >&2
            echo "[agent-entrypoint] WARNING: CI status queries (gh run list/view) will fail." >&2
            echo "[agent-entrypoint] WARNING: Token scopes: $TOKEN_SCOPES" >&2
        fi
    fi
    # Fine-grained PATs don't return X-OAuth-Scopes, so skip the check for those.
    # The agent will get a clear 403 error at runtime if permissions are insufficient.
fi

# --- Setup SSH config if .ssh/ is writable ----------------------------------
if [ -d /home/orchestrator/.ssh ] || mkdir -p /home/orchestrator/.ssh 2>/dev/null; then
    chmod 700 /home/orchestrator/.ssh 2>/dev/null || true

    # Only create SSH config if .ssh/ is writable and config doesn't exist
    if [ ! -f /home/orchestrator/.ssh/config ]; then
        # Test if .ssh/ is writable
        if touch /home/orchestrator/.ssh/.write_test 2>/dev/null; then
            rm -f /home/orchestrator/.ssh/.write_test

            # Create SSH config with accept-new key checking
            cat > /home/orchestrator/.ssh/config <<'SSHEOF'
Host github.com
  StrictHostKeyChecking accept-new
  UserKnownHostsFile /home/orchestrator/.ssh/known_hosts
  IdentityFile /home/orchestrator/.ssh/id_github
SSHEOF
            chmod 600 /home/orchestrator/.ssh/config 2>/dev/null || true
        fi
    fi
fi || true

# --- Authenticate GitHub CLI if token is provided ---------------------------
if [ -n "${GITHUB_TOKEN:-}" ]; then
    mkdir -p /home/orchestrator/.config 2>/dev/null || true

    # Authenticate via token (fallback to gh auth, but don't fail if it errors)
    if command -v gh >/dev/null 2>&1; then
        echo "$GITHUB_TOKEN" | gh auth login --with-token >/dev/null 2>&1 || true
    fi
fi || true

# --- Validate Docker socket access (needed by testcontainers) -------------
# Integration tests use testcontainers to spin up Redis/Elasticsearch
# containers. The socket must be bind-mounted and the orchestrator user
# must have group-level access. Warn loudly if either condition fails so
# the operator can fix the mount / GID mismatch instead of chasing
# "Connection refused" timeouts 60 seconds into the test suite.
if [ -S /var/run/docker.sock ]; then
    if python3 -c "import docker; docker.from_env().ping()" 2>/dev/null; then
        echo "[agent-entrypoint] Docker socket access: OK" >&2
    else
        echo "[agent-entrypoint] WARNING: /var/run/docker.sock exists but is not accessible." >&2
        echo "[agent-entrypoint] WARNING: Testcontainers integration tests will fail." >&2
        echo "[agent-entrypoint] WARNING: Check that DOCKER_GID build arg matches the host docker group GID" >&2
        echo "[agent-entrypoint] WARNING:   Host GID: $(stat -c '%g' /var/run/docker.sock 2>/dev/null || echo 'unknown')" >&2
        echo "[agent-entrypoint] WARNING:   Container docker group GID: $(getent group docker 2>/dev/null | cut -d: -f3 || echo 'not found')" >&2
        echo "[agent-entrypoint] WARNING:   Current user groups: $(id)" >&2
    fi
else
    echo "[agent-entrypoint] INFO: /var/run/docker.sock not mounted. Testcontainers tests will be skipped." >&2
fi

# --- Pre-pull alpine:latest for workspace verification ---------------------
# The DockerContainerAdapter._verify_workspace_writable() method runs a
# throwaway alpine:latest container. If the image is missing and the daemon
# has no network access, the verification (and thus the whole agent run)
# fails. Pull it eagerly when the Docker socket is available.
if [ -S /var/run/docker.sock ] && command -v docker >/dev/null 2>&1; then
    if ! docker image inspect alpine:latest >/dev/null 2>&1; then
        echo "[agent-entrypoint] Pre-pulling alpine:latest for workspace verification..." >&2
        docker pull alpine:latest >/dev/null 2>&1 || \
            echo "[agent-entrypoint] WARNING: Could not pull alpine:latest. Workspace verification may fail." >&2
    fi
fi

# --- Hand off to the requested command --------------------------------------
exec "$@"
