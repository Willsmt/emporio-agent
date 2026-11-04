---
name: cyclomatic-complexity
description: Measures and interprets cyclomatic complexity and maintainability with radon. Use when auditing Python code quality, deciding what to refactor, reviewing a diff before a commit or PR, or when asked about "complexity", "radon", "code too complex" or "refactor a large function".
---

# Cyclomatic complexity with radon

Cyclomatic complexity (CC) counts the independent paths through each function or method. High complexity means
more test cases needed, more room for bugs and code that is harder to change. This skill runs
[radon](https://radon.readthedocs.io), turns its output into a prioritized report and provides a CI gate.

## When to use
- Quality audit or technical-debt survey.
- Before refactoring: find **what** to refactor first.
- Diff/PR review: make sure a change did not make complexity worse.
- After a large feature (tools, agent loop, web handlers).

## Installation
radon is a dev dependency of this project (`pip install -e ".[dev]"`). The script finds it on its own, in this
order: `$RADON` → `.venv/bin/radon` → `.venv/bin/python -m radon` → `radon` on PATH → `uvx radon`. If none exists,
it fails with install instructions (exit code 2).

## Usage
Always from the project root:

```bash
# Full report (src/)
.claude/skills/cyclomatic-complexity/scripts/check_complexity.sh

# One package
.claude/skills/cyclomatic-complexity/scripts/check_complexity.sh src/emporio/tools

# Only what changed against the base branch — ideal for PR review
.claude/skills/cyclomatic-complexity/scripts/check_complexity.sh --changed origin/main

# List everything, including rank B, and save as Markdown
.claude/skills/cyclomatic-complexity/scripts/check_complexity.sh \
    --min-rank B --top 0 --markdown docs/complexity-report.md
```

If the `.sh` is not executable, call `python .claude/skills/cyclomatic-complexity/scripts/complexity_report.py`.

### Main flags
| Flag | Effect |
| --- | --- |
| `--min-rank {A..F}` | Minimum rank listed in the table (default `C`). |
| `--fail-on {A..F}` | Rank that makes the command exit 1 (default `D`, i.e. CC >= 21). |
| `--changed REF` | Only `.py` files changed against `REF` (via `git diff`). |
| `--baseline FILE` | Only fail on **new** or **worsened** blocks since the baseline. |
| `--update-baseline` | Write the current state as the baseline and exit 0. |
| `--mi-threshold N` | List files with a maintainability index below `N` (default 20). |
| `--top N` | Maximum table rows; `0` shows all (default 25). |
| `--markdown F` / `--json F` | Write the report / the raw data. |
| `--ignore a,b` | Ignored directories (default excludes `.venv`, `data`, `graphify-out`, caches). |

Exit codes: `0` clean · `1` threshold exceeded · `2` execution error.

## Rank scale
| Rank | CC | Reading | Action |
| --- | --- | --- | --- |
| A | 1–5 | Simple | None. |
| B | 6–10 | Well structured | None. |
| C | 11–20 | Slightly complex | Watch; refactor when touching the code. |
| D | 21–30 | High risk | Refactor — many paths to test. |
| E | 31–40 | Alarming | Refactor with priority. |
| F | 41+ | Design error | Split into smaller units now. |

The **maintainability index (MI)** is a separate per-file metric from 0 to 100 (Halstead volume, CC and lines).
MI < 20 means a file that is hard to maintain, usually from accumulated size and complexity.

## How to interpret and act
1. **Prioritize by risk, not by the number.** CC 25 in code that handles prices or customer data deserves more
   attention than CC 25 in a utility script.
2. **Cross with test coverage.** CC tells how many test cases a block needs; CC 22 with three tests is a gap.
3. **Do not chase the number.** Extracting six single-use helpers just to lower the rank scatters the logic and
   hurts readability. The goal is clearer code; the rank is the symptom.
4. **Ignore known false positives**: long `if/elif` dispatchers over event types and declarative configuration.

Refactoring patterns for each cause are in [references/refactoring-patterns.md](references/refactoring-patterns.md).

## Baseline for legacy code
On an existing codebase, `--fail-on D` may flag dozens of old blocks. A baseline freezes that debt so the gate only
blocks what is new:

```bash
.claude/skills/cyclomatic-complexity/scripts/check_complexity.sh --baseline .complexity-baseline.json --update-baseline
.claude/skills/cyclomatic-complexity/scripts/check_complexity.sh --baseline .complexity-baseline.json
```

Commit `.complexity-baseline.json` and run `--update-baseline` again after reducing complexity, to lock the gain.

## Raw radon commands
```bash
radon cc src -s -a -nc     # complexity, sorted, rank C+, with average
radon mi src -s            # maintainability index per file
radon raw src -s           # LOC, LLOC, comments
radon hal src              # Halstead metrics
radon cc src -j            # JSON (the format the script consumes)
```

## After refactoring
Running the report changes no code. Refactorings that result from it are code changes: run the `doc-sync` agent
as the last step (see `CLAUDE.md`).
