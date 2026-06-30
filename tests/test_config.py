"""Tests for configuration loading and validation."""

import importlib

import pytest

import config


@pytest.fixture(autouse=True)
def clear_cache():
    """Ensure each test gets a fresh, uncached Settings."""
    config.get_settings.cache_clear()
    yield
    config.get_settings.cache_clear()


def test_missing_secrets_raises(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("TAVILY_API_KEY", raising=False)
    config.get_settings.cache_clear()

    settings = config.get_settings()
    with pytest.raises(config.ConfigError) as exc:
        settings.validate()
    assert "OPENAI_API_KEY" in str(exc.value)
    assert "TAVILY_API_KEY" in str(exc.value)


def test_validate_passes_with_secrets(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("TAVILY_API_KEY", "tvly-test")
    config.get_settings.cache_clear()

    settings = config.get_settings()
    settings.validate()  # should not raise
    assert settings.openai_api_key == "sk-test"


def test_int_override(monkeypatch):
    monkeypatch.setenv("SEARCH_MAX_RESULTS", "9")
    config.get_settings.cache_clear()
    assert config.get_settings().search_max_results == 9


def test_invalid_int_raises(monkeypatch):
    monkeypatch.setenv("LLM_TIMEOUT_S", "not-a-number")
    config.get_settings.cache_clear()
    with pytest.raises(config.ConfigError):
        config.get_settings()


def test_defaults(monkeypatch):
    for var in ("MODEL_NAME", "TEMPERATURE", "SCRAPE_MAX_CHARS"):
        monkeypatch.delenv(var, raising=False)
    config.get_settings.cache_clear()
    s = config.get_settings()
    assert s.model_name == "gpt-4o-mini"
    assert s.temperature == 0.0
    assert s.scrape_max_chars == 3000
