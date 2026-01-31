"""Public API for Scholarlink."""

from scholarlink.crawler import extract_authors_from_url

__all__ = ["extract_authors"]


async def extract_authors(url: str) -> tuple[list[str], str]:
    """
    Extract publication authors from a scientific paper URL.

    Crawls the page with Crawl4AI and uses LLM extraction to obtain
    the list of author names.

    Args:
        url: Full URL of the paper (e.g. bioRxiv or PNAS article page).

    Returns:
        Tuple of (authors list, comma-separated authors string).

    Raises:
        ExtractionError: If the crawl or extraction fails.
    """
    return await extract_authors_from_url(url)
