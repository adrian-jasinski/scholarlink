"""Pydantic models for paper metadata extraction."""

from pydantic import BaseModel, Field


class PaperMetadata(BaseModel):
    """Metadata extracted from a scientific paper page."""

    authors: list[str] = Field(
        ...,
        description="List of publication author full names in order of appearance",
    )
