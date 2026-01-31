"""Tests for Scholarlink Pydantic models."""

import pytest
from pydantic import ValidationError

from scholarlink.models import AuthorInfo, PaperMetadata

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
