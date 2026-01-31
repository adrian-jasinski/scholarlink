"""Tests for Scholarlink crawler module."""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from crawl4ai import CacheMode, LLMExtractionStrategy
from scholarlink.crawler import (
    CLOUDFLARE_MANUAL_WAIT_SECONDS,
    DEFAULT_PROTECTED_DOMAINS,
    ExtractionError,
    _build_crawler_kwargs,
    _build_run_config,
    _get_delay_and_notify,
    _get_protected_domains,
    _is_playwright_browser_error,
    _is_protected_domain,
    _parse_extraction_result,
    extract_authors_from_url,
)
from scholarlink.models import PaperMetadata


def test_is_protected_domain_biorxiv_true() -> None:
    """URL with host in default protected set returns True."""
    assert _is_protected_domain("https://www.biorxiv.org/content/10.1101/123") is True
    assert _is_protected_domain("https://biorxiv.org/content/10.1101/123") is True


def test_is_protected_domain_pnas_true() -> None:
    """URL with pnas.org host returns True."""
    assert _is_protected_domain("https://www.pnas.org/doi/10.1073/123") is True


def test_is_protected_domain_other_host_false() -> None:
    """URL with host not in protected set returns False."""
    assert _is_protected_domain("https://example.com/paper") is False
    assert _is_protected_domain("https://arxiv.org/abs/1234.5678") is False


def test_is_protected_domain_empty_or_invalid_false() -> None:
    """Empty or invalid URL returns False."""
    assert _is_protected_domain("") is False
    assert _is_protected_domain("not-a-url") is False


def test_get_protected_domains_default(monkeypatch: pytest.MonkeyPatch) -> None:
    """With env unset, returns default frozenset."""
    monkeypatch.delenv("SCHOLARLINK_PROTECTED_DOMAINS", raising=False)
    assert _get_protected_domains() == DEFAULT_PROTECTED_DOMAINS


def test_get_protected_domains_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """With env set, returns frozenset of normalized hosts."""
    monkeypatch.setenv("SCHOLARLINK_PROTECTED_DOMAINS", "a.com, b.com ")
    domains = _get_protected_domains()
    assert domains == frozenset({"a.com", "b.com"})


def test_is_protected_domain_uses_custom_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """When SCHOLARLINK_PROTECTED_DOMAINS is set, only those hosts are protected."""
    monkeypatch.setenv("SCHOLARLINK_PROTECTED_DOMAINS", "a.com,b.com")
    assert _is_protected_domain("https://a.com/foo") is True
    assert _is_protected_domain("https://www.biorxiv.org/foo") is False


def test_parse_extraction_result_valid_dict() -> None:
    """Valid JSON dict with authors returns PaperMetadata."""
    raw = json.dumps({"authors": ["A", "B"]})
    meta = _parse_extraction_result(raw, "https://example.com/paper")
    assert meta.authors == ["A", "B"]


def test_parse_extraction_result_list_wrapper() -> None:
    """JSON list with single dict unwraps to PaperMetadata."""
    raw = json.dumps([{"authors": ["A"]}])
    meta = _parse_extraction_result(raw, "https://example.com/paper")
    assert meta.authors == ["A"]


def test_parse_extraction_result_empty_string_raises() -> None:
    """Empty or whitespace raw raises ExtractionError."""
    with pytest.raises(ExtractionError, match="No content was extracted"):
        _parse_extraction_result("", "https://example.com/paper")
    with pytest.raises(ExtractionError, match="No content was extracted"):
        _parse_extraction_result("   ", "https://example.com/paper")


def test_parse_extraction_result_invalid_json_raises() -> None:
    """Invalid JSON raises ExtractionError."""
    with pytest.raises(ExtractionError, match="invalid JSON"):
        _parse_extraction_result("not json", "https://example.com/paper")


def test_parse_extraction_result_wrong_type_raises() -> None:
    """Dict with authors not a list raises ExtractionError."""
    raw = json.dumps({"authors": 1})
    with pytest.raises(ExtractionError, match="expected schema"):
        _parse_extraction_result(raw, "https://example.com/paper")


def test_parse_extraction_result_empty_list_raises() -> None:
    """JSON empty list raises ExtractionError."""
    with pytest.raises(ExtractionError, match="empty list"):
        _parse_extraction_result("[]", "https://example.com/paper")


def test_is_playwright_browser_error_executable_missing() -> None:
    """Exception with 'Executable doesn't exist' returns True."""
    e = Exception("Executable doesn't exist at path")
    assert _is_playwright_browser_error(e) is True


def test_is_playwright_browser_error_playwright_module() -> None:
    """Exception from playwright module returns True."""
    class FakePlaywrightError(Exception):
        pass

    FakePlaywrightError.__module__ = "playwright.driver"
    e = FakePlaywrightError("playwright error")
    assert _is_playwright_browser_error(e) is True


def test_is_playwright_browser_error_other_false() -> None:
    """Other exceptions return False."""
    assert _is_playwright_browser_error(ValueError("other")) is False
    assert _is_playwright_browser_error(Exception("something else")) is False


def test_get_delay_and_notify_not_protected() -> None:
    """When not protected, returns 0.1."""
    assert _get_delay_and_notify(False, False) == 0.1


def test_get_delay_and_notify_protected_no_manual() -> None:
    """When protected and not cloudflare_manual, returns 3.0."""
    assert _get_delay_and_notify(True, False) == 3.0


def test_get_delay_and_notify_protected_manual() -> None:
    """When protected and cloudflare_manual, returns CLOUDFLARE_MANUAL_WAIT_SECONDS."""
    assert _get_delay_and_notify(True, True) == CLOUDFLARE_MANUAL_WAIT_SECONDS


def test_get_delay_and_notify_protected_manual_prints_stderr(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """When protected and cloudflare_manual, prints message to stderr."""
    _get_delay_and_notify(True, True)
    captured = capsys.readouterr()
    assert "Cloudflare" in captured.err or "Waiting" in captured.err


def test_build_run_config_smoke() -> None:
    """_build_run_config returns CrawlerRunConfig with bypass cache and given delay."""
    llm_config = MagicMock()
    strategy = LLMExtractionStrategy(
        llm_config=llm_config,
        schema=PaperMetadata.model_json_schema(),
        extraction_type="schema",
        instruction="Extract authors.",
        input_format="markdown",
    )
    config = _build_run_config(strategy, 2.5)
    assert config.cache_mode == CacheMode.BYPASS
    assert config.delay_before_return_html == 2.5
    assert config.extraction_strategy is strategy


def test_build_crawler_kwargs_no_stealth() -> None:
    """_build_crawler_kwargs(False, False, False) returns config with headless True."""
    result = _build_crawler_kwargs(False, False, False)
    assert "config" in result
    assert result["config"].headless is True


def test_build_crawler_kwargs_stealth_headless() -> None:
    """_build_crawler_kwargs(True, False, False) has enable_stealth and headless True."""
    result = _build_crawler_kwargs(True, False, False)
    assert result["config"].enable_stealth is True
    assert result["config"].headless is True
    assert "crawler_strategy" in result


def test_build_crawler_kwargs_stealth_cloudflare_manual() -> None:
    """_build_crawler_kwargs(True, True, True) has headless False."""
    result = _build_crawler_kwargs(True, True, True)
    assert result["config"].headless is False


@pytest.mark.asyncio
async def test_extract_authors_from_url_success() -> None:
    """extract_authors_from_url returns authors when crawl returns valid JSON."""
    mock_result = MagicMock()
    mock_result.success = True
    mock_result.extracted_content = json.dumps({"authors": ["Alice", "Bob"]})
    mock_result.error_message = None

    with (
        patch("scholarlink.crawler._get_llm_config"),
        patch(
            "scholarlink.crawler._run_crawl",
            new_callable=AsyncMock,
            return_value=mock_result,
        ),
    ):
        authors, authors_str = await extract_authors_from_url(
            "https://example.com/paper", mode="normal"
        )
    assert authors == ["Alice", "Bob"]
    assert authors_str == "Alice, Bob"


@pytest.mark.asyncio
async def test_extract_authors_from_url_invalid_mode() -> None:
    """Invalid mode raises ExtractionError."""
    with pytest.raises(ExtractionError, match="mode must be one of"):
        await extract_authors_from_url("https://example.com/paper", mode="invalid")


@pytest.mark.asyncio
async def test_extract_authors_from_url_crawl_fails() -> None:
    """When _run_crawl returns success=False, raises ExtractionError."""
    mock_result = MagicMock()
    mock_result.success = False
    mock_result.error_message = "Connection failed"

    with (
        patch("scholarlink.crawler._get_llm_config"),
        patch(
            "scholarlink.crawler._run_crawl",
            new_callable=AsyncMock,
            return_value=mock_result,
        ),
    ):
        with pytest.raises(ExtractionError, match="Crawl failed"):
            await extract_authors_from_url("https://example.com/paper")


@pytest.mark.asyncio
async def test_extract_authors_from_url_empty_content_raises() -> None:
    """When extracted_content is empty, raises ExtractionError."""
    mock_result = MagicMock()
    mock_result.success = True
    mock_result.extracted_content = ""
    mock_result.error_message = None

    with (
        patch("scholarlink.crawler._get_llm_config"),
        patch(
            "scholarlink.crawler._run_crawl",
            new_callable=AsyncMock,
            return_value=mock_result,
        ),
    ):
        with pytest.raises(ExtractionError, match="No content was extracted"):
            await extract_authors_from_url("https://example.com/paper")


@pytest.mark.asyncio
async def test_extract_authors_from_url_cloudflare_phrase_raises() -> None:
    """When extracted content contains Cloudflare phrase, raises ExtractionError."""
    # Use valid JSON; "cloudflare" in authors makes combined string trigger the check
    mock_result = MagicMock()
    mock_result.success = True
    mock_result.extracted_content = json.dumps({"authors": ["Alice", "cloudflare"]})
    mock_result.error_message = None

    with (
        patch("scholarlink.crawler._get_llm_config"),
        patch(
            "scholarlink.crawler._run_crawl",
            new_callable=AsyncMock,
            return_value=mock_result,
        ),
    ):
        with pytest.raises(ExtractionError, match="Cloudflare"):
            await extract_authors_from_url("https://example.com/paper")
