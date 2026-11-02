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
