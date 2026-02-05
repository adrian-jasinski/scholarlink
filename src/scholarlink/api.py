"""Public API for Scholarlink."""

from scholarlink.crawler import extract_authors_from_url
from scholarlink.linkedin_lookup import search_linkedin_profiles
from scholarlink.models import AuthorInfo, LinkedInLookupResult
from scholarlink.search import SearchBackend

__all__ = ["extract_authors", "find_linkedin_profiles"]


async def extract_authors(
    url: str,
    *,
    mode: str = "normal",
    cloudflare_manual: bool = False,
) -> tuple[list[AuthorInfo], str]:
    """
    Extract publication authors from a scientific paper URL.

    Crawls the page with Crawl4AI and uses LLM extraction to obtain
    author details (name, affiliation, contact, ORCID, other).

    Args:
        url: Full URL of the paper (e.g. bioRxiv or PNAS article page).
        mode: "normal" or "stealth". See MODE_HELP in crawler.
        cloudflare_manual: If True and the URL is on a protected domain, show
            the browser and wait so the user can complete the Cloudflare
            challenge manually.

    Returns:
        Tuple of (list of AuthorInfo, CSV string with one line per author).

    Raises:
        ExtractionError: If the crawl or extraction fails.
    """
    return await extract_authors_from_url(url, mode=mode, cloudflare_manual=cloudflare_manual)


async def find_linkedin_profiles(
    authors: list[AuthorInfo],
    *,
    search_backend: SearchBackend | None = None,
    max_results: int | None = None,
) -> list[LinkedInLookupResult]:
    """
    Find LinkedIn profile URLs for each author via search and LLM review.

    For each author, searches for "{name} LinkedIn Profile", sends results to the
    configured LLM, and returns one URL (confidence >= 75), up to 10 URLs
    (50-75), or not_found (< 50).

    Args:
        authors: List of AuthorInfo from e.g. extract_authors.
        search_backend: Optional search backend; uses config search_provider if None.
        max_results: Max search results per author; uses config search_max_results if None.

    Returns:
        List of LinkedInLookupResult, one per author.
    """
    return await search_linkedin_profiles(
        authors,
        search_backend=search_backend,
        max_results=max_results,
    )
