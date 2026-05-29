"""Credential providers for the Claude Code adapter.

A credential provider exposes a single ``async get_credential(key) -> str | None``
method. The strategies inside this package consume the protocol structurally;
new implementations only need to satisfy that contract.

This module ships two implementations:

- :class:`EnvironmentCredentialProvider` reads from ``os.environ``.
- :class:`StaticCredentialProvider` returns a pre-supplied mapping (useful
  for tests and for orchestrators that hold credentials in their own
  registry).

Production deployments may inject vault-backed providers (HashiCorp Vault,
AWS Secrets Manager, ...) by implementing the same protocol elsewhere.
"""

from __future__ import annotations

import os
from collections.abc import Mapping

from codetoreum.adapters.secondary.claude_code.strategies.host import (
    CredentialProviderProtocol,
)


class EnvironmentCredentialProvider(CredentialProviderProtocol):
    """Resolve credentials from the process environment."""

    async def get_credential(self, key: str) -> str | None:
        return os.environ.get(key)


class StaticCredentialProvider(CredentialProviderProtocol):
    """Return credentials from a pre-supplied mapping (test / vault adapter)."""

    def __init__(self, credentials: Mapping[str, str]) -> None:
        self._credentials = dict(credentials)

    async def get_credential(self, key: str) -> str | None:
        return self._credentials.get(key)


__all__ = [
    "EnvironmentCredentialProvider",
    "StaticCredentialProvider",
]
