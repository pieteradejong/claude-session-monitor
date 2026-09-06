#!/usr/bin/env python3
"""Read-only local dashboard for Claude Code session state.

Reads the session registry under ~/.claude/sessions and serves it as JSON.
Never writes to ~/.claude. Binds to loopback only -- the data includes local
filesystem paths and should not leave the machine.
"""

import argparse
import calendar
import glob
import json
import os
import subprocess
import time
from http.server import BaseHTTPRequestHandler, HTTPServer

CLAUDE_DIR = os.path.expanduser("~/.claude")
SESSIONS_DIR = os.path.join(CLAUDE_DIR, "sessions")
HERE = os.path.dirname(os.path.abspath(__file__))

# Sort order for the dashboard: what needs you, then what is running, then the rest.
STATUS_RANK = {"waiting": 0, "busy": 1, "idle": 2}


def process_table():
    """Map of pid -> process start time (epoch seconds, UTC).

    One `ps` call rather than one per candidate pid: the registry can hold
    hundreds of entries and per-pid subprocesses would dominate the scan.

    `ps` renders lstart in the local timezone while the registry records
    procStart in UTC, so we force ps into UTC and compare epochs rather than
    strings -- otherwise every session looks dead outside UTC+0.
    """
    try:
        out = subprocess.run(
            ["ps", "-eo", "pid=,lstart="],
            capture_output=True, text=True, timeout=5,
            env={**os.environ, "TZ": "UTC"},
        ).stdout
    except (OSError, subprocess.SubprocessError):
        return {}

    table = {}
    for line in out.splitlines():
        pid_str, _, lstart = line.strip().partition(" ")
        try:
            table[int(pid_str)] = _epoch(lstart)
        except ValueError:
            continue
    return table


def _epoch(stamp):
    """Parse a `ps`-style 'Sun Sep  6 13:29:34 2026' stamp as UTC epoch seconds."""
    if not stamp:
        return None
    try:
        return calendar.timegm(time.strptime(" ".join(str(stamp).split()),
                                             "%a %b %d %H:%M:%S %Y"))
    except (ValueError, TypeError):
        return None


def is_live(entry, table):
    """True if this registry entry refers to a process that is still running.

    Existence alone is not enough. Pids are recycled, so a dead session's pid
    may now belong to an unrelated process; comparing the recorded start time
    against the live one is what rules that out. A couple of seconds of slack
    absorbs the sub-second rounding between the two sources.
    """
    pid = entry.get("pid")
    if not isinstance(pid, int) or pid not in table:
        return False

    recorded, actual = _epoch(entry.get("procStart")), table[pid]
    if recorded is None or actual is None:
        return True  # nothing to verify against; existence is the best we have
    return abs(recorded - actual) <= 2


def scan():
    """Return (live_sessions, stale_count). Malformed files are skipped."""
    table = process_table()
    live, stale = [], 0

    for path in glob.glob(os.path.join(SESSIONS_DIR, "*.json")):
        try:
            with open(path) as fh:
                entry = json.load(fh)
        except (json.JSONDecodeError, OSError, UnicodeDecodeError):
            # Sessions rewrite these files continuously, so a read can land
            # mid-write. One bad file must never abort the scan.
            continue
        if not isinstance(entry, dict):
            continue

        if is_live(entry, table):
            live.append({
                "pid": entry.get("pid"),
                "name": entry.get("name") or "(unnamed)",
                "status": entry.get("status") or "unknown",
                "needs": entry.get("needs"),
                "cwd": entry.get("cwd") or "",
                "startedAt": entry.get("startedAt"),
                "updatedAt": entry.get("updatedAt"),
                "version": entry.get("version"),
            })
        else:
            stale += 1

    live.sort(key=lambda s: (STATUS_RANK.get(s["status"], 9), s["name"].lower()))
    return live, stale


class Handler(BaseHTTPRequestHandler):
    def _send(self, code, body, content_type):
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        path = self.path.split("?", 1)[0]

        if path == "/api/sessions":
            live, stale = scan()
            payload = {
                "sessions": live,
                "counts": {
                    "live": len(live),
                    "stale": stale,
                    "waiting": sum(1 for s in live if s["status"] == "waiting"),
                    "busy": sum(1 for s in live if s["status"] == "busy"),
                },
                "scannedAt": int(time.time() * 1000),
            }
            self._send(200, json.dumps(payload).encode(), "application/json")
            return

        if path in ("/", "/index.html"):
            try:
                with open(os.path.join(HERE, "index.html"), "rb") as fh:
                    self._send(200, fh.read(), "text/html; charset=utf-8")
            except OSError:
                self._send(500, b"index.html not found", "text/plain")
            return

        self._send(404, b"not found", "text/plain")

    def log_message(self, *args):
        pass  # the polling loop would otherwise print a line every 2s


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--port", type=int, default=8787)
    ap.add_argument("--host", default="127.0.0.1",
                    help="loopback by default; exposing this publishes local paths")
    args = ap.parse_args()

    if not os.path.isdir(SESSIONS_DIR):
        raise SystemExit(f"no session registry at {SESSIONS_DIR} -- is Claude Code installed?")

    print(f"claude-session-monitor -> http://{args.host}:{args.port}  (ctrl-c to stop)")
    try:
        HTTPServer((args.host, args.port), Handler).serve_forever()
    except KeyboardInterrupt:
        print()


if __name__ == "__main__":
    main()
