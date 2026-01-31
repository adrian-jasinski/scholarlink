"""Tests for Scholarlink public API."""

from unittest.mock import AsyncMock, patch

import pytest

from scholarlink.api import extract_authors


@pytest.mark.asyncio
async def test_extract_authors_returns_result_from_crawler() -> None:
    """extract_authors returns the tuple from extract_authors_from_url."""
    with patch(
        "scholarlink.api.extract_authors_from_url",
        new_callable=AsyncMock,
        return_value=(["A"], "A"),
    ):
        result = await extract_authors("https://example.com/paper")
    assert result == (["A"], "A")


@pytest.mark.asyncio
async def test_extract_authors_forwards_mode_and_cloudflare_manual() -> None:
    """extract_authors forwards mode and cloudflare_manual to extract_authors_from_url."""
    with patch(
        "scholarlink.api.extract_authors_from_url",
        new_callable=AsyncMock,
        return_value=(["Alice"], "Alice"),
    ) as mock_extract:
        await extract_authors(
            "https://example.com/paper",
            mode="stealth",
            cloudflare_manual=True,
        )
        mock_extract.assert_called_once_with(
            "https://example.com/paper",
            mode="stealth",
            cloudflare_manual=True,
        )
