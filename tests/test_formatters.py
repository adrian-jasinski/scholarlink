"""Tests for Scholarlink formatters."""

import csv
import io

from scholarlink.formatters import CSV_COLUMNS, authors_to_csv
from scholarlink.models import AuthorInfo


def test_authors_to_csv_empty_list_header_only() -> None:
    """Empty list with header returns only the header line."""
    result = authors_to_csv([], include_header=True)
    lines = result.splitlines()
    assert len(lines) == 1
    assert lines[0] == "name,affiliation,contact,orcid,other"


def test_authors_to_csv_empty_list_no_header() -> None:
    """Empty list without header returns empty string."""
    result = authors_to_csv([], include_header=False)
    assert result == ""


def test_authors_to_csv_one_author_all_fields() -> None:
    """One author with all fields produces header and one data line."""
    authors = [
        AuthorInfo(
            name="Alice",
            affiliation="MIT",
            contact="a@b.com",
            orcid="0000-0001-2345-6789",
            other="Lead",
        )
    ]
    result = authors_to_csv(authors)
    lines = result.splitlines()
    assert len(lines) == 2
    assert lines[0] == "name,affiliation,contact,orcid,other"
    # Parse second line as CSV to avoid depending on exact quoting
    row = next(csv.reader(io.StringIO(lines[1])))
    assert row == ["Alice", "MIT", "a@b.com", "0000-0001-2345-6789", "Lead"]


def test_authors_to_csv_one_author_name_only() -> None:
    """One author with only name produces correct row with empty optional columns."""
    authors = [AuthorInfo(name="Bob")]
    result = authors_to_csv(authors, include_header=True)
    lines = result.splitlines()
    assert len(lines) == 2
    row = next(csv.reader(io.StringIO(lines[1])))
    assert row == ["Bob", "", "", "", ""]


def test_authors_to_csv_multiple_authors() -> None:
    """Multiple authors produce one line per author."""
    authors = [
        AuthorInfo(name="Alice", affiliation="MIT"),
        AuthorInfo(name="Bob", affiliation="Stanford"),
    ]
    result = authors_to_csv(authors)
    lines = result.splitlines()
    assert len(lines) == 3
    assert lines[0] == "name,affiliation,contact,orcid,other"
    row1 = next(csv.reader(io.StringIO(lines[1])))
    row2 = next(csv.reader(io.StringIO(lines[2])))
    assert row1[0] == "Alice" and row1[1] == "MIT"
    assert row2[0] == "Bob" and row2[1] == "Stanford"


def test_authors_to_csv_escaping_comma() -> None:
    """Values containing commas are quoted so CSV round-trip preserves them."""
    authors = [
        AuthorInfo(name="Alice", affiliation="MIT, Department of Biology"),
    ]
    result = authors_to_csv(authors)
    lines = result.splitlines()
    assert len(lines) == 2
    row = next(csv.reader(io.StringIO(lines[1])))
    assert row[0] == "Alice"
    assert row[1] == "MIT, Department of Biology"


def test_authors_to_csv_escaping_quote() -> None:
    """Values containing double quotes are escaped for CSV round-trip."""
    authors = [
        AuthorInfo(name="Alice", other='Role: "Corresponding author"'),
    ]
    result = authors_to_csv(authors)
    lines = result.splitlines()
    assert len(lines) == 2
    row = next(csv.reader(io.StringIO(lines[1])))
    assert row[0] == "Alice"
    assert row[4] == 'Role: "Corresponding author"'


def test_csv_columns_constant() -> None:
    """CSV_COLUMNS matches expected column order."""
    assert CSV_COLUMNS == ("name", "affiliation", "contact", "orcid", "other")
