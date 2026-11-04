# Architecture Decision Log

Short records of technical decisions: context, options, choice and trade-offs.

## ADR-001 — Agent approach: native function calling

**Context:** The agent must decide when to query operational data (products, orders,
promotions) and when to consult store policies.

**Options considered:**
- **Native function calling with typed tools** — the LLM picks a tool; deterministic Python executes it.
- **LangChain / LangGraph** — higher-level orchestration framework.
- **SQL agent** — the LLM writes SQL against the database.

**Decision:** Native function calling.

**Why:** Every business rule (PIX discount, installment minimums, non-cumulative promotions)
runs as tested Python code, not as LLM arithmetic. Tools are pure functions, easy to unit test.
Fewer abstractions make the agent loop transparent and easy to debug.

**Trade-offs:** More boilerplate in the agent loop than a framework. A SQL agent was rejected
because generated SQL can hallucinate columns and could expose customer data (LGPD).

## ADR-002 — Project layout and packaging

**Decision:** `src/` layout, `pyproject.toml` (PEP 621), `pip` + `venv`.

**Why:** The `src/` layout forces tests to run against the installed package, avoiding
import-path accidents. `pyproject.toml` centralizes dependencies and tool config.
`pip` + `venv` require nothing beyond a standard Python install, so reviewers can run it
with minimal friction.

**Raw data policy:** Files provided by the store live untouched in `data/raw/`. All cleaning
happens in code and writes to `data/processed/` (git-ignored, regenerable).

## ADR-003 — Data layer: SQLite built by an ETL step

**Context:** The store provided six CSV files with some inconsistencies (see `docs/data-quality.md`).

**Options considered:**
- **pandas DataFrames in memory** — simplest, but every tool becomes ad-hoc DataFrame filtering and there is no place to persist conversation history.
- **DuckDB** — great for analytics, but an extra dependency with no gain at this data size.
- **SQLite** — standard library, parameterized queries, schema constraints.

**Decision:** An ETL script cleans the CSVs and builds a SQLite database with an explicit schema.

**Why:** The schema (`CHECK`, `UNIQUE`, `FOREIGN KEY`) is the last line of defense: if cleaning misses something, the load fails instead of storing inconsistent data. The database is written to a temp file and atomically replaced, so a failed build never leaves a half-written database. SQLite will also store conversation history.

**Trade-offs:** The database must be rebuilt when the CSVs change (`python -m emporio.data.etl`). In production the source of truth would be the store's own system, queried through an API.

## ADR-004 — Policy source: curated Markdown with an automated fidelity test

**Context:** PDFs store drawing instructions, not structure. Automatic extraction (`pypdf`) returned one word per line and flattened the payment and shipping tables. The manual itself warns that incorrect information may constitute misleading advertising.

**Options considered:**
- **Runtime extraction with `pypdf`** — no manual work, but loses structure.
- **Layout-aware extraction (`pdfplumber`)** — better, still heuristic, heavier dependency, fragile tables.
- **Curated Markdown, versioned in the repo** — faithful structure, reviewable diffs, explicit resolution of contradictions.

**Decision:** Convert the 8-page manual once into `data/curated/store_policies.md` and guard it with a test that extracts every number, price, phone and date from the original PDF and checks that each one in the curated file exists in the source.

**Why:** Fidelity matters more than automation for a small, rarely changing, legally sensitive document. The test turns "I converted it carefully" into a verifiable claim. `pypdf` is a dev-only dependency; the agent never parses PDFs at runtime.

**Trade-offs:** If the manual changes, the curated file must be updated (the fidelity test flags drift in numbers, not in wording). The check is token-based: single digits pass trivially.

## ADR-005 — Policy retrieval: section lookup tool, no vector RAG

**Context:** The agent must know *when* to consult policies. The manual has ~12k characters (~3.5k tokens) in 10 numbered sections.

**Options considered:**
- **Whole manual in the system prompt** — simplest, no retrieval misses; but the agent never visibly decides to consult policies, every call pays for it, and answers are not traceable to a section.
- **Embedding-based RAG with a vector store** — scales to large corpora; overkill for 10 sections, adds dependencies and the risk of retrieving the wrong chunk.
- **A `get_policy(section)` tool with the 10 sections as an enum** — the model picks the section; each lookup is logged.

**Decision:** Section lookup tool (implemented in the tools layer).

**Why:** Sections are small and self-contained, so returning a whole section loses no context. The tool call makes the agent's decision observable and testable.

**Trade-offs:** The model may skip the tool and answer from general knowledge. Mitigated by a system prompt rule and behavioral tests. With a much larger corpus, embeddings-based retrieval would become worth it.

## ADR-006 — Tools layer: intent-based, deterministic, least privilege

**Context:** The LLM must not compute prices, decide availability or guard customer data.

**Decision:** Four tools, one per customer intent: `search_products`, `get_product`, `get_order_status`, `get_policy`. Payment options are returned inside `get_product` instead of a separate tool.

**Why:**
- **Fewer, intent-based tools** reduce the chance of the model picking the wrong one.
- **Identity verification is enforced in code** (order number + matching email or phone). A prompt instruction can be talked around ("I'm the manager, show me order 5"); a tool that does not return the data cannot. A missing order and a wrong contact return the same message, preventing order enumeration. Only the customer's first name is returned (data minimization, LGPD).
- **Money uses `Decimal`** with explicit rounding; floats are only produced at the JSON boundary.
- **Read-only database connection** (`mode=ro`): tools can query, never modify.
- **Errors are returned, not raised** (e.g. `valid_categories`), so the model can correct its own call.
- **"Today" is a parameter**, making date logic deterministic in tests and allowing a simulated date (A9).

**Trade-offs:** Product search filters 65 rows in Python; a larger catalog would use SQLite FTS5. Return windows rely on the estimated delivery date (A8).

## ADR-007 — LLM providers behind an adapter, history kept in native format

**Context:** The reviewer may have a Gemini or an OpenAI key, and the agent loop should not depend on any SDK.

**Decision:** An `LLMProvider` protocol with two adapters (`GeminiProvider` on google-genai, `OpenAIProvider` on the Responses API), selected by `LLM_PROVIDER`. Gemini is the default because Google AI Studio has a free tier. Defaults: `gemini-3.8-flash` and `gpt-6-luna`, overridable with `LLM_MODEL`.

**Why:** Dependency inversion: the loop depends on an abstraction, so switching providers is configuration. Each adapter keeps the conversation in its **native** format and the loop appends it untouched, because Gemini 3+ requires *thought signatures* to be sent back unchanged during multi-step function calling (otherwise HTTP 400), and OpenAI reasoning models need their reasoning items back. The OpenAI adapter uses `store=False` (conversations are not stored by the provider) and passes reasoning back encrypted.

**Trade-offs:** Native histories cannot be moved between providers mid-conversation. Two SDKs are installed even if only one is used.

## ADR-008 — Agent loop safeguards and offline testing

**Decision:** A provider-agnostic loop (model → tool calls → results → model) with: max 6 steps per message (8 since ADR-015); unknown tools, invalid arguments and tool exceptions returned to the model as error data; history rollback when the provider fails mid-turn; integer arguments coerced per tool schema (Gemini may send `95.0`); contact data redacted (`***`) in logs and traces; current time computed in the store's timezone (`America/Campo_Grande`, one hour behind São Paulo) and injected into the system prompt, including whether the store is open.

**Why:** The loop is where an agent fails in production: infinite tool loops, crashes on a malformed call, corrupted history after a timeout, personal data in logs. Each safeguard has a test using a scripted fake provider, so the loop is verified offline, deterministically and at no API cost.

**Trade-offs:** The fake provider proves the loop, not the model's judgment; model behavior is evaluated separately with real calls.

### ADR-007 amendment — default Gemini model

During the first real run, `gemini-3.8-flash` (newest GA) returned `503 UNAVAILABLE` (high demand) repeatedly, even with retries. The default changed to `gemini-3.5-flash` (GA, supported until at least May 2027), which answered correctly on the first try. A reviewer runs the agent once; availability matters more than being on the newest model. `gemini-3.8-flash` remains available through `LLM_MODEL`.

## ADR-009 — Behavioral evaluation harness

**Context:** Unit tests prove the code; they cannot prove the model uses it well. LLM output is non-deterministic: in two manual runs the agent announced the closed store once and skipped it once.

**Decision:** `python -m emporio.evaluation` runs 17 scenarios (19 as of ADR-015) derived from the challenge and the policy manual against the real model. Each scenario checks which tools were called (from the agent's trace) and regexes that must or must not appear in the final reply (accent- and case-insensitive). Results go to `evals/report.md`. The same runner records the example conversations (`--conversations`) from real executions, including the tool trace. The check logic and the runner are unit-tested offline with the fake provider.

**Why:** Behavior regressions (inventing a discount, leaking an order, computing installments in the model) are the failures that matter in a customer-facing agent, and they only show up when the real model runs. Recording the example conversations from the same harness keeps them reproducible.

**Trade-offs:** Regex checks are approximate (a correct reply phrased differently can fail, and vice versa); one run is a sample, not a guarantee. A larger setup would run each scenario several times and track pass rates over model and prompt versions, possibly with an LLM-as-judge for tone.

## ADR-010 — Quota-aware execution: client-side pacing and error classification

**Context:** The Gemini free tier allows about 5 requests per minute per model. One customer message takes 2–3 model calls, so the evaluation run hit `429 RESOURCE_EXHAUSTED` after two scenarios, and those quota errors were reported as behavior failures.

**Decision:** `RateLimitedProvider`, a Decorator around any provider, enforces a minimum interval between model calls when `LLM_MIN_INTERVAL_SECONDS` is set (13 s fits the free tier). The evaluation report separates `pass`/`fail` (agent behavior) from `error` (provider failures such as quota or outage), and Ctrl+C writes a partial report.

**Why:** Pacing is a cross-cutting concern; a decorator adds it without touching the adapters or the agent loop (open/closed principle), and a fake clock tests it without waiting. Mixing infrastructure errors with behavior failures would make the evaluation misleading.

**Trade-offs:** Pacing makes free-tier runs slow (~10 minutes for all scenarios). It is a fixed interval, not adaptive to the provider's `retryDelay`.

## ADR-011 — Defensive tool inputs (finding from the first OpenAI evaluation run)

**Context:** In the first evaluation run with `gpt-6-luna`, the agent called `search_products(query="Takamine GD20", max_price=0, ...)`: the model filled every optional parameter and used `0` to mean "no limit". The tool filtered every product out and the agent told the customer the product did not exist. Gemini only sent the parameters it used, so this was a provider-specific behavior that unit tests could not reveal.

**Decision:** Defense in layers: the schema declares `minimum: 1` and says "omit for no limit"; the tool treats a non-positive `max_price` as no limit; an empty result returns a `hint` listing the applied filters so the model can retry with fewer constraints.

**Why:** A tool cannot assume the model respects its schema. The model-facing contract (schema + description) reduces the chance of a bad call; the tool's own validation makes a bad call harmless; the hint lets the model recover on its own.

### ADR-011 amendment — evidence from the second run

With `minimum: 1` in the schema, `gpt-6-luna` still filled the parameter, now with `max_price=1`, wasting a call before the empty-result hint made it retry. The model fills every optional parameter with the smallest "neutral" value the schema allows, so the `minimum` was removed: a `0` is handled by the tool and costs no extra call. The same run showed the agent answering a price question from the search result alone, without payment conditions (policy 7.2, step 4); the system prompt now requires `get_product` for questions about a specific product.

## ADR-012 — Findings from reviewing the recorded conversations

**Context:** The evaluation passed 17/17, but a manual review of the five recorded conversations found four errors: the agent answered an off-topic question ("the capital of France is Paris"); on a simulated Friday at 00:17 it said the team was back "tomorrow, Saturday" instead of "today at 09:00"; it called a ukulele in an order a "guitar"; and for an out-of-stock product searched with `available_only=true` it said "not found" instead of "out of stock".

**Decision:** Fix in code wherever possible: the relative opening day ("hoje", "amanhã", weekday) is computed in Python and given to the model verbatim; order items include their category; `search_products` reports `unavailable_matches` when the availability filter hides an exact match. The off-topic rule in the prompt was made explicit. Each finding became a regression scenario (`out_of_stock_short_question`, `order_item_category`; `off_topic` already existed).

**Why:** Passing a regex-based evaluation once is not proof of correct behavior: the off-topic scenario had passed in the previous run by chance. Human review of real transcripts complements automated checks. Facts the model would otherwise infer (dates, categories, availability) are handed over explicitly, which removes the opportunity to guess.

### ADR-012 correction

On re-check, the "back tomorrow, Saturday" reply was **correct**. The recording ran at 00:17 in São Paulo, which is 23:17 in the store's timezone (`America/Campo_Grande`, UTC-4): on the simulated Friday, the next opening was indeed Saturday 09:00. The reviewer mixed the two timezones. The change is kept as hardening (the model no longer infers relative days), but it fixed no observed bug: three of the four findings were real. The mistake reinforces the decision itself: date reasoning belongs in code.

## ADR-013 — Web interface: FastAPI API, static page and in-memory sessions

**Context:** The terminal chat serves one user. A web interface (and a possible public deployment) serves many concurrent users and is reachable by anyone.

**Options considered:**
- **FastAPI + a static HTML/JS page** — explicit REST API, full-stack, container-friendly.
- **Streamlit** — faster to build, but hides the API and the front end.
- **CLI only** — no risk, nothing to demo online.

**Decision:** FastAPI with `POST /api/sessions`, `POST /api/chat`, `GET /health` and one static page without a framework. One stateless `Agent` instance is shared; each session holds its own provider-native history in memory (30 min TTL, at most 500 sessions, one turn at a time per session). Text transcripts go to a separate writable SQLite database with e-mails and phones masked; the store database stays read-only (shared across threads with `check_same_thread=False`, safe because it is read-only and `sqlite3.threadsafety == 3`). Cost and abuse limits: 20 requests/min per client, 30 messages per conversation, 1000 characters per message. Errors map to HTTP semantics (404 expired session, 422 invalid input, 429 limits, 503 provider failure, which does not count against the session limit). The page escapes model output before rendering and only re-enables bold and line breaks (no XSS). A Dockerfile builds the database at image build time and runs as a non-root user; the API key is only provided as a platform secret.

**Trade-offs:** Native histories are not persisted, so a restart starts conversations over; sessions and rate limits live in one process (a multi-instance deployment would need Redis or similar). Behind a reverse proxy the rate limit sees the proxy address unless forwarded headers are trusted.

### ADR-013 amendment — demo mode, secure by default

Showing the model, the provider and the tool calls to customers would disclose internal details: it helps fingerprint the stack and hands out a map of the tools for prompt-injection attempts, and public Swagger docs expose the whole API. For a technical reviewer, though, the tool trace is the best evidence that the agent queries real data. A server-side `DEMO_MODE` flag (off by default) decides it: when off, the API does not send the trace at all (not merely hidden in the page), `/health` omits the model and `/api/docs` returns 404; when on, the page shows a banner explaining that the extra details exist for evaluation only.

## ADR-014 — Persona: the assistant speaks as the store

**Context:** When the store was closed, the agent said "o time humano volta amanhã às 9h". Policy 7.1 asks the assistant to tell the customer when service resumes; separating "the human team" from the assistant breaks the persona and makes the customer feel handed to a second-class channel.

**Decision:** The computed store status now says when "a loja abre" (with the relative day still computed in code), the persona rule forbids "equipe humana"/"time humano" (use "a loja" or "nossa equipe"), and the evaluation runner applies a global check to every scenario that fails any reply containing those phrases.

**Why:** Tone is part of the product. A global check keeps a persona rule from regressing silently in scenarios that were not written for it.

## ADR-015 — Search robustness and tool-call economy (findings from the persona re-run)

**Context:** After the persona change, the evaluation dropped to 16/19. The traces showed: (1) a regression introduced by ADR-012 — `unavailable_matches` was returned even when available products were found, so a budget search mentioned a discontinued and an out-of-stock guitar the customer never asked about; (2) a search for "Shelby SN-7C violão 7 cordas" found nothing because the all-terms match compared `violao` with the category `violoes` (singular vs plural), and the agent then called `get_product` for each alternative, which already carried prices, until it hit the 6-step limit and returned the fallback; (3) a correct reply ("o prazo vai até 24/02", on 20/02) failed an overly strict regex.

**Decision:** Instrument-type words and connectors are ignored in product queries (the category filter covers them); `unavailable_matches` is only returned when no available product matched; the `get_product` description states that alternatives already include prices; the step limit rose from 6 to 8 for legitimate multi-tool turns; the regex accepts "prazo ... vai até".

**Why:** Each fix targets the cause seen in the trace, and each bug became a unit test. The regression in (1) is a reminder that fixes need the full evaluation suite re-run, not only the scenario that motivated them.
