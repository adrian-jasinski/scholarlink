"""Tests for Scholarlink search backend (Google)."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from scholarlink.models import SearchResult
from scholarlink.search import GoogleBackend, get_search_backend, _linkedin_verbose


def test_get_search_backend_google() -> None:
    """get_search_backend returns GoogleBackend for 'google'."""
    backend = get_search_backend("google")
    assert isinstance(backend, GoogleBackend)


def test_get_search_backend_duckduckgo_raises() -> None:
    """get_search_backend raises for 'duckduckgo' (removed)."""
    with pytest.raises(ValueError, match="Unknown search_provider"):
        get_search_backend("duckduckgo")


def test_get_search_backend_unknown_raises() -> None:
    """get_search_backend raises for unknown provider."""
    with pytest.raises(ValueError, match="Unknown search_provider"):
        get_search_backend("unknown")


@pytest.mark.asyncio
async def test_google_backend_search_returns_search_results() -> None:
    """GoogleBackend.search returns list of SearchResult from googlesearch.search."""
    backend = GoogleBackend()
    mock_result = MagicMock()
    mock_result.title = "Jane Doe | LinkedIn"
    mock_result.url = "https://www.linkedin.com/in/janedoe/"
    mock_result.description = "Profile description"

    def _fake_sync_search() -> list[SearchResult]:
        return [
            SearchResult(
                title=mock_result.title,
                snippet=mock_result.description,
                url=mock_result.url,
            )
        ]

    with patch("asyncio.to_thread", new_callable=AsyncMock, return_value=_fake_sync_search()):
        results = await backend.search("Jane Doe LinkedIn Profile", max_results=10)

    assert len(results) == 1
    assert results[0].title == "Jane Doe | LinkedIn"
    assert results[0].url == "https://www.linkedin.com/in/janedoe/"
    assert results[0].snippet == "Profile description"


def test_linkedin_verbose_env() -> None:
    """_linkedin_verbose returns True when SCHOLARLINK_LINKEDIN_VERBOSE is 1 or true."""
    import os

    with patch.dict(os.environ, {"SCHOLARLINK_LINKEDIN_VERBOSE": "1"}, clear=False):
        assert _linkedin_verbose() is True
    with patch.dict(os.environ, {"SCHOLARLINK_LINKEDIN_VERBOSE": "true"}, clear=False):
        assert _linkedin_verbose() is True
    with patch.dict(os.environ, {"SCHOLARLINK_LINKEDIN_VERBOSE": "0"}, clear=False):
        assert _linkedin_verbose() is False
