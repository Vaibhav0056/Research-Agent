# 🔬 ResearchMind — Multi-Agent Research System

> Type a topic. Four AI "workers" search the web, read the best source, write a
> structured report, and grade their own work — all in one click.

<p align="center">
  <img alt="Python" src="https://img.shields.io/badge/Python-3.12-3776AB">
  <img alt="UI" src="https://img.shields.io/badge/UI-Streamlit-ff4b4b">
  <img alt="LLM" src="https://img.shields.io/badge/LLM-OpenAI-412991">
  <img alt="Orchestration" src="https://img.shields.io/badge/Orchestration-LangChain-1c3c3c">
  <img alt="Search" src="https://img.shields.io/badge/Search-Tavily-0ea5e9">
</p>

---

## 📑 Table of Contents

1. [What is this, in one paragraph?](#1-what-is-this-in-one-paragraph)
2. [Concepts you need (explained from zero)](#2-concepts-you-need-explained-from-zero)
3. [The big picture (architecture)](#3-the-big-picture-architecture)
4. [End-to-end walkthrough of one run](#4-end-to-end-walkthrough-of-one-run)
5. [The files, and what each one does](#5-the-files-and-what-each-one-does)
6. [How a request flows through the code](#6-how-a-request-flows-through-the-code)
7. [Setup & running it yourself](#7-setup--running-it-yourself)
8. [Configuration reference](#8-configuration-reference)
9. [Production hardening (what makes it "real")](#9-production-hardening-what-makes-it-real)
10. [Deployment](#10-deployment)
11. [Testing](#11-testing)
12. [Limitations & roadmap](#12-limitations--roadmap)
13. [Glossary](#13-glossary)

---

## 1. What is this, in one paragraph?

Doing research by hand is slow: you search Google, open ten tabs, skim pages,
take notes, write a summary, then wonder if it's any good. **ResearchMind
automates that entire loop.** You give it one topic (e.g. *"fusion energy
progress in 2025"*). Behind the scenes, a small team of AI programs cooperates:
one **searches** the live web, one **reads** the most relevant page, one
**writes** a structured report, and one **critiques** that report and gives it a
score out of 10. You watch the progress live in a web page and download the
finished report as a Markdown file.

---

## 2. Concepts you need (explained from zero)

If you've never touched AI tooling, here are the only ideas you need. Each is
one sentence plus why it matters here.

| Term | Plain-English meaning | Why it's in this project |
|---|---|---|
| **LLM** (Large Language Model) | A program (like OpenAI's GPT) that takes text in and produces text out — it can write, summarize, and reason. | It's the "brain" every worker uses. |
| **API key** | A secret password that lets your program use a paid online service. | We need one for OpenAI (the LLM) and one for Tavily (web search). |
| **Prompt** | The instructions you give the LLM ("write a report structured like this…"). | Each worker has a carefully written prompt that defines its job. |
| **Tool** | A normal function (search the web, download a page) that the AI is *allowed to call* when it decides it needs to. | Gives the AI "hands" to reach the live internet. |
| **Agent** | An LLM that can **decide on its own** whether and when to use a tool. | Our Search and Reader workers are agents — they choose what to search/scrape. |
| **Chain** | A fixed pipeline: *prompt → LLM → text*, with no decision-making. | Our Writer and Critic are chains — they always do the same step. |
| **Streamlit** | A Python library that turns a script into a web app, no web-dev needed. | It's the user interface you see in the browser. |
| **Pipeline** | A series of steps where each step's output feeds the next. | Search → Read → Write → Critique is our 4-step pipeline. |

> **Agent vs. Chain — the one distinction that matters:** an *agent* is given
> tools and gets to choose if/when to use them (it "reasons"). A *chain* is a
> straight line with no choices. We use agents where judgment is needed (which
> page to read?) and chains where the task is always the same (write the
> report).

---

## 3. The big picture (architecture)

```
                          ┌──────────────────────────────────┐
                          │         YOUR WEB BROWSER          │
                          │   (the Streamlit page, app.py)    │
                          └──────────────┬───────────────────┘
                                         │  1 topic + "Run" click
                                         ▼
        ┌────────────────────────────────────────────────────────────┐
        │                    THE 4-STAGE PIPELINE                      │
        │                                                              │
        │   ┌─────────────┐   search results   ┌──────────────┐       │
        │   │ 1. SEARCH   │ ─────────────────► │ 2. READER    │       │
        │   │   (agent)   │                    │   (agent)    │       │
        │   └──────┬──────┘                    └──────┬───────┘       │
        │          │ uses tool                        │ uses tool      │
        │          ▼                                  ▼                │
        │   web_search()                        scrape_url()           │
        │   via Tavily API                      via requests + BS4     │
        │                                                              │
        │   ┌─────────────┐    report text     ┌──────────────┐       │
        │   │ 3. WRITER   │ ◄───────────────── │ (combined     │       │
        │   │   (chain)   │                    │  research)    │       │
        │   └──────┬──────┘                    └──────────────┘       │
        │          │ report                                            │
        │          ▼                                                   │
        │   ┌─────────────┐                                            │
        │   │ 4. CRITIC   │ ──► score /10 + strengths + improvements   │
        │   │   (chain)   │                                            │
        │   └─────────────┘                                            │
        └────────────────────────────────────────────────────────────┘
                                         │
                                         ▼
                          ┌──────────────────────────────────┐
                          │  Report shown on page + .md file  │
                          └──────────────────────────────────┘

   Supporting layers (used by every stage):
   • config.py        → loads settings & secret API keys
   • logging_setup.py → records what happened (with a per-run id)
   • OpenAI API       → the LLM brain for all 4 workers
```

**Read it top to bottom:** your topic enters at the browser, flows down through
four workers (each feeding the next), and the final report comes back out to the
page. The two boxes on the left (`config`, `logging`) are plumbing that every
stage relies on.

---

## 4. End-to-end walkthrough of one run

Let's follow the topic **"CRISPR gene editing"** through the whole system.

1. **You type the topic and click "Run Research Pipeline."**
   The web page ([app.py](app.py)) checks the topic isn't empty or absurdly
   long, then kicks off the pipeline.

2. **Stage 1 — Search.** The Search *agent* is handed your topic. It decides to
   call its one tool, `web_search`, which asks the **Tavily** search service for
   the 5 best web results. Each result comes back as *Title + URL + a short
   snippet*. The agent hands these back as text.

3. **Stage 2 — Read.** The Reader *agent* receives those search results, looks
   at the URLs, and **picks the single most promising one**. It calls its tool,
   `scrape_url`, which downloads that page and strips out the junk (menus,
   scripts, footers), leaving clean readable text.

4. **Stage 3 — Write.** Now we have two piles of information: the search
   snippets and the deep page text. The Writer *chain* glues them together and
   feeds them to the LLM with a strict instruction: *produce a report with an
   Introduction, at least 3 Key Findings, a Conclusion, and a list of Sources.*
   Out comes a polished Markdown report.

5. **Stage 4 — Critique.** The Critic *chain* reads that report and grades it:
   a **Score: X/10**, a list of **Strengths**, a list of **Areas to Improve**,
   and a one-line verdict. This is the system checking its own work.

6. **You see the result.** The report renders on the page, the raw search and
   scraped text are tucked into collapsible panels, the critic's score appears,
   and a **Download (.md)** button lets you save it.

If you run the *same* topic again within an hour, steps 2–5 are **cached** —
results return instantly and you aren't charged again.

---

## 5. The files, and what each one does

| File | Role | What a beginner should know |
|---|---|---|
| [`app.py`](app.py) | **The web app (UI).** | This is what `streamlit run` launches. It draws the page, takes your topic, runs the 4 stages with live progress, shows results, and handles errors gracefully. |
| [`agents.py`](agents.py) | **Builds the 4 workers.** | Defines the Search & Reader agents and the Writer & Critic chains, plus the shared LLM connection. |
| [`tools.py`](tools.py) | **The AI's "hands."** | Two functions the agents can call: `web_search` (Tavily) and `scrape_url` (download + clean a web page, with safety checks). |
| [`pipeline.py`](pipeline.py) | **Headless version (no UI).** | Runs the same 4 stages from the terminal. Great for scripting or debugging. |
| [`config.py`](config.py) | **Settings + secrets.** | One place that loads your API keys and all tunable numbers (timeouts, limits). Refuses to start if keys are missing. |
| [`logging_setup.py`](logging_setup.py) | **Logging.** | Standardized log messages with a per-run id so you can trace one request. |
| [`requirements.txt`](requirements.txt) | **Dependency list.** | The exact libraries (and versions) to install. |
| [`Dockerfile`](Dockerfile) | **Container recipe.** | Packages the app to run anywhere via Docker. |
| [`.streamlit/config.toml`](.streamlit/config.toml) | **App theme/server config.** | Dark theme + server settings. No secrets. |
| `.env.example` / `.streamlit/secrets.toml.example` | **Secret templates.** | Copy these and fill in your keys. |
| [`tests/`](tests/) | **Automated tests.** | Check config loading and the scraper's safety guard. |

---

## 6. How a request flows through the code

This is the same journey as section 4, but mapped to actual functions — useful
if you want to read or modify the code.

```
app.py
  └─ user clicks "Run"  →  sets session_state, st.rerun()
       └─ run_search(topic)            # cached
            └─ agents.build_search_agent().invoke(...)
                 └─ tools.web_search()         → Tavily API
       └─ run_reader(topic, search)    # cached
            └─ agents.build_reader_agent().invoke(...)
                 └─ tools.scrape_url()         → requests + BeautifulSoup
       └─ run_writer(topic, research)  # cached
            └─ agents.get_writer_chain().invoke(...)   → OpenAI
       └─ run_critic(report)           # cached
            └─ agents.get_critic_chain().invoke(...)   → OpenAI
       └─ render report + download button

Every .invoke() above is wrapped in try/except in app.py, so a failure
shows a friendly message instead of crashing. config.py supplies keys and
limits to all of them; logging_setup.py records each step.
```

**Why the stages are separate functions:** each is decorated with
`@st.cache_data`, which means *"if you've seen these exact inputs before, reuse
the answer."* That's what makes repeats free and instant.

**Why agents are built fresh but the LLM is shared:** `get_llm()` is cached
(one connection reused everywhere) for efficiency, while each agent is a thin
wrapper created per call.

---

## 7. Setup & running it yourself

### Prerequisites
- **Python 3.12** (or 3.11). Check with `python --version`.
- An **OpenAI API key** → https://platform.openai.com/api-keys
- A **Tavily API key** (free tier available) → https://tavily.com

### Steps

```bash
# 1. Get the code and enter the folder
cd "RESEARCH AGENT"

# 2. Create an isolated Python environment (keeps deps tidy)
python -m venv .venv
# Windows:
.venv\Scripts\activate
# macOS / Linux:
source .venv/bin/activate

# 3. Install the libraries
pip install -r requirements.txt

# 4. Add your two API keys
cp .env.example .env        # (Windows: copy .env.example .env)
#   then open .env and paste your real keys

# 5a. Launch the web app
streamlit run app.py
#    → opens http://localhost:8501 in your browser

# 5b. OR run it in the terminal with no UI
python pipeline.py
```

If a key is missing or wrong, the app shows a clear message ("Missing required
secret(s): OPENAI_API_KEY …") instead of a confusing crash.

---

## 8. Configuration reference

Everything is tunable via environment variables (in `.env`) or Streamlit
secrets. You only *need* the two keys; the rest have sensible defaults (defined
in [`config.py`](config.py)).

| Variable | Default | What it controls |
|---|---|---|
| `OPENAI_API_KEY` | — *(required)* | Access to the LLM. |
| `TAVILY_API_KEY` | — *(required)* | Access to web search. |
| `MODEL_NAME` | `gpt-4o-mini` | Which OpenAI model to use. |
| `TEMPERATURE` | `0.0` | Creativity vs. determinism (0 = most consistent). |
| `LLM_TIMEOUT_S` | `60` | Max seconds to wait for the LLM. |
| `LLM_MAX_RETRIES` | `3` | Retry attempts on LLM errors. |
| `SEARCH_MAX_RESULTS` | `5` | Web results per search. |
| `SCRAPE_TIMEOUT_S` | `8` | Max seconds to download a page. |
| `SCRAPE_MAX_CHARS` | `3000` | How much scraped text to keep. |
| `SCRAPE_MAX_BYTES` | `3000000` | Max page size to download (~3 MB). |
| `MAX_TOPIC_CHARS` | `300` | Longest allowed topic. |
| `LOG_LEVEL` | `INFO` | Logging verbosity (`DEBUG`/`INFO`/`WARNING`). |

---

## 9. Production hardening (what makes it "real")

This project started as a prototype and was hardened into something safe to
deploy. The table below is the *why*, in beginner terms.

| Concern | The risk if ignored | What we did |
|---|---|---|
| **Missing keys** | App crashes with a cryptic stack trace. | [`config.py`](config.py) checks keys at startup and shows a clear message. |
| **Web content is dangerous** | A scraped page could inject malicious HTML/scripts into our page (an "XSS" attack). | All untrusted text is **HTML-escaped** before display ([app.py](app.py)). |
| **Scraping any URL** | The AI could be tricked into fetching internal/private servers (an "SSRF" attack). | [`tools.py`](tools.py) blocks non-web URLs and private/loopback/cloud-metadata addresses. |
| **Network hiccups** | One blip kills the whole run. | LLM calls and scraping **retry automatically** with timeouts. |
| **Crashes shown to users** | Ugly tracebacks, confused users. | Any failure becomes a friendly error; the real error is logged. |
| **Cost blowup** | Re-running the same topic re-bills you. | Stage results are **cached for 1 hour**. |
| **"It worked yesterday"** | Library updates silently break things. | [`requirements.txt`](requirements.txt) pins versions. |
| **No visibility** | Can't tell what happened in production. | Structured logging with a per-run id. |

---

## 10. Deployment

### Option A — Streamlit Community Cloud (easiest, free)

1. Push this repo to GitHub.
2. Go to [share.streamlit.io](https://share.streamlit.io) and create an app
   pointing at `app.py`.
3. In **App → Settings → Secrets**, paste (TOML format):
   ```toml
   OPENAI_API_KEY = "sk-..."
   TAVILY_API_KEY = "tvly-..."
   ```
4. Deploy. The app reads these automatically via `st.secrets`.

> `.streamlit/config.toml` (theme/server) is committed; `.env` and
> `.streamlit/secrets.toml` are git-ignored — **no secrets are ever committed.**

### Option B — Docker (any VM / Cloud Run / ECS)

```bash
docker build -t researchmind .
docker run -p 8501:8501 \
  -e OPENAI_API_KEY=sk-... \
  -e TAVILY_API_KEY=tvly-... \
  researchmind
```

The container runs as a non-root user and exposes a health check at
`/_stcore/health` for load balancers.

---

## 11. Testing

```bash
pip install -r requirements.txt
pytest -q
```

- `tests/test_config.py` — verifies settings load and that missing keys are
  caught.
- `tests/test_tools.py` — verifies the scraper's safety guard blocks unsafe URLs.

---

## 12. Limitations & roadmap

**Honest scope — what it does *not* do yet:**
- Reads **one** web page per run (depth, not breadth) — it's not a full crawler.
- The critic **scores** the report but doesn't loop back to auto-improve it.
- No login, no per-user rate limiting — add a reverse proxy or auth before
  exposing it publicly.
- Reports aren't saved server-side; the only durable copy is the file you
  download.

**Natural next steps if you scale it up:**
- A **database** to store past reports and scores.
- A **task queue** (e.g. Celery) so many users can run pipelines at once.
- **Parallel** search/scrape of multiple sources instead of one.

---

## 13. Glossary

- **LLM** — Large Language Model; the AI text engine (here, OpenAI GPT).
- **Agent** — an LLM that can decide to call tools.
- **Chain** — a fixed prompt→LLM→output step (no decisions).
- **Tool** — a function the AI may call (search, scrape).
- **Prompt** — the instructions given to the LLM.
- **API key** — secret credential for a paid service.
- **Streamlit** — the Python library that renders the web UI.
- **Caching** — reusing a previous result for identical input.
- **XSS** — Cross-Site Scripting; injecting malicious HTML/JS into a page.
- **SSRF** — Server-Side Request Forgery; tricking a server into fetching
  internal resources.
- **Pipeline** — a sequence where each step feeds the next.

---

## 📄 License & Credits

Original work by **[AkarshVyas](https://github.com/AkarshVyas/Multi-agent-research-system)**.
Replicated, documented, and hardened for study and demonstration purposes.

<p align="center"><i>1 topic in. 4 agents working. 1 polished report out.</i></p>
