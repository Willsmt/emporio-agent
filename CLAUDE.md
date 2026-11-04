# CLAUDE.md — Empório da Música customer service agent

Context for AI coding agents working in this repository. Keep it accurate: after any code change,
run the `doc-sync` agent (`.claude/agents/doc-sync.md`) as the last step.

Decision records: [`docs/decisions.md`](docs/decisions.md) · Data assumptions: [`docs/data-quality.md`](docs/data-quality.md)

## What this is
A Python prototype of an LLM customer service agent ("Mel") for a fictional musical instrument store.
The LLM understands intent and writes replies; deterministic, tested Python tools fetch data and apply
every business rule (prices, installments, availability, return deadlines, identity checks).

## Commands
```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
python -m emporio.data.etl          # build data/processed/emporio.db from data/raw + data/curated
pytest -q                           # offline test suite (no API calls)
python -m emporio.chat --trace      # terminal chat; needs .env (see .env.example)
```

## Architecture map
| Path | Responsibility |
|---|---|
| `data/raw/` | Files provided by the store. **Never modify.** |
| `data/curated/store_policies.md` | Policy manual converted from the PDF, with "Esclarecimento" notes resolving contradictions |
| `src/emporio/data/` | ETL: clean CSVs, parse policies, build SQLite (`schema.sql` holds the constraints) |
| `src/emporio/tools/` | Deterministic tools: `catalog`, `pricing` (pure), `orders` (identity check), `policies`; `db.py` opens read-only connections |
| `src/emporio/agent/tool_registry.py` | Tool names, JSON schemas and descriptions shown to the LLM |
| `src/emporio/agent/agent.py` | Provider-agnostic loop: model → tool calls → results → model (max 6 steps) |
| `src/emporio/agent/providers/` | `LLMProvider` protocol + Gemini and OpenAI adapters |
| `src/emporio/agent/prompts.py` | System prompt (persona + rules) and store-time context |
| `src/emporio/settings.py` | Environment settings (`LLM_PROVIDER`, `LLM_MODEL`, `LLM_API_KEY`, `STORE_TODAY`) |
| `src/emporio/chat.py` | Terminal interface |
| `tests/fakes.py` | `ScriptedProvider`: fake LLM used to test the loop offline |

## Invariants (do not break)
1. The LLM never computes prices, discounts or deadlines; that logic lives in `src/emporio/tools/` with tests.
2. `get_order_status` returns data only when order id **and** e-mail/phone match the same customer, and returns the
   same message for "not found" and "wrong contact" (anti-enumeration). Only the first name is exposed.
3. Tools use read-only database connections. Money uses `Decimal`; floats only at the JSON boundary.
4. Provider histories stay in their native format and are appended unchanged (Gemini thought signatures).
5. Contact data is redacted (`***`) in logs and traces.
6. Raw data is immutable; if the curated policy file changes, `tests/test_policies.py` must still pass
   (every number must exist in the original PDF).

## Where to change what
- **New tool:** function in `src/emporio/tools/` → register in `tool_registry.py` → unit tests + an agent-loop test.
- **New LLM provider:** adapter in `src/emporio/agent/providers/` implementing `LLMProvider` → wire in `create_provider` → adapter tests with SDK types.
- **Agent behavior / persona:** `src/emporio/agent/prompts.py`.
- **Business rule from the manual:** the matching tool module, never the prompt alone.

## Conventions
- Python 3.11+, `src/` layout, code and docs in English; customer-facing replies in Brazilian Portuguese.
- Every change ships with tests; technical decisions get an ADR in `docs/decisions.md`; data assumptions go to `docs/data-quality.md`.
- Conventional Commits (`feat(scope): ...`). No co-author trailers.
- Secrets only in `.env` (git-ignored). Never print or log API keys.
