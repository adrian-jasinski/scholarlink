"""Scholarlink: extract publication authors from scientific paper URLs using Crawl4AI."""

from dotenv import load_dotenv

from scholarlink.api import extract_authors

load_dotenv()

__all__ = ["extract_authors"]
