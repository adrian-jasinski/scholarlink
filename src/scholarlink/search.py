"""Search backend for LinkedIn profile lookup (Google; free, no API key)."""

import asyncio
import os
import sys
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


def get_search_backend(provider: str) -> SearchBackend:
    """Return a search backend for the given provider name ('google')."""
    p = provider.strip().lower()
    if p == "google":
        return GoogleBackend()
    raise ValueError(f"Unknown search_provider {provider!r}. Only 'google' is supported.")
