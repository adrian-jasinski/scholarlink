"""Scholarlink: extract publication authors from scientific paper URLs using Crawl4AI."""

from dotenv import load_dotenv

from scholarlink.api import (
    extract_authors,
    extract_authors_from_file,
    extract_authors_single,
    find_linkedin_profiles,
)

load_dotenv()

__all__ = [
    "extract_authors",
    "extract_authors_from_file",
    "extract_authors_single",
    "find_linkedin_profiles",
]
