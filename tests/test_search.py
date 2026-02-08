"""Tests for Scholarlink search backend (Google)."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from scholarlink.models import SearchResult
from scholarlink.search import (
    BrowserBackend,
    GoogleBackend,
    get_search_backend,
    _linkedin_verbose,
)


def test_get_search_backend_google() -> None:
    """get_search_backend returns GoogleBackend for 'google'."""
    backend = get_search_backend("google")
    assert isinstance(backend, GoogleBackend)


def test_get_search_backend_browser() -> None:
    """get_search_backend returns BrowserBackend for 'browser'."""
    backend = get_search_backend("browser")
    assert isinstance(backend, BrowserBackend)


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


@pytest.mark.asyncio
async def test_browser_backend_search_returns_search_results() -> None:
    """BrowserBackend.search returns list of SearchResult from mocked Playwright."""
    mock_first = MagicMock()
    mock_first.get_attribute = AsyncMock(return_value="https://www.linkedin.com/in/janedoe/")
    mock_first.text_content = AsyncMock(
        side_effect=["Jane Doe | LinkedIn", "Profile description"]
    )

    mock_block = MagicMock()
    mock_block.locator.return_value.first = mock_first

    mock_consent_first = MagicMock()
    mock_consent_first.is_visible = AsyncMock(return_value=False)

    mock_locator = MagicMock()
    mock_locator.first = mock_consent_first
    mock_locator.all = AsyncMock(return_value=[mock_block])

    mock_page = MagicMock()
    mock_page.goto = AsyncMock()
    mock_page.locator.return_value = mock_locator
    mock_page.wait_for_selector = AsyncMock()
    mock_page.wait_for_timeout = AsyncMock()

    mock_context = MagicMock()
    mock_context.new_page = AsyncMock(return_value=mock_page)

    mock_browser = MagicMock()
    mock_browser.new_context = AsyncMock(return_value=mock_context)
    mock_browser.close = AsyncMock()

    mock_p = MagicMock()
    mock_p.chromium.launch = AsyncMock(return_value=mock_browser)

    class FakePlaywright:
        async def __aenter__(self) -> MagicMock:
            return mock_p

        async def __aexit__(self, *args: object) -> None:
            pass

    backend = BrowserBackend()
    with patch("playwright.async_api.async_playwright", return_value=FakePlaywright()):
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
