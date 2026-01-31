"""CLI for Scholarlink."""

import asyncio
import json

import typer

from scholarlink.api import extract_authors
from scholarlink.crawler import ExtractionError

app = typer.Typer(
    help="Extract publication authors from a scientific paper URL using Crawl4AI.",
    invoke_without_command=True,
)


@app.callback()
def run_cmd(
    url: str = typer.Argument(
        ...,
        help="URL of the paper (e.g. https://www.biorxiv.org/content/10.1101/2025.08.14.670328v1)",
    ),
    json_output: bool = typer.Option(
        False,
        "--json",
        help='Output authors as JSON: {"authors": [...], "authors_str": "..."}',
    ),
) -> None:
    try:
        authors_list, authors_str = asyncio.run(extract_authors(url))
    except ExtractionError as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(1) from None

    if json_output:
        typer.echo(json.dumps({"authors": authors_list, "authors_str": authors_str}))
    else:
        typer.echo(authors_str)


def main() -> None:
    """Entry point for the script (pyproject.scripts)."""
    app()


if __name__ == "__main__":
    main()
