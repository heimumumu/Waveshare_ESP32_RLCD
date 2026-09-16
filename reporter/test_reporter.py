# Syna project-specific code and modifications: Copyright (c) 2026 黑沐.
# SPDX-License-Identifier: MIT; third-party notices remain applicable.
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import reporter


class ReporterIdentityTests(unittest.TestCase):
    def test_identity_is_stable(self):
        with tempfile.TemporaryDirectory() as root, patch.dict(
            os.environ, {"SYNA_REPORTER_DATA_DIR": root}, clear=False
        ):
            first = reporter.load_identity()
            second = reporter.load_identity()
            self.assertEqual(first["reporter_id"], second["reporter_id"])
            self.assertEqual(first["pairing_token"], second["pairing_token"])


class CodexLoginTests(unittest.TestCase):
    def test_missing_auth_clears_quota_and_requests_login(self):
        with tempfile.TemporaryDirectory() as root, patch.dict(
            os.environ,
            {"CODEX_HOME": str(Path(root) / "missing"), "OPENAI_API_KEY": ""},
            clear=False,
        ), patch.object(reporter.sys, "platform", "win32"):
            self.assertFalse(reporter.codex_auth_available())
            quota = reporter.CodexQuotaCollector()._read_snapshot()
            agent = reporter.CodexAgentMonitor().snapshot()
            self.assertEqual(quota.source, "login_required")
            self.assertIsNone(quota.short_remaining_percent)
            self.assertEqual(agent.state, "login_required")
            self.assertEqual(agent.task, "请登录 Codex")


class QuotaRecoveryTests(unittest.TestCase):
    def test_failure_cache_backoff_expiry_and_recovery(self):
        collector = reporter.CodexQuotaCollector()
        with patch('reporter.time.monotonic', return_value=100) as clock:
            good = reporter.QuotaSnapshot(week_remaining_percent=65, updated_at=10, source='codex_app_server')
            self.assertEqual(collector._accept_snapshot(good), 30)
            failure = reporter.QuotaSnapshot(source='unavailable', updated_at=20)
            self.assertEqual([collector._accept_snapshot(failure) for _ in range(5)], [5, 10, 20, 30, 30])
            cached = collector.snapshot()
            self.assertEqual((cached.week_remaining_percent, cached.short_remaining_percent, cached.updated_at, cached.stale), (65, None, 10, True))
            clock.return_value = 220
            self.assertIsNone(collector.snapshot().week_remaining_percent)
            clock.return_value = 221
            collector._accept_snapshot(reporter.QuotaSnapshot(week_remaining_percent=60, source='codex_app_server'))
            self.assertFalse(collector.snapshot().stale)
            self.assertEqual(collector.snapshot().week_remaining_percent, 60)
            self.assertEqual(collector._accept_snapshot(failure), 5)

    def test_logout_clears_cache_and_later_failure_cannot_restore_it(self):
        collector = reporter.CodexQuotaCollector()
        collector._accept_snapshot(reporter.QuotaSnapshot(week_remaining_percent=65, source='codex_app_server'))
        collector._accept_snapshot(reporter.QuotaSnapshot(source='login_required'))
        self.assertEqual(collector.snapshot().source, 'login_required')
        collector._accept_snapshot(reporter.QuotaSnapshot(source='unavailable'))
        self.assertIsNone(collector.snapshot().week_remaining_percent)

    def test_cached_window_is_cleared_at_its_reset(self):
        collector = reporter.CodexQuotaCollector()
        collector._accept_snapshot(reporter.QuotaSnapshot(short_remaining_percent=0, short_resets_at=100,
            week_remaining_percent=65, week_resets_at=200, source='codex_app_server'))
        collector._accept_snapshot(reporter.QuotaSnapshot(source='unavailable'))
        with patch('reporter.time.time', return_value=100):
            self.assertIsNone(collector.snapshot().short_remaining_percent)
            self.assertEqual(collector.snapshot().week_remaining_percent, 65)


if __name__ == "__main__":
    unittest.main()
