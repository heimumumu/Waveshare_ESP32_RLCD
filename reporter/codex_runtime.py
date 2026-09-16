# Syna project-specific code and modifications: Copyright (c) 2026 黑沐.
# SPDX-License-Identifier: MIT; third-party notices remain applicable.
"""Read lifecycle labels from Codex's local logs and session records.

SQL projects fixed start/end labels, timestamps and process identities. Message
content, prompts, responses and tool arguments never leave the database query.
The bounded session fallback parses JSON locally and returns only task lifecycle
timestamps and states; it never logs or publishes conversation content.
This is a version-specific fallback for stdio clients without a shared socket.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
import logging
import sqlite3
import time
import json
from datetime import datetime


@dataclass(frozen=True)
class RuntimeActivity:
    state: str
    active_count: int
    updated_at: int


def _rollout_event(path: Path):
    """Read backwards to the latest lifecycle event; never expose message text."""
    try:
        with path.open("rb") as stream:
            end = stream.seek(0, 2)
            remaining = 8 * 1024 * 1024
            suffix = b""
            while end and remaining:
                size = min(end, remaining, 65536)
                end -= size
                remaining -= size
                stream.seek(end)
                lines = (stream.read(size) + suffix).split(b"\n")
                suffix = lines.pop(0) if end else b""
                for line in reversed(lines):
                    if b'"event_msg"' not in line:
                        continue
                    try:
                        item = json.loads(line)
                        payload = item.get("payload", {})
                        kind = payload.get("type")
                        if item.get("type") != "event_msg" or kind not in {
                            "task_started", "task_complete", "task_aborted", "turn_aborted"
                        }:
                            continue
                        timestamp = datetime.fromisoformat(item["timestamp"].replace("Z", "+00:00")).timestamp()
                        return timestamp, kind == "task_started"
                    except (ValueError, KeyError, TypeError, AttributeError):
                        continue
    except OSError:
        pass
    return None


def _rollout_activity(root, threads, now):
    if not threads:
        return None
    connection = None
    events = []
    try:
        connection = sqlite3.connect((root / "state_5.sqlite").resolve().as_uri() + "?mode=ro",
                                     uri=True, timeout=0.1)
        for thread, born in threads.items():
            row = connection.execute("SELECT rollout_path FROM threads WHERE id = ?", (thread,)).fetchone()
            if row:
                event = _rollout_event(Path(row[0]))
                if event and born - 1 <= event[0] <= now + 2:
                    events.append(event)
    except (OSError, sqlite3.Error):
        return None
    finally:
        if connection is not None:
            connection.close()
    if not events:
        return None
    count = sum(active for _, active in events)
    latest = max(timestamp for timestamp, _ in events)
    return RuntimeActivity("working" if count else "done" if now - latest <= 120 else "idle",
                           count, int(latest))


def read_activity(root: Path, processes: dict[int, float], now: float) -> RuntimeActivity | None:
    path = root / "logs_2.sqlite"
    if not processes or not path.is_file():
        return None
    connection = None
    try:
        connection = sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True, timeout=0.1)
        deadline = time.monotonic() + 0.15
        connection.set_progress_handler(lambda: int(time.monotonic() > deadline), 1000)
        # Use the timestamp index and cap both the lookback and number of rows.
        # Do not SELECT feedback_log_body or any conversation-bearing columns.
        rows = connection.execute("""
            SELECT ts, process_uuid,
                   CASE WHEN feedback_log_body LIKE 'app-server event: turn/started %'
                        THEN 'start' ELSE 'end' END AS event
            FROM logs
            WHERE ts >= ? AND target = 'codex_app_server::outgoing_message'
              AND (feedback_log_body LIKE 'app-server event: turn/started %'
                   OR feedback_log_body LIKE 'app-server event: turn/completed %')
            ORDER BY ts DESC, ts_nanos DESC, id DESC LIMIT 10000
        """, (int(max(min(processes.values()) - 1, now - 48 * 3600)),)).fetchall()
        # Some Windows clients emit item events without outgoing turn events.
        # Bind the rollout fallback to threads observed in a live process only.
        threads = {}
        try:
            identities = connection.execute("""
                SELECT ts, process_uuid, thread_id FROM logs
                WHERE ts >= ? ORDER BY ts DESC, ts_nanos DESC, id DESC LIMIT 10000
            """, (int(max(min(processes.values()) - 1, now - 48 * 3600)),)).fetchall()
            for timestamp, identity, thread in identities:
                match = re.fullmatch(r"pid:(\d+):[^:]+", str(identity or ""))
                born = processes.get(int(match.group(1))) if match else None
                if thread and born is not None and born - 1 <= timestamp <= now + 2:
                    threads[thread] = born
        except sqlite3.Error:
            pass  # Older log schemas can still use outgoing lifecycle labels.
    except (OSError, sqlite3.Error) as error:
        logging.debug("Codex lifecycle read unavailable: %s", error)
        return None
    finally:
        if connection is not None:
            connection.close()

    # Each process can own several simultaneous turns. A completed turn must
    # not clear another turn that is still running in the same client.
    pending: dict[str, int] = {}
    latest = 0
    completed = 0
    for timestamp, identity, event in reversed(rows):
        match = re.fullmatch(r"pid:(\d+):[^:]+", str(identity or ""))
        if match is None:
            continue
        born = processes.get(int(match.group(1)))
        if born is None or timestamp < born - 1 or timestamp > now + 2:
            continue
        latest = max(latest, timestamp)
        if event == "start":
            pending[identity] = pending.get(identity, 0) + 1
        else:
            pending[identity] = max(0, pending.get(identity, 0) - 1)
            completed = max(completed, timestamp)
    rollout = _rollout_activity(root, threads, now)
    if rollout is not None and rollout.updated_at >= latest:
        return rollout
    if not latest:
        return None
    count = sum(pending.values())
    if count:
        return RuntimeActivity("working", count, latest)
    if completed and now - completed <= 120:
        return RuntimeActivity("done", 0, completed)
    return RuntimeActivity("idle", 0, latest)
