"""Tests for Scholarlink Pydantic models."""

import pytest
from pydantic import ValidationError

from scholarlink.models import (
    AuthorInfo,
    LinkedInLookupResult,
    LinkedInReviewResult,
    PaperMetadata,
    SearchResult,
)

# --- AuthorInfo ---


def test_author_info_name_only() -> None:
    """AuthorInfo with only name is valid."""
    a = AuthorInfo(name="Alice Smith")
    assert a.name == "Alice Smith"
    assert a.affiliation is None
    assert a.contact is None
    assert a.orcid is None
    assert a.other is None


def test_author_info_all_fields() -> None:
    """AuthorInfo with all fields present is valid."""
    a = AuthorInfo(
        name="Alice Smith",
        affiliation="MIT, Department of Biology",
        contact="alice@mit.edu",
        orcid="0000-0001-2345-6789",
        other="Corresponding author",
    )
    assert a.name == "Alice Smith"
    assert a.affiliation == "MIT, Department of Biology"
    assert a.contact == "alice@mit.edu"
    assert a.orcid == "0000-0001-2345-6789"
    assert a.other == "Corresponding author"


def test_author_info_missing_name_raises() -> None:
    """AuthorInfo without name raises ValidationError."""
    with pytest.raises(ValidationError):
        AuthorInfo.model_validate({})


def test_author_info_name_not_string_raises() -> None:
    """AuthorInfo with non-string name raises ValidationError."""
    with pytest.raises(ValidationError):
        AuthorInfo.model_validate({"name": 123})


def test_author_info_optional_fields_empty_string() -> None:
    """AuthorInfo accepts empty string for optional fields (LLM may return "")."""
    a = AuthorInfo(
        name="Bob",
        affiliation="",
        contact="",
        orcid="",
        other="",
    )
    assert a.name == "Bob"
    assert a.affiliation == ""
    assert a.contact == ""
    assert a.orcid == ""
    assert a.other == ""


# --- PaperMetadata ---


def test_paper_metadata_valid_authors() -> None:
    """PaperMetadata with list of AuthorInfo builds and authors match."""
    meta = PaperMetadata(
        authors=[
            AuthorInfo(name="Alice Smith"),
            AuthorInfo(name="Bob Jones", affiliation="Stanford"),
        ]
    )
    assert len(meta.authors) == 2
    assert meta.authors[0].name == "Alice Smith"
    assert meta.authors[1].name == "Bob Jones"
    assert meta.authors[1].affiliation == "Stanford"


def test_paper_metadata_empty_list_valid() -> None:
    """Empty authors list is valid."""
    meta = PaperMetadata(authors=[])
    assert meta.authors == []


def test_paper_metadata_missing_authors_raises() -> None:
    """Missing authors field raises ValidationError."""
    with pytest.raises(ValidationError):
        PaperMetadata.model_validate({})


def test_paper_metadata_authors_not_list_raises() -> None:
    """authors not a list raises ValidationError."""
    with pytest.raises(ValidationError):
        PaperMetadata.model_validate({"authors": "Alice"})


def test_paper_metadata_authors_item_not_author_info_raises() -> None:
    """authors list containing non-AuthorInfo (e.g. plain string) raises ValidationError."""
    with pytest.raises(ValidationError):
        PaperMetadata.model_validate({"authors": ["Alice", "Bob"]})


def test_paper_metadata_authors_item_missing_name_raises() -> None:
    """authors list item without name raises ValidationError."""
    with pytest.raises(ValidationError):
        PaperMetadata.model_validate({"authors": [{"affiliation": "MIT"}]})


# --- SearchResult ---


def test_search_result_minimal() -> None:
    """SearchResult with title and url is valid."""
    r = SearchResult(title="Foo", url="https://example.com")
    assert r.title == "Foo"
    assert r.snippet == ""
    assert r.url == "https://example.com"


def test_search_result_all_fields() -> None:
    """SearchResult with snippet is valid."""
    r = SearchResult(
        title="LinkedIn - John Doe",
        snippet="Profile page",
        url="https://linkedin.com/in/johndoe",
    )
    assert r.snippet == "Profile page"


# --- LinkedInReviewResult ---


def test_linkedin_review_result_valid() -> None:
    """LinkedInReviewResult with required confidence is valid."""
    r = LinkedInReviewResult(
        profile_urls=["https://linkedin.com/in/jane"],
        best_url="https://linkedin.com/in/jane",
        confidence=80,
    )
    assert r.confidence == 80
    assert r.best_url == "https://linkedin.com/in/jane"


def test_linkedin_review_result_confidence_bounds() -> None:
    """LinkedInReviewResult accepts 0 and 100."""
    LinkedInReviewResult(profile_urls=[], best_url=None, confidence=0)
    LinkedInReviewResult(profile_urls=[], best_url=None, confidence=100)


def test_linkedin_review_result_confidence_out_of_bounds_raises() -> None:
    """LinkedInReviewResult confidence must be 0-100."""
    with pytest.raises(ValidationError):
        LinkedInReviewResult(profile_urls=[], best_url=None, confidence=-1)
    with pytest.raises(ValidationError):
        LinkedInReviewResult(profile_urls=[], best_url=None, confidence=101)


# --- LinkedInLookupResult ---


def test_linkedin_lookup_result_found() -> None:
    """LinkedInLookupResult status found has single url."""
    author = AuthorInfo(name="Jane Doe")
    r = LinkedInLookupResult(
        author=author,
        status="found",
        url="https://linkedin.com/in/janedoe",
        urls=[],
    )
    assert r.status == "found"
    assert r.url == "https://linkedin.com/in/janedoe"
    assert r.urls == []


def test_linkedin_lookup_result_ambiguous() -> None:
    """LinkedInLookupResult status ambiguous has urls list."""
    author = AuthorInfo(name="John Smith")
    r = LinkedInLookupResult(
        author=author,
        status="ambiguous",
        url=None,
        urls=["https://linkedin.com/in/johnsmith1", "https://linkedin.com/in/johnsmith2"],
    )
    assert r.status == "ambiguous"
    assert r.url is None
    assert len(r.urls) == 2


def test_linkedin_lookup_result_not_found() -> None:
    """LinkedInLookupResult status not_found has no url."""
    author = AuthorInfo(name="Unknown")
    r = LinkedInLookupResult(author=author, status="not_found", url=None, urls=[])
    assert r.status == "not_found"
    assert r.url is None
    assert r.urls == []
