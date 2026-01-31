"""Crawl4AI integration for fetching and extracting paper metadata."""

import json
import os
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

from scholarlink.config import get_config
from scholarlink.formatters import authors_to_csv
from scholarlink.models import AuthorInfo, PaperMetadata

# Allowed crawler modes: single source of truth for cli/api/crawler
CRAWLER_MODES = ("normal", "stealth")
MODE_HELP = "normal uses stealth only for protected domains; stealth uses stealth for all URLs"


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
    """Build CrawlerRunConfig with bypass cache and given strategy/delay."""
    return CrawlerRunConfig(
        cache_mode=CacheMode.BYPASS,
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


def _parse_extraction_result(raw: str, url: str) -> PaperMetadata:
    """Parse raw JSON from LLM extraction into PaperMetadata; raise ExtractionError on failure."""
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
            raise ExtractionError(
                f"No structured data was extracted from {url}. The LLM returned an empty list."
            )
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
    authors = metadata.authors
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
