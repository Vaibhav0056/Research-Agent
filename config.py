"""Centralized configuration and secret management.

Secrets are resolved in this order:
1. Streamlit secrets (``st.secrets``) when running under Streamlit
   (e.g. Streamlit Community Cloud, where secrets live in the dashboard).
2. Process environment variables (loaded from a local ``.env`` in dev).

This keeps the same code working both locally (``.env``) and on
Streamlit Community Cloud (dashboard secrets) without branching.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from functools import lru_cache

from dotenv import load_dotenv

# Load .env once for local development. On Streamlit Cloud there is no .env;
# values come from st.secrets / the environment instead, so this is a no-op.
load_dotenv()


class ConfigError(RuntimeError):
    """Raised when required configuration is missing or invalid."""


def _get_secret(name: str, default: str | None = None) -> str | None:
    """Read a secret from Streamlit secrets first, then the environment.

    Importing/using ``st.secrets`` is wrapped defensively so this module is
    safe to import from non-Streamlit contexts (CLI, tests, workers).
    """
    try:
        import streamlit as st  # imported lazily; optional at runtime

        # Accessing st.secrets raises if no secrets file exists, hence the guard.
        if name in st.secrets:  # type: ignore[operator]
            value = st.secrets[name]
            if value:
                return str(value)
    except Exception:
        pass

    return os.getenv(name, default)


def _get_int(name: str, default: int) -> int:
    raw = _get_secret(name)
    if raw is None or str(raw).strip() == "":
        return default
    try:
        return int(raw)
    except (TypeError, ValueError):
        raise ConfigError(f"Config '{name}' must be an integer, got: {raw!r}")


def _get_float(name: str, default: float) -> float:
    raw = _get_secret(name)
    if raw is None or str(raw).strip() == "":
        return default
    try:
        return float(raw)
    except (TypeError, ValueError):
        raise ConfigError(f"Config '{name}' must be a number, got: {raw!r}")


@dataclass(frozen=True)
class Settings:
    """Immutable application settings, resolved at import time."""

    # ── Secrets ──
    openai_api_key: str = ""
    tavily_api_key: str = ""

    # ── Model ──
    model_name: str = "gpt-4o-mini"
    temperature: float = 0.0
    llm_timeout_s: int = 60
    llm_max_retries: int = 3

    # ── Search / scrape ──
    search_max_results: int = 5
    scrape_timeout_s: int = 8
    scrape_max_chars: int = 3000
    scrape_max_bytes: int = 3_000_000  # cap download size (~3 MB) before parsing
    snippet_max_chars: int = 300
    handoff_max_chars: int = 800

    # ── App guardrails ──
    max_topic_chars: int = 300
    log_level: str = "INFO"

    # Names of required secrets, used for validation messages.
    _required: tuple[str, ...] = field(
        default=("openai_api_key", "tavily_api_key"), repr=False
    )

    def validate(self) -> None:
        """Raise ConfigError listing every missing required secret."""
        missing = [
            name.upper()
            for name in self._required
            if not getattr(self, name, "").strip()
        ]
        if missing:
            raise ConfigError(
                "Missing required secret(s): "
                + ", ".join(missing)
                + ". Set them in your .env file (local) or in the Streamlit "
                "Cloud app settings → Secrets (deployed)."
            )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Build and cache Settings. Does NOT validate — call .validate() to enforce."""
    return Settings(
        openai_api_key=_get_secret("OPENAI_API_KEY", "") or "",
        tavily_api_key=_get_secret("TAVILY_API_KEY", "") or "",
        model_name=_get_secret("MODEL_NAME", "gpt-4o-mini") or "gpt-4o-mini",
        temperature=_get_float("TEMPERATURE", 0.0),
        llm_timeout_s=_get_int("LLM_TIMEOUT_S", 60),
        llm_max_retries=_get_int("LLM_MAX_RETRIES", 3),
        search_max_results=_get_int("SEARCH_MAX_RESULTS", 5),
        scrape_timeout_s=_get_int("SCRAPE_TIMEOUT_S", 8),
        scrape_max_chars=_get_int("SCRAPE_MAX_CHARS", 3000),
        scrape_max_bytes=_get_int("SCRAPE_MAX_BYTES", 3_000_000),
        snippet_max_chars=_get_int("SNIPPET_MAX_CHARS", 300),
        handoff_max_chars=_get_int("HANDOFF_MAX_CHARS", 800),
        max_topic_chars=_get_int("MAX_TOPIC_CHARS", 300),
        log_level=_get_secret("LOG_LEVEL", "INFO") or "INFO",
    )
