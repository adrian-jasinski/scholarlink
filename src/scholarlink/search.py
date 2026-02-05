"""Search backends for LinkedIn profile lookup (Serper, Tavily)."""

import asyncio
import os
from typing import Protocol

import httpx

from scholarlink.models import SearchResult

SERPER_API_URL = "https://google.serper.dev/search"


class SearchBackend(Protocol):
    """Protocol for search backends: one async method returning list of SearchResult."""

    async def search(self, query: str, max_results: int = 10) -> list[SearchResult]:
        """Run a search and return up to max_results results (title, snippet, url)."""
        ...


class SerperBackend:
    """Google search via Serper API. Requires SERPER_API_KEY env var."""

    def __init__(self) -> None:
        api_key = os.getenv("SERPER_API_KEY")
        if not api_key or not api_key.strip():
            raise ValueError(
                "SERPER_API_KEY is not set. Set it in the environment to use Serper search."
            )
        self._api_key: str = api_key.strip()

    async def search(self, query: str, max_results: int = 10) -> list[SearchResult]:
        """Search Google via Serper and return organic results as SearchResult list."""
        payload = {"q": query, "num": min(max_results, 20)}
        headers = {"X-API-KEY": self._api_key, "Content-Type": "application/json"}
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(SERPER_API_URL, json=payload, headers=headers)
            resp.raise_for_status()
            data = resp.json()
        organic = data.get("organic") or []
        results: list[SearchResult] = []
        for i, item in enumerate(organic):
            if i >= max_results:
                break
            if not isinstance(item, dict):
                continue
            link = item.get("link") or item.get("url")
            title = item.get("title") or ""
            snippet = item.get("snippet") or ""
            if link:
                results.append(SearchResult(title=title, snippet=snippet, url=link))
        return results


class TavilyBackend:
    """Web search via Tavily API. Requires TAVILY_API_KEY env var."""

    def __init__(self) -> None:
        api_key = os.getenv("TAVILY_API_KEY")
        if not api_key or not api_key.strip():
            raise ValueError(
                "TAVILY_API_KEY is not set. Set it in the environment to use Tavily search."
            )
        self._api_key: str = api_key.strip()

    async def search(self, query: str, max_results: int = 10) -> list[SearchResult]:
        """Search via Tavily and return results as SearchResult list."""
        from tavily import TavilyClient  # type: ignore[import-untyped]

        def _sync_search() -> list[SearchResult]:
            client = TavilyClient(api_key=self._api_key)
            response = client.search(query=query, max_results=max_results)
            out: list[SearchResult] = []
            for r in getattr(response, "results", []) or []:
                url = getattr(r, "url", None) or (r.get("url") if isinstance(r, dict) else None)
                title = getattr(r, "title", None) or (r.get("title") if isinstance(r, dict) else "") or ""
                content = getattr(r, "content", None) or (r.get("content") if isinstance(r, dict) else "") or ""
                if url:
                    out.append(SearchResult(title=title, snippet=content, url=url))
            return out

        return await asyncio.to_thread(_sync_search)


def get_search_backend(provider: str) -> SearchBackend:
    """Return a search backend for the given provider name ('serper' or 'tavily')."""
    p = provider.strip().lower()
    if p == "serper":
        return SerperBackend()
    if p == "tavily":
        return TavilyBackend()
    raise ValueError(
        f"Unknown search_provider {provider!r}. Use 'serper' or 'tavily'."
    )
