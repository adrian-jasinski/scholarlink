"""Crawl4AI integration for fetching and extracting paper metadata."""

import json
import os
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

from scholarlink.models import PaperMetadata

# Cloudflare-protected domains: use undetected browser + stealth
DEFAULT_PROTECTED_DOMAINS = frozenset(
    {
        "biorxiv.org",
        "www.biorxiv.org",
        "pnas.org",
        "www.pnas.org",
    }
)

# Phrases that indicate Cloudflare challenge text leaked into extracted content
CLOUDFLARE_PHRASES = ("cloudflare", "verifying you are human", "ray id")


def _get_protected_domains() -> frozenset[str]:
    """Return the set of hostnames that use Cloudflare (from env or default)."""
    env_val = os.getenv("SCHOLARLINK_PROTECTED_DOMAINS")
    if env_val:
        return frozenset(d.strip().lower() for d in env_val.split(",") if d.strip())
    return DEFAULT_PROTECTED_DOMAINS


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


AUTHORS_EXTRACTION_INSTRUCTION = """
From this scientific article page, extract all publication authors.
Return them as a list of full names in order of appearance.
Do not include affiliations, links, or "View ORCID Profile" text—only author names.
If the page lists authors in a single comma-separated line, split them into the list.
Preserve the exact spelling and order of names.
""".strip()


class ExtractionError(Exception):
    """Raised when crawling or author extraction fails."""

    pass


def _get_llm_config() -> LLMConfig:
    provider = os.getenv("SCHOLARLINK_LLM_PROVIDER", "openai/gpt-4o-mini")
    api_token = os.getenv("OPENAI_API_KEY")
    if not api_token and "openai" in provider.lower():
        raise ExtractionError(
            "OPENAI_API_KEY is not set. Set it in the environment to use "
            "LLM-based author extraction."
        )
    return LLMConfig(provider=provider, api_token=api_token or "")


async def extract_authors_from_url(url: str) -> tuple[list[str], str]:
    """
    Crawl a paper URL with Crawl4AI and extract authors using LLM extraction.

    Returns:
        Tuple of (authors list, comma-separated authors string).

    Raises:
        ExtractionError: If the crawl fails or extracted content is invalid.
    """
    llm_config = _get_llm_config()
    extraction_strategy = LLMExtractionStrategy(
        llm_config=llm_config,
        schema=PaperMetadata.model_json_schema(),
        extraction_type="schema",
        instruction=AUTHORS_EXTRACTION_INSTRUCTION,
        input_format="markdown",
        apply_chunking=False,
        extra_args={"temperature": 0.0, "max_tokens": 2000},
    )
    protected = _is_protected_domain(url)
    run_config = CrawlerRunConfig(
        cache_mode=CacheMode.BYPASS,
        extraction_strategy=extraction_strategy,
        delay_before_return_html=3.0 if protected else 0.1,
    )
    if protected:
        browser_config = BrowserConfig(
            enable_stealth=True,
            headless=False,
        )
        crawler_strategy = AsyncPlaywrightCrawlerStrategy(
            browser_config=browser_config,
            browser_adapter=UndetectedAdapter(),
        )
        crawler_kwargs = {"crawler_strategy": crawler_strategy, "config": browser_config}
    else:
        browser_config = BrowserConfig(headless=True)
        crawler_kwargs = {"config": browser_config}

    try:
        async with AsyncWebCrawler(**crawler_kwargs) as crawler:
            result = await crawler.arun(url=url, config=run_config)
    except Exception as e:  # noqa: BLE001
        err_msg = str(e)
        if "Executable doesn't exist" in err_msg or "playwright" in type(e).__module__:
            raise ExtractionError(
                "Playwright browser is not installed. Run:\n"
                "  uv run python -m playwright install chromium"
            ) from e
        raise

    if not result.success:
        msg = result.error_message or "Crawl failed"
        raise ExtractionError(f"Crawl failed for {url}: {msg}")

    raw = result.extracted_content
    if not raw or not raw.strip():
        raise ExtractionError(
            f"No content was extracted from {url}. The page may be empty or "
            "the LLM returned nothing."
        )

    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        raise ExtractionError(f"Extraction returned invalid JSON from {url}: {e}") from e

    # LLM may return a list (e.g. [{"authors": [...]}] or []) instead of a single object
    if isinstance(data, list):
        if not data:
            raise ExtractionError(
                f"No structured data was extracted from {url}. The LLM returned an empty list."
            )
        data = data[0]
    if not isinstance(data, dict):
        raise ExtractionError(
            f"Extraction returned unexpected type from {url}: expected dict, "
            f"got {type(data).__name__}"
        )

    try:
        metadata = PaperMetadata.model_validate(data)
    except Exception as e:
        raise ExtractionError(
            f"Extracted data did not match expected schema from {url}: {e}"
        ) from e

    authors = metadata.authors
    authors_str = ", ".join(authors) if authors else ""
    # Reject if Cloudflare challenge text leaked into extracted content
    combined = (authors_str + " " + raw).lower()
    if any(phrase in combined for phrase in CLOUDFLARE_PHRASES):
        raise ExtractionError(
            f"Extracted content from {url} looks like a Cloudflare challenge page. "
            "Retry or ensure the URL is on a protected domain (undetected browser "
            "is used automatically)."
        )
    return authors, authors_str
