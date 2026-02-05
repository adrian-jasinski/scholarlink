"""Tests for Scholarlink crawler module."""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from crawl4ai import CacheMode, LLMExtractionStrategy

from scholarlink.config import get_config, reset_config
from scholarlink.crawler import (
    ExtractionError,
    _build_crawler_kwargs,
    _build_run_config,
    _extract_author_names_only,
    _fallback_author_names_from_markdown,
    _get_delay_and_notify,
    _get_markdown_text,
    _get_protected_domains,
    _is_playwright_browser_error,
    _is_protected_domain,
    _parse_extraction_result,
    extract_authors_from_url,
)
from scholarlink.models import AuthorInfo, PaperMetadata


def test_is_protected_domain_biorxiv_true() -> None:
    """URL with host in default protected set returns True."""
    assert _is_protected_domain("https://www.biorxiv.org/content/10.1101/123") is True
    assert _is_protected_domain("https://biorxiv.org/content/10.1101/123") is True


def test_is_protected_domain_pnas_true(monkeypatch: pytest.MonkeyPatch) -> None:
    """URL with pnas.org host returns True when pnas is in protected_domains."""
    from scholarlink import crawler as crawler_module

    monkeypatch.setattr(
        crawler_module,
        "_get_protected_domains",
        lambda: frozenset({"biorxiv.org", "www.biorxiv.org", "pnas.org", "www.pnas.org"}),
    )
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
    reset_config()
    assert _get_protected_domains() == get_config().protected_domains_frozenset()


def test_get_protected_domains_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """With env set, returns frozenset of normalized hosts."""
    monkeypatch.setenv("SCHOLARLINK_PROTECTED_DOMAINS", "a.com, b.com ")
    reset_config()
    domains = _get_protected_domains()
    assert domains == frozenset({"a.com", "b.com"})


def test_is_protected_domain_uses_custom_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """When SCHOLARLINK_PROTECTED_DOMAINS is set, only those hosts are protected."""
    monkeypatch.setenv("SCHOLARLINK_PROTECTED_DOMAINS", "a.com,b.com")
    reset_config()
    assert _is_protected_domain("https://a.com/foo") is True
    assert _is_protected_domain("https://www.biorxiv.org/foo") is False


def _author_dict(
    name: str,
    affiliation: str = "",
    contact: str = "",
    orcid: str = "",
    other: str = "",
) -> dict:
    return {
        "name": name,
        "affiliation": affiliation,
        "contact": contact,
        "orcid": orcid,
        "other": other,
    }


def test_parse_extraction_result_valid_dict() -> None:
    """Valid JSON dict with authors (list of AuthorInfo) returns PaperMetadata."""
    raw = json.dumps(
        {
            "authors": [
                _author_dict("Alice", "MIT", "a@b.com", "0000-0001-2345-6789", ""),
                _author_dict("Bob", "Stanford", "", "", ""),
            ]
        }
    )
    meta = _parse_extraction_result(raw, "https://example.com/paper")
    assert len(meta.authors) == 2
    assert meta.authors[0].name == "Alice" and meta.authors[0].affiliation == "MIT"
    assert meta.authors[1].name == "Bob" and meta.authors[1].affiliation == "Stanford"


def test_parse_extraction_result_list_wrapper() -> None:
    """JSON list with single dict unwraps to PaperMetadata."""
    raw = json.dumps([{"authors": [_author_dict("A")]}])
    meta = _parse_extraction_result(raw, "https://example.com/paper")
    assert len(meta.authors) == 1
    assert meta.authors[0].name == "A"


def test_parse_extraction_result_list_of_author_dicts() -> None:
    """LLM returns bare list of author dicts (e.g. biorxiv) wraps to PaperMetadata."""
    raw = json.dumps(
        [
            _author_dict("Alice", "MIT", "", "", ""),
            _author_dict("Bob", "Stanford", "bob@stanford.edu", "0000-0002-3456-7890", ""),
        ]
    )
    meta = _parse_extraction_result(raw, "https://example.com/paper")
    assert len(meta.authors) == 2
    assert meta.authors[0].name == "Alice" and meta.authors[0].affiliation == "MIT"
    assert meta.authors[1].name == "Bob" and meta.authors[1].contact == "bob@stanford.edu"
    assert meta.authors[1].orcid == "0000-0002-3456-7890"


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


def test_parse_extraction_result_authors_plain_strings_raises() -> None:
    """Authors as list of plain strings (old shape) raises ExtractionError."""
    raw = json.dumps({"authors": ["Alice", "Bob"]})
    with pytest.raises(ExtractionError, match="expected schema"):
        _parse_extraction_result(raw, "https://example.com/paper")


def test_parse_extraction_result_empty_list_returns_none() -> None:
    """JSON empty list returns None (caller may try fallback)."""
    meta = _parse_extraction_result("[]", "https://example.com/paper")
    assert meta is None


def test_get_markdown_text_none_when_missing() -> None:
    """When result has no markdown, returns None."""
    result = MagicMock(spec=[])
    assert _get_markdown_text(result) is None


def test_get_markdown_text_string() -> None:
    """When result.markdown is a string, returns it."""
    result = MagicMock()
    result.markdown = "## Title\n\nSome text."
    assert _get_markdown_text(result) == "## Title\n\nSome text."


def test_get_markdown_text_raw_markdown_object() -> None:
    """When result.markdown has raw_markdown, returns that."""
    result = MagicMock()
    result.markdown = MagicMock()
    result.markdown.raw_markdown = "# Paper\n\nAuthors: A, B"
    result.markdown.fit_markdown = None
    assert _get_markdown_text(result) == "# Paper\n\nAuthors: A, B"


def test_fallback_author_names_from_markdown_empty() -> None:
    """Empty or no author block returns empty list."""
    assert _fallback_author_names_from_markdown("") == []
    assert _fallback_author_names_from_markdown("Just abstract text.") == []


def test_fallback_author_names_from_markdown_after_authors_label() -> None:
    """Authors listed after 'Authors:' are parsed as name-only AuthorInfo."""
    text = "Title\n\nAuthors: Alice Foo, Bob Bar, Carol Baz.\n\nAbstract\n\n..."
    authors = _fallback_author_names_from_markdown(text)
    assert len(authors) >= 2
    names = [a.name for a in authors]
    assert "Alice Foo" in names
    assert "Bob Bar" in names
    for a in authors:
        assert a.affiliation is None
        assert a.contact is None
        assert a.orcid is None


@pytest.mark.asyncio
async def test_extract_author_names_only_returns_name_only_authors() -> None:
    """Second-attempt LLM (names-only) returns AuthorInfo with name set only."""
    with patch("scholarlink.crawler._get_llm_config"), patch(
        "scholarlink.crawler.LLMExtractionStrategy"
    ) as mock_strategy_cls:
        mock_strategy = MagicMock()
        mock_strategy.arun = AsyncMock(
            return_value=[{"authors": ["Alpha One", "Beta Two"], "error": False}]
        )
        mock_strategy_cls.return_value = mock_strategy
        authors = await _extract_author_names_only(
            "# Paper\n\nSome text.", "https://example.com/paper"
        )
    assert len(authors) == 2
    assert authors[0].name == "Alpha One"
    assert authors[1].name == "Beta Two"
    for a in authors:
        assert a.affiliation is None and a.contact is None and a.orcid is None


@pytest.mark.asyncio
async def test_extract_authors_from_url_empty_list_second_attempt_used() -> None:
    """When first attempt returns [], second attempt (names-only) on same data is used."""
    mock_result = MagicMock()
    mock_result.success = True
    mock_result.extracted_content = "[]"
    mock_result.error_message = None
    mock_result.markdown = MagicMock()
    mock_result.markdown.raw_markdown = "# Title\n\nBody..."
    mock_result.markdown.fit_markdown = None
    second_attempt_authors = [
        AuthorInfo(name="Second One", affiliation=None, contact=None, orcid=None, other=None),
        AuthorInfo(name="Second Two", affiliation=None, contact=None, orcid=None, other=None),
    ]

    with (
        patch("scholarlink.crawler._get_llm_config"),
        patch(
            "scholarlink.crawler._run_crawl",
            new_callable=AsyncMock,
            return_value=mock_result,
        ),
        patch(
            "scholarlink.crawler._extract_author_names_only",
            new_callable=AsyncMock,
            return_value=second_attempt_authors,
        ),
    ):
        authors, csv_str = await extract_authors_from_url(
            "https://example.com/paper", mode="normal"
        )
    assert authors == second_attempt_authors
    assert "name,affiliation,contact,orcid,other" in csv_str
    assert "Second One" in csv_str and "Second Two" in csv_str


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
    """When protected and cloudflare_manual, returns config cloudflare_manual_wait_seconds."""
    reset_config()
    assert _get_delay_and_notify(True, True) == get_config().cloudflare_manual_wait_seconds


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
    """extract_authors_from_url returns (authors, csv_str) when crawl returns valid JSON."""
    mock_result = MagicMock()
    mock_result.success = True
    mock_result.extracted_content = json.dumps(
        {
            "authors": [
                _author_dict("Alice", "MIT", "a@b.com", "", ""),
                _author_dict("Bob", "Stanford", "", "0000-0002-3456-7890", ""),
            ]
        }
    )
    mock_result.error_message = None

    with (
        patch("scholarlink.crawler._get_llm_config"),
        patch(
            "scholarlink.crawler._run_crawl",
            new_callable=AsyncMock,
            return_value=mock_result,
        ),
    ):
        authors, csv_str = await extract_authors_from_url(
            "https://example.com/paper", mode="normal"
        )
    assert len(authors) == 2
    assert authors[0].name == "Alice" and authors[0].affiliation == "MIT"
    assert authors[1].name == "Bob" and authors[1].orcid == "0000-0002-3456-7890"
    assert "name,affiliation,contact,orcid,other" in csv_str
    lines = csv_str.splitlines()
    assert len(lines) == 3  # header + 2 authors
    assert "Alice" in lines[1] and "Bob" in lines[2]


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
async def test_extract_authors_from_url_empty_list_uses_fallback() -> None:
    """When LLM returns empty list, fallback from markdown returns name-only CSV rows."""
    mock_result = MagicMock()
    mock_result.success = True
    mock_result.extracted_content = "[]"
    mock_result.error_message = None
    mock_result.markdown = MagicMock()
    mock_result.markdown.raw_markdown = (
        "# Paper title\n\nAuthors: Jane Doe, John Smith.\n\nAbstract\n\n..."
    )
    mock_result.markdown.fit_markdown = None

    with (
        patch("scholarlink.crawler._get_llm_config"),
        patch(
            "scholarlink.crawler._run_crawl",
            new_callable=AsyncMock,
            return_value=mock_result,
        ),
    ):
        authors, csv_str = await extract_authors_from_url(
            "https://example.com/paper", mode="normal"
        )
    assert len(authors) >= 2
    names = [a.name for a in authors]
    assert "Jane Doe" in names
    assert "John Smith" in names
    for a in authors:
        assert a.affiliation is None and a.contact is None and a.orcid is None
    assert "name,affiliation,contact,orcid,other" in csv_str
    lines = csv_str.splitlines()
    assert len(lines) >= 3  # header + at least 2 authors


@pytest.mark.asyncio
async def test_extract_authors_from_url_cloudflare_phrase_raises() -> None:
    """When extracted content contains Cloudflare phrase, raises ExtractionError."""
    # Use valid JSON; author name "cloudflare" makes combined string trigger the check
    mock_result = MagicMock()
    mock_result.success = True
    mock_result.extracted_content = json.dumps(
        {"authors": [_author_dict("Alice"), _author_dict("cloudflare")]}
    )
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
