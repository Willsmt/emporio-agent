# Cyclomatic complexity report (radon)

- Blocks analyzed: **88**
- Average complexity: **3.23** (rank A)
- Distribution: A 76 · B 9 · C 2 · D 1
- Failure threshold: rank **D** (CC >= 21)

## Blocks ranked B or worse

| Rank | CC | Block | Location |
| --- | --- | --- | --- |
| D | 28 | `search_products` | `src/emporio/tools/catalog.py:54` |
| C | 12 | `main` | `src/emporio/evaluation/runner.py:117` |
| C | 11 | `GeminiProvider.parse_response` | `src/emporio/agent/providers/gemini.py:30` |
| B | 10 | `main` | `src/emporio/chat.py:12` |
| B | 10 | `write_report` | `src/emporio/evaluation/runner.py:64` |
| B | 9 | `evaluate` | `src/emporio/evaluation/checks.py:22` |
| B | 8 | `load_settings` | `src/emporio/settings.py:33` |
| B | 8 | `create_app` | `src/emporio/web/app.py:39` |
| B | 7 | `chat` | `src/emporio/web/app.py:71` |
| B | 6 | `OpenAIProvider.parse_response` | `src/emporio/agent/providers/openai_provider.py:31` |
| B | 6 | `get_order_status` | `src/emporio/tools/orders.py:40` |
| B | 6 | `SlidingWindowLimiter.allow` | `src/emporio/web/rate_limit.py:29` |

## Maintainability index below 20.0

No file below the threshold. ✅

## Gate result

❌ **1 violation** (rank >= D):

- `src/emporio/tools/catalog.py:54` — `search_products` → CC 28 (rank D)

## Refactoring plan

Scope: every block ranked C or worse in the table above. Patterns refer to
`.claude/skills/cyclomatic-complexity/references/refactoring-patterns.md`. No code was changed when this
report was written.

| Priority | Block | Rank (CC) | Verdict |
| --- | --- | --- | --- |
| 1 | `search_products` (`src/emporio/tools/catalog.py:54`) | D (28) | **Refactor** |
| 2 | `main` (`src/emporio/evaluation/runner.py:117`) | C (12) | Optional: only when the file is next touched |
| 3 | `GeminiProvider.parse_response` (`src/emporio/agent/providers/gemini.py:30`) | C (11) | **Do not refactor**: add a test instead |

### 1. `search_products` (D, CC 28): refactor

**Why first:** it is the only gate violation. It is also a customer-facing tool that the LLM calls on almost every
turn, and it applies the availability rule from policy 7.3 and the promotional-price filter. It mixes two separate
jobs in one function:

1. **Filtering** (a loop of four `if ...: continue` filters, plus the `available_only`/`hidden_matches` branch).
2. **Response annotation**: four independent post-processing steps (`note`, `unavailable_matches`, `hint`,
   unknown-category `error`), each with a compound condition.

**Patterns that apply:**
- **#7 Loops with filters → a pipeline of small predicates.** Extract `matches_terms(row, terms)` and
  `in_category(row, category_key)` as named predicates. The price and availability checks need the summarized
  product, so keep them in the loop or put them in a second predicate stage. Do **not** push the filtering to SQL:
  matching uses Python `normalize()`, and `max_price` is compared against the discounted price that
  `pricing.apply_discount` computes (invariant 1: price logic stays in the tested pricing module).
- **#4 Compound boolean conditions → named predicate**, combined with the "list of rules" idea from **#3**: move
  each response annotation into its own small function (`add_truncation_note`, `add_unavailable_matches`,
  `add_empty_hint`, `add_category_error`). `search_products` then just runs them in order. Each one is a cohesive
  rule from the manual or from the anti-hallucination prompts, so it can be tested on its own.
- Side fix while in there: the unknown-category branch calls `list_categories(conn)` twice. Fetch it once.

**Expected result:** `search_products` drops to rank A/B, and the helpers stay at A. Total CC barely changes
because the decisions are real; they just move to places with names (see the pattern #4 note).

**Safety net:** `tests/test_catalog.py` already has 16 tests that cover nearly every branch (truncation note,
promotional price vs. `max_price`, zero `max_price`, hidden matches, category browsing, unknown category, ignored
terms). Refactor without changing those tests. Any test that needs editing signals a behavior change. Keep the
order of the annotations: the unknown-category `error` is currently returned **together with** the empty-result
`hint`, and turning it into an early return would change what the model sees.

### 2. `runner.main` (C, CC 12): optional, low priority

**Why low:** this is an offline evaluation CLI (`python -m emporio.evaluation.runner`). It does not handle customer
data, prices or business rules. Its CC comes from argument handling, two run modes (`--conversations` vs.
scenarios), a `KeyboardInterrupt` handler and the exit-code expression. The individual steps it calls
(`run_scenario`, `write_report`, `write_conversation`, `summarize`) are already separate and tested in
`tests/test_evaluation.py`, but `main` itself has no direct test.

**Pattern that applies:** **#6 Fat handlers → service layer**, applied to a CLI entry point. Keep `main` thin
(parse args, load settings, pick a mode) and move each mode into its own function, such as
`record_conversations(settings)` and `run_scenarios(settings, only) -> int`. Pattern **#1 (guard clauses)** is
already in use for the settings error and the conversations mode.

**Verdict:** not worth a standalone change. Do it the next time the runner gains a flag or mode, and add a
`main([...])` test with a monkeypatched `run_scenario` so the exit codes (0/1/2) and the partial-report-on-interrupt
path get covered.

### 3. `GeminiProvider.parse_response` (C, CC 11): do not refactor

**Why:** the function is short (about 10 lines). Its CC comes from the `or` fallbacks and the comprehension filters
that translate the SDK's response shape: no candidates or no content, `parts or []`, skipping `thought` parts,
`function_call.id or f"call_{i}"`, `args or {}`. This complexity is part of the format being parsed.

**"When not to refactor" rule that applies:** *Parsers/state machines whose complexity is intrinsic to the format;
invest in edge-case tests instead.* Splitting it into helpers would scatter one cohesive translation, and the
code that handles Gemini thought signatures (invariant 4) is delicate.

**Action instead:** `tests/test_providers.py` covers function calls, the raw content being kept, and thought parts
being ignored. It does **not** cover the `ProviderError` path (no candidates, or `content is None`), the
`call_{i}` id fallback, or `args=None`. Add those edge-case tests. A short comment on the block is optional.

## Resolution

Applied in the commit following this report (`refactor(tools): ...`), following the refactoring plan above:

| Block | Before | After | Action |
|---|---|---|---|
| `search_products` | D (28) | A | Pattern 7: `SearchCriteria` + named predicates (`_matches_text`, `_in_category`, `_within_budget`) and one small function per response annotation. `list_categories` is now called once. The price filter stays in Python (it uses the promotional price) and says so in a comment. Largest block in the module is now B (9). |
| `GeminiProvider.parse_response` | C (11) | C (11) | Not refactored ("When not to refactor": parser of an external format). Two tests added for the uncovered paths: no content (`ProviderError`) and a call without id or args. |
| `runner.main` | C (12) | C (12) | Deferred: internal evaluation CLI with no business rules; refactor with a test when the file next changes. |

The existing unit tests passed unchanged after the refactor, which is the evidence that behavior was preserved. Gate result after the change: no block ranked D or worse.
