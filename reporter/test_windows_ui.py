# Copyright (c) 2026 黑沐. SPDX-License-Identifier: MIT
"""Run with QT_QPA_PLATFORM=offscreen; never touches the user's real worker."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
import sys
import unittest
from unittest.mock import patch, MagicMock
try:
    from PySide6.QtWidgets import QApplication
except ImportError:
    raise unittest.SkipTest("Windows UI tests require PySide6-Essentials")
from PySide6.QtCore import QEventLoop, QTimer
from windows_ui import ReporterWindow, number, launch_command, set_login, login_enabled

app = QApplication.instance() or QApplication([])

class WindowTests(unittest.TestCase):
    def setUp(self):
        self.window = ReporterWindow(preview=True)

    def tearDown(self):
        self.window.wanted = False
        if self.window.worker:
            self.window.worker.kill()
            self.window.worker.waitForFinished(3000)
        self.window.deleteLater()
        app.processEvents()

    def test_missing_metrics_are_not_zero(self):
        self.window.render({'performance': {'cpu_percent': 0}, 'agent': {}, 'devices': []})
        self.assertEqual(self.window.labels['cpu'].text(), '0.0%')
        self.assertEqual(self.window.labels['gpu'].text(), '—')
        self.assertEqual(number(float('nan')), '—')

    def test_stale_quota_is_marked_and_cleared_on_recovery(self):
        self.window.render({'codex_quota': {'week_remaining_percent': 65, 'stale': True}})
        self.assertIn('显示上次数据', self.window.labels['quota_status'].text())
        self.assertIn('65', self.window.labels['quota'].text())
        self.window.render({'codex_quota': {'week_remaining_percent': 60, 'stale': False}})
        self.assertEqual(self.window.labels['quota_status'].text(), 'CODEX')
        self.window.offline()
        self.assertNotIn('60', self.window.labels['quota'].text())

    def test_disconnect_clears_all_live_values(self):
        self.window.render({'computer_name': 'old host', 'performance': {'gpu_percent': 99}, 'media': {'available': True, 'title': 'old song'}, 'devices':[{'ip':'test'}]})
        self.window.offline()
        self.assertEqual(self.window.labels['gpu'].text(), '—')
        self.assertNotIn('old song', self.window.labels['music'].text())
        self.assertNotIn('test', self.window.labels['device'].text())
        self.assertFalse(self.window.diagnostic.isEnabled())
        self.assertEqual(self.window.labels['host'].text(), '')

    def test_small_work_area_keeps_bottom_controls_reachable(self):
        self.window.resize(700, 450)
        self.window.show()
        app.processEvents()
        self.assertGreater(self.window.scroll.verticalScrollBar().maximum(), 0)
        self.window.scroll.ensureWidgetVisible(self.window.login)
        app.processEvents()
        point = self.window.login.mapTo(self.window.scroll.viewport(), self.window.login.rect().center())
        self.assertTrue(self.window.scroll.viewport().rect().contains(point))
        self.window.hide()

    def test_external_worker_is_read_only(self):
        self.window.render({'performance': {}})
        self.assertFalse(self.window.toggle.isEnabled())
        self.assertIsNone(self.window.worker)

    def test_stop_only_owned_process(self):
        worker = MagicMock()
        self.window.worker = worker
        self.window.toggle_service()
        worker.kill.assert_called_once()
        self.assertFalse(self.window.wanted)
        self.window.worker = None

    def test_registry_round_trip_and_quoted_path(self):
        registry = MagicMock()
        with patch.dict(sys.modules, {'winreg': registry}), patch('windows_ui.launch_command', return_value=['C:\\Program Files\\Syna Reporter\\SynaReporter.exe']):
            set_login(True)
            command = registry.SetValueEx.call_args.args[-1]
            self.assertTrue(command.startswith('"C:\\Program Files'))
            registry.QueryValueEx.return_value = (command, 1)
            self.assertTrue(login_enabled())
            set_login(False)
            registry.DeleteValue.assert_called_once()

    def test_worker_crash_schedules_recovery_but_stop_does_not(self):
        worker = MagicMock()
        self.window.worker = worker
        with patch('windows_ui.QTimer.singleShot') as schedule:
            self.window.worker_finished(worker)
            schedule.assert_called_once()
        self.window.worker = worker
        self.window.wanted = False
        with patch('windows_ui.QTimer.singleShot') as schedule:
            self.window.worker_finished(worker)
            schedule.assert_not_called()

    def test_real_child_lifecycle(self):
        with patch('windows_ui.launch_command', return_value=[sys.executable, '-c', 'import time; time.sleep(30)']):
            self.window.start_service()
            process = self.window.worker
            self.assertTrue(process.waitForStarted(3000))
            self.window.toggle_service()
            process.waitForFinished(3000)
            app.processEvents()
            self.assertIsNone(self.window.worker)
            self.assertFalse(self.window.wanted)

if __name__ == '__main__':
    unittest.main()
