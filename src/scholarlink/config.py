"""Configuration: defaults, optional TOML file, and env overrides."""

import os
import tomllib
from pathlib import Path

from pydantic import BaseModel, Field

# Default extraction instruction (long string)
_DEFAULT_AUTHORS_EXTRACTION_INSTRUCTION = """
From this scientific article page, extract all publication authors with details.
Return a single JSON object with exactly one key "authors" whose value is a list of author objects.
For each author, extract in order of appearance:
- name: full name (required)
- affiliation: university, department, or institution if shown
- contact: email or other contact if available
- orcid: ORCID ID if shown (e.g. from "View ORCID Profile" link)
- other: any other author data (roles, identifiers, etc.) if available
Use empty string for missing optional fields. Preserve the exact spelling and order.
Put ORCID ID in orcid, not in name.
""".strip()


class ScholarlinkConfig(BaseModel):
    """Resolved configuration: defaults + optional TOML file + env overrides."""

    cloudflare_manual_wait_seconds: int = Field(
        default=7,
        description="Seconds to wait when user completes Cloudflare challenge manually.",
    )
    delay_default: float = Field(default=0.1, description="Delay in seconds when not protected.")
    delay_protected: float = Field(
        default=3.0,
        description="Delay in seconds when protected, not manual.",
    )
    protected_domains: list[str] = Field(
        default_factory=lambda: [
            "biorxiv.org",
            "www.biorxiv.org",
            "pnas.org",
            "www.pnas.org",
        ],
        description="Default Cloudflare-protected hostnames.",
    )
    cloudflare_phrases: list[str] = Field(
        default_factory=lambda: ["cloudflare", "verifying you are human", "ray id"],
        description="Phrases that indicate Cloudflare challenge text leaked into content.",
    )
    authors_extraction_instruction: str = Field(
        default=_DEFAULT_AUTHORS_EXTRACTION_INSTRUCTION,
        description="LLM instruction for author extraction.",
    )
    llm_temperature: float = Field(default=0.0, description="LLM generation temperature.")
    llm_max_tokens: int = Field(default=2000, description="LLM max tokens.")
    llm_provider: str = Field(
        default="openai/gpt-4o-mini",
        description="LLM provider string (e.g. openai/gpt-4o-mini).",
    )
    search_provider: str = Field(
        default="duckduckgo",
        description="Search backend for LinkedIn lookup: 'duckduckgo' (free, no API key).",
    )
    search_max_results: int = Field(
        default=10,
        ge=1,
        le=20,
        description="Max number of search results to pass to LLM per author.",
    )

    def protected_domains_frozenset(self) -> frozenset[str]:
        """Return protected_domains as a frozenset (lowercased)."""
        return frozenset(d.strip().lower() for d in self.protected_domains if d.strip())

    def cloudflare_phrases_tuple(self) -> tuple[str, ...]:
        """Return cloudflare_phrases as a tuple."""
        return tuple(self.cloudflare_phrases)


_config: ScholarlinkConfig | None = None


def _config_file_path() -> Path | None:
    """Return path to optional config file, or None if not set/present."""
    path_env = os.getenv("SCHOLARLINK_CONFIG")
    if path_env:
        p = Path(path_env)
        return p if p.is_file() else None
    default = Path.cwd() / "scholarlink.toml"
    return default if default.is_file() else None


def _load_toml_overrides() -> dict:
    """Load optional TOML config file; return dict of overrides (only keys present in file)."""
    path = _config_file_path()
    if not path:
        return {}
    try:
        with open(path, "rb") as f:
            data = tomllib.load(f)
    except (OSError, tomllib.TOMLDecodeError):
        return {}
    # Support [tool.scholarlink], [scholarlink], or top-level keys
    if "tool" in data and isinstance(data["tool"], dict) and "scholarlink" in data["tool"]:
        return dict(data["tool"]["scholarlink"])
    if "scholarlink" in data and isinstance(data["scholarlink"], dict):
        return dict(data["scholarlink"])
    # Top-level keys
    allowed = {
        "cloudflare_manual_wait_seconds",
        "delay_default",
        "delay_protected",
        "protected_domains",
        "cloudflare_phrases",
        "authors_extraction_instruction",
        "llm_temperature",
        "llm_max_tokens",
        "llm_provider",
        "search_provider",
        "search_max_results",
    }
    return {k: v for k, v in data.items() if k in allowed}


def _env_overrides() -> dict:
    """Build dict of env overrides for config fields."""
    overrides: dict = {}
    # Protected domains: comma-separated
    env_val = os.getenv("SCHOLARLINK_PROTECTED_DOMAINS")
    if env_val:
        overrides["protected_domains"] = [
            d.strip().lower() for d in env_val.split(",") if d.strip()
        ]
    # LLM provider
    env_val = os.getenv("SCHOLARLINK_LLM_PROVIDER")
    if env_val is not None:
        overrides["llm_provider"] = env_val
    # Numeric/tuning
    env_val = os.getenv("SCHOLARLINK_CLOUDFLARE_MANUAL_WAIT_SECONDS")
    if env_val is not None:
        try:
            overrides["cloudflare_manual_wait_seconds"] = int(env_val)
        except ValueError:
            pass
    env_val = os.getenv("SCHOLARLINK_DELAY_DEFAULT")
    if env_val is not None:
        try:
            overrides["delay_default"] = float(env_val)
        except ValueError:
            pass
    env_val = os.getenv("SCHOLARLINK_DELAY_PROTECTED")
    if env_val is not None:
        try:
            overrides["delay_protected"] = float(env_val)
        except ValueError:
            pass
    env_val = os.getenv("SCHOLARLINK_LLM_TEMPERATURE")
    if env_val is not None:
        try:
            overrides["llm_temperature"] = float(env_val)
        except ValueError:
            pass
    env_val = os.getenv("SCHOLARLINK_LLM_MAX_TOKENS")
    if env_val is not None:
        try:
            overrides["llm_max_tokens"] = int(env_val)
        except ValueError:
            pass
    env_val = os.getenv("SCHOLARLINK_SEARCH_PROVIDER")
    if env_val is not None:
        overrides["search_provider"] = env_val
    env_val = os.getenv("SCHOLARLINK_SEARCH_MAX_RESULTS")
    if env_val is not None:
        try:
            overrides["search_max_results"] = int(env_val)
        except ValueError:
            pass
    return overrides


def get_config() -> ScholarlinkConfig:
    """Return resolved config: defaults + optional TOML file + env overrides (singleton)."""
    global _config
    if _config is not None:
        return _config
    defaults = ScholarlinkConfig()
    toml_data = _load_toml_overrides()
    env_data = _env_overrides()
    # Merge: defaults -> TOML -> env
    merged = defaults.model_dump()
    for k, v in toml_data.items():
        if k in merged:
            merged[k] = v
    for k, v in env_data.items():
        if k in merged:
            merged[k] = v
    _config = ScholarlinkConfig.model_validate(merged)
    return _config


def reset_config() -> None:
    """Clear cached config (for tests)."""
    global _config
    _config = None
