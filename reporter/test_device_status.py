# Syna project-specific code and modifications: Copyright (c) 2026 黑沐.
# SPDX-License-Identifier: MIT; third-party notices remain applicable.
import unittest
from unittest.mock import Mock, patch

from reporter import ReporterState


class DeviceStatusTests(unittest.TestCase):
    def setUp(self):
        self.state = ReporterState({"reporter_id": "test", "computer_name": "Mac", "pairing_token": "test"},
                                   Mock(), Mock(), Mock(), Mock())

    def test_discovery_is_visible_then_expires(self):
        with patch("reporter.time.monotonic", return_value=100):
            self.state.record_device("192.168.1.9", "board")
            self.state.record_device("192.168.1.9", "board")
        with patch("reporter.time.monotonic", return_value=102):
            self.assertEqual(self.state.recent_devices(), [{"ip": "192.168.1.9", "last_seen_seconds": 2}])
        with patch("reporter.time.monotonic", return_value=116):
            self.assertEqual(self.state.recent_devices(), [])

    def test_local_diagnostic_is_not_counted_as_board(self):
        self.state.record_device("127.0.0.1")
        self.assertEqual(self.state.recent_devices(), [])

    def test_peer_storage_is_bounded(self):
        for i in range(100):
            self.state.record_device(f"192.168.1.{i}")
        self.assertLessEqual(len(self.state._devices), 32)


if __name__ == "__main__":
    unittest.main()
