#!/usr/bin/env bash
# init.sh — nothing to install: server.py is stdlib-only (Python 3.11+). Checks the interpreter.
#   ./init.sh            verify python3 >= 3.11; exit 0 = ready
#   ./init.sh --help     this text
set -euo pipefail
cd "$(dirname "$0")"
case "${1:-}" in -h|--help) sed -n '2,4p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;; esac

command -v python3 >/dev/null 2>&1 || { echo "python3 not found" >&2; exit 1; }
python3 -c 'import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)' \
  || { echo "python3 >= 3.11 required, found $(python3 --version)" >&2; exit 1; }
echo "python3 $(python3 --version | cut -d' ' -f2); nothing to install"
echo "ready: ./run.sh  (serves http://127.0.0.1:8787)"
