# Scholarlink

Extract publication authors from scientific paper URLs using [Crawl4AI](https://github.com/unclecode/crawl4ai). Supports bioRxiv, PNAS, and other publishers via LLM-based extraction. The default pipeline extracts **author name** and **affiliation** (e.g. MIT, Stanford, Google DeepMind) only; it does not extract ORCID or other identifiers. For LinkedIn lookup, search uses the author name only when affiliation is missing, and both name and affiliation when present.

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
- **LinkedIn lookup** (for `--linkedin`):
  - **`SCHOLARLINK_SEARCH_PROVIDER`** (optional): Search backend to use:
    - `google` - HTTP scraping (free, may get 429 errors)
    - `brave` - Brave Search API (requires `BRAVE_API_KEY`, fast and reliable)
    - `browser` - Chromium + Google (most reliable, requires Playwright)
    - `bing` - Chromium + Bing (alternative when Google blocks, requires Playwright)
    - Default: `google`
  - **`BRAVE_API_KEY`** (required for `brave` provider): Your Brave Search API key. Get one at [Brave Search API](https://api.search.brave.com/).
  - **`SCHOLARLINK_BRAVE_TIMEOUT_SECONDS`** (optional): HTTP timeout for Brave API requests (default: 30.0).
  - **`SCHOLARLINK_SEARCH_MAX_RESULTS`** (optional): max search results per author (default: 10).
  - **`SCHOLARLINK_SEARCH_DELAY_SECONDS`** (optional): delay between each author's search (default: 2.0).
  - **`SCHOLARLINK_LINKEDIN_VERBOSE`** (optional): set to `1` to print per-author search result counts and errors.
  - **Browser backend options** (only used when `search_provider = "browser"`):
    - **`SCHOLARLINK_BROWSER_HEADLESS`** (optional): `true` (default) or `false`. Set to `false` to see browser window (useful for debugging).
    - **`SCHOLARLINK_BROWSER_USE_STEALTH`** (optional): `true` (default) or `false`. Enable anti-detection features to avoid bot detection.
    - **`SCHOLARLINK_BROWSER_PERSISTENT_CONTEXT`** (optional): `true` or `false` (default). Save cookies between runs to reduce rate limiting.
    - **`SCHOLARLINK_BROWSER_USER_DATA_DIR`** (optional): Custom path for browser profile data. Defaults to `~/.scholarlink/browser-data` if persistent context is enabled.
    - **`SCHOLARLINK_BROWSER_PROXY`** (optional): Proxy server URL (e.g., `http://proxy.example.com:8080`). Useful if you're getting blocked.
    - **`SCHOLARLINK_BROWSER_DEBUG_WAIT_SECONDS`** (optional): Seconds to wait before closing browser when `headless=false` (default: 5.0). Gives you time to inspect the browser before it closes.

**Optional config file**

You can put non-secret options in a TOML file (e.g. `scholarlink.toml` in the project root or path given by `SCHOLARLINK_CONFIG`). Load order: built-in defaults → config file → environment variables. See [scholarlink.toml.example](scholarlink.toml.example) for all options and comments.

## Usage

**CLI**

Single paper URL (use the `paper` command):

```bash
# Print comma-separated authors
uv run scholarlink paper "https://www.biorxiv.org/content/10.1101/2025.08.14.670328v1"

# Output JSON: {"authors": [...], "csv": "..."}
uv run scholarlink paper "https://www.biorxiv.org/content/10.1101/2025.08.14.670328v1" --json

# Write CSV (author_name, link) to file; add --linkedin for LinkedIn column
uv run scholarlink paper "https://..." --output authors.csv
uv run scholarlink paper "https://..." --output authors.csv --linkedin

# Extract authors then find LinkedIn profiles (Google search; requires OPENAI_API_KEY for LLM)
uv run scholarlink paper --linkedin "https://www.biorxiv.org/content/10.1101/2025.08.14.670328v1"
uv run scholarlink paper --linkedin --json "https://..."

# Recommended: Use Brave Search API (fast, reliable, no rate limits)
# Get free API key at https://api.search.brave.com/ (2,000 queries/month free)
export BRAVE_API_KEY=your-key-here
export SCHOLARLINK_SEARCH_PROVIDER=brave
uv run scholarlink paper --linkedin "https://..."

# Alternative: Use browser backend if you don't have Brave API key
# Requires: uv run python -m playwright install chromium
export SCHOLARLINK_SEARCH_PROVIDER=browser
uv run scholarlink paper --linkedin "https://..."

# Run with SCHOLARLINK_LINKEDIN_VERBOSE=1 to see per-author search result counts
export SCHOLARLINK_LINKEDIN_VERBOSE=1
```

Batch from CSV or Excel (list of paper URLs):

```bash
# Read links from CSV or .xlsx (first column or --column NAME), write one CSV with all authors
uv run scholarlink from-file links.csv --output authors.csv
uv run scholarlink from-file links.xlsx --column url --output authors.csv --linkedin
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

### Search Backend Comparison

| Backend | Speed | Reliability | Setup | Rate Limits | Cost |
|---------|-------|-------------|-------|-------------|------|
| **Brave API** (recommended) | ⚡⚡⚡ Fast (0.5-1.5s) | ✅ Excellent | Easy (API key) | Generous | Free tier: 2K/mo |
| **Browser** (Google) | 🐢 Slow (5-10s) | ✅ Very good | Medium (Playwright) | Low | Free |
| **Browser** (Bing) | 🐢 Slow (5-10s) | ✅ Good | Medium (Playwright) | Low | Free |
| **Google scraping** | ⚡ Fast (2-5s) | ⚠️ Frequent 429s | Easy | Very low | Free |



**Recommendation**: Use Brave API if you have an API key (free tier is generous). Otherwise, use Browser backend with Google or Bing.

Check: [https://brave.com/search/api/] - next select plan -> generate API key.

**LinkedIn profile lookup** (after extracting authors): For each author, search uses name only when affiliation was not extracted, or both name and affiliation when available, then an LLM picks the best profile from the results.

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

**Single URL to output CSV** (`extract_authors_single`): Returns rows (author_name, link, optional linkedin) and can write a CSV file.

```python
import asyncio
from scholarlink import extract_authors_single

async def main():
    rows = await extract_authors_single(
        "https://example.com/paper",
        linkedin=True,
        output_path="authors.csv",
    )
    for r in rows:
        print(r["author_name"], r["link"], r.get("linkedin", ""))

asyncio.run(main())
```

**Batch from CSV/Excel** (`extract_authors_from_file`): Read paper URLs from a CSV or Excel file, extract authors for each, write one combined CSV.

```python
import asyncio
from scholarlink import extract_authors_from_file

async def main():
    await extract_authors_from_file(
        "links.csv",
        column="url",
        linkedin=True,
        output_path="authors.csv",
    )

asyncio.run(main())
```

## Browser Backend for LinkedIn Lookup

The browser backend uses a real Chromium browser (via Playwright) to search Google, avoiding the 429 errors and CAPTCHAs that HTTP scraping often triggers.

### Setup

Install Chromium browser:

```bash
uv run python -m playwright install chromium
```

Enable browser backend:

```bash
export SCHOLARLINK_SEARCH_PROVIDER=browser
uv run scholarlink --linkedin "https://www.biorxiv.org/content/10.1101/2025.08.14.670328v1"
```

### Anti-Detection Features

The browser backend includes advanced anti-detection features enabled by default:

**Automatic features**:
- Random user agent rotation (7 different Chrome user agents across Windows, macOS, and Linux)
- Random viewport sizes (6 common resolutions: 1920x1080, 1366x768, 1536x864, 1440x900, 1280x720, 1600x900)
- Human-like random delays between actions (500-2000ms)
- JavaScript stealth overrides (`navigator.webdriver`, `navigator.plugins`, `navigator.languages`, `window.chrome`, etc.)
- Cookie consent handling (automatically clicks "Accept all", "I agree", etc.)

**Configurable features**:
- **Stealth mode** (enabled by default): Comprehensive anti-detection with 21+ Chromium flags
- **Headless mode** (enabled by default): Run without visible window (disable for debugging)
- **Persistent browser context** (disabled by default): Save cookies between runs to reduce rate limiting
- **Proxy support** (optional): Route traffic through a proxy server

### Configuration Options

Configure via environment variables or `scholarlink.toml`:

```bash
# Run browser in visible mode (for debugging)
export SCHOLARLINK_BROWSER_HEADLESS=false

# Enable/disable stealth mode
export SCHOLARLINK_BROWSER_USE_STEALTH=true

# Save cookies between runs (reduces rate limiting)
export SCHOLARLINK_BROWSER_PERSISTENT_CONTEXT=true

# Custom browser profile directory
export SCHOLARLINK_BROWSER_USER_DATA_DIR=/path/to/browser/data

# Use a proxy (useful if you're getting blocked)
export SCHOLARLINK_BROWSER_PROXY=http://proxy.example.com:8080

# Extend wait time before closing browser in debug mode (default: 5.0 seconds)
export SCHOLARLINK_BROWSER_DEBUG_WAIT_SECONDS=10.0

# Enable verbose logging to see what's happening
export SCHOLARLINK_LINKEDIN_VERBOSE=1
```

Or in `scholarlink.toml`:

```toml
[scholarlink]
search_provider = "browser"
browser_headless = true
browser_use_stealth = true
browser_persistent_context = false
browser_debug_wait_seconds = 5.0
# browser_user_data_dir = "/path/to/browser/data"
# browser_proxy = "http://proxy.example.com:8080"
```

### Troubleshooting

**Still getting blocked or seeing CAPTCHAs?**

1. **Try a different search engine** (Bing instead of Google):
   ```bash
   export SCHOLARLINK_SEARCH_PROVIDER=bing
   export SCHOLARLINK_LINKEDIN_VERBOSE=1
   uv run scholarlink --linkedin <url>
   ```

2. **Enable verbose logging** to see what's happening:
   ```bash
   export SCHOLARLINK_LINKEDIN_VERBOSE=1
   uv run scholarlink --linkedin <url>
   ```

3. **Watch the browser** to see if you're hitting CAPTCHAs:
   ```bash
   export SCHOLARLINK_BROWSER_HEADLESS=false
   export SCHOLARLINK_BROWSER_DEBUG_WAIT_SECONDS=10  # Wait 10s before closing
   uv run scholarlink --linkedin <url>
   ```
   The browser will stay open for 10 seconds after the search completes, giving you time to inspect what happened.

4. **Try using a proxy** if you're on a flagged IP:
   ```bash
   export SCHOLARLINK_BROWSER_PROXY=http://proxy.example.com:8080
   uv run scholarlink --linkedin <url>
   ```

5. **Enable persistent context** to save cookies (helps with rate limiting):
   ```bash
   export SCHOLARLINK_BROWSER_PERSISTENT_CONTEXT=true
   uv run scholarlink --linkedin <url>
   ```

6. **Increase delays** between searches:
   ```bash
   export SCHOLARLINK_SEARCH_DELAY_SECONDS=5.0
   uv run scholarlink --linkedin <url>
   ```

**Getting "browser not found" errors?**

Install Chromium:
```bash
uv run python -m playwright install chromium
```

**All authors showing "not_found"?**

This usually means Google is blocking the searches. Try the browser backend with stealth mode enabled (it's on by default), or switch to Bing:

```bash
export SCHOLARLINK_SEARCH_PROVIDER=browser  # or "bing"
export SCHOLARLINK_LINKEDIN_VERBOSE=1
uv run scholarlink --linkedin <url>
```

## Brave Search API Backend

Brave Search API provides a fast, reliable search backend without rate limits or bot detection issues. This is the **recommended** option if you have an API key.

### Setup

1. **Get your API key**: Sign up at [Brave Search API](https://api.search.brave.com/)
   - Free tier: 2,000 queries/month
   - No credit card required for free tier

2. **Add to `.env` file**:
```bash
BRAVE_API_KEY=your-key-here
SCHOLARLINK_SEARCH_PROVIDER=brave
```

3. **Run your search**:
```bash
uv run scholarlink --linkedin "https://www.biorxiv.org/content/10.1101/2025.08.14.670328v1"
```

### Features

- ✅ **Official API** with authentication
- ✅ **No bot detection** or CAPTCHAs
- ✅ **Fast and reliable** responses (typically < 1s per query)
- ✅ **No additional dependencies** (uses built-in HTTP client)
- ✅ **Free tier available**: 2,000 queries/month
- ✅ **Rate limits depend on your plan** (generous limits on paid tiers)
- ✅ **No browser required** (unlike `browser` and `bing` backends)

### Configuration

Configure via environment variables or `scholarlink.toml`:

```bash
# Required: Your Brave API key
export BRAVE_API_KEY=your-key-here

# Optional: HTTP timeout for API requests (default: 30.0 seconds)
export SCHOLARLINK_BRAVE_TIMEOUT_SECONDS=60.0

# Enable verbose logging
export SCHOLARLINK_LINKEDIN_VERBOSE=1
```

Or in `scholarlink.toml`:
```toml
[scholarlink]
search_provider = "brave"
brave_timeout_seconds = 30.0
```

### When to Use Brave

**✅ Use Brave when:**
- You have a Brave API key (free tier is sufficient for most use cases)
- You want the most reliable, fastest results
- You're making many searches and want to avoid rate limits
- You want to avoid browser automation complexity
- You don't want to install Playwright/Chromium

**❌ Don't use Brave when:**
- You don't have an API key (use `google` or `browser` instead)
- You're on a tight budget and searches are very frequent (free tier may run out)

### Performance

Brave API is typically the fastest option:
- **Brave API**: ~0.5-1.5s per query, no rate limits (depends on plan)
- **Google scraping**: ~2-5s per query, frequent 429 errors
- **Browser backends**: ~5-10s per query (includes browser startup/shutdown)

## Bing Backend Alternative

If Google is blocking your searches, you can switch to Bing:

```bash
export SCHOLARLINK_SEARCH_PROVIDER=bing
uv run scholarlink --linkedin "https://www.biorxiv.org/content/10.1101/2025.08.14.670328v1"
```

Or add to your `.env` file:
```bash
SCHOLARLINK_SEARCH_PROVIDER=bing
```

**Features**:
- Uses the same browser backend infrastructure as Google search
- Same anti-detection features (stealth mode, random user agents, etc.)
- Same configuration options (headless, proxy, debug wait, etc.)
- Alternative search engine when Google returns 429 or CAPTCHAs

**Configuration**:
All browser configuration options work with Bing backend:
- `SCHOLARLINK_BROWSER_HEADLESS` - Show/hide browser window
- `SCHOLARLINK_BROWSER_USE_STEALTH` - Enable anti-detection
- `SCHOLARLINK_BROWSER_PERSISTENT_CONTEXT` - Save cookies
- `SCHOLARLINK_BROWSER_PROXY` - Use proxy server
- `SCHOLARLINK_BROWSER_DEBUG_WAIT_SECONDS` - Wait time before closing

**When to use Bing**:
- Google is returning 429 (Too Many Requests) errors
- Google shows CAPTCHA challenges
- You want to compare results from different search engines
- Your IP is flagged by Google but not by Bing

## Development

- Lint/format: `uv run ruff check src/` and `uv run ruff format src/`
- Pre-commit: `uv run pre-commit run --all-files`
- Dev deps: `uv sync --group dev`

## License

See project license file.
