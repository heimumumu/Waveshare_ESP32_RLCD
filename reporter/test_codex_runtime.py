# Syna project-specific code and modifications: Copyright (c) 2026 黑沐.
# SPDX-License-Identifier: MIT; third-party notices remain applicable.
from pathlib import Path
import sqlite3
import json
from datetime import datetime, timezone
import tempfile
import unittest
from unittest.mock import patch

from codex_runtime import read_activity, RuntimeActivity, _rollout_event
import reporter


class LifecycleTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="syna #测试 ")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.db = sqlite3.connect(self.root / "logs_2.sqlite")
        self.addCleanup(self.db.close)
        self.db.execute("""CREATE TABLE logs (
            id INTEGER PRIMARY KEY, ts INTEGER, ts_nanos INTEGER,
            process_uuid TEXT, target TEXT, feedback_log_body TEXT)""")

    def event(self, timestamp, event, pid=42, generation="a"):
        self.db.execute("INSERT INTO logs(ts,ts_nanos,process_uuid,target,feedback_log_body) VALUES (?,0,?,?,?)",
                        (timestamp, f"pid:{pid}:{generation}", "codex_app_server::outgoing_message",
                         f"app-server event: turn/{event} targeted_connections=1"))
        self.db.commit()

    def test_live_start_end_and_idle_without_history_table(self):
        self.event(100, "started")
        self.assertEqual(read_activity(self.root, {42: 90}, 101), RuntimeActivity("working", 1, 100))
        self.event(110, "completed")
        self.assertEqual(read_activity(self.root, {42: 90}, 111), RuntimeActivity("done", 0, 110))
        self.assertEqual(read_activity(self.root, {42: 90}, 240).state, "idle")

    def test_one_completion_does_not_clear_concurrent_turns(self):
        self.event(100, "started")
        self.event(101, "started")
        self.event(102, "completed")
        state = read_activity(self.root, {42: 90}, 103)
        self.assertEqual((state.state, state.active_count), ("working", 1))

    def test_parallel_clients_are_combined(self):
        self.event(100, "started")
        self.event(101, "started", pid=43)
        self.assertEqual(read_activity(self.root, {42: 90, 43: 95}, 103).active_count, 2)

    def test_exited_process_and_reused_pid_cannot_leave_working_state(self):
        self.event(100, "started")
        self.assertIsNone(read_activity(self.root, {}, 110))
        self.assertIsNone(read_activity(self.root, {42: 105}, 110))

    def test_truncated_history_does_not_produce_negative_active_count(self):
        self.event(100, "completed")
        self.event(101, "started")
        self.assertEqual(read_activity(self.root, {42: 90}, 103).active_count, 1)

    def test_unrelated_log_messages_do_not_change_state(self):
        self.db.execute("INSERT INTO logs VALUES (1,100,0,'pid:42:a','another_target','app-server event: turn/started targeted_connections=1')")
        self.db.commit()
        self.assertIsNone(read_activity(self.root, {42: 90}, 101))

    def test_missing_or_new_schema_falls_back(self):
        self.db.execute("DROP TABLE logs")
        self.db.commit()
        self.assertIsNone(read_activity(self.root, {42: 90}, 101))

    def test_live_source_takes_priority_over_finished_history(self):
        monitor = reporter.CodexAgentMonitor()
        with patch.object(reporter, "codex_auth_available", return_value=None), \
                patch.object(monitor, "_codex_running", return_value=True), \
                patch.object(monitor, "_runtime_snapshot", return_value=RuntimeActivity("working", 2, 100)):
            state = monitor.snapshot()
        self.assertEqual((state.state, state.active_count, state.source), ("working", 2, "codex_lifecycle"))

    def test_first_poll_is_not_skipped_when_monotonic_clock_starts_at_zero(self):
        monitor = reporter.CodexAgentMonitor()
        with patch.object(reporter.time, "monotonic", return_value=0.01), \
                patch.object(reporter.psutil, "process_iter", return_value=[]), \
                patch.object(reporter, "read_activity", return_value=None) as read:
            monitor._runtime_snapshot()
            read.assert_called_once()

    def rollout(self, timestamp, kind):
        path = self.root / "session.jsonl"
        with path.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps({"timestamp": datetime.fromtimestamp(timestamp, timezone.utc).isoformat(),
                                     "type": "event_msg", "payload": {"type": kind}}) + "\n")
        return path

    def bind_rollout(self, pid=42):
        self.db.execute("ALTER TABLE logs ADD COLUMN thread_id TEXT")
        self.db.execute("INSERT INTO logs(ts,ts_nanos,process_uuid,target,feedback_log_body,thread_id) VALUES (101,0,?,'codex_core::session::turn','item event','thread')", (f"pid:{pid}:a",))
        self.db.commit()
        with sqlite3.connect(self.root / "state_5.sqlite") as state:
            state.execute("CREATE TABLE threads(id TEXT, rollout_path TEXT)")
            state.execute("INSERT INTO threads VALUES ('thread', ?)", (str(self.root / "session.jsonl"),))
        state.close()

    def test_rollout_without_outgoing_turn_events_updates_start_end_and_idle(self):
        self.bind_rollout()
        self.rollout(100, "task_started")
        self.assertEqual(read_activity(self.root, {42: 90}, 102), RuntimeActivity("working", 1, 100))
        self.rollout(110, "task_complete")
        self.assertEqual(read_activity(self.root, {42: 90}, 111), RuntimeActivity("done", 0, 110))
        self.assertEqual(read_activity(self.root, {42: 90}, 240).state, "idle")

    def test_rollout_from_exited_or_reused_process_is_ignored(self):
        self.bind_rollout()
        self.rollout(100, "task_started")
        self.assertIsNone(read_activity(self.root, {43: 90}, 102))
        self.assertIsNone(read_activity(self.root, {42: 105}, 110))

    def test_rollout_abort_and_partial_write_across_read_blocks(self):
        self.bind_rollout()
        path = self.rollout(100, "task_started")
        with path.open("ab") as stream:
            stream.write(b'{"type":"response_item","payload":"' + b'x' * 70000 + b'"}\n{"partial":')
        self.assertEqual(_rollout_event(path), (100, True))
        with path.open("ab") as stream:
            stream.write(b'null}\n')
        self.rollout(110, "turn_aborted")
        self.assertEqual(read_activity(self.root, {42: 90}, 111).state, "done")


if __name__ == "__main__":
    unittest.main()
