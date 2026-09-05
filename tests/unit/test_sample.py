"""Sample test file to verify pytest configuration."""

import pytest


@pytest.mark.unit
def test_basic_assertion() -> None:
    """Test basic assertion to verify pytest works."""
    assert True


@pytest.mark.unit
def test_sample_fixture(sample_work_item_data: dict[str, str]) -> None:
    """Test that fixtures are loaded correctly."""
    assert sample_work_item_data["id"] == "issue-1"
    assert "title" in sample_work_item_data


@pytest.mark.unit
@pytest.mark.asyncio
async def test_async_function() -> None:
    """Test async function support."""
    result = await async_add(2, 3)
    assert result == 5


async def async_add(a: int, b: int) -> int:
    """Simple async function for testing.

    Args:
        a: First number
        b: Second number

    Returns:
        Sum of a and b
    """
    return a + b
