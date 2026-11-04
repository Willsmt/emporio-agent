#!/usr/bin/env bash
# Shortcut to run the complexity analysis from the project root.
#
#   .claude/skills/cyclomatic-complexity/scripts/check_complexity.sh
#   .claude/skills/cyclomatic-complexity/scripts/check_complexity.sh src/emporio/tools
#   .claude/skills/cyclomatic-complexity/scripts/check_complexity.sh --changed origin/main
#
# All arguments are forwarded to complexity_report.py.
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../../../.." && pwd)"

if [[ -x "$PROJECT_ROOT/.venv/bin/python" ]]; then
  PY="$PROJECT_ROOT/.venv/bin/python"
elif [[ -x "$PROJECT_ROOT/venv/bin/python" ]]; then
  PY="$PROJECT_ROOT/venv/bin/python"
else
  PY="$(command -v python3 || command -v python)"
fi

cd "$PROJECT_ROOT" || exit 2
exec "$PY" "$SCRIPT_DIR/complexity_report.py" "$@"
