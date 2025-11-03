"""
Authentication Infrastructure

This module provides authentication components for the Codetoreum API.
Currently implements a simple token-based authentication system similar to JupyterLab.
"""

from codetoreum.infrastructure.auth.simple_token_auth import SimpleTokenAuthManager

__all__ = ["SimpleTokenAuthManager"]
