"""Read list of paper links from CSV or Excel files."""

import csv
from pathlib import Path

from openpyxl import load_workbook  # type: ignore[import-untyped]


def read_links_from_file(
    path: str | Path,
    column: str | None = None,
) -> list[str]:
    """
    Read paper URLs from a CSV or Excel file.

    For CSV: stdlib csv. For .xlsx: openpyxl (first sheet).
    If column is given, use that header (case-insensitive); else first column.
    Values are stripped; empty cells skipped.

    Args:
        path: Path to .csv or .xlsx file.
        column: Optional column name (header) to read; if None, first column.

    Returns:
        List of non-empty link strings.

    Raises:
        ValueError: If path has unsupported extension or column not found.
    """
    path = Path(path)
    suffix = path.suffix.lower()
    if suffix == ".csv":
        return _read_links_csv(path, column)
    if suffix == ".xlsx":
        return _read_links_excel(path, column)
    raise ValueError(
        f"Unsupported file type: {suffix}. Use .csv or .xlsx."
    )


def _read_links_csv(path: Path, column: str | None) -> list[str]:
    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.reader(f)
        row0 = next(reader, None)
        if row0 is None:
            return []
        if column is not None:
            col_index = _column_index_from_header(row0, column)
            if col_index is None:
                raise ValueError(
                    f"Column {column!r} not found in CSV. Headers: {row0!r}"
                )
        else:
            col_index = 0
        links: list[str] = []
        for row in reader:
            if col_index < len(row):
                val = (row[col_index] or "").strip()
                if val:
                    links.append(val)
        return links


def _column_index_from_header(headers: list[str], column: str) -> int | None:
    """Return 0-based index of header matching column (case-insensitive), else None."""
    want = column.strip().lower()
    for i, h in enumerate(headers):
        if (h or "").strip().lower() == want:
            return i
    return None


def _read_links_excel(path: Path, column: str | None) -> list[str]:
    wb = load_workbook(path, read_only=True, data_only=True)
    sheet = wb.active
    if sheet is None:
        wb.close()
        return []
    rows = list(sheet.iter_rows(values_only=True))
    wb.close()
    if not rows:
        return []
    row0 = [str(c) if c is not None else "" for c in rows[0]]
    if column is not None:
        col_index = _column_index_from_header(row0, column)
        if col_index is None:
            raise ValueError(
                f"Column {column!r} not in Excel. Headers: {row0!r}"
            )
    else:
        col_index = 0
    links: list[str] = []
    for row in rows[1:]:
        if col_index < len(row):
            val = row[col_index]
            if val is not None:
                val = str(val).strip()
            else:
                val = ""
            if val:
                links.append(val)
    return links
