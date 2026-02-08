"""Search backend for LinkedIn profile lookup (Google or Chromium browser)."""

import asyncio
import os
import sys
from urllib.parse import parse_qs, unquote, urlencode, urlparse

from typing import Protocol

from scholarlink.models import SearchResult


def _linkedin_verbose() -> bool:
    """Return True if SCHOLARLINK_LINKEDIN_VERBOSE is set (e.g. 1, true)."""
    v = os.getenv("SCHOLARLINK_LINKEDIN_VERBOSE", "").strip().lower()
    return v in ("1", "true", "yes")


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
    Web search via Google using a real Chromium browser (Playwright).
    Avoids 429/CAPTCHA that scraping often triggers. Requires: uv run python -m playwright install chromium
    """

    def __init__(self, *, timeout_ms: int = 15000, consent_wait_ms: int = 2000) -> None:
        self._timeout_ms = timeout_ms
        self._consent_wait_ms = consent_wait_ms

    async def search(self, query: str, max_results: int = 10) -> list[SearchResult]:
        """Search Google with Chromium and return results as SearchResult list."""
        from playwright.async_api import async_playwright

        out: list[SearchResult] = []
        url = "https://www.google.com/search"
        params = {"q": query, "num": min(max_results + 2, 20), "hl": "en"}
        full_url = f"{url}?{urlencode(params)}"

        try:
            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=True)
                context = await browser.new_context(
                    viewport={"width": 1280, "height": 720},
                    user_agent=(
                        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
                    ),
                )
                page = await context.new_page()
                await page.goto(full_url, wait_until="load", timeout=self._timeout_ms)
                await page.wait_for_timeout(1500)

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

                await browser.close()
        except Exception as e:
            if _linkedin_verbose():
                print(f"Browser search failed: {e}", file=sys.stderr)
            return []

        return out


def get_search_backend(provider: str) -> SearchBackend:
    """Return a search backend for the given provider name ('google' or 'browser')."""
    p = provider.strip().lower()
    if p == "google":
        return GoogleBackend()
    if p == "browser":
        return BrowserBackend()
    raise ValueError(
        f"Unknown search_provider {provider!r}. Supported: 'google', 'browser'."
    )
