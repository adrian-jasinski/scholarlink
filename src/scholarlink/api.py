"""Public API for Scholarlink."""

import sys
from pathlib import Path

from scholarlink.crawler import ExtractionError, extract_authors_from_url
from scholarlink.input_links import read_links_from_file
from scholarlink.linkedin_lookup import search_linkedin_profiles
from scholarlink.models import AuthorInfo, LinkedInLookupResult
from scholarlink.output_csv import authors_to_output_rows, write_output_csv
from scholarlink.search import SearchBackend

__all__ = [
    "extract_authors",
    "extract_authors_from_file",
    "extract_authors_single",
    "find_linkedin_profiles",
]


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


async def extract_authors_single(
    url: str,
    *,
    linkedin: bool = False,
    output_path: str | None = None,
    mode: str = "normal",
    cloudflare_manual: bool = False,
) -> list[dict]:
    """
    Extract authors from a single paper URL and return output rows (author_name, link, optional linkedin).

    Optionally run LinkedIn lookup and write CSV to output_path.

    Args:
        url: Paper URL.
        linkedin: If True, find LinkedIn profile(s) per author.
        output_path: If set, write CSV to this path.
        mode: "normal" or "stealth". See crawler MODE_HELP.
        cloudflare_manual: If True and protected domain, show browser for Cloudflare.

    Returns:
        List of row dicts with author_name, link, and optionally linkedin.
    """
    authors, _ = await extract_authors(url, mode=mode, cloudflare_manual=cloudflare_manual)
    linkedin_results = None
    if linkedin and authors:
        linkedin_results = await find_linkedin_profiles(authors)
    rows = authors_to_output_rows(authors, url, linkedin_results)
    if output_path:
        write_output_csv(rows, output_path, include_linkedin=linkedin)
    return rows


async def extract_authors_from_file(
    input_path: str | Path,
    *,
    column: str | None = None,
    linkedin: bool = False,
    output_path: str | Path,
    mode: str = "normal",
    cloudflare_manual: bool = False,
) -> None:
    """
    Read paper links from CSV or Excel, extract authors for each, write one CSV to output_path.

    On per-URL extraction failure the URL is skipped and an error is logged to stderr.

    Args:
        input_path: Path to .csv or .xlsx file with a column of paper URLs.
        column: Optional column name (header) for links; if None, first column.
        linkedin: If True, find LinkedIn profile(s) per author.
        output_path: Path for result CSV (required).
        mode: "normal" or "stealth". See crawler MODE_HELP.
        cloudflare_manual: If True and protected domain, show browser for Cloudflare.
    """
    links = read_links_from_file(input_path, column=column)
    all_rows: list[dict] = []
    for link in links:
        try:
            authors, _ = await extract_authors(
                link, mode=mode, cloudflare_manual=cloudflare_manual
            )
        except ExtractionError as e:
            print(f"Error for {link}: {e}", file=sys.stderr)
            continue
        linkedin_results = None
        if linkedin and authors:
            try:
                linkedin_results = await find_linkedin_profiles(authors)
            except ValueError as e:
                print(f"LinkedIn lookup failed for {link}: {e}", file=sys.stderr)
        rows = authors_to_output_rows(authors, link, linkedin_results)
        all_rows.extend(rows)
    write_output_csv(all_rows, output_path, include_linkedin=linkedin)
