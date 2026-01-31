"""Tests for Scholarlink public API."""

from unittest.mock import AsyncMock, patch

import pytest

from scholarlink.api import extract_authors
from scholarlink.models import AuthorInfo


@pytest.mark.asyncio
async def test_extract_authors_returns_result_from_crawler() -> None:
    """extract_authors returns (list[AuthorInfo], csv_str) from extract_authors_from_url."""
    authors = [AuthorInfo(name="A")]
    csv_str = "name,affiliation,contact,orcid,other\nA,,,,"

    with patch(
        "scholarlink.api.extract_authors_from_url",
        new_callable=AsyncMock,
        return_value=(authors, csv_str),
    ):
        result = await extract_authors("https://example.com/paper")
    assert result[0] == authors
    assert result[1] == csv_str


@pytest.mark.asyncio
async def test_extract_authors_forwards_mode_and_cloudflare_manual() -> None:
    """extract_authors forwards mode and cloudflare_manual to extract_authors_from_url."""
    authors = [AuthorInfo(name="Alice")]
    csv_str = "name,affiliation,contact,orcid,other\nAlice,,,,"

    with patch(
        "scholarlink.api.extract_authors_from_url",
        new_callable=AsyncMock,
        return_value=(authors, csv_str),
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
