"""Headless research pipeline (CLI + importable).

Orchestrates the 4 stages: search -> read -> write -> critique.
Each stage logs structured progress and raises ``PipelineError`` on failure
so callers (CLI or the Streamlit UI) can handle errors uniformly.
"""

from __future__ import annotations

from agents import (
    build_reader_agent,
    build_search_agent,
    get_critic_chain,
    get_writer_chain,
)
from config import get_settings
from logging_setup import get_logger, new_run_id

logger = get_logger(__name__)


class PipelineError(RuntimeError):
    """Raised when a pipeline stage fails irrecoverably."""

    def __init__(self, stage: str, message: str):
        self.stage = stage
        super().__init__(f"[{stage}] {message}")


def _agent_final_message(result) -> str:
    """Extract the final message content from an agent invocation result."""
    try:
        return result["messages"][-1].content
    except (KeyError, IndexError, AttributeError) as exc:
        raise PipelineError("parse", f"Unexpected agent output shape: {exc}") from exc


def _run_logger(run_id: str):
    """LoggerAdapter that prefixes every message with the run id."""
    import logging

    class _Adapter(logging.LoggerAdapter):
        def process(self, msg, kwargs):
            # Prepend run id without touching msg's own %-placeholders/args.
            return f"run={self.extra['run_id']} | {msg}", kwargs

    return _Adapter(logger, {"run_id": run_id})


def run_research_pipeline(topic: str, run_id: str | None = None) -> dict:
    settings = get_settings()
    settings.validate()
    run_id = run_id or new_run_id()
    log = _run_logger(run_id)

    topic = topic.strip()
    if not topic:
        raise PipelineError("input", "Topic must not be empty.")

    state: dict = {}

    # ── Stage 1: Search ──
    log.info("Stage 1/4 - search agent starting (topic=%r)", topic)
    try:
        search_agent = build_search_agent()
        search_result = search_agent.invoke({
            "messages": [("user", f"Find recent, reliable and detailed information about: {topic}")]
        })
        state["search_results"] = _agent_final_message(search_result)
    except PipelineError:
        raise
    except Exception as exc:  # noqa: BLE001
        log.exception("Search stage failed")
        raise PipelineError("search", str(exc)) from exc

    # ── Stage 2: Read ──
    log.info("Stage 2/4 - reader agent starting")
    try:
        reader_agent = build_reader_agent()
        reader_result = reader_agent.invoke({
            "messages": [("user",
                f"Based on the following search results about '{topic}', "
                f"pick the most relevant URL and scrape it for deeper content.\n\n"
                f"Search Results:\n{state['search_results'][: settings.handoff_max_chars]}"
            )]
        })
        state["scraped_content"] = _agent_final_message(reader_result)
    except PipelineError:
        raise
    except Exception as exc:  # noqa: BLE001
        log.exception("Reader stage failed")
        raise PipelineError("reader", str(exc)) from exc

    # ── Stage 3: Write ──
    log.info("Stage 3/4 - writer chain starting")
    try:
        research_combined = (
            f"SEARCH RESULTS:\n{state['search_results']}\n\n"
            f"DETAILED SCRAPED CONTENT:\n{state['scraped_content']}"
        )
        state["report"] = get_writer_chain().invoke(
            {"topic": topic, "research": research_combined}
        )
    except Exception as exc:  # noqa: BLE001
        log.exception("Writer stage failed")
        raise PipelineError("writer", str(exc)) from exc

    # ── Stage 4: Critique ──
    log.info("Stage 4/4 - critic chain starting")
    try:
        state["feedback"] = get_critic_chain().invoke({"report": state["report"]})
    except Exception as exc:  # noqa: BLE001
        log.exception("Critic stage failed")
        raise PipelineError("critic", str(exc)) from exc

    log.info("Pipeline complete")
    return state


if __name__ == "__main__":
    import sys

    try:
        topic_in = input("\nEnter a research topic: ")
        result = run_research_pipeline(topic_in)
        print("\n" + "=" * 60)
        print("FINAL REPORT\n")
        print(result["report"])
        print("\n" + "=" * 60)
        print("CRITIC FEEDBACK\n")
        print(result["feedback"])
    except PipelineError as exc:
        logger.error("Pipeline failed: %s", exc)
        print(f"\nError: {exc}", file=sys.stderr)
        sys.exit(1)
    except KeyboardInterrupt:
        print("\nCancelled.", file=sys.stderr)
        sys.exit(130)
