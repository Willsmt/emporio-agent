"""Run evaluation scenarios or record example conversations against the configured LLM.

    python -m emporio.evaluation            # run all scenarios, write evals/report.md
    python -m emporio.evaluation --only black_friday
    python -m emporio.evaluation --conversations   # write conversations/*.md
"""
import argparse
import dataclasses
import sys
from datetime import date, datetime
from pathlib import Path

from emporio.agent.factory import build_agent
from emporio.agent.providers import ProviderError
from emporio.config import PROJECT_ROOT
from emporio.evaluation.checks import evaluate
from emporio.evaluation.scenarios import CONVERSATIONS, SCENARIOS, Conversation, Scenario
from emporio.settings import Settings, SettingsError, load_settings

REPORT_PATH = PROJECT_ROOT / "evals" / "report.md"
GLOBAL_EXCLUDES = (r"equipe humana|time humano|atendente humano",)  # persona: the assistant speaks as the store
CONVERSATIONS_DIR = PROJECT_ROOT / "conversations"


def run_turns(settings: Settings, turns: tuple[str, ...], store_today: date | None) -> list[dict]:
    """Run a conversation and return one record per turn: user text, reply and tools used."""
    if store_today:
        settings = dataclasses.replace(settings, store_today=store_today)
    agent = build_agent(settings)
    history: list = []
    records = []
    for user_text in turns:
        reply = agent.run(history, user_text)
        records.append({"user": user_text, "reply": reply.text, "trace": reply.tool_trace})
    return records


STATUS_ICONS = {"pass": "✅", "fail": "❌", "error": "⚠️"}


def run_scenario(settings: Settings, scenario: Scenario) -> dict:
    """Status is "pass"/"fail" for the agent's behavior, or "error" when the provider failed (quota, outage)."""
    try:
        records = run_turns(settings, scenario.turns, scenario.store_today)
    except ProviderError as exc:
        return {"scenario": scenario, "status": "error", "failures": [f"provider error: {str(exc)[:200]}"], "records": []}
    tools_used = [step["tool"] for record in records for step in record["trace"]]
    checks = dataclasses.replace(scenario.checks, reply_excludes=scenario.checks.reply_excludes + GLOBAL_EXCLUDES)
    result = evaluate(checks, tools_used, records[-1]["reply"])
    status = "pass" if result.passed else "fail"
    return {"scenario": scenario, "status": status, "failures": result.failures, "records": records}


def summarize(results: list[dict]) -> str:
    counts = {status: sum(r["status"] == status for r in results) for status in STATUS_ICONS}
    return f"{counts['pass']}/{len(results)} passed, {counts['fail']} failed, {counts['error']} provider errors"


def format_trace(trace: list[dict]) -> str:
    return ", ".join(f"`{step['tool']}({step['arguments']})`" for step in trace) or "—"


def write_report(settings: Settings, results: list[dict]) -> Path:
    lines = [
        "# Behavioral evaluation report",
        "",
        f"- Model: `{settings.provider}/{settings.model}`",
        f"- Run at: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        f"- Result: **{summarize(results)}**",
        "",
        "LLM output is non-deterministic: this is a sample run, not a guarantee. Checks are regex-based and "
        "accent-insensitive; tool checks use the agent's tool trace. ⚠️ marks provider errors (quota, outage), "
        "which say nothing about the agent's behavior.",
        "",
        "| Scenario | Description | Result | Tools used |",
        "|---|---|---|---|",
    ]
    for r in results:
        trace = [step for record in r["records"] for step in record["trace"]]
        lines.append(f"| `{r['scenario'].id}` | {r['scenario'].description} | {STATUS_ICONS[r['status']]} | {format_trace(trace)} |")
    failed = [r for r in results if r["status"] != "pass"]
    if failed:
        lines += ["", "## Failures and errors", ""]
        for r in failed:
            reply = r["records"][-1]["reply"] if r["records"] else "(no reply)"
            lines += [f"### `{r['scenario'].id}`", "", *[f"- {f}" for f in r["failures"]], "", "Reply:", "", f"> {reply.replace(chr(10), chr(10) + '> ')}", ""]
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return REPORT_PATH


def write_conversation(settings: Settings, conversation: Conversation) -> Path:
    records = run_turns(settings, conversation.turns, conversation.store_today)
    lines = [
        f"# {conversation.title}",
        "",
        f"> {conversation.why}",
        "",
        f"- Model: `{settings.provider}/{settings.model}`",
        f"- Recorded at: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
    ]
    if conversation.store_today:
        lines.append(f"- Simulated store date: {conversation.store_today.isoformat()} (`STORE_TODAY`)")
    lines += ["", "---", ""]
    for record in records:
        lines += [f"**Cliente:** {record['user']}", ""]
        if record["trace"]:
            lines += [f"*Tools: {format_trace(record['trace'])}*", ""]
        lines += [f"**Mel:** {record['reply']}", "", "---", ""]
    CONVERSATIONS_DIR.mkdir(parents=True, exist_ok=True)
    path = CONVERSATIONS_DIR / f"{conversation.slug}.md"
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--only", nargs="*", help="scenario ids to run")
    parser.add_argument("--conversations", action="store_true", help="record example conversations instead")
    args = parser.parse_args(argv)
    try:
        settings = load_settings()
    except SettingsError as exc:
        print(f"Configuration error: {exc}")
        return 1

    if args.conversations:
        for conversation in CONVERSATIONS:
            print(f"recording {conversation.slug} ...", flush=True)
            print(f"  -> {write_conversation(settings, conversation)}")
        return 0

    selected = [s for s in SCENARIOS if not args.only or s.id in args.only]
    results = []
    try:
        for scenario in selected:
            result = run_scenario(settings, scenario)
            print(f"{result['status'].upper():5} {scenario.id}  {'; '.join(result['failures'])}", flush=True)
            results.append(result)
    except KeyboardInterrupt:
        print("\nInterrupted: writing a partial report.")
    path = write_report(settings, results)
    print(f"\n{summarize(results)} — report: {path}")
    return 0 if results and all(r["status"] == "pass" for r in results) else 2


if __name__ == "__main__":
    sys.exit(main())
