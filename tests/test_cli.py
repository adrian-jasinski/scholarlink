"""Tests for Scholarlink CLI."""

import json
from unittest.mock import AsyncMock, patch

import typer.testing

from scholarlink.cli import app
from scholarlink.crawler import ExtractionError


def test_cli_invoke_success_stdout_authors() -> None:
    """Invoke with URL returns exit 0 and stdout contains authors string."""
    with patch(
        "scholarlink.cli.extract_authors",
        new_callable=AsyncMock,
        return_value=(["Alice", "Bob"], "Alice, Bob"),
    ):
        runner = typer.testing.CliRunner()
        result = runner.invoke(app, ["https://example.com/paper"])
    assert result.exit_code == 0
    assert "Alice, Bob" in result.stdout


def test_cli_invoke_invalid_mode_exit_2() -> None:
    """--mode invalid returns exit 2 and stderr mentions mode."""
    runner = typer.testing.CliRunner()
    # Pass URL as first positional; use --mode=invalid so "invalid" is not parsed as a command
    result = runner.invoke(app, ["--mode=invalid", "https://example.com/paper"])
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
        result = runner.invoke(app, ["https://example.com/paper"])
    assert result.exit_code == 1
    assert "Crawl failed" in result.stderr


def test_cli_json_output() -> None:
    """--json returns exit 0 and valid JSON with authors and authors_str."""
    with patch(
        "scholarlink.cli.extract_authors",
        new_callable=AsyncMock,
        return_value=(["Alice"], "Alice"),
    ):
        runner = typer.testing.CliRunner()
        # Pass URL first so it is not consumed by --json
        result = runner.invoke(app, ["--json", "https://example.com/paper"])
    assert result.exit_code == 0
    data = json.loads(result.stdout)
    assert "authors" in data
    assert "authors_str" in data
    assert data["authors"] == ["Alice"]
    assert data["authors_str"] == "Alice"
