"""Public API for Scholarlink."""

from scholarlink.crawler import extract_authors_from_url
from scholarlink.models import AuthorInfo

__all__ = ["extract_authors"]


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
