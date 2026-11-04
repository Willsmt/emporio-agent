# Security report

- **Date:** 2026-11-04
- **Commit audited:** `b3eafcf` (`main`)
- **Scope:** static analysis (Bandit, Semgrep) and dependency analysis (pip-audit), plus manual code review.
- **Out of scope:** dynamic testing (Strix). It was not authorized and was not run. The app was not started and no LLM API calls were made.

## Summary

No confirmed vulnerabilities: 0 critical, 0 high, 0 medium, 0 low.
Bandit reported two findings; both were reviewed and classified as false positives.
Semgrep and pip-audit reported nothing. Several low-severity residual risks are listed below.

## Tools

| Tool | Version | Configuration | Result |
|---|---|---|---|
| Bandit | 1.9.4 | `src/`, excluding `.venv` (1393 lines scanned) | 2 findings, both false positives |
| Semgrep | 1.178.0 | rulesets `p/python` and `p/security-audit`; excluding `.venv` and `data/processed`; `--metrics=off` | 0 findings, 0 errors |
| pip-audit | 2.10.1 | `pip freeze --exclude-editable` of the project `.venv` | No known vulnerabilities |
| Strix (dynamic) | — | — | Not run (not authorized) |

Bandit and pip-audit were run from an isolated virtual environment; the project `.venv` was not modified.

## Findings

### False positives

| # | Tool / rule | Severity | Location | Assessment |
|---|---|---|---|---|
| 1 | Bandit B105 (hardcoded password string) | Low | `src/emporio/evaluation/runner.py:38` | `STATUS_ICONS = {"pass": "✅", ...}` is an emoji map for test status. The dict key `pass` triggered the rule; there is no credential. |
| 2 | Bandit B608 (SQL built from strings) | Medium | `src/emporio/tools/catalog.py:108` (`find_alternatives`) | The query is `PRODUCT_QUERY + " WHERE ... = ?"`. Both parts are constants and `product_id` is a bound parameter. Not injectable. |

Optional: suppress them with `# nosec B105` / `# nosec B608` and a short justification comment so future scans stay clean.
The other `execute` calls reviewed (`orders.py`, `get_product` in `catalog.py`, `web/transcripts.py`) all use bound parameters.

### Vulnerable dependencies

None reported by pip-audit.

## Repository invariants (manual review)

| Invariant (CLAUDE.md) | Status | Notes |
|---|---|---|
| Read-only database connections | OK | `src/emporio/tools/db.py` opens the store DB with `file:...?mode=ro`. The only writable database is the separate transcripts DB (`src/emporio/web/transcripts.py`). `check_same_thread=False` is documented and acceptable for a read-only connection. |
| Anti-enumeration in `get_order_status` | OK | In `src/emporio/tools/orders.py`, a missing order and a wrong contact return the same `NOT_VERIFIED` constant. Only the first name is exposed. Phone matching requires at least 8 digits and uses `endswith`, so a short suffix cannot match. `found: True` is returned only after a contact match. |
| Contact data redacted in logs and traces | OK, with a gap | `redact()` in `src/emporio/agent/agent.py` masks the `contact` argument in logs and traces; `mask_contacts()` in `src/emporio/web/transcripts.py` masks e-mail and phone before storage. See residual risk R2. |
| Secrets only in `.env` | OK | `.env` is git-ignored and was never committed (`git log --all -- .env` is empty). `.env.example` holds only names and placeholders. The Dockerfile does not copy `.env`; secrets come from platform environment variables, and `.dockerignore` exists. |

Uvicorn logs requests at request-line level only, so customer message bodies are not written to access logs.

## LLM-specific review (code only)

- **Internals exposure.** `DEMO_MODE` gates `/api/docs`, `/api/openapi.json`, `tool_trace` in chat responses, and model/provider details in `/health`. It defaults to off. `/health` always reports the `demo_mode` flag itself, which is minor. `.env.example` suggests `DEMO_MODE=true` for reviewers; it must never be enabled on a public deployment.
- **XSS.** The static page escapes model output before assigning `innerHTML` and re-allows only `**bold**` and `<br>`. Customer text and the tool trace are rendered with `textContent`. No issue found.
- **Cost abuse.** Current limits: 1000 characters per message, 30 messages per session, 20 requests per minute per client IP, at most 500 sessions with a 30-minute TTL, and 6 agent steps per turn. Gaps are listed under residual risks R1, R4 and R5.
- **Prompt injection.** The model sees customer text and tool results, but every tool is read-only, takes typed arguments, and enforces identity checks in Python. A successful injection can only reach what verified tools already return. The prompt itself was not tested; that requires the dynamic step.

## Residual risks

| ID | Risk | Severity | Recommendation |
|---|---|---|---|
| R1 | The rate limiter keys on `request.client.host`. Behind a reverse proxy, all users share one IP (or the limit can be bypassed if forwarded headers are mishandled). | Low–Medium | Run uvicorn with `--proxy-headers` and `--forwarded-allow-ips`, or key on a trusted `X-Forwarded-For`. |
| R2 | The phone mask regex covers Brazilian formats like `(11) 9xxxx-xxxx` only. Numbers with `+55`, spaces, other separators, or a bare 8-digit number in a sentence may be stored unmasked. | Low | Broaden the pattern, e.g. `\+?\d[\d\s().-]{7,}\d`, and add tests for those formats. |
| R3 | No per-order or per-session cap on identity-check attempts in `get_order_status`; only the global message and rate limits apply. | Low | Count failed verifications per session and/or per order id and stop after a small number. |
| R4 | Sessions can be created without limit (20 per minute per IP), so total LLM spend is bounded only per IP. | Low–Medium | Add a global daily request or token budget. |
| R5 | The limiter's `_hits` dict grows without bound as new client keys appear. | Low | Evict stale keys periodically or use a bounded/TTL structure. |
| R6 | `DEMO_MODE=true` on a public deployment would expose tool traces and API docs. | Low (config) | Keep it off in production; consider failing startup or warning loudly when it is on in a non-local environment. |

## Not covered

- Dynamic testing (Strix or manual runtime probing), including live prompt-injection attempts against `/api/chat`. Running it needs explicit authorization, the app running locally with `DEMO_MODE` off, a budget cap, and acceptance that it spends real API credit.
- Infrastructure and hosting configuration beyond the Dockerfile.

## Resolution

Fixed in the commit following this report (`fix(security): ...`), decided in the chat workflow:

| Finding | Resolution |
|---|---|
| Bandit B105 / B608 false positives | Line-level `# nosec` with the justification in a comment above each |
| Phone masking missed `+55`, spaces and dots | Broader regex; tests cover five formats and confirm prices are not masked |
| Rate limit behind a proxy sees the proxy IP | Uvicorn `proxy_headers` with `FORWARDED_ALLOW_IPS`, set per deployment |
| No global spend cap | Global daily cap of 500 chat messages (HTTP 429) |
| Limiter `_hits` grows unbounded | Stale keys pruned when tracking more than 10,000 clients |
| `DEMO_MODE=true` in production | Warning logged at startup when demo mode is on |
| No per-order attempt limit | Accepted risk: the e-mail/phone space makes brute force impractical under the existing per-session (30) and per-IP (20/min) limits |

While fixing, the tests caught a bug introduced by the fix itself: giving the limiter a `__len__` made an empty limiter falsy, so `limiter or default` silently replaced injected limiters. Defaults now use `is None`.
