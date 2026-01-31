"""Formatting utilities for author data."""

import csv
import io

from scholarlink.models import AuthorInfo

CSV_COLUMNS = ("name", "affiliation", "contact", "orcid", "other")


def authors_to_csv(authors: list[AuthorInfo], include_header: bool = True) -> str:
    """
    Format a list of AuthorInfo as a CSV-like string.

    Columns: name, affiliation, contact, orcid, other.
    One line per author. Uses RFC 4180-style quoting for commas/quotes.

    Args:
        authors: List of author info objects.
        include_header: If True, first line is the column header.

    Returns:
        CSV string (with optional header).
    """
    out = io.StringIO()
    writer = csv.writer(out, quoting=csv.QUOTE_MINIMAL)
    if include_header:
        writer.writerow(CSV_COLUMNS)
    for a in authors:
        row = [
            a.name or "",
            a.affiliation or "",
            a.contact or "",
            a.orcid or "",
            a.other or "",
        ]
        writer.writerow(row)
    return out.getvalue().rstrip("\n")
