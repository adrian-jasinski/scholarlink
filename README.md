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

- **`OPENAI_API_KEY`** (required for default LLM): Set your OpenAI API key for author extraction.
- **`SCHOLARLINK_LLM_PROVIDER`** (optional): LLM provider string, e.g. `openai/gpt-4o-mini` (default) or `ollama/llama3.3` for local models.
- **`SCHOLARLINK_PROTECTED_DOMAINS`** (optional): Comma-separated hostnames that use Cloudflare (e.g. `biorxiv.org,pnas.org`). For these domains the crawler uses undetected browser + stealth; if unset, a default list (bioRxiv, PNAS) is used.

## Usage

**CLI**

```bash
# Print comma-separated authors
uv run scholarlink "https://www.biorxiv.org/content/10.1101/2025.08.14.670328v1"

# Output JSON: {"authors": [...], "authors_str": "..."}
uv run scholarlink "https://www.biorxiv.org/content/10.1101/2025.08.14.670328v1" --json
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

## Development

- Lint/format: `uv run ruff check src/` and `uv run ruff format src/`
- Pre-commit: `uv run pre-commit run --all-files`
- Dev deps: `uv sync --group dev`

## License

See project license file.
