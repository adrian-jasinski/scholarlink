"""Pydantic models for paper metadata extraction."""

from typing import Literal

from pydantic import BaseModel, Field


class AuthorInfo(BaseModel):
    """Per-author metadata extracted from a scientific paper page."""

    name: str = Field(..., description="Full name of the author")
    affiliation: str | None = Field(
        default=None,
        description="University, department, or institution",
    )
    contact: str | None = Field(
        default=None,
        description="Contact data, e.g. email address",
    )
    orcid: str | None = Field(
        default=None,
        description="ORCID identifier if available",
    )
    other: str | None = Field(
        default=None,
        description="Any other author data (e.g. roles, identifiers)",
    )


class PaperMetadata(BaseModel):
    """Metadata extracted from a scientific paper page."""

    authors: list[AuthorInfo] = Field(
        ...,
        description="Authors with details in order of appearance",
    )


class SearchResult(BaseModel):
    """Single result from a web search (title, snippet, URL)."""

    title: str = Field(..., description="Title of the result")
    snippet: str = Field(default="", description="Snippet or description")
    url: str = Field(..., description="Result URL")


class LinkedInReviewResult(BaseModel):
    """LLM output: LinkedIn profile URLs and confidence for one author."""

    profile_urls: list[str] = Field(
        default_factory=list,
        description="All URLs that are LinkedIn profiles (not posts)",
    )
    best_url: str | None = Field(
        default=None,
        description="Most likely profile URL for this person",
    )
    confidence: int = Field(
        ...,
        ge=0,
        le=100,
        description="Confidence score 1-100",
    )


class LinkedInLookupResult(BaseModel):
    """Per-author result of LinkedIn profile lookup."""

    author: AuthorInfo = Field(..., description="Author this result refers to")
    status: Literal["found", "ambiguous", "not_found"] = Field(
        ...,
        description="found: one URL (confidence >= 75); ambiguous: up to 10 URLs (50-75); not_found: < 50",
    )
    url: str | None = Field(
        default=None,
        description="Single profile URL when status is 'found'",
    )
    urls: list[str] = Field(
        default_factory=list,
        description="Up to 10 profile URLs when status is 'ambiguous'",
    )
