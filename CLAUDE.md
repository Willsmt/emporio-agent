# CLAUDE.md — Empório da Música customer service agent

Context for AI coding agents working in this repository. Keep it accurate: after any code change,
run the `doc-sync` agent (`.claude/agents/doc-sync.md`) as the last step.

Decision records: [`docs/decisions.md`](docs/decisions.md) · Data assumptions: [`docs/data-quality.md`](docs/data-quality.md) ·
Reports: [`docs/security-report.md`](docs/security-report.md), [`docs/complexity-report.md`](docs/complexity-report.md)

## What this is
A Python prototype of an LLM customer service agent ("Mel") for a fictional musical instrument store.
The LLM understands intent and writes replies; deterministic, tested Python tools fetch data and apply
every business rule (prices, installments, availability, return deadlines, identity checks).

## Commands
```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
python -m emporio.data.etl          # build data/processed/emporio.db from data/raw + data/curated
pytest -q                           # offline test suite (no API calls), 143 tests
pytest -q --cov=emporio --cov-report=term-missing:skip-covered   # as CI runs it; coverage must be >= 80%
python -m emporio.chat --trace      # terminal chat; needs .env (see .env.example)
python -m emporio.web               # web UI + API on http://127.0.0.1:8000 (HOST/PORT honored); needs .env
python -m emporio.evaluation        # 19 behavioral scenarios against the real LLM -> evals/report.md
python -m emporio.evaluation --only <scenario_id> ...   # run a subset
python -m emporio.evaluation --conversations            # record conversations/*.md
bandit -r src -q                    # static security analysis (CI)
pip-audit --skip-editable           # dependency vulnerabilities (CI)
bash .claude/skills/cyclomatic-complexity/scripts/check_complexity.sh   # complexity gate: fails on any block ranked D or worse
docker build -t emporio . && docker run -p 8000:8000 --env-file .env emporio   # Dockerfile builds the DB at image build time
```
`pyproject.toml` makes `ResourceWarning` and unraisable-exception warnings **errors** in pytest, so a leaked SQLite
connection fails the suite. CI (`.github/workflows/ci.yml`, on push to `main` and on PRs; actions `checkout@v5` and
`setup-python@v6`) runs these jobs:

| Job name in ci.yml | What it gates |
|---|---|
| `tests (<python-version>)` | Matrix Python 3.11, 3.12, 3.13: `pytest` with coverage (`fail_under = 80` in `pyproject.toml`) |
| `security (bandit + pip-audit)` | Python 3.13: `bandit -r src -q` and `pip-audit --skip-editable` (pip and setuptools are upgraded first, otherwise pip-audit flags the runner's old installers) |
| `secrets (gitleaks)` | `gitleaks-action@v2` over the full git history (`fetch-depth: 0`) |
| `complexity (no block ranked D or worse)` | Python 3.13: `check_complexity.sh` gate |
| `integration (docker image smoke test)` | Job id `docker-smoke`, runs after `tests`: builds the image, starts it with a dummy key and checks `/health`, the UI at `/` (references `js/store.js`, which calls `/api/storefront`), `css/chat.css`, the `Content-Security-Policy` header on `/`, `POST /api/sessions`, `/api/docs` returning 404 outside `DEMO_MODE`, and that the container user is uid 10001 (non-root) |

## Environment variables
Read by `src/emporio/settings.py` (`load_settings`, which also calls `load_dotenv`) unless noted. Template: `.env.example`.

| Variable | Default | Meaning |
|---|---|---|
| `LLM_PROVIDER` | `gemini` | `gemini` or `openai`; anything else raises `SettingsError` |
| `LLM_MODEL` | `gemini-3.5-flash` / `gpt-6-luna` (per provider) | Model override |
| `LLM_API_KEY` | none, **required** | Key of the chosen provider |
| `STORE_TODAY` | real date | `YYYY-MM-DD`; simulates the store's current date (e.g. to demo open return windows) |
| `LLM_MIN_INTERVAL_SECONDS` | `0` (off) | Minimum seconds between LLM calls; wraps the provider in `RateLimitedProvider` when > 0 (13 fits the Gemini free tier) |
| `DEMO_MODE` | off | `1`/`true`/`yes` exposes model, tool trace and `/api/docs` in the web app. Never enable in production |
| `HOST` | `127.0.0.1` (`0.0.0.0` in the Dockerfile) | Web bind address (`web/__main__.py`) |
| `PORT` | `8000` | Web port (`web/__main__.py`) |
| `FORWARDED_ALLOW_IPS` | `127.0.0.1` | Trusted proxy addresses (or `*`) so the rate limit sees the real client IP (`web/__main__.py`) |

## Architecture map
| Path | Responsibility |
|---|---|
| `data/raw/` | Files provided by the store. **Never modify.** |
| `data/curated/store_policies.md` | Policy manual converted from the PDF, with "Esclarecimento" notes resolving contradictions |
| `src/emporio/config.py` | Project paths (`RAW_DIR`, `CURATED_DIR`, `DB_PATH`, `POLICIES_PATH`) |
| `src/emporio/settings.py` | `Settings` dataclass, `load_settings`, store timezone (`America/Campo_Grande`), default models |
| `src/emporio/text.py` | `normalize` (lowercase, no accents) and `digits_only` helpers |
| `src/emporio/data/etl.py` | Clean CSVs, validate, build SQLite in a temp file and atomically replace (connection closed before the replace) |
| `src/emporio/data/policies.py`, `schema.sql` | Policy section parsing; DB schema and constraints |
| `src/emporio/tools/catalog.py` | `search_products` (`SearchCriteria`, predicates, response annotations), `get_product`, alternatives |
| `src/emporio/tools/pricing.py` | Pure money logic: discounts, PIX, installments (`Decimal`) |
| `src/emporio/tools/orders.py` | `get_order_status` with identity check and return/exchange windows |
| `src/emporio/tools/policies.py` | `get_policy` section lookup |
| `src/emporio/tools/db.py` | Read-only SQLite connections |
| `src/emporio/agent/tool_registry.py` | Tool names, JSON schemas and descriptions shown to the LLM |
| `src/emporio/agent/agent.py` | Provider-agnostic loop: model -> tool calls -> results -> model (`MAX_STEPS = 8`) |
| `src/emporio/agent/types.py` | `ToolCall`, `ModelTurn`, `ToolSpec` shared by loop and adapters |
| `src/emporio/agent/factory.py` | `build_agent(settings)`: read-only DB + tools + provider + prompt |
| `src/emporio/agent/prompts.py` | System prompt (persona + rules) and store-time context |
| `src/emporio/agent/providers/base.py` | `LLMProvider` protocol and `ProviderError` |
| `src/emporio/agent/providers/gemini.py`, `openai_provider.py` | `GeminiProvider` (google-genai) and `OpenAIProvider` (Responses API) adapters |
| `src/emporio/agent/providers/rate_limit.py` | `RateLimitedProvider`: decorator that paces `generate` |
| `src/emporio/agent/providers/__init__.py` | `create_provider` factory (wraps with `RateLimitedProvider` when interval > 0) |
| `src/emporio/chat.py` | Terminal interface |
| `src/emporio/evaluation/scenarios.py` | The 19 scenarios and the recorded conversations |
| `src/emporio/evaluation/checks.py` | `Checks` / `evaluate`: tool-trace and regex checks |
| `src/emporio/evaluation/runner.py`, `__main__.py` | Runs scenarios against the real LLM, writes `evals/report.md` or `conversations/*.md` |
| `src/emporio/web/app.py` | FastAPI app: `/health`, `POST /api/sessions`, `POST /api/chat`, `GET /api/storefront`, store page `/`, chat page `/chat`, `/static`; `create_app`; `add_security_headers` middleware sets CSP, `X-Content-Type-Options` and `Referrer-Policy` on `/`, `/chat` and `/static/*` only (ADR-018) |
| `src/emporio/web/sessions.py` | In-memory `SessionStore` (30 min TTL, max 500 sessions) |
| `src/emporio/web/rate_limit.py` | `SlidingWindowLimiter` (20 req/min per client IP; global cap of 500 messages/day) |
| `src/emporio/web/transcripts.py` | Text transcripts in `data/processed/transcripts.db` with e-mails and phones masked (`mask_contacts`) |
| `src/emporio/web/static/store.html`, `css/store.css`, `js/store.js` | Store front page served at `/` (no framework) |
| `src/emporio/web/static/index.html`, `css/chat.css`, `js/chat.js` | Chat page served at `/chat` and embedded as the widget (no framework). No inline `<style>`, `<script>`, `style=` or `on*=` allowed: the CSP blocks them (ADR-018) |
| `src/emporio/web/static/mel_hero.svg`, `mel_icon.svg` | Mel mascot images |
| `src/emporio/web/__main__.py` | Starts uvicorn with proxy headers |
| `tests/` | Offline suite; `tests/fakes.py` has `ScriptedProvider`, a fake LLM for the loop |
| `evals/report.md`, `conversations/` | Generated evaluation report and recorded conversations (outputs of `python -m emporio.evaluation`) |
| `Dockerfile` | Image for the web app; builds the DB at build time, runs as non-root (uid 10001) |
| `.claude/agents/` | `doc-sync` (keeps docs in sync) and `security-auditor` (Bandit, Semgrep, pip-audit; reports only) |
| `.claude/skills/cyclomatic-complexity/` | Radon-based complexity report and the gate script used by CI |

## Reports
[`docs/security-report.md`](docs/security-report.md) (security audit and resolution) ·
[`docs/complexity-report.md`](docs/complexity-report.md) (cyclomatic complexity and resolution).
Regenerate them with the `security-auditor` agent and the `cyclomatic-complexity` skill.

## Invariants (do not break)
1. The LLM never computes prices, discounts or deadlines; that logic lives in `src/emporio/tools/` with tests.
2. `get_order_status` returns data only when order id **and** e-mail/phone match the same customer, and returns the
   same message for "not found" and "wrong contact" (anti-enumeration). Only the first name is exposed.
3. Tools use read-only database connections. Money uses `Decimal`; floats only at the JSON boundary.
4. Provider histories stay in their native format and are appended unchanged (Gemini thought signatures).
5. Contact data is redacted (`***`) in logs and traces; web transcripts mask e-mails and phones before storage.
6. Raw data is immutable; if the curated policy file changes, `tests/test_policies.py` must still pass
   (every number must exist in the original PDF).

## Where to change what
- **New tool:** function in `src/emporio/tools/` → register in `tool_registry.py` → unit tests + an agent-loop test.
- **New LLM provider:** adapter in `src/emporio/agent/providers/` implementing `LLMProvider` → wire in `create_provider` → adapter tests with SDK types.
- **Agent behavior / persona:** `src/emporio/agent/prompts.py`; add or update a scenario in `src/emporio/evaluation/scenarios.py` and re-run the full evaluation.
- **Web limits / sessions:** constants in `src/emporio/web/app.py` (`MAX_MESSAGE_CHARS` 1000, `MAX_MESSAGES_PER_SESSION` 30, `REQUESTS_PER_MINUTE_PER_CLIENT` 20, `MAX_MESSAGES_PER_DAY` 500) and `sessions.py`.
- **New setting:** `settings.py` + `.env.example` + the table above.
- **Business rule from the manual:** the matching tool module, never the prompt alone.

## Conventions
- Python 3.11+, `src/` layout, code and docs in English; customer-facing replies in Brazilian Portuguese.
- Every change ships with tests (CI gates: coverage >= 80%, Bandit, pip-audit, gitleaks, no complexity block ranked D or worse, docker smoke test); technical decisions get an ADR in `docs/decisions.md`; data assumptions go to `docs/data-quality.md`.
- Conventional Commits (`feat(scope): ...`). No co-author trailers.
- Secrets only in `.env` (git-ignored). Never print or log API keys.
