"""Tests for output_csv module (author_name, link, optional linkedin)."""

import csv
import io
from pathlib import Path

import pytest

from scholarlink.models import AuthorInfo, LinkedInLookupResult
from scholarlink.output_csv import (
    OUTPUT_COLUMNS_BASE,
    OUTPUT_COLUMNS_WITH_LINKEDIN,
    authors_to_output_rows,
    write_output_csv,
)


def test_authors_to_output_rows_no_linkedin() -> None:
    """Without linkedin_results, rows have only author_name and link."""
    authors = [
        AuthorInfo(name="Alice", affiliation="MIT"),
        AuthorInfo(name="Bob"),
    ]
    rows = authors_to_output_rows(authors, "https://example.com/paper")
    assert len(rows) == 2
    assert rows[0] == {"author_name": "Alice", "link": "https://example.com/paper"}
    assert rows[1] == {"author_name": "Bob", "link": "https://example.com/paper"}


def test_authors_to_output_rows_with_linkedin_found() -> None:
    """With linkedin_results status 'found', linkedin column is single URL."""
    authors = [AuthorInfo(name="Jane")]
    results = [
        LinkedInLookupResult(
            author=authors[0],
            status="found",
            url="https://linkedin.com/in/jane",
            urls=[],
        )
    ]
    rows = authors_to_output_rows(authors, "https://paper.com/1", results)
    assert len(rows) == 1
    assert rows[0]["author_name"] == "Jane"
    assert rows[0]["link"] == "https://paper.com/1"
    assert rows[0]["linkedin"] == "https://linkedin.com/in/jane"


def test_authors_to_output_rows_with_linkedin_ambiguous() -> None:
    """With status 'ambiguous', linkedin column is semicolon-separated list."""
    authors = [AuthorInfo(name="Bob")]
    results = [
        LinkedInLookupResult(
            author=authors[0],
            status="ambiguous",
            url=None,
            urls=["https://linkedin.com/in/bob1", "https://linkedin.com/in/bob2"],
        )
    ]
    rows = authors_to_output_rows(authors, "https://paper.com/2", results)
    assert rows[0]["linkedin"] == "https://linkedin.com/in/bob1; https://linkedin.com/in/bob2"


def test_authors_to_output_rows_with_linkedin_not_found() -> None:
    """With status 'not_found', linkedin column is empty."""
    authors = [AuthorInfo(name="Unknown")]
    results = [
        LinkedInLookupResult(
            author=authors[0],
            status="not_found",
            url=None,
            urls=[],
        )
    ]
    rows = authors_to_output_rows(authors, "https://paper.com/3", results)
    assert rows[0]["linkedin"] == ""


def test_authors_to_output_rows_empty_authors() -> None:
    """Empty authors list returns empty rows."""
    rows = authors_to_output_rows([], "https://example.com/paper")
    assert rows == []


def test_write_output_csv_to_path(tmp_path: Path) -> None:
    """write_output_csv writes UTF-8 CSV with header and rows."""
    rows = [
        {"author_name": "Alice", "link": "https://a.com"},
        {"author_name": "Bob", "link": "https://b.com"},
    ]
    out = tmp_path / "out.csv"
    write_output_csv(rows, str(out), include_linkedin=False)
    content = out.read_text(encoding="utf-8")
    lines = content.splitlines()
    assert lines[0] == "author_name,link"
    assert "Alice" in content and "Bob" in content


def test_write_output_csv_with_linkedin(tmp_path: Path) -> None:
    """write_output_csv with include_linkedin adds linkedin column."""
    rows = [
        {"author_name": "A", "link": "https://a.com", "linkedin": "https://linkedin.com/in/a"},
    ]
    out = tmp_path / "out.csv"
    write_output_csv(rows, out, include_linkedin=True)
    content = out.read_text(encoding="utf-8")
    assert "author_name,link,linkedin" in content
    assert "linkedin.com/in/a" in content


def test_write_output_csv_to_file_object() -> None:
    """write_output_csv accepts file-like object."""
    rows = [{"author_name": "X", "link": "https://x.com"}]
    buf = io.StringIO()
    write_output_csv(rows, buf, include_linkedin=False)
    content = buf.getvalue()
    assert "author_name,link" in content
    assert "X" in content


def test_output_columns_constants() -> None:
    """Output column tuples are as expected."""
    assert OUTPUT_COLUMNS_BASE == ("author_name", "link")
    assert OUTPUT_COLUMNS_WITH_LINKEDIN == ("author_name", "link", "linkedin")
