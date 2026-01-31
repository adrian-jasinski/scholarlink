"""Public API for Scholarlink."""

from scholarlink.crawler import MODE_HELP, extract_authors_from_url

__all__ = ["extract_authors"]


async def extract_authors(
    url: str,
    *,
    mode: str = "normal",
    cloudflare_manual: bool = False,
) -> tuple[list[str], str]:
    f"""
    Extract publication authors from a scientific paper URL.

    Crawls the page with Crawl4AI and uses LLM extraction to obtain
    the list of author names.

    Args:
        url: Full URL of the paper (e.g. bioRxiv or PNAS article page).
        mode: "normal" or "stealth". {MODE_HELP}.
        cloudflare_manual: If True and the URL is on a protected domain, show
            the browser and wait so the user can complete the Cloudflare
            challenge manually.

    Returns:
        Tuple of (authors list, comma-separated authors string).

    Raises:
        ExtractionError: If the crawl or extraction fails.
    """
    return await extract_authors_from_url(url, mode=mode, cloudflare_manual=cloudflare_manual)
