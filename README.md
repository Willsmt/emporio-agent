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
| Decision log (15 ADRs, with the evidence behind each change) | [`docs/decisions.md`](docs/decisions.md)                                                                       |
| Data quality findings and assumptions                        | [`docs/data-quality.md`](docs/data-quality.md)                                                                 |
| Behavioral evaluation report (19/19)                         | [`evals/report.md`](evals/report.md)                                                                           |
| Example conversations (5)                                    | [`conversations/`](conversations/)                                                                             |
| Security audit and complexity report                         | [`docs/security-report.md`](docs/security-report.md), [`docs/complexity-report.md`](docs/complexity-report.md) |
| Map of the code for AI agents and humans                     | [`CLAUDE.md`](CLAUDE.md)                                                                                       |

## Quickstart

Requires Python 3.11+ (CI runs 3.11, 3.12 and 3.13) and an API key for Gemini or OpenAI.

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
python -m emporio.data.etl        # builds data/processed/emporio.db from data/raw + data/curated
pytest -q                         # 128 offline tests, no API calls
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
| `tests (3.11 / 3.12 / 3.13)` | 128 offline tests; coverage must stay at 80% or more (currently ~84%); a leaked SQLite connection fails the suite    |
| `security`                   | Bandit (static analysis) and pip-audit (known vulnerabilities in dependencies)                                       |
| `secrets`                    | gitleaks over the full git history                                                                                   |
| `complexity`                 | No function ranked D or worse in cyclomatic complexity                                                               |
| `integration`                | Builds the Docker image, starts it and checks the UI, the API, closed docs outside `DEMO_MODE` and the non-root user |

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
