"""Crawl4AI integration for fetching and extracting paper metadata."""

import json
import os
import re
import sys
from urllib.parse import urlparse

from crawl4ai import (
    AsyncWebCrawler,
    BrowserConfig,
    CacheMode,
    CrawlerRunConfig,
    LLMConfig,
    LLMExtractionStrategy,
    UndetectedAdapter,
)
from crawl4ai.async_crawler_strategy import AsyncPlaywrightCrawlerStrategy
from crawl4ai.markdown_generation_strategy import DefaultMarkdownGenerator

from scholarlink.config import get_config
from scholarlink.formatters import authors_to_csv
from scholarlink.models import AuthorInfo, PaperMetadata

# Allowed crawler modes: single source of truth for cli/api/crawler
CRAWLER_MODES = ("normal", "stealth")
MODE_HELP = "normal uses stealth only for protected domains; stealth uses stealth for all URLs"

# Second-attempt extraction: schema and instruction for "authors as list of names only"
_AUTHORS_NAMES_ONLY_SCHEMA = {
    "type": "object",
    "properties": {"authors": {"type": "array", "items": {"type": "string"}}},
    "required": ["authors"],
}
_AUTHORS_NAMES_ONLY_INSTRUCTION = (
    "Extract only the full names of all authors from this scientific article. "
    "Return a JSON object with a single key 'authors' and value a list of author name strings, "
    'e.g. {"authors": ["First Last", "Another Author"]}. No other fields.'
)
# Max markdown chars to send in second attempt (avoid token limits)
_SECOND_ATTEMPT_MARKDOWN_MAX_CHARS = 12000


def _get_protected_domains() -> frozenset[str]:
    """Return the set of hostnames that use Cloudflare (from config: file or env)."""
    return get_config().protected_domains_frozenset()


def _is_protected_domain(url: str) -> bool:
    """Return True if the URL's host is in the protected-domains list."""
    try:
        parsed = urlparse(url)
        host = (parsed.hostname or "").lower()
        if not host:
            return False
        return host in _get_protected_domains()
    except Exception:
        return False


class ExtractionError(Exception):
    """Raised when crawling or author extraction fails."""

    pass


def _get_llm_config() -> LLMConfig:
    cfg = get_config()
    api_token = os.getenv("OPENAI_API_KEY")
    if not api_token and "openai" in cfg.llm_provider.lower():
        raise ExtractionError(
            "OPENAI_API_KEY is not set. Set it in the environment to use "
            "LLM-based author extraction."
        )
    return LLMConfig(provider=cfg.llm_provider, api_token=api_token or "")


def _is_playwright_browser_error(exc: BaseException) -> bool:
    """Return True if the exception indicates Playwright browser is not installed."""
    err_msg = str(exc)
    return "Executable doesn't exist" in err_msg or "playwright" in type(exc).__module__


def _get_delay_and_notify(protected: bool, cloudflare_manual: bool) -> float:
    """Return delay in seconds; print stderr message if cloudflare_manual and protected."""
    cfg = get_config()
    delay = cfg.delay_default
    if protected:
        if cloudflare_manual:
            delay = float(cfg.cloudflare_manual_wait_seconds)
            print(
                "A browser window will open. Complete the Cloudflare challenge "
                f"if shown. Waiting up to {delay} seconds...",
                file=sys.stderr,
            )
        else:
            delay = cfg.delay_protected
    return delay


def _build_run_config(extraction_strategy: LLMExtractionStrategy, delay: float) -> CrawlerRunConfig:
    """Build CrawlerRunConfig with bypass cache, markdown, and given strategy/delay."""
    return CrawlerRunConfig(
        cache_mode=CacheMode.BYPASS,
        markdown_generator=DefaultMarkdownGenerator(),
        extraction_strategy=extraction_strategy,
        delay_before_return_html=delay,
    )


def _build_crawler_kwargs(use_stealth: bool, protected: bool, cloudflare_manual: bool) -> dict:
    """Build kwargs for AsyncWebCrawler (config and optionally crawler_strategy)."""
    if use_stealth:
        browser_config = BrowserConfig(
            enable_stealth=True,
            headless=False if (protected and cloudflare_manual) else True,
        )
        crawler_strategy = AsyncPlaywrightCrawlerStrategy(
            browser_config=browser_config,
            browser_adapter=UndetectedAdapter(),
        )
        return {"crawler_strategy": crawler_strategy, "config": browser_config}
    return {"config": BrowserConfig(headless=True)}


async def _run_crawl(crawler_kwargs: dict, url: str, run_config: CrawlerRunConfig):
    """Run the crawler and return the result; re-raise Playwright errors as ExtractionError."""
    try:
        async with AsyncWebCrawler(**crawler_kwargs) as crawler:
            return await crawler.arun(url=url, config=run_config)
    except Exception as e:  # noqa: BLE001
        if _is_playwright_browser_error(e):
            raise ExtractionError(
                "Playwright browser is not installed. Run:\n"
                "  uv run python -m playwright install chromium"
            ) from e
        raise


async def _extract_author_names_only(markdown_text: str, url: str) -> list[AuthorInfo]:
    """Second attempt: same scraped markdown, LLM extracts only author names as list.

    Returns list of AuthorInfo with name set only; empty list on failure or no names.
    Does not scrape again.
    """
    if not markdown_text or not markdown_text.strip():
        return []
    text = markdown_text.strip()
    if len(text) > _SECOND_ATTEMPT_MARKDOWN_MAX_CHARS:
        text = text[:_SECOND_ATTEMPT_MARKDOWN_MAX_CHARS]
    cfg = get_config()
    llm_config = _get_llm_config()
    strategy = LLMExtractionStrategy(
        llm_config=llm_config,
        schema=_AUTHORS_NAMES_ONLY_SCHEMA,
        extraction_type="schema",
        instruction=_AUTHORS_NAMES_ONLY_INSTRUCTION,
        input_format="markdown",
        apply_chunking=False,
        extra_args={"temperature": cfg.llm_temperature, "max_tokens": cfg.llm_max_tokens},
    )
    try:
        results = await strategy.arun(url, [text])
    except Exception:
        return []
    if not results or not isinstance(results[0], dict):
        return []
    first = results[0]
    if first.get("error") or "authors" not in first:
        return []
    raw_names = first["authors"]
    if not isinstance(raw_names, list):
        return []
    names = [n.strip() for n in raw_names if isinstance(n, str) and n.strip()]
    return [
        AuthorInfo(name=name, affiliation=None, contact=None, orcid=None, other=None)
        for name in names
    ]


def _get_markdown_text(result) -> str | None:
    """Return raw markdown string from Crawl4AI result, or None if not available."""
    md = getattr(result, "markdown", None)
    if md is None:
        return None
    if isinstance(md, str):
        return md if md.strip() else None
    return getattr(md, "raw_markdown", None) or getattr(md, "fit_markdown", None)


def _fallback_author_names_from_markdown(text: str) -> list[AuthorInfo]:
    """Extract author names from markdown when LLM returned empty list.

    Looks for common patterns (Authors:, Author:, comma/newline-separated names)
    in the first part of the text. Returns list of AuthorInfo with name set only.
    """
    if not text or not text.strip():
        return []
    # Use first ~12k chars to avoid noise from full article
    head = text[:12000].strip()
    names: list[str] = []
    # Find block that likely contains author names: line(s) after "Author(s)" or similar
    author_label = re.compile(
        r"\b(?:authors?|contributors?)\s*[:\s]+",
        re.IGNORECASE,
    )
    match = author_label.search(head)
    if match:
        after = head[match.end() :]
        # Take until double newline or a section header
        block = re.split(
            r"\n\s*\n|(?=^#|\babstract\b|\bintroduction\b)",
            after,
            maxsplit=1,
            flags=re.IGNORECASE | re.MULTILINE,
        )[0]
        # Split by comma or newline, clean
        for part in re.split(r"[\n,;]|(?:\s+and\s+)", block):
            name = part.strip()
            if not name:
                continue
            # Remove common suffixes/prefixes in parentheses
            name = re.sub(r"\s*\([^)]*\)\s*", " ", name).strip()
            # Strip trailing punctuation (e.g. "John Smith." -> "John Smith")
            name = name.rstrip(".,;:")
            # Keep if it looks like a name (2–6 words, letters/spaces/hyphens)
            if re.match(r"^[\w\s\-\.]+$", name) and 2 <= len(name.split()) <= 6:
                names.append(name)
    if not names:
        # Fallback only when we saw an author-like label (avoid matching random lines)
        has_author_word = re.compile(r"\b(?:authors?|contributors?)\b", re.IGNORECASE)
        if has_author_word.search(head):
            # First line that looks like "Name1, Name2, Name3" in first 2k chars
            first_chunk = head[:2000]
            for line in first_chunk.splitlines():
                line = line.strip()
                if not line or len(line) < 10:
                    continue
                parts = [p.strip() for p in re.split(r"[\s,;]+(?:and\s+)?", line) if p.strip()]
                if 2 <= len(parts) <= 15 and all(re.match(r"^[\w\.\-]+$", p) for p in parts):
                    # Likely "First Last" pairs: join pairs if even count
                    if len(parts) % 2 == 0:
                        names = [" ".join(parts[i : i + 2]) for i in range(0, len(parts), 2)]
                    else:
                        names = parts
                    break
    seen: set[str] = set()
    unique: list[str] = []
    for n in names:
        n_clean = n.rstrip(".,;:").strip()
        if not n_clean:
            continue
        key = n_clean.lower()
        if key not in seen:
            seen.add(key)
            unique.append(n_clean)
    return [
        AuthorInfo(name=name, affiliation=None, contact=None, orcid=None, other=None)
        for name in unique
    ]


def _parse_extraction_result(raw: str, url: str) -> PaperMetadata | None:
    """Parse raw JSON from LLM extraction into PaperMetadata.

    Returns None when the LLM returned an empty list (caller may try fallback).
    Raises ExtractionError on other failures.
    """
    if not raw or not raw.strip():
        raise ExtractionError(
            f"No content was extracted from {url}. The page may be empty or "
            "the LLM returned nothing."
        )
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        raise ExtractionError(f"Extraction returned invalid JSON from {url}: {e}") from e
    if isinstance(data, list):
        if not data:
            return None
        first = data[0]
        if isinstance(first, dict) and "authors" in first:
            data = first
        elif isinstance(first, dict) and "name" in first and "authors" not in first:
            data = {"authors": data}
        else:
            data = first
    if not isinstance(data, dict):
        raise ExtractionError(
            f"Extraction returned unexpected type from {url}: expected dict, "
            f"got {type(data).__name__}"
        )
    try:
        return PaperMetadata.model_validate(data)
    except Exception as e:
        raise ExtractionError(
            f"Extracted data did not match expected schema from {url}: {e}"
        ) from e


async def extract_authors_from_url(
    url: str,
    *,
    mode: str = "normal",
    cloudflare_manual: bool = False,
) -> tuple[list[AuthorInfo], str]:
    """
    Crawl a paper URL with Crawl4AI and extract authors using LLM extraction.

    Args:
        url: Paper URL to crawl.
        mode: "normal" uses stealth only for protected domains; "stealth" uses
            stealth for all URLs.
        cloudflare_manual: If True and URL is protected, show browser and wait
            so the user can complete the Cloudflare challenge manually.

    Returns:
        Tuple of (list of AuthorInfo, CSV-like string with one line per author).

    Raises:
        ExtractionError: If the crawl fails or extracted content is invalid.
    """
    if mode not in CRAWLER_MODES:
        raise ExtractionError(f"mode must be one of {CRAWLER_MODES!r}, got {mode!r}")
    cfg = get_config()
    llm_config = _get_llm_config()
    extraction_strategy = LLMExtractionStrategy(
        llm_config=llm_config,
        schema=PaperMetadata.model_json_schema(),
        extraction_type="schema",
        instruction=cfg.authors_extraction_instruction,
        input_format="markdown",
        apply_chunking=False,
        extra_args={"temperature": cfg.llm_temperature, "max_tokens": cfg.llm_max_tokens},
    )
    protected = _is_protected_domain(url)
    use_stealth = protected or (mode == "stealth")
    delay = _get_delay_and_notify(protected, cloudflare_manual)
    run_config = _build_run_config(extraction_strategy, delay)
    crawler_kwargs = _build_crawler_kwargs(use_stealth, protected, cloudflare_manual)

    result = await _run_crawl(crawler_kwargs, url, run_config)
    if not result.success:
        msg = result.error_message or "Crawl failed"
        raise ExtractionError(f"Crawl failed for {url}: {msg}")

    raw = result.extracted_content or ""
    metadata = _parse_extraction_result(raw, url)
    if metadata is not None:
        authors = metadata.authors
    else:
        # First attempt returned nothing: second LLM pass on same scraped data (no re-scrape)
        # Extract only author names as list, then convert to expected output format
        markdown_text = _get_markdown_text(result) or ""
        authors = await _extract_author_names_only(markdown_text, url)
        if not authors:
            authors = _fallback_author_names_from_markdown(markdown_text)
    csv_str = authors_to_csv(authors)
    # Reject if Cloudflare challenge text leaked into extracted content
    names_str = " ".join(a.name for a in authors) if authors else ""
    combined = (names_str + " " + raw).lower()
    if any(phrase in combined for phrase in get_config().cloudflare_phrases_tuple()):
        raise ExtractionError(
            f"Extracted content from {url} looks like a Cloudflare challenge page. "
            "Retry or ensure the URL is on a protected domain (undetected browser "
            "is used automatically)."
        )
    return authors, csv_str
