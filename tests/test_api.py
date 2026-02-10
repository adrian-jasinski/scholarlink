"""Tests for Scholarlink public API."""

from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from scholarlink.api import (
    extract_authors,
    extract_authors_from_file,
    extract_authors_single,
    find_linkedin_profiles,
)
from scholarlink.models import AuthorInfo, LinkedInLookupResult


@pytest.mark.asyncio
async def test_extract_authors_returns_result_from_crawler() -> None:
    """extract_authors returns (list[AuthorInfo], csv_str) from extract_authors_from_url."""
    authors = [AuthorInfo(name="A")]
    csv_str = "name,affiliation,contact,orcid,other\nA,,,,"

    with patch(
        "scholarlink.api.extract_authors_from_url",
        new_callable=AsyncMock,
        return_value=(authors, csv_str),
    ):
        result = await extract_authors("https://example.com/paper")
    assert result[0] == authors
    assert result[1] == csv_str


@pytest.mark.asyncio
async def test_extract_authors_forwards_mode_and_cloudflare_manual() -> None:
    """extract_authors forwards mode and cloudflare_manual to extract_authors_from_url."""
    authors = [AuthorInfo(name="Alice")]
    csv_str = "name,affiliation,contact,orcid,other\nAlice,,,,"

    with patch(
        "scholarlink.api.extract_authors_from_url",
        new_callable=AsyncMock,
        return_value=(authors, csv_str),
    ) as mock_extract:
        await extract_authors(
            "https://example.com/paper",
            mode="stealth",
            cloudflare_manual=True,
        )
        mock_extract.assert_called_once_with(
            "https://example.com/paper",
            mode="stealth",
            cloudflare_manual=True,
        )


@pytest.mark.asyncio
async def test_find_linkedin_profiles_returns_results() -> None:
    """find_linkedin_profiles returns list of LinkedInLookupResult from search_linkedin_profiles."""
    from scholarlink.models import LinkedInLookupResult

    authors = [AuthorInfo(name="Jane")]
    expected = [
        LinkedInLookupResult(
            author=authors[0],
            status="found",
            url="https://linkedin.com/in/jane",
            urls=[],
        )
    ]
    with patch(
        "scholarlink.api.search_linkedin_profiles",
        new_callable=AsyncMock,
        return_value=expected,
    ):
        result = await find_linkedin_profiles(authors)
    assert result == expected
    assert len(result) == 1
    assert result[0].status == "found"
    assert result[0].url == "https://linkedin.com/in/jane"


@pytest.mark.asyncio
async def test_extract_authors_single_returns_rows() -> None:
    """extract_authors_single returns list of dicts with author_name, link."""
    authors = [AuthorInfo(name="Alice"), AuthorInfo(name="Bob")]
    csv_str = "name,affiliation,contact,orcid,other\nAlice,,,,\nBob,,,,"

    with patch(
        "scholarlink.api.extract_authors_from_url",
        new_callable=AsyncMock,
        return_value=(authors, csv_str),
    ):
        result = await extract_authors_single("https://example.com/paper")
    assert len(result) == 2
    assert result[0]["author_name"] == "Alice"
    assert result[0]["link"] == "https://example.com/paper"
    assert result[1]["author_name"] == "Bob"
    assert result[1]["link"] == "https://example.com/paper"


@pytest.mark.asyncio
async def test_extract_authors_single_with_linkedin() -> None:
    """extract_authors_single with linkedin=True includes linkedin in rows."""
    authors = [AuthorInfo(name="Jane")]
    csv_str = "name,affiliation,contact,orcid,other\nJane,,,,"

    with patch(
        "scholarlink.api.extract_authors_from_url",
        new_callable=AsyncMock,
        return_value=(authors, csv_str),
    ), patch(
        "scholarlink.api.search_linkedin_profiles",
        new_callable=AsyncMock,
        return_value=[
            LinkedInLookupResult(
                author=authors[0],
                status="found",
                url="https://linkedin.com/in/jane",
                urls=[],
            )
        ],
    ):
        result = await extract_authors_single(
            "https://example.com/paper",
            linkedin=True,
        )
    assert result[0]["linkedin"] == "https://linkedin.com/in/jane"


@pytest.mark.asyncio
async def test_extract_authors_single_writes_csv_when_output_path_set(tmp_path: Path) -> None:
    """extract_authors_single with output_path writes CSV file."""
    authors = [AuthorInfo(name="Alice")]
    csv_str = "name,affiliation,contact,orcid,other\nAlice,,,,"

    with patch(
        "scholarlink.api.extract_authors_from_url",
        new_callable=AsyncMock,
        return_value=(authors, csv_str),
    ):
        out = tmp_path / "out.csv"
        await extract_authors_single("https://example.com/paper", output_path=str(out))
    content = out.read_text(encoding="utf-8")
    assert "author_name,link" in content
    assert "Alice" in content
    assert "https://example.com/paper" in content


@pytest.mark.asyncio
async def test_extract_authors_from_file_writes_csv(tmp_path: Path) -> None:
    """extract_authors_from_file reads links, extracts, writes output CSV."""
    csv_in = tmp_path / "in.csv"
    csv_in.write_text("url\nhttps://a.com\nhttps://b.com\n", encoding="utf-8")
    out_path = tmp_path / "out.csv"

    authors_a = [AuthorInfo(name="A1")]
    authors_b = [AuthorInfo(name="B1")]

    with patch(
        "scholarlink.api.read_links_from_file",
        return_value=["https://a.com", "https://b.com"],
    ), patch(
        "scholarlink.api.extract_authors_from_url",
        new_callable=AsyncMock,
        side_effect=[
            (authors_a, "csv1"),
            (authors_b, "csv2"),
        ],
    ):
        await extract_authors_from_file(str(csv_in), output_path=str(out_path))

    content = out_path.read_text(encoding="utf-8")
    assert "author_name,link" in content
    assert "A1" in content and "https://a.com" in content
    assert "B1" in content and "https://b.com" in content


@pytest.mark.asyncio
async def test_extract_authors_from_file_skips_failed_url(tmp_path: Path) -> None:
    """When one URL raises ExtractionError, it is skipped and rest are processed."""
    from scholarlink.crawler import ExtractionError

    out_path = tmp_path / "out.csv"

    with patch(
        "scholarlink.api.read_links_from_file",
        return_value=["https://fail.com", "https://ok.com"],
    ), patch(
        "scholarlink.api.extract_authors_from_url",
        new_callable=AsyncMock,
        side_effect=[
            ExtractionError("Crawl failed"),
            ([AuthorInfo(name="Only")], "csv"),
        ],
    ):
        await extract_authors_from_file("dummy.csv", output_path=str(out_path))

    content = out_path.read_text(encoding="utf-8")
    assert "Only" in content
    assert "https://ok.com" in content
    assert "fail.com" not in content or content.count("https://") == 1
