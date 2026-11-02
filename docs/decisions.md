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
