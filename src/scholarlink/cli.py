"""CLI for Scholarlink."""

import asyncio
import json

import typer

from scholarlink.api import extract_authors
from scholarlink.crawler import CRAWLER_MODES, ExtractionError, MODE_HELP

app = typer.Typer(
    help=("Extract publication authors from a scientific paper URL using Crawl4AI."),
    invoke_without_command=True,
)


@app.callback()
def run_cmd(
    url: str = typer.Argument(
        ...,
        help="URL of the paper (e.g. biorxiv or PNAS article page)",
    ),
    json_output: bool = typer.Option(
        False,
        "--json",
        help='Output authors as JSON: {"authors": [...], "authors_str": "..."}',
    ),
    mode: str = typer.Option(
        "normal",
        "--mode",
        help=f"Crawler mode: {MODE_HELP}.",
    ),
    cloudflare_manual: bool = typer.Option(
        False,
        "--cloudflare-manual",
        help=(
            "For protected domains: show browser and wait so you can complete "
            "Cloudflare challenge manually."
        ),
    ),
) -> None:
    if mode not in CRAWLER_MODES:
        typer.echo(
            f"Error: --mode must be one of {CRAWLER_MODES!r}, got {mode!r}",
            err=True,
        )
        raise typer.Exit(2) from None
    try:
        authors_list, authors_str = asyncio.run(
            extract_authors(url, mode=mode, cloudflare_manual=cloudflare_manual)
        )
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
