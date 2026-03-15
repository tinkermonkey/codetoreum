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

# --- Hand off to the requested command --------------------------------------
exec "$@"
