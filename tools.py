"""LangChain tools: Tavily web search + a hardened BeautifulSoup scraper.

Hardening over the prototype:
- Real error handling with logging (errors are still returned as text so the
  calling agent can react, but the underlying exception is logged).
- ``raise_for_status`` + content-type and size checks before parsing.
- Retries with exponential backoff on transient network failures (tenacity).
- A basic SSRF guard that refuses non-http(s) schemes and private/loopback
  hosts — important once this is exposed to untrusted input on the web.
"""

from __future__ import annotations

import ipaddress
import socket
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup
from langchain.tools import tool
from tavily import TavilyClient
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from config import get_settings
from logging_setup import get_logger

logger = get_logger(__name__)
settings = get_settings()

# Lazily construct the Tavily client so importing this module never crashes
# when keys are absent (e.g. during tests or `--help`).
_tavily_client: TavilyClient | None = None


def _tavily() -> TavilyClient:
    global _tavily_client
    if _tavily_client is None:
        if not settings.tavily_api_key:
            raise RuntimeError("TAVILY_API_KEY is not configured.")
        _tavily_client = TavilyClient(api_key=settings.tavily_api_key)
    return _tavily_client


def _is_safe_url(url: str) -> tuple[bool, str]:
    """Reject anything but public http(s) URLs (basic SSRF protection)."""
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        return False, f"unsupported scheme '{parsed.scheme}'"
    if not parsed.hostname:
        return False, "missing host"

    try:
        # Resolve and check every address the host maps to.
        infos = socket.getaddrinfo(parsed.hostname, None)
    except socket.gaierror:
        return False, "host could not be resolved"

    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if (
            ip.is_private
            or ip.is_loopback
            or ip.is_link_local
            or ip.is_reserved
            or ip.is_multicast
        ):
            return False, "host resolves to a non-public address"
    return True, ""


@tool
def web_search(query: str) -> str:
    """Search the web for recent and reliable information on a topic.

    Returns Titles, URLs and snippets.
    """
    try:
        results = _tavily().search(
            query=query, max_results=settings.search_max_results
        )
    except Exception as exc:  # noqa: BLE001 - surface to the agent as text
        logger.exception("Tavily search failed for query=%r", query)
        return f"Search failed: {exc}"

    hits = results.get("results", []) if isinstance(results, dict) else []
    if not hits:
        logger.warning("Tavily returned no results for query=%r", query)
        return "No search results found."

    out = []
    for r in hits:
        snippet = (r.get("content") or "")[: settings.snippet_max_chars]
        out.append(
            f"Title: {r.get('title', 'N/A')}\n"
            f"URL: {r.get('url', 'N/A')}\n"
            f"Snippet: {snippet}\n"
        )
    logger.info("web_search returned %d results for query=%r", len(out), query)
    return "\n----\n".join(out)


@retry(
    retry=retry_if_exception_type(
        (requests.ConnectionError, requests.Timeout)
    ),
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=0.5, max=4),
    reraise=True,
)
def _fetch(url: str) -> requests.Response:
    """Fetch a URL with retries on transient network errors."""
    resp = requests.get(
        url,
        timeout=settings.scrape_timeout_s,
        headers={"User-Agent": "Mozilla/5.0 (ResearchMind bot)"},
        stream=True,
    )
    resp.raise_for_status()
    return resp


@tool
def scrape_url(url: str) -> str:
    """Scrape and return clean text content from a given URL for deeper reading."""
    safe, reason = _is_safe_url(url)
    if not safe:
        logger.warning("Blocked scrape of unsafe URL %r: %s", url, reason)
        return f"Could not scrape URL: blocked ({reason})."

    try:
        resp = _fetch(url)

        content_type = resp.headers.get("Content-Type", "")
        if "html" not in content_type and "text" not in content_type:
            return (
                f"Could not scrape URL: unsupported content type "
                f"'{content_type or 'unknown'}'."
            )

        # Read up to scrape_max_bytes to avoid loading huge pages into memory.
        raw = resp.raw.read(settings.scrape_max_bytes, decode_content=True)
        html = raw.decode(resp.encoding or "utf-8", errors="replace")

        soup = BeautifulSoup(html, "html.parser")
        for tag in soup(["script", "style", "nav", "footer", "noscript"]):
            tag.decompose()

        text = soup.get_text(separator=" ", strip=True)[: settings.scrape_max_chars]
        if not text:
            return "Could not scrape URL: page had no readable text."
        logger.info("Scraped %d chars from %s", len(text), url)
        return text

    except requests.HTTPError as exc:
        logger.warning("HTTP error scraping %s: %s", url, exc)
        return f"Could not scrape URL: HTTP {exc.response.status_code if exc.response else '?'}."
    except requests.RequestException as exc:
        logger.warning("Network error scraping %s: %s", url, exc)
        return f"Could not scrape URL: network error ({exc})."
    except Exception as exc:  # noqa: BLE001 - never crash the agent
        logger.exception("Unexpected error scraping %s", url)
        return f"Could not scrape URL: {exc}"
