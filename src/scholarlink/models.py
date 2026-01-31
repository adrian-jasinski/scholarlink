"""Pydantic models for paper metadata extraction."""

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
