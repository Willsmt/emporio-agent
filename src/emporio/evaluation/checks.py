"""Pure assertion logic for evaluation scenarios (tested offline)."""
import re
from dataclasses import dataclass, field

from emporio.text import normalize


@dataclass(frozen=True)
class Checks:
    tools_called: tuple[str, ...] = ()
    tools_not_called: tuple[str, ...] = ()
    reply_matches: tuple[str, ...] = ()  # every regex must match the final reply
    reply_excludes: tuple[str, ...] = ()  # no regex may match the final reply


@dataclass
class CheckResult:
    passed: bool
    failures: list[str] = field(default_factory=list)


def evaluate(checks: Checks, tools_used: list[str], final_reply: str) -> CheckResult:
    """Compare accent- and case-insensitively, so 'indisponível' matches 'indisponivel'."""
    reply = normalize(final_reply)
    failures = []
    failures += [f"expected tool {t} to be called" for t in checks.tools_called if t not in tools_used]
    failures += [f"tool {t} must not be called" for t in checks.tools_not_called if t in tools_used]
    failures += [f"reply should match /{p}/" for p in checks.reply_matches if not re.search(normalize(p), reply)]
    failures += [f"reply must not match /{p}/" for p in checks.reply_excludes if re.search(normalize(p), reply)]
    return CheckResult(passed=not failures, failures=failures)
