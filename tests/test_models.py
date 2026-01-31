"""Tests for Scholarlink Pydantic models."""

import pytest
from pydantic import ValidationError

from scholarlink.models import PaperMetadata


def test_paper_metadata_valid_authors() -> None:
    """Valid list of author strings builds and authors match."""
    meta = PaperMetadata(authors=["Alice Smith", "Bob Jones"])
    assert meta.authors == ["Alice Smith", "Bob Jones"]


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


def test_paper_metadata_non_string_item_raises() -> None:
    """Non-string item in authors raises ValidationError."""
    with pytest.raises(ValidationError):
        PaperMetadata.model_validate({"authors": ["Alice", 123]})
