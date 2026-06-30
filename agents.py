"""Agent and chain factories.

The LLM is configured from ``config.Settings`` (model, temperature, timeout,
retries) instead of hard-coded values, so behaviour is tunable per environment
without code changes.
"""

from __future__ import annotations

from functools import lru_cache

from langchain.agents import create_agent
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI

from config import get_settings
from logging_setup import get_logger
from tools import scrape_url, web_search

logger = get_logger(__name__)


@lru_cache(maxsize=1)
def get_llm() -> ChatOpenAI:
    """Build a single shared, retry-aware LLM client."""
    settings = get_settings()
    settings.validate()  # fail fast with a clear message if keys are missing
    logger.info(
        "Initializing LLM model=%s temperature=%s timeout=%ss retries=%s",
        settings.model_name,
        settings.temperature,
        settings.llm_timeout_s,
        settings.llm_max_retries,
    )
    return ChatOpenAI(
        model=settings.model_name,
        temperature=settings.temperature,
        timeout=settings.llm_timeout_s,
        max_retries=settings.llm_max_retries,
        api_key=settings.openai_api_key,
    )


# ── Tool-using agents ──────────────────────────────────────────────────────
def build_search_agent():
    return create_agent(model=get_llm(), tools=[web_search])


def build_reader_agent():
    return create_agent(model=get_llm(), tools=[scrape_url])


# ── Writer chain ───────────────────────────────────────────────────────────
writer_prompt = ChatPromptTemplate.from_messages([
    ("system", "You are an expert research writer. Write clear, structured and insightful reports."),
    ("human", """Write a detailed research report on the topic below.

Topic: {topic}

Research Gathered:
{research}

Structure the report as:
- Introduction
- Key Findings (minimum 3 well-explained points)
- Conclusion
- Sources (list all URLs found in the research)

Be detailed, factual and professional."""),
])


# ── Critic chain ───────────────────────────────────────────────────────────
critic_prompt = ChatPromptTemplate.from_messages([
    ("system", "You are a sharp and constructive research critic. Be honest and specific."),
    ("human", """Review the research report below and evaluate it strictly.

Report:
{report}

Respond in this exact format:

Score: X/10

Strengths:
- ...
- ...

Areas to Improve:
- ...
- ...

One line verdict:
..."""),
])


def _build_chain(prompt: ChatPromptTemplate):
    return prompt | get_llm() | StrOutputParser()


# Lazily-built chains so importing this module doesn't require API keys
# (e.g. in tests). They are constructed on first access.
_writer_chain = None
_critic_chain = None


def get_writer_chain():
    global _writer_chain
    if _writer_chain is None:
        _writer_chain = _build_chain(writer_prompt)
    return _writer_chain


def get_critic_chain():
    global _critic_chain
    if _critic_chain is None:
        _critic_chain = _build_chain(critic_prompt)
    return _critic_chain
