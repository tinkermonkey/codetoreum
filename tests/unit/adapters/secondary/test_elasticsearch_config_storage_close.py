"""Unit tests for ElasticsearchConfigStorage client-ownership on close.

The store must close its Elasticsearch client on shutdown only when it owns it
(owns_client=True, the production resolver path). A store handed an
externally-owned client (the default, used by tests sharing one client across
stores) must NOT close it — otherwise close() pulls the rug out from other
users and, in production, the unowned client leaks its aiohttp session.
"""

from unittest.mock import AsyncMock

import pytest

from codetoreum.adapters.secondary.elasticsearch_config_storage import (
    ElasticsearchConfigStorage,
)


@pytest.mark.asyncio
async def test_close_closes_client_when_owned():
    client = AsyncMock()
    storage = ElasticsearchConfigStorage(
        es_client=client,
        create_index_templates=False,
        owns_client=True,
    )

    await storage.close()

    client.close.assert_awaited_once()


@pytest.mark.asyncio
async def test_close_leaves_externally_owned_client_open():
    client = AsyncMock()
    storage = ElasticsearchConfigStorage(
        es_client=client,
        create_index_templates=False,
        # owns_client defaults to False
    )

    await storage.close()

    client.close.assert_not_awaited()
