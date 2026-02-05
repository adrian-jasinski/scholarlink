"""Search backend for LinkedIn profile lookup (DuckDuckGo, free, no API key)."""

import asyncio
from typing import Protocol

from scholarlink.models import SearchResult


class SearchBackend(Protocol):
    """Protocol for search backends: one async method returning list of SearchResult."""

    async def search(self, query: str, max_results: int = 10) -> list[SearchResult]:
        """Run a search and return up to max_results results (title, snippet, url)."""
        ...


class DuckDuckGoBackend:
    """Web search via DuckDuckGo. Free, no API key required."""

    async def search(self, query: str, max_results: int = 10) -> list[SearchResult]:
        """Search DuckDuckGo and return results as SearchResult list."""
        from duckduckgo_search import DDGS

        def _sync_search() -> list[SearchResult]:
            ddgs = DDGS()
            raw = list(ddgs.text(query, max_results=max_results))
            out: list[SearchResult] = []
            for r in raw:
                if not isinstance(r, dict):
                    continue
                url = r.get("href") or r.get("url")
                title = r.get("title") or ""
                body = r.get("body") or ""
                if url:
                    out.append(SearchResult(title=title, snippet=body, url=url))
            return out

        return await asyncio.to_thread(_sync_search)


def get_search_backend(provider: str) -> SearchBackend:
    """Return a search backend for the given provider name ('duckduckgo')."""
    p = provider.strip().lower()
    if p == "duckduckgo":
        return DuckDuckGoBackend()
    raise ValueError(
        f"Unknown search_provider {provider!r}. Use 'duckduckgo' (free, no API key)."
    )
