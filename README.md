# claude-session-monitor

A read-only local web dashboard for Claude Code session state. It answers one question
that nothing else currently answers: **which of my running sessions are blocked waiting
on me?**

If you use Claude Code across many projects, sessions accumulate. Each one is a live
process with a state — working, waiting for input, or idle — but that state is only
visible from inside the session itself. Once you have a dozen terminal tabs, the
information you actually need (*two of these are waiting on a prompt; the rest are fine
to ignore*) is invisible.

Claude Code already records everything needed to show this. It writes a small JSON
registry file per session to `~/.claude/sessions/`, including a `status` field and a
`needs` field describing what the session is blocked on. This tool reads those files,
discards the stale ones, and renders the result.

> **Status: working.** Verified against Claude Code `2.1.263` on macOS.

## Quick start

```sh
python3 server.py            # serves http://127.0.0.1:8787
python3 server.py --port 9000
```

No dependencies beyond the Python 3.11+ standard library. Nothing to install, no build
step, no `node_modules`.

## What it shows

Live sessions, grouped by status, most-urgent first:

| Field | Source | Notes |
|---|---|---|
| Name | `name` | Session's own label, derived or user-set |
| Status | `status` | `busy` / `waiting` / `idle` |
| Blocked on | `needs` | e.g. "send a prompt to start" — only set when waiting |
| Directory | `cwd` | Where the session was launched |
| Uptime | `startedAt` | Derived |
| Last activity | `updatedAt` | Derived |
| PID | `pid` | For matching against your terminal tabs |

Sort order puts `waiting` first, then `busy`, then `idle` — the dashboard should be
useful at a glance without scrolling.

## Data sources

All paths are read-only. **The tool never writes to `~/.claude`.**

| Path | Contains |
|---|---|
| `~/.claude/sessions/<pid>.json` | Session registry: `pid`, `sessionId`, `name`, `status`, `cwd`, `startedAt`, `updatedAt`, `version`, `procStart` |
| `~/.claude/jobs/<id>/state.json` | Background job state: `state`, `detail`, `tempo`, `inFlight {tasks, queued}`, `needs` |
| `~/.claude/daemon.status.json` | Supervisor PID and worker map |

A session registry file looks roughly like this (synthetic example):

```json
{
  "pid": 12345,
  "sessionId": "0000aaaa-0000-bbbb-0000-cccccccccccc",
  "cwd": "/path/to/a/project",
  "startedAt": 1788701375181,
  "procStart": "Sun Sep  6 13:29:34 2026",
  "name": "example-session",
  "status": "waiting",
  "version": "2.1.263"
}
```

## Architecture

A single-file stdlib HTTP server plus one static page.

```
server.py     scan() → filter dead PIDs → JSON at /api/sessions
index.html    fetches /api/sessions every 2s, re-renders the table
```

Roughly 250 lines total. The core of it is liveness filtering:

```python
def is_live(entry, table):
    pid = entry.get("pid")
    if not isinstance(pid, int) or pid not in table:
        return False
    recorded, actual = _epoch(entry.get("procStart")), table[pid]
    if recorded is None or actual is None:
        return True          # nothing to verify against
    return abs(recorded - actual) <= 2
```

`table` comes from a single `ps -eo pid=,lstart=` call run with `TZ=UTC`, parsed to
epoch seconds. One `ps` invocation, not one per pid.

**Design choices worth stating:**

- **Polling, not SSE or WebSockets.** The scan reads a few hundred small files and
  completes in milliseconds. A 2-second `fetch` loop is simpler and needs no reconnect
  logic.
- **Stdlib only.** This is a single-purpose local tool. Flask, Express, or a frontend
  build step would be more infrastructure than the problem deserves.
- **No database.** The filesystem is the state; there is nothing to persist.
- **No auth.** Justified *only* because it binds to loopback. See Privacy.

## Gotchas

These are the things that will actually break an implementation, discovered by reading
the real directory rather than assuming its shape.

1. **Registry files outlive their sessions.** Entries are not removed the moment a
   session exits, so between Claude Code's own periodic cleanups the directory can hold
   many times more dead entries than live ones — a ratio of roughly 9:1 was observed
   before a cleanup pass reduced it to zero. Filtering is the central logic of the scan,
   not an afterthought; a naive implementation reports wildly too many sessions, and its
   error varies with how recently cleanup ran.

2. **PID reuse is real and will produce false positives.** `kill -0` alone is not
   sufficient: the OS recycles PIDs, so a dead session's PID may now belong to an
   unrelated process, which would then be displayed as a live Claude session. The
   registry stores `procStart` (the process start timestamp) for precisely this reason —
   always cross-check it against `ps -o lstart= -p <pid>` before trusting a match.

3. **`procStart` is UTC; `ps` prints local time.** This is the bug that will silently
   break the liveness check everywhere except UTC+0, and it fails in the worst
   direction — *every* session looks dead, so the dashboard renders an empty page rather
   than an error. Do not compare the two as strings. Run `ps` with `TZ=UTC` in its
   environment, parse both sides to epoch seconds, and allow a couple of seconds of
   slack for rounding.

4. **`etimes` does not exist on macOS `ps`.** The elapsed-seconds column that would
   sidestep timezones entirely is a GNU/procps extension; BSD `ps` rejects it with
   `keyword not found`. Parse `lstart` instead.

5. **Files are written while you read them.** Sessions update their own registry entries
   continuously, so a read can land mid-write and yield truncated JSON. Wrap every
   `json.load` in `try`/`except (json.JSONDecodeError, OSError)` and skip the file. One
   malformed file must never abort the scan.

6. **These paths are internal and undocumented.** Verified against Claude Code
   `2.1.263`. The layout of `~/.claude/` is not a public API and may change without
   notice. Fail soft: if a directory is missing or a field is absent, degrade to showing
   less rather than crashing.

## Privacy

This tool reads files that contain personal data, which shapes two hard requirements.

- **Bind to `127.0.0.1` only — never `0.0.0.0`.** The `cwd` field exposes your full
  project layout, and `detail` in the job state files contains verbatim excerpts of
  conversation text. None of that should ever be reachable from the network.
- **Never commit captured output.** `.gitignore` covers scratch and output paths. Do not
  paste real scan results into issues, commits, or documentation — that includes session
  names, absolute home paths, and directory listings. Every example in this README is
  synthetic for exactly this reason.

The code itself contains no secrets and reads only well-known paths, which is why the
repository is public while its data stays local.

## Non-goals

- **Writing to `~/.claude`.** Live sessions own those files. A reader that never writes
  cannot corrupt anything.
- **Killing or controlling sessions.** Out of scope for v1. It is a window, not a
  cockpit.
- **Network or multi-machine access.** Localhost only, by design.
- **Authentication.** Unnecessary while it is loopback-bound, and adding it would imply
  the tool is safe to expose. It is not.

## Roadmap

- [x] `server.py` — scan, liveness filter, JSON endpoint
- [x] `index.html` — auto-refreshing view grouped by status
- [x] Stale-file count, surfaced as a number (cleanup stays manual)
- [ ] Background job panel from `jobs/*/state.json`
- [ ] CI workflow (`ruff` + `black --check`), matching the workspace convention
- [ ] `--once` flag to print a table to stdout and exit, for terminal use

## License

MIT — see [LICENSE](LICENSE).
