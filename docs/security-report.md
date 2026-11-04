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
- **XSS.** The static page escapes model output before assigning `innerHTML` and re-allows only `**bold**` and `<br>`. Customer text and the tool trace are rendered with `textContent`. No issue found. Later hardening (ADR-018): the pages no longer use inline scripts or styles, and a strict CSP is sent on `/`, `/chat` and `/static/*` (not on `/api/docs`, which needs a CDN script and inline code in `DEMO_MODE`).
- **Cost abuse.** Current limits: 1000 characters per message, 30 messages per session, 20 requests per minute per client IP, at most 500 sessions with a 30-minute TTL, and 6 agent steps per turn (raised to 8 later, see ADR-015). Gaps are listed under residual risks R1, R4 and R5.
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
| Rate limit behind a proxy sees the proxy IP | Uvicorn `proxy_headers` with `FORWARDED_ALLOW_IPS`, set per deployment (later replaced by `TRUSTED_PROXY_HOPS`, see addendum S1 and ADR-019) |
| No global spend cap | Global daily cap of 500 chat messages (HTTP 429) |
| Limiter `_hits` grows unbounded | Stale keys pruned when tracking more than 10,000 clients |
| `DEMO_MODE=true` in production | Warning logged at startup when demo mode is on |
| No per-order attempt limit | Accepted risk: the e-mail/phone space makes brute force impractical under the existing per-session (30) and per-IP (20/min) limits |

While fixing, the tests caught a bug introduced by the fix itself: giving the limiter a `__len__` made an empty limiter falsy, so `limiter or default` silently replaced injected limiters. Defaults now use `is None`.


## Addendum — store front and CSP (ADR-017, ADR-018)

**Date:** 2026-11-04. **Mode:** report only (no code changed, no dynamic testing, Strix not run).

**Scope:** commits `6da152d` (store front, ADR-017) and `48552b5` (HTML/CSS/JS split and strict CSP, ADR-018), reviewed with `git diff ab26879..HEAD`. Files read in full: `src/emporio/web/app.py`, `storefront.py`, `__main__.py`, `rate_limit.py`, `static/store.html`, `static/index.html`, `static/js/store.js`, `static/js/chat.js`, both SVGs, `Dockerfile`, the `ci.yml` and `pyproject.toml` diffs, ADR-017 and ADR-018. Also checked the installed uvicorn source for proxy-header behavior.

### Tools run

| Tool | Version | Command | Result |
|---|---|---|---|
| Bandit | 1.9.4 | `bandit -r src -q` | 0 issues. One warning only: `# nosec B105` at `src/emporio/evaluation/runner.py:39` has no failing test on that line (the existing nosec is now redundant, harmless). |
| Semgrep | 1.178.0 | `semgrep scan --config p/python --config p/security-audit --config p/javascript --metrics=off --exclude .venv --exclude data/processed src` | 288 rules on 46 files (JS included): 0 findings. |
| pip-audit | 2.10.1 | `pip-audit --skip-editable` | No known vulnerabilities (the editable `emporio-agent` is skipped, as expected). |

### Findings

| ID | Severity | Title | Evidence | Recommendation |
|---|---|---|---|---|
| S1 | Medium | `FORWARDED_ALLOW_IPS=*` lets a client spoof its IP and bypass the per-IP rate limit | `README.md:44`, `src/emporio/web/__main__.py:39-40`, `src/emporio/web/app.py:80-83` | Do not use `*`; trust only the proxy address range, or key the limiter on a platform header |
| S2 | Low | `postMessage` handlers check `origin` but not `source` | `src/emporio/web/static/js/chat.js:102-105`, `src/emporio/web/static/js/store.js:24-28` | Add `e.source === window.parent` (chat) and `e.source === frame.contentWindow` (store) |
| S3 | Low | `/api/storefront` is uncached, runs a full product scan per call, and shares the chat's per-IP budget | `src/emporio/web/app.py:122-128`, `src/emporio/web/storefront.py:50-52`, `src/emporio/tools/db.py:11` | Cache the payload for a short TTL (for example 30-60 s); consider a separate limiter bucket |
| S4 | Low | Missing defense-in-depth headers; API/JSON responses carry none | `src/emporio/web/app.py:35-39`, `:53-59` | Add `Permissions-Policy`, `Cross-Origin-Opener-Policy`, `X-Content-Type-Options` on all responses; HSTS at the TLS terminator |
| S5 | Low (demo only) | `/api/docs` in `DEMO_MODE` has no CSP or framing protection, and the README deploys with `DEMO_MODE=true` | `src/emporio/web/app.py:31-34`, `:57`, `README.md:44` | Accept for the demo; keep `DEMO_MODE` off in production; optionally add `frame-ancestors 'self'` / `X-Frame-Options` to docs |
| S6 | Info | CSP has two loose spots: `img-src data:` is unused, no `upgrade-insecure-requests` | `src/emporio/web/app.py:32` | Drop `data:` if nothing needs it; optional `upgrade-insecure-requests` |

### Finding details

**S1 (Medium).** The README deploy command sets `FORWARDED_ALLOW_IPS=*`. With `*`, uvicorn 0.54.0 trusts every peer and takes the **leftmost** `X-Forwarded-For` entry (`uvicorn/middleware/proxy_headers.py`, `get_trusted_client_address`, `always_trust` branch). That entry is client-controlled, so an attacker sends a new fake IP per request and `request.client.host` (`app.py:81`) changes each time, defeating the 20 requests/min limit on `/api/sessions`, `/api/chat` and `/api/storefront`. Cost stays bounded by the global daily cap (500 messages, `app.py:107`) and 30 messages per session, so impact is capped, but one attacker can exhaust the whole day's budget in minutes and lock out real customers. It also lets the limiter's `_hits` map churn up to its 10,000-key prune threshold. Fix: set `FORWARDED_ALLOW_IPS` to the proxy's address or CIDR (Cloud Run front-end ranges are not static, so a platform header such as the right-most `X-Forwarded-For` entry added by Google is the safer key), and update the README, `.env.example` and CLAUDE.md wording that suggests `*`.

**S2 (Low).** `chat.js:103` accepts any same-origin message with a string `ask` and submits it as a customer message; `store.js:25` accepts any same-origin `ready: true`. Neither checks `e.source`. Because `e.origin` must equal `location.origin`, a cross-origin page cannot reach these handlers (sandboxed frames report origin `"null"` and are rejected), so this is only reachable by other same-origin script, which would already be XSS. Tightening `source` is cheap hardening. No `"*"` targetOrigin is used anywhere: all sends use `location.origin` (`store.js:19`, `:27`; `chat.js:119`).

**S3 (Low).** Each call to `/api/storefront` executes `PRODUCT_QUERY` over the whole `products` table, builds summaries in Python and runs `_policy_field` (`storefront.py:18-21`, `:50-52`, `:55-74`). The catalog is small and the limiter applies (`app.py:125`), so the cost is low, but there is no caching or `Cache-Control`. The endpoint uses the same limiter as chat, so a page load (storefront call plus `/api/sessions` when the widget opens) consumes the same 20/min budget; behind a shared-IP proxy this couples browsing to chat availability. It also reuses a single SQLite connection across threadpool workers (`__main__.py:22`, `db.py:11`, `check_same_thread=False`); this is read-only and the module documents it, and `/health` is unlimited. The connection is never explicitly closed (process lifetime). Fix: memoize `build_storefront` with a short TTL (keyed on the store-time minute because of the open/closed label).

**S4 (Low).** The middleware sets CSP, `nosniff` and `Referrer-Policy` only on `/`, `/chat` and `/static/*` (`app.py:57`). JSON responses (`/api/*`, `/health`) get no `X-Content-Type-Options`; they are `application/json`, so sniffing risk is negligible. Not set anywhere: `Strict-Transport-Security` (should come from the TLS terminator such as Cloud Run, but verify), `Permissions-Policy`, `Cross-Origin-Opener-Policy` (the app does not use `window.open`, so `same-origin` is safe), `X-Frame-Options` (redundant with `frame-ancestors 'self'` for current browsers). No `Cache-Control` on `/api/storefront` or the HTML.

**S5 (Low, demo only).** `/api/docs` and `/api/openapi.json` exist only with `DEMO_MODE`, and Swagger UI loads scripts and CSS from a CDN with an inline bootstrap script, so excluding them from the strict CSP is an acceptable trade-off: the alternative is a looser global policy. The real risk is a third-party CDN script (supply chain) running on the app's origin in a deployment that, per the README, runs with `DEMO_MODE=true` publicly; that origin holds no cookies or credentials (sessions are bearer ids in JS memory), which limits the impact to the demo chat itself. Residual: the docs page can be framed by other sites (clickjacking of "Try it out" calls that spend API credit, still limited by the rate limits). Keep `DEMO_MODE` off in production (already R6).

**S6 (Info).** `img-src 'self' data:` allows `data:` images; all images are served files (`/static/mel_*.svg`), so `data:` is unneeded. No script or style bypass found: `script-src 'self'` and `style-src 'self'` have no `unsafe-inline`, no `unsafe-eval`, no wildcard or CDN host, and there are no JSONP or user-uploaded script endpoints on the origin that could be used as a script gadget (the only same-origin JS is the two files in `static/js/`; `/api/*` returns JSON with a JSON content type and `nosniff` is not needed for script execution because `script-src` plus MIME checking applies to `<script src>`).

### Triage of tool output

| Tool item | Verdict | Reason |
|---|---|---|
| Bandit: `nosec B105` unused warning (`runner.py:39`) | Accepted (noise) | Pre-existing suppression of the `"pass"` dict key; no issue is hidden. |
| Bandit: any issue | None reported | Nothing to triage. |
| Semgrep: any finding | None reported | 288 Python, JS and multilang rules, 0 findings (including no `innerHTML`/`document.write`/`postMessage` wildcard hits). |
| pip-audit | None reported | No vulnerable dependency; editable project skipped by design. |

Note on tool coverage: the one `innerHTML` assignment with data (`chat.js:25`) was not flagged by Semgrep; manual review (below) confirms it is safe.

### Checked and fine

- **Storefront fields (`storefront.py:55-74`):** only name, address, phone, hours, category names with counts, and at most 6 promotions (`product_id`, name, category, promotion label, percent, list and sale price). No cost, SKU, stock quantity, status or description. Unavailable items are filtered out (`:52`). The product ids and prices are already public through the chat and `search_products`.
- **Storefront and contact data:** address and phone come from the curated public policy table; no customer or order data is reachable from this endpoint (it never calls the agent or `orders`).
- **Storefront rate limiting:** it does call `check_rate_limit` (`app.py:125`), the same limiter as chat, before doing any work.
- **No `"*"` targetOrigin:** every `postMessage` send targets `location.origin` (`store.js:19`, `:27`; `chat.js:119`).
- **Hostile framing:** `frame-ancestors 'self'` (`app.py:33`) blocks cross-origin framing of `/` and `/chat`, so a hostile page cannot embed the chat to inject messages or read replies; the store's own iframe (`/chat?embed=1`, same origin) still works. The `embed` parameter only adds a CSS class (`chat.js:1`).
- **Opener attacks:** a hostile page opening `/chat` in a window cannot post `ask` messages, because `e.origin` would differ from `location.origin`. Replies are never sent out through `postMessage` (only `{ready: true}` goes to the parent).
- **Iframe `ready` handshake:** carries no data; at worst a same-origin script flips the `ready` flag early.
- **DOM rendering, store page (`store.js`):** all API data goes through `textContent` (`el()` helper, `:3`, `:42-66`); no `innerHTML`, no `href`/`src` built from data, no `eval` or string timers. The `data-ask` text is derived from catalog names and sent as a chat message, not as HTML.
- **DOM rendering, chat (`chat.js`):** `renderSafe` escapes `&`, `<`, `>`, `"` first (`:17`) and then adds only `<strong>` and `<br>` (`:18`); the `**…**` capture sits inside already-escaped text and cannot form attributes or tags. Customer text, errors, trace and model name use `textContent` (`:30`, `:34`, `:40`, `:115`). No links or images are produced from LLM output. The other `innerHTML` uses are constant empty strings (`:58`, `:66`).
- **CSP directives:** `default-src 'self'`, `script-src 'self'`, `style-src 'self'`, `connect-src 'self'`, `frame-src 'self'`, `base-uri 'none'` (blocks base-tag injection), `form-action 'self'`, `object-src 'none'` all present and tight. JS `element.style.display` (`store.js:71`, `chat.js:114`) is CSSOM and is not blocked by `style-src`.
- **No inline code:** `store.html` and `index.html` have no inline `<script>`, `<style>`, `style=` or `on*=`; both load only `/static/` files (also covered by tests in `tests/test_web.py`).
- **SVGs:** `mel_hero.svg` and `mel_icon.svg` contain no `<script>`, `href`, `xlink`, `foreignObject` or event handlers; they load via `<img>` (scripts would not run there) and `/static/*` carries the CSP if opened directly.
- **Static serving:** `StaticFiles(directory=STATIC_DIR)` (`app.py:139`) serves only the static folder (no stray files, no directory listing, path traversal handled by Starlette).
- **Docs exposure outside demo mode:** `docs_url` and `openapi_url` are `None` unless `demo_mode` (`app.py:71`); the CI smoke test asserts `/api/docs` returns 404.
- **Existing controls unchanged:** message length (1000, `app.py:44`; `chat.js:104` also slices to 1000), 30 messages per session, global 500/day cap and the agent, prompt and tools are untouched by these commits.
- **CI and packaging:** the `ci.yml` changes only add smoke-test `curl` assertions (CSP header, storefront, chat page); no new secrets, permissions or third-party actions. `pyproject.toml` only adds the CSS/JS package-data globs. Dockerfile: non-root uid 10001, DB built at image time, no `.env` copied; unchanged by the diff.
- **Proxy-header change (`__main__.py:35-41`):** the default `127.0.0.1` is safe; the issue is only the documented `*` setting (S1).
- **Prompt injection from the new surface:** the `ask` strings are built from catalog data in the store page and from the same-origin check; they reach the model exactly as typed customer text would, with the existing limits.

### Next steps (need approval)

1. Fix S1: change the README deploy command and guidance for `FORWARDED_ALLOW_IPS`, and decide the client-IP source for Cloud Run.
2. Optional hardening: S2 (`e.source` checks), S3 (TTL cache, separate limiter bucket), S4/S6 (extra headers, drop `data:`).
3. Dynamic verification of the rate-limit bypass (S1) and of the framing and CSP behavior in a browser needs explicit authorization, a local run with `DEMO_MODE` off, and a budget cap.

### Resolution

**Date:** 2026-11-04. Decided with the maintainer; recorded in ADR-019.

| Finding | Status | Resolution and evidence |
|---|---|---|
| S1 | Fixed | `FORWARDED_ALLOW_IPS` and uvicorn `proxy_headers` removed (`proxy_headers=False`). New `TRUSTED_PROXY_HOPS` (integer >= 0, default 0, invalid value stops startup); `client_ip` in `web/app.py` uses the socket peer for 0 hops, otherwise the N-th `X-Forwarded-For` entry from the right (Cloud Run appends the real client IP last, so the deploy uses `1`). Tests: `test_client_ip` (0 hops, spoofed leading entries, missing/empty header, fewer entries than hops, whitespace), `test_rate_limit_keys_on_last_forwarded_entry_behind_one_proxy` (limit 2/min: changing the first entry gives 201, 201, 429; a different last entry is a new client), `test_trusted_proxy_hops` and `test_invalid_trusted_proxy_hops_is_a_configuration_error`. README deploy command, CLAUDE.md and `.env.example` updated. Live verification (2026-11-04, Cloud Run revision emporio-agent-00005, TRUSTED_PROXY_HOPS=1): 21 POST /api/sessions requests from one machine, each with a different spoofed X-Forwarded-For value (10.0.0.1 to 10.0.0.21), returned 201 twenty times and 429 on the 21st, so the spoofed values were ignored and all requests counted as one client. Within the same minute, while that machine was still rate limited, a phone on a different network opened the demo and created a session normally, so different clients keep separate limits. Before the fix, the spoofed header would have given each request a fresh limit. |
| S2 | Fixed | `chat.js` also requires `e.source === window.parent` (and that the page is framed); `store.js` also requires `frame && e.source === frame.contentWindow`. Headless Chrome: a same-origin `{ready: true}` posted by the store page to itself and a same-origin `{ask}` posted by top-level `/chat` to itself are both ignored, while the real store-to-widget question still gets an answer. |
| S3 | Accepted | The storefront read is cheap (small catalog, read-only SQLite) and already rate limited; a page load uses 2 of the 20 requests/min (`/api/storefront` plus `/api/sessions` when the widget opens). No cache or separate bucket for now. |
| S4 | Fixed (partial) | `X-Content-Type-Options: nosniff` on every response, including `/api/*` and `/health`; `Permissions-Policy: camera=(), microphone=(), geolocation=()` and `Cross-Origin-Opener-Policy: same-origin` on `/`, `/chat` and `/static/*`. Tests: `test_every_response_is_nosniff_but_only_pages_get_page_headers`, `test_pages_and_static_files_send_strict_csp`. HSTS is deliberately not set by the app: `*.run.app` is under the `.app` TLD, which is on the browsers' HSTS preload list, so HTTPS is already forced; another domain should set HSTS at its TLS terminator. `Cache-Control` and `X-Frame-Options` not added (the latter is covered by `frame-ancestors 'self'`). |
| S5 | Accepted | `/api/docs` is intentional and exists only in `DEMO_MODE`, for technical review; it stays off in production (R6). |
| S6 | Fixed (partial) | `data:` removed from `img-src`; test asserts it is absent. `upgrade-insecure-requests` not added (all resources are same-origin and the origin is HTTPS-only). Headless Chrome on `/` and `/chat` (store, widget open, question asked, chat page): zero CSP violations, console errors or failed loads. |

Verification: `pytest -q` 162 passed (coverage 85%), `bandit -r src -q` no issues, complexity gate passed (new `client_ip` CC 6, rank B).
