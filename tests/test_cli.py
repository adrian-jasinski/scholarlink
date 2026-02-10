"""Tests for Scholarlink CLI."""

import json
from unittest.mock import AsyncMock, patch

import typer.testing

from scholarlink.cli import app
from scholarlink.crawler import ExtractionError
from scholarlink.models import AuthorInfo


def _csv_two_authors() -> str:
    return (
        "name,affiliation,contact,orcid,other\n"
        "Alice,MIT,a@b.com,,\nBob,Stanford,,0000-0002-3456-7890,"
    )


def test_cli_invoke_success_stdout_csv() -> None:
    """paper <url> returns exit 0 and stdout is CSV (header + one line per author)."""
    authors = [
        AuthorInfo(name="Alice", affiliation="MIT", contact="a@b.com"),
        AuthorInfo(name="Bob", affiliation="Stanford", orcid="0000-0002-3456-7890"),
    ]
    csv_str = _csv_two_authors()

    with patch(
        "scholarlink.cli.extract_authors",
        new_callable=AsyncMock,
        return_value=(authors, csv_str),
    ):
        runner = typer.testing.CliRunner()
        result = runner.invoke(app, ["paper", "https://example.com/paper"])
    assert result.exit_code == 0
    assert "name,affiliation,contact,orcid,other" in result.stdout
    assert "Alice" in result.stdout and "Bob" in result.stdout


def test_cli_invoke_invalid_mode_exit_2() -> None:
    """--mode invalid returns exit 2 and stderr mentions mode."""
    runner = typer.testing.CliRunner()
    result = runner.invoke(app, ["paper", "--mode=invalid", "https://example.com/paper"])
    assert result.exit_code == 2
    assert "mode" in result.stderr.lower()


def test_cli_extraction_error_exit_1() -> None:
    """When extract_authors raises ExtractionError, exit 1 and stderr contains message."""
    with patch(
        "scholarlink.cli.extract_authors",
        new_callable=AsyncMock,
        side_effect=ExtractionError("Crawl failed for URL"),
    ):
        runner = typer.testing.CliRunner()
        result = runner.invoke(app, ["paper", "https://example.com/paper"])
    assert result.exit_code == 1
    assert "Crawl failed" in result.stderr


def test_cli_json_output() -> None:
    """paper --json returns exit 0 and valid JSON with authors (list of objects) and csv."""
    authors = [AuthorInfo(name="Alice", affiliation="MIT")]
    csv_str = "name,affiliation,contact,orcid,other\nAlice,MIT,,,"

    with patch(
        "scholarlink.cli.extract_authors",
        new_callable=AsyncMock,
        return_value=(authors, csv_str),
    ):
        runner = typer.testing.CliRunner()
        result = runner.invoke(app, ["paper", "--json", "https://example.com/paper"])
    assert result.exit_code == 0
    data = json.loads(result.stdout)
    assert "authors" in data
    assert "csv" in data
    expected = [
        {
            "name": "Alice",
            "affiliation": "MIT",
            "contact": None,
            "orcid": None,
            "other": None,
        }
    ]
    assert data["authors"] == expected
    assert data["csv"] == csv_str


def test_cli_linkedin_flag_success() -> None:
    """--linkedin runs extract then find_linkedin_profiles and prints tab-separated."""
    from scholarlink.models import LinkedInLookupResult

    authors = [AuthorInfo(name="Alice")]
    lookup_results = [
        LinkedInLookupResult(
            author=authors[0],
            status="found",
            url="https://linkedin.com/in/alice",
            urls=[],
        )
    ]
    with patch(
        "scholarlink.cli.extract_authors",
        new_callable=AsyncMock,
        return_value=(authors, "name,affiliation,contact,orcid,other\nAlice,,,,"),
    ), patch(
        "scholarlink.cli.find_linkedin_profiles",
        new_callable=AsyncMock,
        return_value=lookup_results,
    ):
        runner = typer.testing.CliRunner()
        result = runner.invoke(app, ["paper", "--linkedin", "https://example.com/paper"])
    assert result.exit_code == 0
    assert "Alice" in result.stdout
    assert "found" in result.stdout
    assert "linkedin.com/in/alice" in result.stdout


def test_cli_linkedin_flag_json() -> None:
    """--linkedin --json outputs JSON array of lookup results."""
    from scholarlink.models import LinkedInLookupResult

    authors = [AuthorInfo(name="Bob")]
    lookup_results = [
        LinkedInLookupResult(
            author=authors[0],
            status="ambiguous",
            url=None,
            urls=["https://linkedin.com/in/bob1"],
        )
    ]
    with patch(
        "scholarlink.cli.extract_authors",
        new_callable=AsyncMock,
        return_value=(authors, "csv"),
    ), patch(
        "scholarlink.cli.find_linkedin_profiles",
        new_callable=AsyncMock,
        return_value=lookup_results,
    ):
        runner = typer.testing.CliRunner()
        result = runner.invoke(app, ["paper", "--linkedin", "--json", "https://example.com/paper"])
    assert result.exit_code == 0
    data = json.loads(result.stdout)
    assert isinstance(data, list)
    assert len(data) == 1
    assert data[0]["status"] == "ambiguous"
    assert data[0]["urls"] == ["https://linkedin.com/in/bob1"]


def test_cli_output_writes_csv(tmp_path) -> None:
    """paper --output FILE calls extract_authors_single and writes CSV, prints confirmation."""
    with patch(
        "scholarlink.cli.extract_authors_single",
        new_callable=AsyncMock,
        return_value=[
            {"author_name": "Alice", "link": "https://example.com/paper"},
        ],
    ):
        runner = typer.testing.CliRunner()
        out_file = tmp_path / "authors.csv"
        result = runner.invoke(app, ["paper", "https://example.com/paper", "--output", str(out_file)])
    assert result.exit_code == 0
    assert "Wrote CSV to" in result.stdout
    assert str(out_file) in result.stdout


def test_cli_from_file_success(tmp_path) -> None:
    """from-file subcommand calls extract_authors_from_file and prints confirmation."""
    in_file = tmp_path / "in.csv"
    in_file.write_text("url\nhttps://a.com\n", encoding="utf-8")
    out_file = tmp_path / "out.csv"

    with patch(
        "scholarlink.cli.extract_authors_from_file",
        new_callable=AsyncMock,
    ):
        runner = typer.testing.CliRunner()
        result = runner.invoke(
            app,
            [
                "from-file",
                str(in_file),
                "--output",
                str(out_file),
            ],
        )
    assert result.exit_code == 0
    assert "Wrote CSV to" in result.stdout
    assert str(out_file) in result.stdout


def test_cli_from_file_linkedin_flag(tmp_path) -> None:
    """from-file with --linkedin passes linkedin=True."""
    in_file = tmp_path / "in.csv"
    in_file.write_text("url\nhttps://a.com\n", encoding="utf-8")
    out_file = tmp_path / "out.csv"

    with patch(
        "scholarlink.cli.extract_authors_from_file",
        new_callable=AsyncMock,
    ) as mock_fn:
        runner = typer.testing.CliRunner()
        runner.invoke(
            app,
            ["from-file", str(in_file), "--output", str(out_file), "--linkedin"],
        )
        mock_fn.assert_called_once()
        call_kw = mock_fn.call_args[1]
        assert call_kw["linkedin"] is True
        assert call_kw["output_path"] == str(out_file)
