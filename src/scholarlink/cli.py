"""CLI for Scholarlink."""

import asyncio
import json
import os

import typer

from scholarlink.api import extract_authors
from scholarlink.config import reset_config
from scholarlink.crawler import CRAWLER_MODES, MODE_HELP, ExtractionError

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
        help='Output authors as JSON: {"authors": [...], "csv": "..."}',
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
    config: str | None = typer.Option(
        None,
        "--config",
        help="Path to TOML config file (overrides SCHOLARLINK_CONFIG and default scholarlink.toml).",
    ),
) -> None:
    if config is not None:
        os.environ["SCHOLARLINK_CONFIG"] = config
        reset_config()
    if mode not in CRAWLER_MODES:
        typer.echo(
            f"Error: --mode must be one of {CRAWLER_MODES!r}, got {mode!r}",
            err=True,
        )
        raise typer.Exit(2) from None
    try:
        authors_list, csv_str = asyncio.run(
            extract_authors(url, mode=mode, cloudflare_manual=cloudflare_manual)
        )
    except ExtractionError as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(1) from None

    if json_output:
        authors_data = [a.model_dump() for a in authors_list]
        typer.echo(json.dumps({"authors": authors_data, "csv": csv_str}))
    else:
        typer.echo(csv_str)


def main() -> None:
    """Entry point for the script (pyproject.scripts)."""
    app()


if __name__ == "__main__":
    main()
