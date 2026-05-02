"""Application bootstrap module.

Provides bootstrapping infrastructure for both simulation and production modes.
- production_config: Production adapter selection configuration
- production_bootstrap: Production application bootstrap
"""

from .production_config import create_production_adapter_config

__all__ = ["create_production_adapter_config"]
