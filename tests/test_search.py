"""Tests for Scholarlink search backends."""

import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from scholarlink.models import SearchResult
from scholarlink.search import SerperBackend, TavilyBackend, get_search_backend


def test_get_search_backend_serper() -> None:
    """get_search_backend returns SerperBackend for 'serper' when key is set."""
    with patch.dict("os.environ", {"SERPER_API_KEY": "test-key"}):
        backend = get_search_backend("serper")
    assert isinstance(backend, SerperBackend)


def test_get_search_backend_tavily() -> None:
    """get_search_backend returns TavilyBackend for 'tavily' when key is set."""
    with patch.dict("os.environ", {"TAVILY_API_KEY": "test-key"}):
        backend = get_search_backend("tavily")
    assert isinstance(backend, TavilyBackend)


def test_get_search_backend_unknown_raises() -> None:
    """get_search_backend raises for unknown provider."""
    with pytest.raises(ValueError, match="Unknown search_provider"):
        get_search_backend("unknown")


def test_serper_backend_missing_key_raises() -> None:
    """SerperBackend raises when SERPER_API_KEY is not set."""
    env = {k: v for k, v in os.environ.items() if k != "SERPER_API_KEY"}
    with patch.dict("os.environ", env, clear=True):
        with pytest.raises(ValueError, match="SERPER_API_KEY"):
            SerperBackend()


def test_serper_backend_empty_key_raises() -> None:
    """SerperBackend raises when SERPER_API_KEY is empty."""
    with patch.dict("os.environ", {"SERPER_API_KEY": ""}):
        with pytest.raises(ValueError, match="SERPER_API_KEY"):
            SerperBackend()


@pytest.mark.asyncio
async def test_serper_backend_search_returns_search_results() -> None:
    """SerperBackend.search returns list of SearchResult from organic results."""
    import os

    with patch.dict("os.environ", {"SERPER_API_KEY": "test-key"}):
        backend = SerperBackend()
    mock_response = MagicMock()
    mock_response.json.return_value = {
        "organic": [
            {"title": "Jane Doe | LinkedIn", "link": "https://linkedin.com/in/janedoe", "snippet": "Profile"},
            {"title": "Other", "link": "https://other.com", "snippet": "Other site"},
        ]
    }
    mock_response.raise_for_status = MagicMock()

    with patch("httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client_cls.return_value = mock_client

        results = await backend.search("Jane Doe LinkedIn Profile", max_results=10)

    assert len(results) == 2
    assert results[0].title == "Jane Doe | LinkedIn"
    assert results[0].url == "https://linkedin.com/in/janedoe"
    assert results[1].url == "https://other.com"


@pytest.mark.asyncio
async def test_serper_backend_search_respects_max_results() -> None:
    """SerperBackend.search returns at most max_results items."""
    with patch.dict("os.environ", {"SERPER_API_KEY": "test-key"}):
        backend = SerperBackend()
    mock_response = MagicMock()
    mock_response.json.return_value = {
        "organic": [
            {"title": f"Result {i}", "link": f"https://example.com/{i}", "snippet": ""}
            for i in range(15)
        ]
    }
    mock_response.raise_for_status = MagicMock()

    with patch("httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client_cls.return_value = mock_client

        results = await backend.search("query", max_results=3)

    assert len(results) == 3


def test_tavily_backend_missing_key_raises() -> None:
    """TavilyBackend raises when TAVILY_API_KEY is not set."""
    env = {k: v for k, v in os.environ.items() if k != "TAVILY_API_KEY"}
    with patch.dict("os.environ", env, clear=True):
        with pytest.raises(ValueError, match="TAVILY_API_KEY"):
            TavilyBackend()


@pytest.mark.asyncio
async def test_tavily_backend_search_returns_search_results() -> None:
    """TavilyBackend.search returns list of SearchResult from Tavily response."""
    with patch.dict("os.environ", {"TAVILY_API_KEY": "test-key"}):
        backend = TavilyBackend()

    expected = [
        SearchResult(
            title="Jane Doe | LinkedIn",
            snippet="Profile",
            url="https://linkedin.com/in/jane",
        )
    ]

    with patch("asyncio.to_thread", new_callable=AsyncMock, return_value=expected):
        results = await backend.search("Jane Doe LinkedIn Profile", max_results=10)

    assert len(results) == 1
    assert results[0].url == "https://linkedin.com/in/jane"
    assert results[0].title == "Jane Doe | LinkedIn"
