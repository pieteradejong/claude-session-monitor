#!/usr/bin/env bash
# test.sh — every check in one place. Exit 0 = green. `run.sh test` runs this script.
#   ./test.sh            compile server.py, --help smoke test, index.html present, shell syntax
#                        and shellcheck of the scripts, no tracked .env
#   ./test.sh --help     this text
set -euo pipefail
cd "$(dirname "$0")"
case "${1:-}" in -h|--help) sed -n '2,5p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;; esac

echo "== python"
python3 -c 'import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)' \
  || { echo "python3 >= 3.11 required" >&2; exit 1; }
python3 -m py_compile server.py

echo "== server --help (no files read, nothing served)"
python3 server.py --help >/dev/null

echo "== static page"
[ -f index.html ] || { echo "index.html missing" >&2; exit 1; }
for f in ./*.js; do [ -f "$f" ] && node --check "$f"; done

echo "== shell"
for f in ./*.sh; do bash -n "$f"; /bin/bash -n "$f"; done
if command -v shellcheck >/dev/null 2>&1; then shellcheck -S warning ./*.sh
else echo "shellcheck not installed — syntax-checked only (brew install shellcheck)"; fi

echo "== secrets"
tracked="$(git ls-files | grep -E '(^|/)\.env(\..+)?$' | grep -vE '\.env\.(example|template)$' || true)"
[ -z "$tracked" ] || { echo "tracked env files:"; echo "$tracked"; exit 1; }

echo "== all green"
