# Empório da Música — AI customer service agent

![CI](https://github.com/Willsmt/emporio-agent/actions/workflows/ci.yml/badge.svg)

A Python prototype of an LLM customer service agent ("Mel") for **Empório da Música**, a fictional musical
instrument store in Campo Grande (MS). Mel answers in Brazilian Portuguese about products, prices, promotions,
payment conditions, store policies and order status.

**Core design idea:** the LLM talks, the code decides. Every business rule (prices, discounts, installments,
availability, return deadlines, identity checks) lives in deterministic, tested Python tools. The model only
chooses which tool to call and turns the result into a friendly answer.

| What                                                         | Where                                                                                                          |
| ------------------------------------------------------------ | -------------------------------------------------------------------------------------------------------------- |
| Live demo | [Live demo](#live-demo) |
| Technical decisions, in short                                | [Technical decisions](#technical-decisions)                                                                    |
| Decision log (16 ADRs, with the evidence behind each change) | [`docs/decisions.md`](docs/decisions.md)                                                                       |
| Data quality findings and assumptions                        | [`docs/data-quality.md`](docs/data-quality.md)                                                                 |
| Behavioral evaluation report (19/19)                         | [`evals/report.md`](evals/report.md)                                                                           |
| Example conversations (5)                                    | [`conversations/`](conversations/)                                                                             |
| Security audit and complexity report                         | [`docs/security-report.md`](docs/security-report.md), [`docs/complexity-report.md`](docs/complexity-report.md) |
| Map of the code for AI agents and humans                     | [`CLAUDE.md`](CLAUDE.md)                                                                                       |

## Live demo

**https://emporio-agent-580393723122.southamerica-east1.run.app**

Hosted on Google Cloud Run with OpenAI `gpt-6-luna` and `DEMO_MODE=true`, so each answer shows the model and the
tools it called. Try a price ("Quanto custa o Takamine GD20?"), a policy ("Posso devolver um produto?"), an order
status (you will be asked for the e-mail or phone on file) and something off-topic.

- The first request after a quiet period can take a few seconds while the container starts.
- It runs as a single instance (sessions live in memory) with the same limits as locally, plus a hard spend limit
  on the API key. If a limit is reached, the chat says the assistant is unavailable.
- It is hosted for the evaluation period and may be taken down afterwards; everything also runs locally (below).

Deployed from this repository's Dockerfile, with the API key in Secret Manager:

```bash
gcloud run deploy emporio-agent --source . --region southamerica-east1 --allow-unauthenticated \
  --max-instances 1 --memory 1Gi --timeout 120 \
  --set-env-vars "LLM_PROVIDER=openai,DEMO_MODE=true,FORWARDED_ALLOW_IPS=*" \
  --set-secrets "LLM_API_KEY=openai-api-key:latest"
```

## Quickstart

Requires Python 3.11+ (CI runs 3.11, 3.12 and 3.13) and an API key for Gemini or OpenAI.

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
python -m emporio.data.etl        # builds data/processed/emporio.db from data/raw + data/curated
pytest -q                         # 129 offline tests, no API calls
cp .env.example .env              # set LLM_PROVIDER and LLM_API_KEY
```

Talk to the agent:

```bash
python -m emporio.chat --trace    # terminal; --trace prints each tool call
python -m emporio.web             # web UI on http://127.0.0.1:8000
```

Or with Docker (the image builds the database and runs as a non-root user):

```bash
docker build -t emporio . && docker run -p 8000:8000 --env-file .env emporio
```

### Configuration

| Variable                   | Default                           | Notes                                                                 |
| -------------------------- | --------------------------------- | --------------------------------------------------------------------- |
| `LLM_PROVIDER`             | `gemini`                          | `gemini` or `openai`                                                  |
| `LLM_API_KEY`              | required                          | Key for the chosen provider                                           |
| `LLM_MODEL`                | `gemini-3.5-flash` / `gpt-6-luna` | Per-provider default                                                  |
| `STORE_TODAY`              | real date                         | `YYYY-MM-DD`, to simulate a date (e.g. to demo an open return window) |
| `LLM_MIN_INTERVAL_SECONDS` | `0`                               | Paces LLM calls; `13` fits the Gemini free tier                       |
| `DEMO_MODE`                | off                               | See below                                                             |

The full list, including the web server variables, is in [`CLAUDE.md`](CLAUDE.md#environment-variables).

### `DEMO_MODE` (recommended for reviewers)

With `DEMO_MODE=true`, the web UI shows, under each answer, **which model replied and which tools it called with
which arguments**, plus the API docs at `/api/docs`. This is intentional: it lets a reviewer see that prices come
from `get_product` and not from the model's memory. It is **off by default**, because a production chat should not
expose its internals to customers.

## How it works

```
customer ──► FastAPI / terminal ──► Agent loop (max 8 steps) ──► LLMProvider ──► Gemini or OpenAI
                                          │
                                          ▼
                              deterministic tools (read-only SQLite)
                 search_products · get_product · get_order_status · get_policy
```

**Data.** The raw CSVs and the policy PDF are never modified. An ETL cleans them into SQLite with an explicit
schema and constraints, written to a temp file and swapped atomically. The data had real problems (for example a
duplicate customer and contradictions inside the policy manual); each one is documented with the decision taken in
[`docs/data-quality.md`](docs/data-quality.md).

**Policies.** The PDF was converted into a curated Markdown file. Where the manual contradicts itself, an
"Esclarecimento" note records the interpretation. A test checks that every number in the curated file exists in
the original PDF, so the curation cannot invent policy. The agent fetches a policy section through a tool instead
of a RAG pipeline: the manual is small and well structured, so exact sections beat similarity search here.

**Tools.** Money uses `Decimal` with explicit rounding. `get_order_status` verifies identity inside the tool
(order number plus the e-mail or phone on file), returns the same message for "not found" and "wrong contact" to
prevent enumeration, and exposes only the customer's first name (data minimization, LGPD).

**Agent loop.** Provider-agnostic, behind an `LLMProvider` protocol with Gemini and OpenAI adapters. Each provider
keeps its history in its native format (Gemini thought signatures, OpenAI encrypted reasoning). The store's
open/closed status and next opening day are computed in Python in the store's timezone (`America/Campo_Grande`),
not left to the model.

**Web.** FastAPI with in-memory sessions, per-IP sliding-window rate limit, a daily message cap, input size limit,
and transcripts with e-mails and phones masked before storage. The page is plain HTML with an XSS-safe renderer.

## Technical decisions

The challenge leaves these choices open and asks for the reasoning. Each one has a full ADR in
[`docs/decisions.md`](docs/decisions.md); this is the short version.

| Decision             | Choice                                                                               | Why                                                                                                                                                                                                               |
| -------------------- | ------------------------------------------------------------------------------------ | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Agent approach       | **Native function calling**, own loop, no agent framework                            | Four tools and one loop do not need LangChain or LlamaIndex. Owning the loop keeps it small, readable and fully testable offline with a scripted fake LLM.                                                        |
| Why not a SQL agent  | Tools with fixed queries                                                             | Letting the model write SQL means it could skip the identity check on orders or compute prices itself. Business rules must be enforced by code, not requested in a prompt.                                        |
| Retrieval            | **No vector RAG**; `get_policy` returns whole policy sections                        | The manual is short and well structured. Exact sections are deterministic and cheaper than embeddings, with no chunking or ranking errors to tune. RAG becomes worth it when the knowledge base grows.            |
| Model and provider   | `gemini-3.5-flash` by default, `gpt-6-luna` (OpenAI) as an alternative               | Both have reliable tool calling and low cost. A newer Gemini model was dropped after repeated 503 errors. The provider is one setting, because the loop talks to an `LLMProvider` protocol.                       |
| Prompt strategy      | Short persona + numbered rules; facts only from tools                                | The prompt holds behavior, never data. The only facts it receives are computed in Python (current store time and whether the store is open). A rule was added only after a failing scenario showed it was needed. |
| Interface            | Terminal (`--trace`) for development, FastAPI + HTML page for demo                   | The terminal shows each tool call while iterating; the web page is what a reviewer or the store staff would use.                                                                                                  |
| Conversation history | Kept per session, in memory, for 30 minutes; transcripts stored with contacts masked | Multi-turn context is needed ("and the price in PIX?"). Long-term memory across visits was left out on purpose: there is no customer login, and keeping personal data without a need conflicts with LGPD.         |
| Data treatment       | ETL into SQLite with constraints, curated policy Markdown                            | The data had duplicates and the manual contradicts itself; fixing that once, with tests, is safer than asking the model to cope with it on every message.                                                         |

### Assumptions

Where the challenge or the data was ambiguous, I made a reasonable assumption and wrote it down:

- The store's clock is `America/Campo_Grande`, the store's own timezone, not the server's.
- Contradictions in the policy manual are resolved in "Esclarecimento" notes in the curated file, each one listed in
  [`docs/data-quality.md`](docs/data-quality.md) with the reasoning.
- Order data is personal: the agent only discusses an order after the customer confirms the e-mail or phone on file.
- Accessories and services the store does not list are treated as out of scope, and the agent says so instead of guessing.

## Evaluation

```bash
python -m emporio.evaluation                  # 19 scenarios against the real LLM -> evals/report.md
python -m emporio.evaluation --conversations  # records conversations/*.md
```

Each scenario checks **behavior**, not exact wording: which tools must (or must not) be called, and regex checks on
the reply (the right price, no invented phone number, no off-topic answer, persona rules). Scenarios cover price
lookup, budget search, promotions, out-of-stock and discontinued items, installments, store hours, the identity
check and enumeration attempts, return windows, and prompt injection.

The agent reached 19/19 through evidence-based cycles: read the tool trace, form a hypothesis, make the smallest
fix, re-run everything. Each fix is recorded as an ADR with the failing evidence. Provider errors (quota, 503) are
reported separately from behavior failures, so an outage is never counted as a wrong answer.

The recorded evaluation used OpenAI, because the Gemini free tier allows only a few requests per minute. Both
providers are supported.

## Quality gates (CI)

| Job                          | Checks                                                                                                               |
| ---------------------------- | -------------------------------------------------------------------------------------------------------------------- |
| `tests (3.11 / 3.12 / 3.13)` | 129 offline tests; coverage must stay at 80% or more (currently ~84%); a leaked SQLite connection fails the suite    |
| `security (bandit + pip-audit)`                | Bandit (static analysis) and pip-audit (known vulnerabilities in dependencies)                                       |
| `secrets (gitleaks)`                    | gitleaks over the full git history                                                                                   |
| `complexity (no block ranked D or worse)`                 | No function ranked D or worse in cyclomatic complexity                                                               |
| `integration (docker image smoke test)`                | Builds the Docker image, starts it and checks the UI, the API, closed docs outside `DEMO_MODE` and the non-root user |

Real LLM calls are deliberately **not** in CI: they cost money, depend on quotas and are non-deterministic, and a
gate that fails because a provider returned 503 teaches people to ignore CI. They run through the evaluation
command above, and the report is committed as evidence.

## Known limitations

- **Single process.** Sessions and rate limits live in memory, so they reset on restart and do not work across
  several instances. Production would move them to Redis.
- **No per-order attempt limit** on the identity check. Enumeration is mitigated by the uniform error message and
  the global rate limit, but a dedicated lockout per order number is an accepted risk for this prototype (see the
  security report).
- **Evaluation is rule-based.** Regex and tool-trace checks prove the facts are right, not that the tone is good
  or that the answer is faithful to the policy text. The next step is an LLM-as-a-judge layer (e.g. DeepEval
  faithfulness and answer relevancy) on top of the current checks.
- **The LLM can still phrase things imperfectly.** Numbers come from tools, but wording is the model's. The
  evaluation covers the known failure modes, not every possible question.
- **No real store integrations.** Stock, orders and policies come from the provided files, not from live systems.
- **Portuguese only** for customers; the code and docs are in English.

## With more time

- Move sessions and rate limits to Redis and add a lockout per order number on the identity check.
- Provider fallback (OpenAI to Gemini) for new sessions, as a decorator like `RateLimitedProvider`. Switching in the
  middle of a conversation is harder: each provider keeps its history in its native format (Gemini thought
  signatures, OpenAI encrypted reasoning), so the context would have to be translated or dropped.
- Add an LLM-as-a-judge layer to the evaluation for tone and policy faithfulness, plus paraphrased versions of each
  scenario to measure robustness.
- Observability: trace each conversation (tool calls, latency, tokens and cost per answer) with OpenTelemetry or Langfuse.
- Stream answers to the web page, so long replies feel faster.
- A handoff flow: when the agent cannot help, open a ticket for the staff with the conversation summary.
- Connect the tools to the store's real systems instead of exported files.

## How I used AI in this project

This project was built with AI assistance, and I want to be explicit about how.

- **Pair programming with Claude (chat).** I used Claude as a pair to discuss options for each decision (with pros,
  cons and a recommendation), and to draft code. **The decisions were mine**, and every change went through my
  terminal in small commits that only landed after the tests passed. When a suggestion was wrong, I caught it
  through tests or by checking the data; one of those cases (a timezone mistake) is recorded in the decision log.
- **Claude Code agents and skills in [`.claude/`](.claude/).** I adapted three agents/skills presented in a
  Pythonando workshop on AI-assisted development, and ran each on this codebase:
  - `security-auditor`: static analysis and dependency audit, with each finding triaged by hand. The result and
    the fixes are in [`docs/security-report.md`](docs/security-report.md).
  - `cyclomatic-complexity`: a radon-based report with a refactoring plan. I applied it (the worst function went
    from D(28) to A) and declined one suggestion on purpose; see [`docs/complexity-report.md`](docs/complexity-report.md).
  - `doc-sync`: keeps [`CLAUDE.md`](CLAUDE.md) and the docs aligned with the code after each change.
- **Context engineering.** [`CLAUDE.md`](CLAUDE.md) gives any coding agent the architecture map, commands and the
  invariants that must not be broken, so the next change starts from the project's rules, not from guesses.
- **What the AI did not do:** decide the architecture, choose trade-offs, or commit untested code. The CI gates
  above apply to AI-written code exactly as they would to mine.

## Project structure

```
data/raw/                original files from the store (never modified)
data/curated/            policy manual converted from the PDF, with clarification notes
src/emporio/data/        ETL and database schema
src/emporio/tools/       deterministic business tools
src/emporio/agent/       agent loop, prompts, provider adapters
src/emporio/evaluation/  behavioral scenarios and runner
src/emporio/web/         FastAPI app, sessions, rate limits, transcripts, UI
tests/                   offline test suite
docs/                    decisions, data quality, security and complexity reports
evals/, conversations/   evaluation report and recorded conversations
```

---

Willians Martins · [GitHub](https://github.com/Willsmt) · [LinkedIn](https://www.linkedin.com/in/willians-martins-dev)
