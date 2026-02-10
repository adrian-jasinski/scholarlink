"""Search backend for LinkedIn profile lookup (Google, Brave API, or Chromium browser)."""

import asyncio
import os
import random
import sys
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlencode, urlparse

from typing import Protocol

import httpx

from scholarlink.models import SearchResult


def _linkedin_verbose() -> bool:
    """Return True if SCHOLARLINK_LINKEDIN_VERBOSE is set (e.g. 1, true)."""
    v = os.getenv("SCHOLARLINK_LINKEDIN_VERBOSE", "").strip().lower()
    return v in ("1", "true", "yes")


def _random_user_agent() -> str:
    """Return a random realistic Chrome user agent for different platforms."""
    agents = [
        # Windows Chrome
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Windows NT 11.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
        # macOS Chrome
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
        # Linux Chrome
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
    ]
    return random.choice(agents)


def _random_viewport() -> dict[str, int]:
    """Return a random realistic viewport size."""
    viewports = [
        {"width": 1920, "height": 1080},
        {"width": 1366, "height": 768},
        {"width": 1536, "height": 864},
        {"width": 1440, "height": 900},
        {"width": 1280, "height": 720},
        {"width": 1600, "height": 900},
    ]
    return random.choice(viewports)


def _random_delay(min_ms: int = 500, max_ms: int = 2000) -> int:
    """Return a random delay in milliseconds for human-like behavior."""
    return random.randint(min_ms, max_ms)


class SearchBackend(Protocol):
    """Protocol for search backends: one async method returning list of SearchResult."""

    async def search(self, query: str, max_results: int = 10) -> list[SearchResult]:
        """Run a search and return up to max_results results (title, snippet, url)."""
        ...


class GoogleBackend:
    """Web search via Google (scraping). Free, no API key. Matches manual Google search results."""

    async def search(self, query: str, max_results: int = 10) -> list[SearchResult]:
        """Search Google and return results as SearchResult list."""
        from googlesearch import search as google_search  # type: ignore[import-untyped]

        def _sync_search() -> list[SearchResult]:
            out: list[SearchResult] = []
            try:
                for r in google_search(query, num_results=max_results, advanced=True):
                    title = getattr(r, "title", None) or ""
                    url = getattr(r, "url", None) or ""
                    description = getattr(r, "description", None) or ""
                    if url:
                        out.append(SearchResult(title=title, snippet=description, url=url))
            except Exception as e:
                if _linkedin_verbose():
                    print(f"Google search failed: {e}", file=sys.stderr)
                return []
            return out

        return await asyncio.to_thread(_sync_search)


def _extract_url_from_google_redirect(href: str) -> str | None:
    """Extract real URL from Google's /url?q=... redirect link."""
    if not href or "google.com" in href:
        return None
    if href.startswith("/url?"):
        parsed = urlparse(href)
        qs = parse_qs(parsed.query)
        for key in ("q", "url"):
            if key in qs and qs[key]:
                return unquote(qs[key][0])
    return href if href.startswith("http") else None


class BrowserBackend:
    """
    Web search via Google using a real Chromium browser (Playwright) with anti-detection.
    Avoids 429/CAPTCHA that scraping often triggers. Requires: uv run python -m playwright install chromium

    Features:
    - Stealth mode with anti-detection arguments
    - Random user agents and viewports
    - Human-like random delays
    - Persistent browser context (optional) for cookies
    - Proxy support (optional)
    """

    def __init__(
        self,
        *,
        timeout_ms: int = 15000,
        consent_wait_ms: int = 2000,
        headless: bool = True,
        use_stealth: bool = True,
        persistent_context: bool = False,
        user_data_dir: str | None = None,
        proxy: str | None = None,
        debug_wait_seconds: float = 5.0,
    ) -> None:
        self._timeout_ms = timeout_ms
        self._consent_wait_ms = consent_wait_ms
        self._headless = headless
        self._use_stealth = use_stealth
        self._persistent_context = persistent_context
        self._user_data_dir = user_data_dir
        self._proxy = proxy
        self._debug_wait_seconds = debug_wait_seconds

    def _get_stealth_args(self) -> list[str]:
        """Return Chromium launch arguments for stealth mode."""
        return [
            "--disable-blink-features=AutomationControlled",
            "--disable-dev-shm-usage",
            "--disable-web-security",
            "--disable-features=IsolateOrigins,site-per-process",
            "--no-sandbox",
            "--disable-setuid-sandbox",
            "--disable-infobars",
            "--window-position=0,0",
            "--ignore-certificate-errors",
            "--ignore-certificate-errors-spki-list",
            "--disable-extensions",
            "--disable-gpu",
            "--disable-background-timer-throttling",
            "--disable-backgrounding-occluded-windows",
            "--disable-renderer-backgrounding",
            "--disable-features=TranslateUI",
            "--disable-ipc-flooding-protection",
            "--enable-features=NetworkService,NetworkServiceInProcess",
            "--force-color-profile=srgb",
            "--metrics-recording-only",
            "--mute-audio",
        ]

    async def search(self, query: str, max_results: int = 10) -> list[SearchResult]:
        """Search Google with Chromium (with anti-detection) and return results as SearchResult list."""
        from playwright.async_api import async_playwright

        out: list[SearchResult] = []
        url = "https://www.google.com/search"
        params = {"q": query, "num": min(max_results + 2, 20), "hl": "en"}
        full_url = f"{url}?{urlencode(params)}"

        try:
            async with async_playwright() as p:
                # Configure launch options
                launch_options: dict = {
                    "headless": self._headless,
                }

                if self._use_stealth:
                    launch_options["args"] = self._get_stealth_args()

                if self._proxy:
                    launch_options["proxy"] = {"server": self._proxy}

                browser = await p.chromium.launch(**launch_options)

                # Use persistent context if enabled (saves cookies)
                if self._persistent_context:
                    user_data = self._user_data_dir or str(Path.home() / ".scholarlink" / "browser-data")
                    Path(user_data).mkdir(parents=True, exist_ok=True)
                    context = await p.chromium.launch_persistent_context(
                        user_data,
                        headless=self._headless,
                        viewport=_random_viewport(),
                        user_agent=_random_user_agent(),
                        args=self._get_stealth_args() if self._use_stealth else [],
                        proxy={"server": self._proxy} if self._proxy else None,
                    )
                    page = context.pages[0] if context.pages else await context.new_page()
                else:
                    # Regular context with random fingerprint
                    context = await browser.new_context(
                        viewport=_random_viewport(),
                        user_agent=_random_user_agent(),
                    )
                    page = await context.new_page()

                # Add stealth JavaScript overrides
                if self._use_stealth:
                    await page.add_init_script("""
                        Object.defineProperty(navigator, 'webdriver', {
                            get: () => undefined
                        });
                        Object.defineProperty(navigator, 'plugins', {
                            get: () => [1, 2, 3, 4, 5]
                        });
                        Object.defineProperty(navigator, 'languages', {
                            get: () => ['en-US', 'en']
                        });
                        window.chrome = {
                            runtime: {}
                        };
                        Object.defineProperty(navigator, 'permissions', {
                            get: () => ({
                                query: () => Promise.resolve({ state: 'granted' })
                            })
                        });
                    """)

                # Navigate with random initial delay
                await page.wait_for_timeout(_random_delay(300, 800))
                await page.goto(full_url, wait_until="load", timeout=self._timeout_ms)
                await page.wait_for_timeout(_random_delay(1000, 2000))

                # Accept consent/cookies if present (EU etc.) – try several variants
                for consent_selector in (
                    'button:has-text("Accept all")',
                    'button:has-text("I agree")',
                    '[aria-label*="Accept all"]',
                    'button:has-text("Accept")',
                    'form[action*="consent"] button[type="submit"]',
                ):
                    try:
                        btn = page.locator(consent_selector).first
                        if await btn.is_visible():
                            await btn.click(timeout=self._consent_wait_ms)
                            await page.wait_for_timeout(1200)
                            break
                    except Exception:
                        pass

                # Wait for results; if selector never appears, still try extraction
                try:
                    await page.wait_for_selector(
                        "div.g, div[data-ved], .ezO2md, #search a[href^='/url?q=']",
                        state="attached",
                        timeout=10000,
                    )
                except Exception:
                    await page.wait_for_timeout(2000)

                # Selectors: div.g is classic; .ezO2md is used by googlesearch-python; div[data-ved] for newer layout
                blocks = await page.locator("div.g, div.ezO2md").all()
                seen_urls: set[str] = set()

                for block in blocks:
                    if len(out) >= max_results:
                        break
                    try:
                        link_el = block.locator("a[href^='/url?q='], a[href^='http']").first
                        href = await link_el.get_attribute("href")
                        if not href:
                            continue
                        real_url = _extract_url_from_google_redirect(href)
                        if not real_url or real_url in seen_urls:
                            continue
                        if "google.com" in real_url:
                            continue
                        seen_urls.add(real_url)

                        title_el = block.locator("h3, [role='heading'], .CVA68e").first
                        title = (await title_el.text_content()) or ""

                        snippet_el = block.locator(".VwiC3b, .FrIlee, .s, [data-sncf]").first
                        snippet = (await snippet_el.text_content()) or ""

                        out.append(SearchResult(title=title.strip(), snippet=snippet.strip(), url=real_url))
                    except Exception:
                        continue

                # Fallback if no blocks found (DOM changed or consent still blocking): use any result link in #search
                if not out:
                    try:
                        link_els = await page.locator("#search a[href^='/url?q=']").all()
                        for link_el in link_els:
                            if len(out) >= max_results:
                                break
                            href = await link_el.get_attribute("href")
                            if not href:
                                continue
                            real_url = _extract_url_from_google_redirect(href)
                            if not real_url or real_url in seen_urls or "google.com" in real_url:
                                continue
                            seen_urls.add(real_url)
                            title = (await link_el.text_content()) or ""
                            out.append(SearchResult(title=title.strip(), snippet="", url=real_url))
                    except Exception:
                        pass

                # Wait before closing if in non-headless mode (for debugging/inspection)
                if not self._headless and self._debug_wait_seconds > 0:
                    if _linkedin_verbose():
                        print(
                            f"Debug mode: waiting {self._debug_wait_seconds}s before closing browser...",
                            file=sys.stderr,
                        )
                    await page.wait_for_timeout(int(self._debug_wait_seconds * 1000))

                await browser.close()
        except Exception as e:
            if _linkedin_verbose():
                print(f"Browser search failed: {e}", file=sys.stderr)
            return []

        return out


class BraveBackend:
    """
    Web search via Brave Search API.

    Requires BRAVE_API_KEY environment variable. Free tier: 2,000 queries/month.
    API docs: https://api.search.brave.com/app/documentation/web-search/get-started
    """

    API_URL = "https://api.search.brave.com/res/v1/web/search"
    MAX_API_RESULTS = 20  # Brave API maximum

    def __init__(self, *, timeout_seconds: float = 30.0) -> None:
        """
        Initialize Brave search backend.

        Args:
            timeout_seconds: HTTP request timeout (default: 30.0)
        """
        self._timeout = timeout_seconds

    async def search(self, query: str, max_results: int = 10) -> list[SearchResult]:
        """
        Search Brave and return results as SearchResult list.

        Args:
            query: Search query string
            max_results: Maximum number of results to return (capped at 20 by API)

        Returns:
            List of SearchResult objects (empty list on error)
        """
        api_key = os.getenv("BRAVE_API_KEY")
        if not api_key:
            if _linkedin_verbose():
                print("BRAVE_API_KEY environment variable not set", file=sys.stderr)
            return []

        try:
            headers = {
                "Accept": "application/json",
                "X-Subscription-Token": api_key,
            }
            params = {
                "q": query,
                "count": min(max_results, self.MAX_API_RESULTS),
            }

            async with httpx.AsyncClient() as client:
                response = await client.get(
                    self.API_URL,
                    headers=headers,
                    params=params,
                    timeout=self._timeout,
                )
                response.raise_for_status()
                data = response.json()

            out: list[SearchResult] = []
            if "web" in data and "results" in data["web"]:
                for result in data["web"]["results"][:max_results]:
                    title = result.get("title", "") or ""
                    result_url = result.get("url", "") or ""
                    description = result.get("description", "") or ""
                    if result_url:
                        out.append(SearchResult(title=title, snippet=description, url=result_url))
            return out
        except httpx.HTTPError as e:
            if _linkedin_verbose():
                print(f"Brave search HTTP error: {e}", file=sys.stderr)
            return []
        except Exception as e:
            if _linkedin_verbose():
                print(f"Brave search failed: {e}", file=sys.stderr)
            return []


class BingBrowserBackend(BrowserBackend):
    """
    Web search via Bing using a real Chromium browser (Playwright) with anti-detection.
    Avoids 429/CAPTCHA that scraping often triggers. Requires: uv run python -m playwright install chromium

    Features (inherited from BrowserBackend):
    - Stealth mode with anti-detection arguments
    - Random user agents and viewports
    - Human-like random delays
    - Persistent browser context (optional) for cookies
    - Proxy support (optional)
    """

    async def search(self, query: str, max_results: int = 10) -> list[SearchResult]:
        """Search Bing with Chromium (with anti-detection) and return results as SearchResult list."""
        from playwright.async_api import async_playwright

        out: list[SearchResult] = []
        url = "https://www.bing.com/search"
        params = {"q": query, "count": min(max_results + 2, 20)}
        full_url = f"{url}?{urlencode(params)}"

        try:
            async with async_playwright() as p:
                # Configure launch options
                launch_options: dict = {
                    "headless": self._headless,
                }

                if self._use_stealth:
                    launch_options["args"] = self._get_stealth_args()

                if self._proxy:
                    launch_options["proxy"] = {"server": self._proxy}

                browser = await p.chromium.launch(**launch_options)

                # Use persistent context if enabled (saves cookies)
                if self._persistent_context:
                    user_data = self._user_data_dir or str(Path.home() / ".scholarlink" / "browser-data")
                    Path(user_data).mkdir(parents=True, exist_ok=True)
                    context = await p.chromium.launch_persistent_context(
                        user_data,
                        headless=self._headless,
                        viewport=_random_viewport(),
                        user_agent=_random_user_agent(),
                        args=self._get_stealth_args() if self._use_stealth else [],
                        proxy={"server": self._proxy} if self._proxy else None,
                    )
                    page = context.pages[0] if context.pages else await context.new_page()
                else:
                    # Regular context with random fingerprint
                    context = await browser.new_context(
                        viewport=_random_viewport(),
                        user_agent=_random_user_agent(),
                    )
                    page = await context.new_page()

                # Add stealth JavaScript overrides
                if self._use_stealth:
                    await page.add_init_script("""
                        Object.defineProperty(navigator, 'webdriver', {
                            get: () => undefined
                        });
                        Object.defineProperty(navigator, 'plugins', {
                            get: () => [1, 2, 3, 4, 5]
                        });
                        Object.defineProperty(navigator, 'languages', {
                            get: () => ['en-US', 'en']
                        });
                        window.chrome = {
                            runtime: {}
                        };
                        Object.defineProperty(navigator, 'permissions', {
                            get: () => ({
                                query: () => Promise.resolve({ state: 'granted' })
                            })
                        });
                    """)

                # Navigate with random initial delay
                await page.wait_for_timeout(_random_delay(300, 800))
                await page.goto(full_url, wait_until="load", timeout=self._timeout_ms)
                await page.wait_for_timeout(_random_delay(1000, 2000))

                # Accept consent/cookies if present (EU etc.) – try several variants
                for consent_selector in (
                    'button:has-text("Accept all")',
                    'button:has-text("I agree")',
                    'button:has-text("Accept")',
                    '#bnp_btn_accept',  # Bing-specific
                    '[aria-label*="Accept"]',
                ):
                    try:
                        btn = page.locator(consent_selector).first
                        if await btn.is_visible():
                            await btn.click(timeout=self._consent_wait_ms)
                            await page.wait_for_timeout(1200)
                            break
                    except Exception:
                        pass

                # Wait for results; if selector never appears, still try extraction
                try:
                    await page.wait_for_selector(
                        "li.b_algo, #b_results li",
                        state="attached",
                        timeout=10000,
                    )
                except Exception:
                    await page.wait_for_timeout(2000)

                # Bing-specific selectors: li.b_algo is the main result container
                blocks = await page.locator("li.b_algo").all()
                seen_urls: set[str] = set()

                for block in blocks:
                    if len(out) >= max_results:
                        break
                    try:
                        # Bing uses direct hrefs (no redirect like Google)
                        link_el = block.locator("h2 a").first
                        href = await link_el.get_attribute("href")
                        if not href or not href.startswith("http"):
                            continue
                        if href in seen_urls:
                            continue
                        if "bing.com" in href:
                            continue
                        seen_urls.add(href)

                        title_el = block.locator("h2 a").first
                        title = (await title_el.text_content()) or ""

                        # Bing snippet selectors
                        snippet_el = block.locator(".b_caption p, .b_snippet").first
                        snippet = (await snippet_el.text_content()) or ""

                        out.append(SearchResult(title=title.strip(), snippet=snippet.strip(), url=href))
                    except Exception:
                        continue

                # Fallback if no blocks found: use any result link in #b_results
                if not out:
                    try:
                        link_els = await page.locator("#b_results a[href^='http']").all()
                        for link_el in link_els:
                            if len(out) >= max_results:
                                break
                            href = await link_el.get_attribute("href")
                            if not href or not href.startswith("http"):
                                continue
                            if href in seen_urls or "bing.com" in href:
                                continue
                            seen_urls.add(href)
                            title = (await link_el.text_content()) or ""
                            out.append(SearchResult(title=title.strip(), snippet="", url=href))
                    except Exception:
                        pass

                # Wait before closing if in non-headless mode (for debugging/inspection)
                if not self._headless and self._debug_wait_seconds > 0:
                    if _linkedin_verbose():
                        print(
                            f"Debug mode: waiting {self._debug_wait_seconds}s before closing browser...",
                            file=sys.stderr,
                        )
                    await page.wait_for_timeout(int(self._debug_wait_seconds * 1000))

                await browser.close()
        except Exception as e:
            if _linkedin_verbose():
                print(f"Bing browser search failed: {e}", file=sys.stderr)
            return []

        return out


def get_search_backend(provider: str) -> SearchBackend:
    """Return a search backend for the given provider name ('google', 'browser', 'bing', or 'brave')."""
    from scholarlink.config import get_config

    p = provider.strip().lower()
    if p == "google":
        return GoogleBackend()
    if p == "brave":
        cfg = get_config()
        return BraveBackend(timeout_seconds=cfg.brave_timeout_seconds)
    if p == "browser":
        cfg = get_config()
        return BrowserBackend(
            headless=cfg.browser_headless,
            use_stealth=cfg.browser_use_stealth,
            persistent_context=cfg.browser_persistent_context,
            user_data_dir=cfg.browser_user_data_dir,
            proxy=cfg.browser_proxy,
            debug_wait_seconds=cfg.browser_debug_wait_seconds,
        )
    if p == "bing":
        cfg = get_config()
        return BingBrowserBackend(
            headless=cfg.browser_headless,
            use_stealth=cfg.browser_use_stealth,
            persistent_context=cfg.browser_persistent_context,
            user_data_dir=cfg.browser_user_data_dir,
            proxy=cfg.browser_proxy,
            debug_wait_seconds=cfg.browser_debug_wait_seconds,
        )
    raise ValueError(
        f"Unknown search_provider {provider!r}. Supported: 'google', 'brave', 'browser', 'bing'."
    )
