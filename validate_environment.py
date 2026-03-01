#!/usr/bin/env python3
"""
Development Environment Validation Script for Codetoreum

This script validates that the codetoreum-agent Docker container has all the
required tools and dependencies installed correctly.
"""

import subprocess
import sys
from collections.abc import Sequence


def run_command(cmd: Sequence[str] | str, description: str) -> bool:
    """Run a command in the Docker container and check the result."""
    print(f"Testing: {description}...", end=" ")
    try:
        # Build command as list, handling shell commands properly
        if isinstance(cmd, str):
            docker_cmd = ["docker", "run", "--rm", "codetoreum-agent:latest", "sh", "-c", cmd]
        else:
            docker_cmd = ["docker", "run", "--rm", "codetoreum-agent:latest"] + list(cmd)

        result = subprocess.run(docker_cmd, capture_output=True, text=True, timeout=30, check=False)
        if result.returncode == 0:
            output = result.stdout.strip()
            if output:
                print(f"✓ PASS - {output}")
            else:
                print("✓ PASS")
            return True
        print(f"✗ FAIL - {result.stderr.strip()}")
        return False
    except subprocess.TimeoutExpired:
        print("✗ FAIL - Command timed out")
        return False
    except Exception as e:
        print(f"✗ FAIL - {e!s}")
        return False


def main() -> None:
    """Run all validation tests."""
    print("=" * 70)
    print("Codetoreum Agent Environment Validation")
    print("=" * 70)
    print()

    tests = [
        # Critical CLI tools (REQUIRED)
        (["which", "claude"], "Claude CLI availability"),
        (["claude", "--version"], "Claude CLI version"),
        (["which", "git"], "Git CLI availability"),
        (["git", "--version"], "Git CLI version"),
        (["which", "gh"], "GitHub CLI availability"),
        (["gh", "--version"], "GitHub CLI version"),
        # Python environment
        (["python3", "--version"], "Python version"),
        (["pip", "--version"], "pip version"),
        # Core Python dependencies
        ("python3 -c 'import fastapi'", "FastAPI import"),
        ("python3 -c 'import sqlalchemy'", "SQLAlchemy import"),
        ("python3 -c 'import redis'", "Redis import"),
        ("python3 -c 'import docker'", "Docker SDK import"),
        ("python3 -c 'import pytest'", "pytest import"),
        ("python3 -c 'import git'", "GitPython import"),
        # Build tools
        (["which", "gcc"], "GCC availability"),
        (["which", "make"], "make availability"),
    ]

    results = []
    for cmd, description in tests:
        results.append(run_command(cmd, description))

    print()
    print("=" * 70)
    total = len(results)
    passed = sum(results)
    failed = total - passed

    print(f"Results: {passed}/{total} tests passed")

    if failed > 0:
        print(f"⚠️  {failed} test(s) failed")
        sys.exit(1)
    else:
        print("✓ All tests passed! Environment is ready.")
        sys.exit(0)


if __name__ == "__main__":
    main()
