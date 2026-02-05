"""Tests for Scholarlink search backend (DuckDuckGo)."""

from unittest.mock import AsyncMock, patch

import pytest

from scholarlink.models import SearchResult
from scholarlink.search import DuckDuckGoBackend, get_search_backend


def test_get_search_backend_duckduckgo() -> None:
    """get_search_backend returns DuckDuckGoBackend for 'duckduckgo'."""
    backend = get_search_backend("duckduckgo")
    assert isinstance(backend, DuckDuckGoBackend)


def test_get_search_backend_unknown_raises() -> None:
    """get_search_backend raises for unknown provider."""
    with pytest.raises(ValueError, match="Unknown search_provider"):
        get_search_backend("unknown")


@pytest.mark.asyncio
async def test_duckduckgo_backend_search_returns_search_results() -> None:
    """DuckDuckGoBackend.search returns list of SearchResult from DDGS.text()."""
    backend = DuckDuckGoBackend()
    mock_results = [
        {"title": "Jane Doe | LinkedIn", "href": "https://linkedin.com/in/janedoe", "body": "Profile"},
        {"title": "Other", "href": "https://other.com", "body": "Other site"},
    ]

    def _fake_sync_search() -> list[SearchResult]:
        return [
            SearchResult(title=r["title"], snippet=r.get("body", ""), url=r["href"])
            for r in mock_results
        ]

    with patch("asyncio.to_thread", new_callable=AsyncMock, return_value=_fake_sync_search()):
        results = await backend.search("Jane Doe LinkedIn Profile", max_results=10)

    assert len(results) == 2
    assert results[0].title == "Jane Doe | LinkedIn"
    assert results[0].url == "https://linkedin.com/in/janedoe"
    assert results[1].url == "https://other.com"


@pytest.mark.asyncio
async def test_duckduckgo_backend_search_maps_body_to_snippet() -> None:
    """DuckDuckGo result 'body' is mapped to SearchResult.snippet."""
    backend = DuckDuckGoBackend()
    mock_results = [{"title": "T", "href": "https://x.com", "body": "Snippet text"}]

    def _fake_sync_search() -> list[SearchResult]:
        return [SearchResult(title=r["title"], snippet=r.get("body", ""), url=r["href"]) for r in mock_results]

    with patch("asyncio.to_thread", new_callable=AsyncMock, return_value=_fake_sync_search()):
        results = await backend.search("query", max_results=5)

    assert results[0].snippet == "Snippet text"
