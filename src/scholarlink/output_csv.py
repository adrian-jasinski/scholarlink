"""Output CSV format: Author name, Link, optional LinkedIn."""

import csv
import io
from pathlib import Path
from typing import IO

from scholarlink.models import AuthorInfo, LinkedInLookupResult

OUTPUT_COLUMNS_BASE = ("author_name", "link")
OUTPUT_COLUMNS_WITH_LINKEDIN = ("author_name", "link", "linkedin")


def authors_to_output_rows(
    authors: list[AuthorInfo],
    link: str,
    linkedin_results: list[LinkedInLookupResult] | None = None,
) -> list[dict]:
    """
    Build output rows for the author+link CSV format.

    One row per author with author_name and link. If linkedin_results is
    provided (one per author in same order), add linkedin column: single URL
    when status is "found", semicolon-separated list when "ambiguous", empty
    when "not_found".

    Args:
        authors: List of extracted authors.
        link: Publication URL.
        linkedin_results: Optional list of LinkedInLookupResult, one per author.

    Returns:
        List of dicts with keys author_name, link, and optionally linkedin.
    """
    include_linkedin = linkedin_results is not None
    rows: list[dict] = []
    for i, author in enumerate(authors):
        row: dict = {
            "author_name": author.name or "",
            "link": link,
        }
        if include_linkedin and i < len(linkedin_results):
            result = linkedin_results[i]
            if result.status == "found" and result.url:
                row["linkedin"] = result.url
            elif result.status == "ambiguous" and result.urls:
                row["linkedin"] = "; ".join(result.urls)
            else:
                row["linkedin"] = ""
        elif include_linkedin:
            row["linkedin"] = ""
        rows.append(row)
    return rows


def write_output_csv(
    rows: list[dict],
    path_or_file: str | Path | IO[str],
    include_linkedin: bool,
) -> None:
    """
    Write rows to CSV with header. Uses columns author_name, link, and
    optionally linkedin. UTF-8 encoding when writing to a path.

    Args:
        rows: List of dicts with author_name, link, and optionally linkedin.
        path_or_file: File path (str or Path) or open file object.
        include_linkedin: If True, include linkedin column in header and rows.
    """
    columns = OUTPUT_COLUMNS_WITH_LINKEDIN if include_linkedin else OUTPUT_COLUMNS_BASE
    if isinstance(path_or_file, (str, Path)):
        with open(path_or_file, "w", newline="", encoding="utf-8") as f:
            _write_csv_to_file(f, rows, columns, include_linkedin)
    else:
        _write_csv_to_file(path_or_file, rows, columns, include_linkedin)


def _write_csv_to_file(
    f: IO[str],
    rows: list[dict],
    columns: tuple[str, ...],
    include_linkedin: bool,
) -> None:
    writer = csv.DictWriter(f, fieldnames=columns, quoting=csv.QUOTE_MINIMAL)
    writer.writeheader()
    for row in rows:
        out_row = {k: row.get(k, "") for k in columns}
        writer.writerow(out_row)
