"""Tests for input_links module (read links from CSV/Excel)."""

from pathlib import Path

import pytest

from scholarlink.input_links import read_links_from_file


def test_read_links_csv_first_column(tmp_path: Path) -> None:
    """CSV with no column uses first column."""
    csv_path = tmp_path / "links.csv"
    csv_path.write_text(
        "url\n"
        "https://example.com/paper1\n"
        "https://example.com/paper2\n",
        encoding="utf-8",
    )
    links = read_links_from_file(csv_path)
    assert links == ["https://example.com/paper1", "https://example.com/paper2"]


def test_read_links_csv_with_column_name(tmp_path: Path) -> None:
    """CSV with --column uses that header."""
    csv_path = tmp_path / "links.csv"
    csv_path.write_text(
        "title,link,notes\n"
        "Paper A,https://a.com,\n"
        "Paper B,https://b.com,\n",
        encoding="utf-8",
    )
    links = read_links_from_file(csv_path, column="link")
    assert links == ["https://a.com", "https://b.com"]


def test_read_links_csv_column_case_insensitive(tmp_path: Path) -> None:
    """Column name match is case-insensitive."""
    csv_path = tmp_path / "links.csv"
    csv_path.write_text(
        "URL\nhttps://example.com/1\n",
        encoding="utf-8",
    )
    links = read_links_from_file(csv_path, column="url")
    assert links == ["https://example.com/1"]


def test_read_links_csv_skips_empty(tmp_path: Path) -> None:
    """Empty cells are skipped."""
    csv_path = tmp_path / "links.csv"
    csv_path.write_text(
        "url\n"
        "https://first.com\n"
        "\n"
        "https://third.com\n",
        encoding="utf-8",
    )
    links = read_links_from_file(csv_path)
    assert links == ["https://first.com", "https://third.com"]


def test_read_links_csv_column_not_found_raises(tmp_path: Path) -> None:
    """Missing column name raises ValueError."""
    csv_path = tmp_path / "links.csv"
    csv_path.write_text("a,b\n1,2\n", encoding="utf-8")
    with pytest.raises(ValueError, match="Column .* not found"):
        read_links_from_file(csv_path, column="nonexistent")


def test_read_links_csv_empty_file(tmp_path: Path) -> None:
    """Empty CSV returns empty list."""
    csv_path = tmp_path / "empty.csv"
    csv_path.write_text("", encoding="utf-8")
    links = read_links_from_file(csv_path)
    assert links == []


def test_read_links_excel_first_column(tmp_path: Path) -> None:
    """Excel first sheet, first column when no column name."""
    from openpyxl import Workbook

    xlsx_path = tmp_path / "links.xlsx"
    wb = Workbook()
    ws = wb.active
    ws.append(["url"])
    ws.append(["https://example.com/1"])
    ws.append(["https://example.com/2"])
    wb.save(xlsx_path)
    wb.close()
    links = read_links_from_file(xlsx_path)
    assert links == ["https://example.com/1", "https://example.com/2"]


def test_read_links_excel_with_column_name(tmp_path: Path) -> None:
    """Excel with column name uses that header."""
    from openpyxl import Workbook

    xlsx_path = tmp_path / "links.xlsx"
    wb = Workbook()
    ws = wb.active
    ws.append(["title", "link"])
    ws.append(["Paper 1", "https://p1.com"])
    ws.append(["Paper 2", "https://p2.com"])
    wb.save(xlsx_path)
    wb.close()
    links = read_links_from_file(xlsx_path, column="link")
    assert links == ["https://p1.com", "https://p2.com"]


def test_read_links_unsupported_extension_raises(tmp_path: Path) -> None:
    """Unsupported file extension raises ValueError."""
    bad = tmp_path / "file.txt"
    bad.write_text("x", encoding="utf-8")
    with pytest.raises(ValueError, match="Unsupported file type"):
        read_links_from_file(bad)
