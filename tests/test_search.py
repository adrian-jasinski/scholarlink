"""Tests for Scholarlink search backend (Google)."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from scholarlink.models import SearchResult
from scholarlink.search import (
    BingBrowserBackend,
    BraveBackend,
    BrowserBackend,
    GoogleBackend,
    get_search_backend,
    _linkedin_verbose,
    _random_user_agent,
    _random_viewport,
    _random_delay,
)


def test_get_search_backend_google() -> None:
    """get_search_backend returns GoogleBackend for 'google'."""
    backend = get_search_backend("google")
    assert isinstance(backend, GoogleBackend)


def test_get_search_backend_brave() -> None:
    """get_search_backend returns BraveBackend for 'brave'."""
    backend = get_search_backend("brave")
    assert isinstance(backend, BraveBackend)


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
    # Mock link element (for result extraction)
    mock_link_first = MagicMock()
    mock_link_first.get_attribute = AsyncMock(return_value="https://www.linkedin.com/in/janedoe/")

    # Mock title element
    mock_title_first = MagicMock()
    mock_title_first.text_content = AsyncMock(return_value="Jane Doe | LinkedIn")

    # Mock snippet element
    mock_snippet_first = MagicMock()
    mock_snippet_first.text_content = AsyncMock(return_value="Profile description")

    # Mock block locator (returns different elements based on selector)
    mock_block = MagicMock()
    def block_locator_side_effect(selector: str) -> MagicMock:
        if "a[href" in selector:
            mock = MagicMock()
            mock.first = mock_link_first
            return mock
        elif "h3" in selector or "heading" in selector:
            mock = MagicMock()
            mock.first = mock_title_first
            return mock
        else:  # snippet selectors
            mock = MagicMock()
            mock.first = mock_snippet_first
            return mock
    mock_block.locator = MagicMock(side_effect=block_locator_side_effect)

    # Mock consent button (not visible)
    mock_consent_first = MagicMock()
    mock_consent_first.is_visible = AsyncMock(return_value=False)

    # Mock page locator (returns different things based on selector)
    def page_locator_side_effect(selector: str) -> MagicMock:
        mock_loc = MagicMock()
        if "button" in selector or "consent" in selector.lower():
            mock_loc.first = mock_consent_first
        elif "div.g" in selector or "ezO2md" in selector:
            mock_loc.all = AsyncMock(return_value=[mock_block])
        else:
            mock_loc.all = AsyncMock(return_value=[])
            mock_loc.first = mock_consent_first
        return mock_loc

    mock_page = MagicMock()
    mock_page.goto = AsyncMock()
    mock_page.locator = MagicMock(side_effect=page_locator_side_effect)
    mock_page.wait_for_selector = AsyncMock()
    mock_page.wait_for_timeout = AsyncMock()
    mock_page.add_init_script = AsyncMock()  # Required for stealth JS injection

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


def test_random_user_agent() -> None:
    """_random_user_agent returns a valid Chrome user agent string."""
    agent = _random_user_agent()
    assert isinstance(agent, str)
    assert "Mozilla/5.0" in agent
    assert "Chrome" in agent
    assert "Safari/537.36" in agent
    # Test that multiple calls can return different agents (with high probability)
    agents = {_random_user_agent() for _ in range(20)}
    assert len(agents) > 1  # Should get at least 2 different agents in 20 tries


def test_random_viewport() -> None:
    """_random_viewport returns a valid viewport dict with width and height."""
    viewport = _random_viewport()
    assert isinstance(viewport, dict)
    assert "width" in viewport
    assert "height" in viewport
    assert isinstance(viewport["width"], int)
    assert isinstance(viewport["height"], int)
    assert viewport["width"] > 0
    assert viewport["height"] > 0
    # Test that multiple calls can return different viewports (with high probability)
    viewports = {(v["width"], v["height"]) for v in (_random_viewport() for _ in range(20))}
    assert len(viewports) > 1  # Should get at least 2 different viewports in 20 tries


def test_random_delay() -> None:
    """_random_delay returns an int in the specified range."""
    # Test default range (500-2000)
    delay = _random_delay()
    assert isinstance(delay, int)
    assert 500 <= delay <= 2000
    # Test custom range
    delay = _random_delay(100, 200)
    assert 100 <= delay <= 200
    # Test that multiple calls return different values (with high probability)
    delays = {_random_delay(100, 1000) for _ in range(20)}
    assert len(delays) > 1  # Should get at least 2 different delays in 20 tries


def test_browser_backend_with_stealth_disabled() -> None:
    """BrowserBackend can be created with stealth disabled."""
    backend = BrowserBackend(use_stealth=False)
    assert backend._use_stealth is False
    assert backend._headless is True  # Default


def test_browser_backend_with_headless_disabled() -> None:
    """BrowserBackend can be created with headless disabled."""
    backend = BrowserBackend(headless=False)
    assert backend._headless is False
    assert backend._use_stealth is True  # Default


def test_browser_backend_with_proxy() -> None:
    """BrowserBackend can be configured with proxy."""
    backend = BrowserBackend(proxy="http://proxy.example.com:8080")
    assert backend._proxy == "http://proxy.example.com:8080"


def test_browser_backend_with_persistent_context() -> None:
    """BrowserBackend can use persistent context."""
    backend = BrowserBackend(persistent_context=True)
    assert backend._persistent_context is True


def test_browser_backend_with_user_data_dir() -> None:
    """BrowserBackend can use custom user data directory."""
    backend = BrowserBackend(user_data_dir="/custom/path")
    assert backend._user_data_dir == "/custom/path"


def test_browser_backend_with_debug_wait_seconds() -> None:
    """BrowserBackend can use custom debug wait seconds."""
    backend = BrowserBackend(debug_wait_seconds=10.0)
    assert backend._debug_wait_seconds == 10.0


def test_browser_backend_debug_wait_defaults() -> None:
    """BrowserBackend has default debug_wait_seconds of 5.0."""
    backend = BrowserBackend()
    assert backend._debug_wait_seconds == 5.0


def test_browser_backend_get_stealth_args() -> None:
    """BrowserBackend._get_stealth_args returns a list of stealth arguments."""
    backend = BrowserBackend()
    args = backend._get_stealth_args()
    assert isinstance(args, list)
    assert len(args) > 0
    assert "--disable-blink-features=AutomationControlled" in args
    assert "--no-sandbox" in args


def test_get_search_backend_browser_uses_config() -> None:
    """get_search_backend('browser') uses configuration from get_config()."""
    from scholarlink.config import reset_config
    import os

    # Reset config to force reload
    reset_config()

    # Set environment variables
    with patch.dict(
        os.environ,
        {
            "SCHOLARLINK_BROWSER_HEADLESS": "false",
            "SCHOLARLINK_BROWSER_USE_STEALTH": "false",
            "SCHOLARLINK_BROWSER_PROXY": "http://test-proxy:8080",
        },
        clear=False,
    ):
        backend = get_search_backend("browser")
        assert isinstance(backend, BrowserBackend)
        assert backend._headless is False
        assert backend._use_stealth is False
        assert backend._proxy == "http://test-proxy:8080"

    # Clean up
    reset_config()


def test_get_search_backend_bing() -> None:
    """get_search_backend returns BingBrowserBackend for 'bing'."""
    backend = get_search_backend("bing")
    assert isinstance(backend, BingBrowserBackend)


@pytest.mark.asyncio
async def test_bing_browser_backend_search_returns_search_results() -> None:
    """BingBrowserBackend.search returns list of SearchResult from mocked Playwright."""
    # Mock link element (Bing uses direct hrefs in h2 a)
    mock_link_first = MagicMock()
    mock_link_first.get_attribute = AsyncMock(return_value="https://www.linkedin.com/in/janedoe/")
    mock_link_first.text_content = AsyncMock(return_value="Jane Doe | LinkedIn")

    # Mock snippet element
    mock_snippet_first = MagicMock()
    mock_snippet_first.text_content = AsyncMock(return_value="Profile description")

    # Mock Bing result block (li.b_algo)
    mock_block = MagicMock()
    def block_locator_side_effect(selector: str) -> MagicMock:
        if "h2 a" in selector:
            mock = MagicMock()
            mock.first = mock_link_first
            return mock
        else:  # .b_caption p, .b_snippet
            mock = MagicMock()
            mock.first = mock_snippet_first
            return mock
    mock_block.locator = MagicMock(side_effect=block_locator_side_effect)

    # Mock consent button (not visible)
    mock_consent_first = MagicMock()
    mock_consent_first.is_visible = AsyncMock(return_value=False)

    # Mock page locator (returns different things based on selector)
    def page_locator_side_effect(selector: str) -> MagicMock:
        mock_loc = MagicMock()
        if "button" in selector or "#bnp_btn_accept" in selector:
            mock_loc.first = mock_consent_first
        elif "li.b_algo" in selector:
            mock_loc.all = AsyncMock(return_value=[mock_block])
        else:
            mock_loc.all = AsyncMock(return_value=[])
            mock_loc.first = mock_consent_first
        return mock_loc

    mock_page = MagicMock()
    mock_page.goto = AsyncMock()
    mock_page.locator = MagicMock(side_effect=page_locator_side_effect)
    mock_page.wait_for_selector = AsyncMock()
    mock_page.wait_for_timeout = AsyncMock()
    mock_page.add_init_script = AsyncMock()

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

    backend = BingBrowserBackend()
    with patch("playwright.async_api.async_playwright", return_value=FakePlaywright()):
        results = await backend.search("Jane Doe LinkedIn Profile", max_results=10)

    assert len(results) == 1
    assert results[0].title == "Jane Doe | LinkedIn"
    assert results[0].url == "https://www.linkedin.com/in/janedoe/"
    assert results[0].snippet == "Profile description"


def test_bing_browser_backend_uses_config() -> None:
    """get_search_backend('bing') uses configuration from get_config()."""
    from scholarlink.config import reset_config
    import os

    reset_config()

    with patch.dict(
        os.environ,
        {
            "SCHOLARLINK_BROWSER_HEADLESS": "false",
            "SCHOLARLINK_BROWSER_USE_STEALTH": "false",
        },
        clear=False,
    ):
        backend = get_search_backend("bing")
        assert isinstance(backend, BingBrowserBackend)
        assert backend._headless is False
        assert backend._use_stealth is False

    reset_config()


@pytest.mark.asyncio
async def test_brave_backend_search_returns_search_results() -> None:
    """BraveBackend.search returns list of SearchResult from Brave API."""
    import os

    backend = BraveBackend(timeout_seconds=15.0)

    # Mock API response
    mock_api_response = {
        "web": {
            "results": [
                {
                    "title": "Jane Doe | LinkedIn",
                    "url": "https://www.linkedin.com/in/janedoe/",
                    "description": "Profile description",
                }
            ]
        }
    }

    # Mock httpx response
    mock_response = MagicMock()
    mock_response.json = MagicMock(return_value=mock_api_response)
    mock_response.raise_for_status = MagicMock()

    # Mock httpx client
    mock_client = MagicMock()
    mock_client.get = AsyncMock(return_value=mock_response)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock()

    with patch.dict(os.environ, {"BRAVE_API_KEY": "test-key"}, clear=False):
        with patch("httpx.AsyncClient", return_value=mock_client):
            results = await backend.search("Jane Doe LinkedIn Profile", max_results=10)

    assert len(results) == 1
    assert results[0].title == "Jane Doe | LinkedIn"
    assert results[0].url == "https://www.linkedin.com/in/janedoe/"
    assert results[0].snippet == "Profile description"


def test_brave_backend_with_custom_timeout() -> None:
    """BraveBackend can be configured with custom timeout."""
    backend = BraveBackend(timeout_seconds=60.0)
    assert backend._timeout == 60.0


def test_brave_backend_default_timeout() -> None:
    """BraveBackend has default timeout of 30.0."""
    backend = BraveBackend()
    assert backend._timeout == 30.0


def test_get_search_backend_brave_uses_config() -> None:
    """get_search_backend('brave') uses configuration from get_config()."""
    from scholarlink.config import reset_config
    import os

    reset_config()

    with patch.dict(
        os.environ,
        {"SCHOLARLINK_BRAVE_TIMEOUT_SECONDS": "45.0"},
        clear=False,
    ):
        backend = get_search_backend("brave")
        assert isinstance(backend, BraveBackend)
        assert backend._timeout == 45.0

    reset_config()
