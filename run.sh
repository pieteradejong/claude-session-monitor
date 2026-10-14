#!/usr/bin/env bash
# run.sh — entry points. Read-only dashboard over ~/.claude/sessions, loopback only.
#   ./run.sh [serve] [--port N]   serve http://127.0.0.1:8787 (default)
#   ./run.sh test                 every check (delegates to ./test.sh)
#   ./run.sh help                 this text
set -euo pipefail
cd "$(dirname "$0")"

cmd="${1:-serve}"
[ $# -gt 0 ] && shift
case "$cmd" in
  serve) exec python3 server.py "$@" ;;
  test)  exec ./test.sh "$@" ;;
  help|-h|--help) sed -n '2,5p' "$0" | sed 's/^# \{0,1\}//' ;;
  *) echo "unknown command: $cmd" >&2; sed -n '2,5p' "$0" | sed 's/^# \{0,1\}//' >&2; exit 2 ;;
esac
