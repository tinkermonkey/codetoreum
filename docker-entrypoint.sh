#!/bin/sh
# Docker entrypoint for agent containers
# Handles SSH config and GitHub CLI authentication setup
# Falls through to actual command on any error

set -e

# Setup SSH config if .ssh/ is writable
if [ -d /home/orchestrator/.ssh ] || mkdir -p /home/orchestrator/.ssh 2>/dev/null; then
    chmod 700 /home/orchestrator/.ssh 2>/dev/null || true

    # Only create SSH config if .ssh/ is writable and config doesn't exist
    if [ ! -f /home/orchestrator/.ssh/config ]; then
        # Test if .ssh/ is writable
        if touch /home/orchestrator/.ssh/.write_test 2>/dev/null; then
            rm -f /home/orchestrator/.ssh/.write_test

            # Create SSH config with accept-new key checking
            cat > /home/orchestrator/.ssh/config <<'EOF'
Host github.com
  StrictHostKeyChecking accept-new
  UserKnownHostsFile /home/orchestrator/.ssh/known_hosts
  IdentityFile /home/orchestrator/.ssh/id_github
EOF
            chmod 600 /home/orchestrator/.ssh/config 2>/dev/null || true
        fi
    fi
fi

# Authenticate GitHub CLI if token is provided
if [ -n "$GITHUB_TOKEN" ]; then
    mkdir -p /home/orchestrator/.config 2>/dev/null || true

    # Authenticate via token (fallback to gh auth)
    if command -v gh >/dev/null 2>&1; then
        echo "$GITHUB_TOKEN" | gh auth login --with-token >/dev/null 2>&1 || true
    fi
fi

# Execute the actual command
exec "$@"
