# Scholarlink

Extract publication authors from scientific paper URLs using [Crawl4AI](https://github.com/unclecode/crawl4ai). Supports bioRxiv, PNAS, and other publishers via LLM-based extraction.

## Install

```bash
uv sync
```

Optional: install Crawl4AI’s browser (required for crawling). If you see browser-related errors, run:

```bash
crawl4ai-setup
# or
uv run python -m playwright install chromium
```

## Environment

Scholarlink loads variables from a `.env` file in the project root (via [python-dotenv](https://github.com/theskumar/python-dotenv)). Put your API key there so you don't need to export it in the shell:

```bash
# .env
OPENAI_API_KEY=sk-...
```

**Environment variables** (env overrides config file and defaults):

- **`OPENAI_API_KEY`** (required for default LLM): Set your OpenAI API key for author extraction.
- **`SCHOLARLINK_LLM_PROVIDER`** (optional): LLM provider string, e.g. `openai/gpt-4o-mini` (default) or `ollama/llama3.3` for local models.
- **`SCHOLARLINK_PROTECTED_DOMAINS`** (optional): Comma-separated hostnames that use Cloudflare (e.g. `biorxiv.org,pnas.org`). For these domains the crawler uses undetected browser + stealth; if unset, defaults from config or built-in list are used.
- **`SCHOLARLINK_CLOUDFLARE_MANUAL_WAIT_SECONDS`** (optional): Seconds to wait when completing Cloudflare challenge manually (default: 7).
- **`SCHOLARLINK_DELAY_DEFAULT`** (optional): Crawl delay in seconds when not on a protected domain (default: 0.1).
- **`SCHOLARLINK_DELAY_PROTECTED`** (optional): Crawl delay in seconds when on a protected domain without manual Cloudflare (default: 3.0).
- **`SCHOLARLINK_LLM_TEMPERATURE`** (optional): LLM temperature (default: 0.0).
- **`SCHOLARLINK_LLM_MAX_TOKENS`** (optional): LLM max tokens (default: 2000).
- **`SCHOLARLINK_CONFIG`** (optional): Path to a TOML config file. If unset, Scholarlink looks for `scholarlink.toml` in the current working directory.
- **LinkedIn lookup** (for `--linkedin`): uses **DuckDuckGo** search (free, no API key). **`SCHOLARLINK_SEARCH_PROVIDER`** (optional): `duckduckgo` (default). **`SCHOLARLINK_SEARCH_MAX_RESULTS`** (optional): max search results per author (default: 10).

**Optional config file**

You can put non-secret options in a TOML file (e.g. `scholarlink.toml` in the project root or path given by `SCHOLARLINK_CONFIG`). Load order: built-in defaults → config file → environment variables. See [scholarlink.toml.example](scholarlink.toml.example) for all options and comments.

## Usage

**CLI**

```bash
# Print comma-separated authors
uv run scholarlink "https://www.biorxiv.org/content/10.1101/2025.08.14.670328v1"

# Output JSON: {"authors": [...], "authors_str": "..."}
uv run scholarlink "https://www.biorxiv.org/content/10.1101/2025.08.14.670328v1" --json

# Extract authors then find LinkedIn profiles (free DuckDuckGo search; requires OPENAI_API_KEY for LLM)
uv run scholarlink --linkedin "https://www.biorxiv.org/content/10.1101/2025.08.14.670328v1"
uv run scholarlink --linkedin --json "https://..."
```

**Python API**

```python
import asyncio
from scholarlink import extract_authors

async def main():
    authors_list, authors_str = await extract_authors(
        "https://www.biorxiv.org/content/10.1101/2025.08.14.670328v1"
    )
    print(authors_str)

asyncio.run(main())
```

**LinkedIn profile lookup** (after extracting authors):

```python
import asyncio
from scholarlink import extract_authors, find_linkedin_profiles

async def main():
    authors_list, _ = await extract_authors("https://example.com/paper")
    results = await find_linkedin_profiles(authors_list)
    for r in results:
        print(r.author.name, r.status, r.url or r.urls)

asyncio.run(main())
```

## Development

- Lint/format: `uv run ruff check src/` and `uv run ruff format src/`
- Pre-commit: `uv run pre-commit run --all-files`
- Dev deps: `uv sync --group dev`

## License

See project license file.
