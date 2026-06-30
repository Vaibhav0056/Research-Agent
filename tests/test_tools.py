"""Tests for the SSRF guard and tool error handling.

These need the scraping deps (requests/bs4/tavily). They are skipped if those
imports are unavailable so the rest of the suite still runs.
"""

import pytest

pytest.importorskip("bs4")
pytest.importorskip("requests")
pytest.importorskip("tavily")

import tools  # noqa: E402


@pytest.mark.parametrize(
    "url",
    [
        "ftp://example.com/file",       # bad scheme
        "file:///etc/passwd",           # local file
        "http://localhost:8501",        # loopback
        "http://127.0.0.1/admin",       # loopback ip
        "http://169.254.169.254/",      # cloud metadata (link-local)
        "not-a-url",                    # no scheme/host
    ],
)
def test_unsafe_urls_blocked(url):
    safe, reason = tools._is_safe_url(url)
    assert safe is False
    assert reason


def test_public_https_url_allowed():
    # example.com resolves to a public address.
    safe, _ = tools._is_safe_url("https://example.com")
    assert safe is True


def test_scrape_blocks_unsafe_url():
    out = tools.scrape_url.invoke({"url": "http://127.0.0.1/secret"})
    assert "blocked" in out.lower()
