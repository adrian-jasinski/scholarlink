"""Tests for Scholarlink LinkedIn lookup (threshold logic, search_linkedin_profiles)."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from scholarlink.models import AuthorInfo, LinkedInLookupResult, LinkedInReviewResult
from scholarlink.linkedin_lookup import (
    _author_context,
    _format_search_results,
    _linkedin_profile_urls_from_results,
    _review_result_to_lookup,
    search_linkedin_profiles,
)
from scholarlink.models import SearchResult


# --- Threshold / _review_result_to_lookup ---


def test_review_to_lookup_confidence_high_returns_found() -> None:
    """Confidence >= 75 and best_url set -> status found, single url."""
    author = AuthorInfo(name="Jane Doe")
    review = LinkedInReviewResult(
        profile_urls=["https://linkedin.com/in/janedoe"],
        best_url="https://linkedin.com/in/janedoe",
        confidence=80,
    )
    r = _review_result_to_lookup(author, review)
    assert r.status == "found"
    assert r.url == "https://linkedin.com/in/janedoe"
    assert r.urls == []


def test_review_to_lookup_confidence_75_returns_found() -> None:
    """Confidence exactly 75 and best_url -> found."""
    author = AuthorInfo(name="Alice")
    review = LinkedInReviewResult(
        profile_urls=["https://linkedin.com/in/alice"],
        best_url="https://linkedin.com/in/alice",
        confidence=75,
    )
    r = _review_result_to_lookup(author, review)
    assert r.status == "found"
    assert r.url == "https://linkedin.com/in/alice"


def test_review_to_lookup_confidence_50_returns_ambiguous() -> None:
    """Confidence 50-74 -> status ambiguous, up to 10 urls."""
    author = AuthorInfo(name="Bob")
    review = LinkedInReviewResult(
        profile_urls=["https://linkedin.com/in/bob1", "https://linkedin.com/in/bob2"],
        best_url="https://linkedin.com/in/bob1",
        confidence=60,
    )
    r = _review_result_to_lookup(author, review)
    assert r.status == "ambiguous"
    assert r.url is None
    assert r.urls == ["https://linkedin.com/in/bob1", "https://linkedin.com/in/bob2"]


def test_review_to_lookup_confidence_below_50_returns_not_found() -> None:
    """Confidence < 50 -> status not_found."""
    author = AuthorInfo(name="Unknown")
    review = LinkedInReviewResult(
        profile_urls=[],
        best_url=None,
        confidence=30,
    )
    r = _review_result_to_lookup(author, review)
    assert r.status == "not_found"
    assert r.url is None
    assert r.urls == []


def test_review_to_lookup_ambiguous_caps_at_10_urls() -> None:
    """Ambiguous result returns at most 10 urls."""
    author = AuthorInfo(name="Many")
    urls = [f"https://linkedin.com/in/u{i}" for i in range(15)]
    review = LinkedInReviewResult(
        profile_urls=urls,
        best_url=urls[0],
        confidence=65,
    )
    r = _review_result_to_lookup(author, review)
    assert r.status == "ambiguous"
    assert len(r.urls) == 10
    assert r.urls == urls[:10]


# --- Helpers ---


def test_format_search_results() -> None:
    """_format_search_results formats list of SearchResult."""
    results = [
        SearchResult(title="A", snippet="s1", url="https://a.com"),
        SearchResult(title="B", snippet="s2", url="https://b.com"),
    ]
    text = _format_search_results(results)
    assert "1. A" in text
    assert "https://a.com" in text
    assert "2. B" in text
    assert "https://b.com" in text


def test_format_search_results_empty() -> None:
    """_format_search_results empty list returns (No results)."""
    assert _format_search_results([]) == "(No results)"


def test_linkedin_profile_urls_from_results() -> None:
    """_linkedin_profile_urls_from_results returns only URLs containing linkedin.com/in/."""
    results = [
        SearchResult(title="A", snippet="", url="https://www.linkedin.com/in/alice/"),
        SearchResult(title="B", snippet="", url="https://example.com"),
        SearchResult(title="C", snippet="", url="https://linkedin.com/in/bob"),
    ]
    urls = _linkedin_profile_urls_from_results(results)
    assert urls == ["https://www.linkedin.com/in/alice/", "https://linkedin.com/in/bob"]


def test_linkedin_profile_urls_from_results_empty() -> None:
    """_linkedin_profile_urls_from_results returns [] when no profile URLs."""
    results = [
        SearchResult(title="A", snippet="", url="https://linkedin.com/company/foo"),
    ]
    assert _linkedin_profile_urls_from_results(results) == []


def test_author_context() -> None:
    """_author_context returns dict with author fields."""
    author = AuthorInfo(
        name="Jane",
        affiliation="MIT",
        contact="j@m.edu",
        orcid="0000-0000",
        other="Corresponding",
    )
    ctx = _author_context(author)
    assert ctx["name"] == "Jane"
    assert ctx["affiliation"] == "MIT"
    assert ctx["contact"] == "j@m.edu"
    assert ctx["orcid"] == "0000-0000"
    assert ctx["other"] == "Corresponding"


def test_author_context_none_to_empty() -> None:
    """_author_context converts None to empty string."""
    author = AuthorInfo(name="Bob")
    ctx = _author_context(author)
    assert ctx["affiliation"] == ""
    assert ctx["contact"] == ""


# --- search_linkedin_profiles ---


@pytest.mark.asyncio
async def test_search_linkedin_profiles_returns_one_per_author() -> None:
    """search_linkedin_profiles returns one LinkedInLookupResult per author."""
    authors = [
        AuthorInfo(name="Alice"),
        AuthorInfo(name="Bob"),
    ]
    mock_backend = AsyncMock()
    # Return LinkedIn result for Alice only; for Bob return no LinkedIn URLs so fallback does not apply
    mock_backend.search.side_effect = [
        [SearchResult(title="LinkedIn", snippet="", url="https://linkedin.com/in/alice")],
        [SearchResult(title="Other", snippet="", url="https://example.com")],
    ]

    async def mock_llm_review(author: AuthorInfo, results: list) -> LinkedInReviewResult:
        if author.name == "Alice":
            return LinkedInReviewResult(
                profile_urls=["https://linkedin.com/in/alice"],
                best_url="https://linkedin.com/in/alice",
                confidence=90,
            )
        return LinkedInReviewResult(
            profile_urls=[],
            best_url=None,
            confidence=0,
        )

    mock_cfg = MagicMock()
    mock_cfg.search_provider = "google"
    mock_cfg.search_max_results = 10
    mock_cfg.search_delay_seconds = 0
    with patch("scholarlink.linkedin_lookup._call_llm_review", side_effect=mock_llm_review), patch(
        "scholarlink.linkedin_lookup.get_config",
        return_value=mock_cfg,
    ):
        results = await search_linkedin_profiles(
            authors,
            search_backend=mock_backend,
            max_results=5,
        )

    assert len(results) == 2
    assert results[0].author.name == "Alice"
    assert results[0].status == "found"
    assert results[0].url == "https://linkedin.com/in/alice"
    assert results[1].author.name == "Bob"
    assert results[1].status == "not_found"


@pytest.mark.asyncio
async def test_search_linkedin_profiles_empty_authors() -> None:
    """search_linkedin_profiles with empty list returns empty list."""
    with patch("scholarlink.linkedin_lookup.get_search_backend"):
        results = await search_linkedin_profiles([])
    assert results == []


@pytest.mark.asyncio
async def test_search_linkedin_profiles_single_linkedin_fallback() -> None:
    """When LLM returns not_found but raw results have exactly one LinkedIn profile URL, return ambiguous with that URL."""
    author = AuthorInfo(name="Jane")
    mock_backend = AsyncMock()
    single_profile = "https://www.linkedin.com/in/jane-doe-123/"
    mock_backend.search.return_value = [
        SearchResult(title="Other", snippet="", url="https://example.com"),
        SearchResult(title="Jane | LinkedIn", snippet="", url=single_profile),
    ]

    async def mock_llm_review(_author: AuthorInfo, _results: list) -> LinkedInReviewResult:
        return LinkedInReviewResult(profile_urls=[], best_url=None, confidence=0)

    mock_cfg = MagicMock()
    mock_cfg.search_provider = "google"
    mock_cfg.search_max_results = 10
    mock_cfg.search_delay_seconds = 0
    with patch("scholarlink.linkedin_lookup._call_llm_review", side_effect=mock_llm_review), patch(
        "scholarlink.linkedin_lookup.get_config",
        return_value=mock_cfg,
    ):
        results = await search_linkedin_profiles([author], search_backend=mock_backend, max_results=5)

    assert len(results) == 1
    assert results[0].status == "ambiguous"
    assert results[0].urls == [single_profile]
