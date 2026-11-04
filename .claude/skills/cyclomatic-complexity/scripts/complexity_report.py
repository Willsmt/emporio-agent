#!/usr/bin/env python3
"""Run radon and turn its JSON output into a prioritized complexity report.

Wraps `radon cc` (cyclomatic complexity) and `radon mi` (maintainability index),
flattens classes/closures into a single list of blocks, ranks them, and applies
a configurable failure threshold. Supports a baseline file so an existing
codebase can be grandfathered in and only regressions fail the gate.

Exit codes: 0 = clean, 1 = threshold violated, 2 = execution error.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import typing
from pathlib import Path

RANK_BOUNDS = [
    ("A", 1, 5, "simple, low risk"),
    ("B", 6, 10, "well structured, low risk"),
    ("C", 11, 20, "slightly complex, moderate risk"),
    ("D", 21, 30, "more than complex, high risk"),
    ("E", 31, 40, "complex, alarming"),
    ("F", 41, 10**9, "design error, refactor now"),
]
RANK_ORDER = ["A", "B", "C", "D", "E", "F"]

DEFAULT_PATHS = ["src"]
DEFAULT_IGNORE = [
    ".venv",
    "venv",
    "data",
    "graphify-out",
    ".git",
    "__pycache__",
    ".pytest_cache",
]


def fail(message: str) -> "typing.NoReturn":
    """Abort with exit code 2 (execution error), distinct from 1 (gate failed)."""
    print(message, file=sys.stderr)
    sys.exit(2)


def rank_of(complexity: int) -> str:
    for rank, low, high, _ in RANK_BOUNDS:
        if low <= complexity <= high:
            return rank
    return "F"


def resolve_radon() -> list[str]:
    """Find a usable radon invocation, trying the project venv first."""
    env_radon = os.environ.get("RADON")
    if env_radon:
        return env_radon.split()

    root = Path(__file__).resolve().parents[4]
    for candidate in (root / ".venv/bin/radon", root / "venv/bin/radon"):
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return [str(candidate)]

    for python in (root / ".venv/bin/python", root / "venv/bin/python"):
        if python.is_file():
            probe = subprocess.run(
                [str(python), "-c", "import radon"], capture_output=True
            )
            if probe.returncode == 0:
                return [str(python), "-m", "radon"]

    on_path = shutil.which("radon")
    if on_path:
        return [on_path]

    if shutil.which("uvx"):
        return ["uvx", "radon"]
    if shutil.which("uv"):
        return ["uv", "tool", "run", "radon"]

    probe = subprocess.run([sys.executable, "-c", "import radon"], capture_output=True)
    if probe.returncode == 0:
        return [sys.executable, "-m", "radon"]

    fail(
        "radon not found. Install it with one of:\n"
        "  pip install -e \".[dev]\"   # this project's dev dependencies\n"
        "  .venv/bin/pip install radon\n"
        "  uvx radon cc src           # ephemeral run, nothing installed\n"
        "Or point the RADON variable to the executable."
    )


def run_radon(radon: list[str], sub: str, paths: list[str], ignore: list[str]) -> dict:
    cmd = [*radon, sub, "-j"]
    if ignore:
        cmd += ["-i", ",".join(ignore)]
    if sub == "cc":
        cmd += ["-s"]
    if sub == "mi":
        cmd += ["-m"]
    cmd += paths

    try:
        proc = subprocess.run(cmd, capture_output=True, text=True)
    except OSError as exc:
        fail(f"could not run radon ({' '.join(radon)}): {exc}")
    if not proc.stdout.strip():
        fail(
            f"radon {sub} returned no output (exit {proc.returncode}).\n"
            f"command: {' '.join(cmd)}\n{proc.stderr.strip()}"
        )
    try:
        return json.loads(proc.stdout)
    except json.JSONDecodeError:
        fail(f"radon {sub} output is not JSON:\n{proc.stdout[:500]}")


def flatten(path: str, entries: list[dict]) -> list[dict]:
    """Flatten radon cc entries, expanding class methods and closures."""
    blocks: list[dict] = []

    def walk(entry: dict) -> None:
        if entry.get("type") == "class":
            return
        name = entry.get("name", "?")
        classname = entry.get("classname")
        qualname = f"{classname}.{name}" if classname else name
        blocks.append(
            {
                "file": path,
                "name": qualname,
                "lineno": entry.get("lineno", 0),
                "endline": entry.get("endline", 0),
                "type": entry.get("type", "function"),
                "complexity": entry.get("complexity", 0),
                "rank": entry.get("rank") or rank_of(entry.get("complexity", 0)),
            }
        )
        for closure in entry.get("closures", []) or []:
            walk(closure)

    for entry in entries:
        walk(entry)
    return blocks


def collect_blocks(cc_data: dict) -> tuple[list[dict], list[str]]:
    blocks: list[dict] = []
    errors: list[str] = []
    for path, entries in cc_data.items():
        if isinstance(entries, dict) and "error" in entries:
            errors.append(f"{path}: {entries['error']}")
            continue
        blocks.extend(flatten(path, entries))
    return blocks, errors


def changed_files(ref: str) -> list[str]:
    proc = subprocess.run(
        ["git", "diff", "--name-only", "--diff-filter=ACMR", ref, "--", "*.py"],
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        fail(f"git diff failed against '{ref}': {proc.stderr.strip()}")
    return [f for f in proc.stdout.split() if Path(f).is_file()]


def key_of(block: dict) -> str:
    return f"{block['file']}::{block['name']}"


def build_report(blocks, mi_data, args, errors) -> tuple[str, list[dict]]:
    show_idx = RANK_ORDER.index(args.min_rank)
    fail_idx = RANK_ORDER.index(args.fail_on)

    baseline = {}
    if args.baseline and Path(args.baseline).is_file():
        baseline = json.loads(Path(args.baseline).read_text()).get("blocks", {})

    listed = sorted(
        (b for b in blocks if RANK_ORDER.index(b["rank"]) >= show_idx),
        key=lambda b: (-b["complexity"], b["file"], b["lineno"]),
    )

    violations = []
    for block in blocks:
        if RANK_ORDER.index(block["rank"]) < fail_idx:
            continue
        if args.baseline:
            previous = baseline.get(key_of(block))
            if previous is not None and block["complexity"] <= previous:
                continue  # grandfathered, and not worse than before
        violations.append(block)
    violations.sort(key=lambda b: -b["complexity"])

    counts = {rank: 0 for rank in RANK_ORDER}
    for block in blocks:
        counts[block["rank"]] += 1
    total = len(blocks)
    average = sum(b["complexity"] for b in blocks) / total if total else 0.0

    low_mi = sorted(
        (
            (path, info["mi"], info["rank"])
            for path, info in (mi_data or {}).items()
            if isinstance(info, dict) and "mi" in info and info["mi"] < args.mi_threshold
        ),
        key=lambda row: row[1],
    )

    out: list[str] = []
    out.append("# Cyclomatic complexity report (radon)")
    out.append("")
    out.append(f"- Blocks analyzed: **{total}**")
    out.append(f"- Average complexity: **{average:.2f}** (rank {rank_of(round(average) or 1)})")
    out.append(
        "- Distribution: "
        + " · ".join(f"{r} {counts[r]}" for r in RANK_ORDER if counts[r])
    )
    out.append(f"- Failure threshold: rank **{args.fail_on}** (CC >= {dict((r, lo) for r, lo, _, _ in RANK_BOUNDS)[args.fail_on]})")
    if args.baseline:
        state = "applied" if baseline else "missing (first run)"
        out.append(f"- Baseline: `{args.baseline}` — {state}")
    out.append("")

    out.append(f"## Blocks ranked {args.min_rank} or worse")
    out.append("")
    if not listed:
        out.append(f"No block ranked {args.min_rank} or worse. ✅")
    else:
        shown = listed[: args.top] if args.top else listed
        out.append("| Rank | CC | Block | Location |")
        out.append("| --- | --- | --- | --- |")
        for block in shown:
            out.append(
                f"| {block['rank']} | {block['complexity']} | `{block['name']}` "
                f"| `{block['file']}:{block['lineno']}` |"
            )
        if args.top and len(listed) > args.top:
            out.append("")
            out.append(f"_… and {len(listed) - args.top} more block(s). Use `--top 0` to list all._")
    out.append("")

    out.append(f"## Maintainability index below {args.mi_threshold}")
    out.append("")
    if not low_mi:
        out.append("No file below the threshold. ✅")
    else:
        out.append("| MI | Rank | File |")
        out.append("| --- | --- | --- |")
        for path, mi, rank in low_mi:
            out.append(f"| {mi:.1f} | {rank} | `{path}` |")
    out.append("")

    out.append("## Gate result")
    out.append("")
    if violations:
        plural = len(violations) > 1
        label = "violations" if plural else "violation"
        if args.baseline:
            label = "new " + label
        out.append(f"❌ **{len(violations)} {label}** (rank >= {args.fail_on}):")
        out.append("")
        for block in violations:
            out.append(
                f"- `{block['file']}:{block['lineno']}` — `{block['name']}` "
                f"→ CC {block['complexity']} (rank {block['rank']})"
            )
    else:
        out.append(f"✅ No block ranked {args.fail_on} or worse.")

    if errors:
        out.append("")
        out.append("## Files not analyzed")
        out.append("")
        for err in errors:
            out.append(f"- {err}")

    return "\n".join(out) + "\n", violations


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run radon and produce a prioritized cyclomatic complexity report."
    )
    parser.add_argument("paths", nargs="*", default=DEFAULT_PATHS,
                        help=f"paths to analyze (default: {' '.join(DEFAULT_PATHS)})")
    parser.add_argument("--min-rank", choices=RANK_ORDER, default="C",
                        help="minimum rank listed in the report (default: C)")
    parser.add_argument("--fail-on", choices=RANK_ORDER, default="D",
                        help="rank from which the command fails (default: D, CC >= 21)")
    parser.add_argument("--mi-threshold", type=float, default=20.0,
                        help="report files with a maintainability index below this (default: 20)")
    parser.add_argument("--top", type=int, default=25,
                        help="maximum rows in the blocks table; 0 = all (default: 25)")
    parser.add_argument("--ignore", default=",".join(DEFAULT_IGNORE),
                        help="comma-separated directories to ignore")
    parser.add_argument("--changed", metavar="REF",
                        help="analyze only .py files changed against REF (e.g. origin/main)")
    parser.add_argument("--baseline", metavar="FILE",
                        help="baseline file: only fail on new or worsened blocks")
    parser.add_argument("--update-baseline", action="store_true",
                        help="write/update the baseline with the current state and exit 0")
    parser.add_argument("--json", metavar="FILE", help="write the raw result as JSON")
    parser.add_argument("--markdown", metavar="FILE", help="write the report as Markdown")
    parser.add_argument("--no-mi", action="store_true", help="skip the maintainability index")
    args = parser.parse_args()

    paths = list(args.paths)
    if args.changed:
        paths = changed_files(args.changed)
        if not paths:
            print(f"No .py file changed against '{args.changed}'. ✅")
            return 0

    paths = [p for p in paths if Path(p).exists()]
    if not paths:
        fail("No valid path to analyze.")

    ignore = [i for i in args.ignore.split(",") if i]
    radon = resolve_radon()

    cc_data = run_radon(radon, "cc", paths, ignore)
    blocks, errors = collect_blocks(cc_data)
    mi_data = {} if args.no_mi else run_radon(radon, "mi", paths, ignore)

    if args.update_baseline:
        target = args.baseline or ".complexity-baseline.json"
        payload = {"blocks": {key_of(b): b["complexity"] for b in blocks}}
        Path(target).write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
        print(f"Baseline written to {target} ({len(payload['blocks'])} blocks).")
        return 0

    report, violations = build_report(blocks, mi_data, args, errors)
    print(report)

    if args.markdown:
        Path(args.markdown).write_text(report)
    if args.json:
        Path(args.json).write_text(
            json.dumps({"blocks": blocks, "mi": mi_data, "errors": errors}, indent=2) + "\n"
        )

    return 1 if violations else 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        sys.exit(130)
