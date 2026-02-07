"""LinkedIn profile lookup: search per author, LLM review, confidence thresholds."""

import asyncio
import json
import os
import sys
from scholarlink.config import get_config
from scholarlink.models import (
    AuthorInfo,
    LinkedInLookupResult,
    LinkedInReviewResult,
    SearchResult,
)
from scholarlink.search import SearchBackend, get_search_backend, _linkedin_verbose

LINKEDIN_REVIEW_PROMPT = """Please review the attached search results and create the list of all the URLs of LinkedIn Profiles (not posts!).

Author we are looking for:
- Name: {name}
- Affiliation: {affiliation}
- Contact: {contact}
- ORCID: {orcid}
- Other: {other}

Search results (query: "{name} LinkedIn Profile"):
{search_results_text}

Output valid JSON only, with exactly these keys:
- "profile_urls": list of all URLs that are LinkedIn profile pages (not posts or articles)
- "best_url": the single most likely profile URL for this person, or null if none
- "confidence": integer from 1 to 100

Confidence rules:
- If there is exactly one profile matching the searched name, your confidence should be very high (e.g. 85-100).
- If there are many profiles that match the name and none clearly matches the other author data (affiliation, etc.), your confidence should be low (e.g. 10-40).
- If you find no LinkedIn profile URLs in the results, set profile_urls to [], best_url to null, and confidence to 0.
"""

CONFIDENCE_HIGH = 75
CONFIDENCE_LOW = 50
MAX_URLS_AMBIGUOUS = 10
LINKEDIN_PROFILE_PATH = "linkedin.com/in/"


def _linkedin_profile_urls_from_results(results: list[SearchResult]) -> list[str]:
    """Return list of URLs from results that look like LinkedIn profile pages (not posts)."""
    urls: list[str] = []
    for r in results:
        u = (r.url or "").strip()
        if LINKEDIN_PROFILE_PATH in u and u not in urls:
            urls.append(u)
    return urls


def _format_search_results(results: list[SearchResult]) -> str:
    lines = []
    for i, r in enumerate(results, 1):
        lines.append(f"{i}. {r.title}\n   URL: {r.url}\n   {r.snippet}")
    return "\n\n".join(lines) if lines else "(No results)"


def _author_context(author: AuthorInfo) -> dict[str, str]:
    return {
        "name": author.name,
        "affiliation": author.affiliation or "",
        "contact": author.contact or "",
        "orcid": author.orcid or "",
        "other": author.other or "",
    }


def _review_result_to_lookup(author: AuthorInfo, review: LinkedInReviewResult) -> LinkedInLookupResult:
    """Apply confidence thresholds and build LinkedInLookupResult."""
    c = review.confidence
    urls = list(review.profile_urls)[: MAX_URLS_AMBIGUOUS + 1]
    if c >= CONFIDENCE_HIGH and review.best_url:
        return LinkedInLookupResult(
            author=author,
            status="found",
            url=review.best_url,
            urls=[],
        )
    if c >= CONFIDENCE_LOW:
        return LinkedInLookupResult(
            author=author,
            status="ambiguous",
            url=None,
            urls=urls[:MAX_URLS_AMBIGUOUS],
        )
    return LinkedInLookupResult(
        author=author,
        status="not_found",
        url=None,
        urls=[],
    )


async def _call_llm_review(author: AuthorInfo, search_results: list[SearchResult]) -> LinkedInReviewResult:
    """Call configured LLM to get LinkedInReviewResult from author + search results."""
    cfg = get_config()
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key or not api_key.strip():
        raise ValueError(
            "OPENAI_API_KEY is not set. Set it in the environment to use LLM-based LinkedIn review."
        )
    provider = (cfg.llm_provider or "").strip().lower()
    if not provider.startswith("openai/"):
        raise ValueError(
            f"LinkedIn lookup currently supports openai/* LLM provider only; got {cfg.llm_provider!r}."
        )
    model = provider.split("/", 1)[1] or "gpt-4o-mini"
    ctx = _author_context(author)
    search_results_text = _format_search_results(search_results)
    prompt = LINKEDIN_REVIEW_PROMPT.format(
        search_results_text=search_results_text,
        **ctx,
    )
    from openai import AsyncOpenAI

    client = AsyncOpenAI(api_key=api_key.strip())
    resp = await client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": prompt}],
        temperature=cfg.llm_temperature,
        max_tokens=cfg.llm_max_tokens,
    )
    content = (resp.choices[0].message.content or "").strip()
    if not content:
        return LinkedInReviewResult(profile_urls=[], best_url=None, confidence=0)
    # Strip markdown code block if present
    if content.startswith("```"):
        lines = content.split("\n")
        if lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        content = "\n".join(lines)
    try:
        data = json.loads(content)
    except json.JSONDecodeError:
        return LinkedInReviewResult(profile_urls=[], best_url=None, confidence=0)
    try:
        return LinkedInReviewResult.model_validate(data)
    except Exception:
        return LinkedInReviewResult(profile_urls=[], best_url=None, confidence=0)


async def _lookup_one(
    author: AuthorInfo,
    backend: SearchBackend,
    max_results: int,
) -> LinkedInLookupResult:
    """Run search + LLM review + thresholds for one author."""
    query = f"{author.name} LinkedIn Profile"
    results = await backend.search(query, max_results=max_results)
    if _linkedin_verbose():
        n = len(results)
        msg = f'Author "{author.name}": {n} search result(s)'
        if n == 0:
            msg += " (Google may have blocked the request; try a proxy or different network)."
        print(msg, file=sys.stderr)
    review = await _call_llm_review(author, results)
    lookup = _review_result_to_lookup(author, review)
    # Fallback: if LLM found no profiles but raw results contain any LinkedIn profile URLs, treat as ambiguous
    if lookup.status == "not_found":
        profile_urls = _linkedin_profile_urls_from_results(results)
        if profile_urls:
            lookup = LinkedInLookupResult(
                author=author,
                status="ambiguous",
                url=None,
                urls=profile_urls[:MAX_URLS_AMBIGUOUS],
            )
    return lookup


async def search_linkedin_profiles(
    authors: list[AuthorInfo],
    *,
    search_backend: SearchBackend | None = None,
    max_results: int | None = None,
) -> list[LinkedInLookupResult]:
    """
    For each author: search for "{name} LinkedIn Profile", run LLM review, apply confidence thresholds.

    Processes authors sequentially with a delay between searches to avoid rate limits.
    Returns one LinkedInLookupResult per author (found / ambiguous / not_found).
    """
    cfg = get_config()
    backend = search_backend or get_search_backend(cfg.search_provider)
    limit = max_results if max_results is not None else cfg.search_max_results
    delay = cfg.search_delay_seconds
    out: list[LinkedInLookupResult] = []
    for i, author in enumerate(authors):
        result = await _lookup_one(author, backend, limit)
        out.append(result)
        if delay > 0 and i < len(authors) - 1:
            await asyncio.sleep(delay)
    return out
