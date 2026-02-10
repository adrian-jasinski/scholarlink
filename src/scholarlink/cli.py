"""CLI for Scholarlink."""

import asyncio
import json
import os

import typer

from scholarlink.api import (
    extract_authors,
    extract_authors_from_file,
    extract_authors_single,
    find_linkedin_profiles,
)
from scholarlink.config import reset_config
from scholarlink.crawler import CRAWLER_MODES, MODE_HELP, ExtractionError

app = typer.Typer(
    help=("Extract publication authors from a scientific paper URL using Crawl4AI."),
    invoke_without_command=True,
)


@app.callback()
def run_cmd(
    config: str | None = typer.Option(
        None,
        "--config",
        help="Path to TOML config file (overrides SCHOLARLINK_CONFIG and default scholarlink.toml).",
    ),
) -> None:
    if config is not None:
        os.environ["SCHOLARLINK_CONFIG"] = config
        reset_config()


@app.command("paper")
def paper_cmd(
    url: str = typer.Argument(
        ...,
        help="URL of the paper (e.g. biorxiv or PNAS article page)",
    ),
    json_output: bool = typer.Option(
        False,
        "--json",
        help='Output authors as JSON: {"authors": [...], "csv": "..."}; with --linkedin output LinkedIn results as JSON',
    ),
    linkedin: bool = typer.Option(
        False,
        "--linkedin",
        help="After extracting authors, find LinkedIn profile(s) per author (uses Google search)",
    ),
    output: str | None = typer.Option(
        None,
        "--output",
        help="Write result to CSV file (author_name, link, optional linkedin column)",
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
    if output is not None:
        try:
            asyncio.run(
                extract_authors_single(
                    url,
                    linkedin=linkedin,
                    output_path=output,
                    mode=mode,
                    cloudflare_manual=cloudflare_manual,
                )
            )
        except ExtractionError as e:
            typer.echo(f"Error: {e}", err=True)
            raise typer.Exit(1) from None
        except ValueError as e:
            typer.echo(f"Error: {e}", err=True)
            raise typer.Exit(1) from None
        typer.echo(f"Wrote CSV to {output}")
        return
    try:
        authors_list, csv_str = asyncio.run(
            extract_authors(url, mode=mode, cloudflare_manual=cloudflare_manual)
        )
    except ExtractionError as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(1) from None
    if linkedin:
        if not authors_list:
            typer.echo("No authors extracted.", err=True)
            raise typer.Exit(0) from None
        try:
            results = asyncio.run(find_linkedin_profiles(authors_list))
        except ValueError as e:
            typer.echo(f"Error: {e}", err=True)
            raise typer.Exit(1) from None
        if json_output:
            out = [
                {
                    "author": r.author.model_dump(),
                    "status": r.status,
                    "url": r.url,
                    "urls": r.urls,
                }
                for r in results
            ]
            typer.echo(json.dumps(out))
        else:
            for r in results:
                typer.echo(f"{r.author.name}\t{r.status}\t{r.url or ''}\t{','.join(r.urls)}")
    else:
        if json_output:
            authors_data = [a.model_dump() for a in authors_list]
            typer.echo(json.dumps({"authors": authors_data, "csv": csv_str}))
        else:
            typer.echo(csv_str)


@app.command()
def from_file(
    input_file: str = typer.Argument(
        ...,
        help="Path to CSV or Excel file with a column of paper URLs",
    ),
    column: str | None = typer.Option(
        None,
        "--column",
        help="Column name (header) containing links; if omitted, first column is used",
    ),
    linkedin: bool = typer.Option(
        False,
        "--linkedin",
        help="Find LinkedIn profile(s) per author",
    ),
    output: str = typer.Option(
        ...,
        "--output",
        help="Path for output CSV file (author_name, link, optional linkedin)",
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
        asyncio.run(
            extract_authors_from_file(
                input_file,
                column=column,
                linkedin=linkedin,
                output_path=output,
                mode=mode,
                cloudflare_manual=cloudflare_manual,
            )
        )
    except ValueError as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(1) from None
    typer.echo(f"Wrote CSV to {output}")


def main() -> None:
    """Entry point for the script (pyproject.scripts)."""
    app()


if __name__ == "__main__":
    main()
