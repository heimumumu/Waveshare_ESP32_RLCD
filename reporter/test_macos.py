# Syna project-specific code and modifications: Copyright (c) 2026 黑沐.
# SPDX-License-Identifier: MIT; third-party notices remain applicable.
import asyncio
import json
import os
from pathlib import Path
import plistlib
import socket
import subprocess
import sys
import tempfile
import time
import unittest
import urllib.request
from unittest.mock import MagicMock, Mock, patch

import media_monitor
import platform_support
import reporter
from macos_service import service_definition


@unittest.skipUnless(sys.platform == "darwin", "macOS adaptation tests")
class MacSupportTests(unittest.TestCase):
    def test_http_startup_does_not_require_local_dns(self):
        with patch.object(socket, "getfqdn", side_effect=AssertionError("DNS must not block startup")):
            server = reporter.ReporterHTTPServer(("127.0.0.1", 0), reporter.BaseHTTPRequestHandler)
            try:
                self.assertGreater(server.server_port, 0)
            finally:
                server.server_close()

    def test_data_path_and_disk(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(platform_support.application_data_dir(),
                             Path.home() / "Library/Application Support/SynaReporter")
            self.assertIn(platform_support.disk_root(), ("/", "/System/Volumes/Data"))

    def test_instance_lock_releases_on_close(self):
        with tempfile.TemporaryDirectory() as root, patch.dict(os.environ, {"SYNA_REPORTER_DATA_DIR": root}):
            first = reporter.acquire_single_instance("worker")
            self.assertIsNotNone(first)
            self.assertIsNone(reporter.acquire_single_instance("worker"))
            first.close()
            second = reporter.acquire_single_instance("worker")
            self.assertIsNotNone(second)
            second.close()

    def test_codex_extension_found_without_shell_path(self):
        with tempfile.TemporaryDirectory() as root, patch.object(Path, "home", return_value=Path(root)), \
                patch.object(platform_support.shutil, "which", return_value=None), \
                patch.object(platform_support.platform, "machine", return_value="arm64"), \
                patch.dict(os.environ, {"SYNA_CODEX_EXECUTABLE": ""}):
            executable = Path(root) / ".vscode/extensions/openai.chatgpt-99-darwin-arm64/bin/macos-aarch64/codex"
            executable.parent.mkdir(parents=True)
            executable.touch()
            executable.chmod(0o755)
            self.assertEqual(platform_support.codex_executable(), str(executable))

    def test_mac_login_is_not_inferred_from_auth_file(self):
        with patch.object(Path, "read_text", side_effect=AssertionError("must use app-server")):
            self.assertIsNone(reporter.codex_auth_available())

    def test_quota_child_does_not_make_codex_appear_online(self):
        own = Mock(info={"name": "codex", "ppid": os.getpid()})
        desktop = Mock(info={"name": "Codex", "ppid": 1})
        with patch.object(reporter.psutil, "process_iter", return_value=[own]):
            self.assertFalse(reporter.CodexAgentMonitor._codex_running())
        with patch.object(reporter.psutil, "process_iter", return_value=[own, desktop]):
            self.assertTrue(reporter.CodexAgentMonitor._codex_running())

    def test_logged_out_app_server_clears_quota(self):
        process = MagicMock()
        process.stdout.__iter__.return_value = iter([])
        process.poll.return_value = 0
        with patch.object(reporter.CodexQuotaCollector, "_codex_executable", return_value="codex"), \
                patch.object(reporter.subprocess, "Popen", return_value=process), \
                patch.object(reporter.CodexQuotaCollector, "_wait_for_response", side_effect=[
                    {"result": {}}, {"result": {"account": None}}
                ]):
            snapshot = reporter.CodexQuotaCollector()._read_snapshot()
            self.assertEqual(snapshot.source, "login_required")
            self.assertIsNone(snapshot.week_remaining_percent)

    def test_shutdown_terminates_unresponsive_quota_child(self):
        collector = reporter.CodexQuotaCollector()
        real_popen = subprocess.Popen
        children = []

        def spawn(*args, **kwargs):
            child = real_popen([sys.executable, "-c", "import time; time.sleep(60)"], **kwargs)
            children.append(child)
            return child

        with patch.object(collector, "_codex_executable", return_value="codex"), \
                patch.object(reporter.subprocess, "Popen", side_effect=spawn), \
                patch.object(reporter.logging, "warning"):
            collector.start()
            try:
                deadline = time.monotonic() + 3
                while collector._process is None and time.monotonic() < deadline:
                    time.sleep(0.02)
                self.assertIsNotNone(collector._process)
                collector.stop()
                self.assertFalse(collector._thread.is_alive())
                self.assertTrue(all(child.poll() is not None for child in children))
            finally:
                collector.stop()
                for child in children:
                    if child.poll() is None:
                        child.kill()
                    child.wait()

    def test_metrics_available_without_windows_or_nvidia(self):
        collector = reporter.MetricsCollector()
        collector.start()
        try:
            deadline = time.monotonic() + 5
            snapshot = collector.snapshot()
            while snapshot.memory_percent == 0 and time.monotonic() < deadline:
                time.sleep(0.05)
                snapshot = collector.snapshot()
            self.assertTrue(collector._thread.is_alive())
            self.assertGreater(snapshot.memory_percent, 0)
            self.assertGreater(snapshot.disk_percent, 0)
            self.assertGreaterEqual(snapshot.cpu_percent, 0)
            if snapshot.gpu_percent is not None:
                self.assertGreaterEqual(snapshot.gpu_percent, 0)
                self.assertLessEqual(snapshot.gpu_percent, 100)
        finally:
            collector.stop()

    def test_no_media_channel_is_safe(self):
        monitor = media_monitor.NeteaseMediaMonitor()
        self.assertIsNone(monitor._local)
        with patch.object(monitor._mac or monitor._cdp, "read", return_value=None):
            result = asyncio.run(monitor._read(None))
        self.assertFalse(result.available)

    def test_cdp_seek_to_zero_does_not_keep_estimated_progress(self):
        monitor = media_monitor.NeteaseMediaMonitor()
        monitor._mac = None  # Exercise the retained Windows/CDP route.
        monitor._clock_title = "Song"
        monitor._clock_position = 120
        monitor._clock_status = "playing"
        with patch.object(monitor._cdp, "read", return_value={
            "title": "Song", "artist": "Artist", "position": 0,
            "duration": 200, "playback_status": "playing", "song_id": 123
        }), patch.object(monitor._resolver, "resolve", return_value=(123, [(0, "line")])):
            result = asyncio.run(monitor._read(None))
        self.assertTrue(result.available)
        self.assertEqual(result.position_seconds, 0)

    def test_launchd_preserves_paths_with_spaces_and_venv(self):
        definition = service_definition(Path("/tmp/中文 project/.venv/bin/python"),
                                        Path("/tmp/中文 project/reporter.py"))
        definition = plistlib.loads(plistlib.dumps(definition))
        self.assertEqual(definition["ProgramArguments"][0], "/tmp/中文 project/.venv/bin/python")
        self.assertIn("--no-supervisor", definition["ProgramArguments"])


@unittest.skipUnless(sys.platform == "darwin", "macOS subprocess lifecycle")
class MacProtocolTests(unittest.TestCase):
    def test_worker_http_udp_identity_and_sigterm(self):
        # Do not disturb an existing Reporter using the protocol's fixed port.
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as probe:
            try:
                probe.bind(("0.0.0.0", reporter.DISCOVERY_PORT))
            except OSError:
                self.skipTest("UDP 8766 already in use")
        with socket.socket() as probe:
            probe.bind(("127.0.0.1", 0))
            port = probe.getsockname()[1]
        with tempfile.TemporaryDirectory() as root:
            environment = dict(os.environ, SYNA_REPORTER_DATA_DIR=root,
                               CODEX_HOME=root, SYNA_CODEX_EXECUTABLE="/nonexistent/codex")
            app = os.environ.get("SYNA_TEST_APP")
            command = [app] if app else [sys.executable, str(Path(reporter.__file__).resolve())]
            identities = []
            for attempt in range(2):
                arguments = command + ["--port", str(port)] + (["--no-supervisor"] if attempt == 0 else [])
                process = subprocess.Popen(arguments, env=environment, stdout=subprocess.DEVNULL,
                                           stderr=subprocess.PIPE, text=True)
                try:
                    deadline = time.monotonic() + 10
                    while True:
                        try:
                            with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/v1/status", timeout=1) as response:
                                status = json.load(response)
                            break
                        except OSError:
                            if process.poll() is not None or time.monotonic() > deadline:
                                self.fail("Worker failed to start")
                            time.sleep(0.1)
                    self.assertNotIn("pairing_token", status)
                    identities.append(status["reporter_id"])
                    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as client:
                        client.settimeout(3)
                        client.sendto(b"[]", ("127.0.0.1", 8766))
                        client.sendto(reporter.DISCOVERY_REQUEST, ("127.0.0.1", 8766))
                        discovery = json.loads(client.recv(8192))
                    self.assertEqual(discovery["type"], "AI_PANEL_REPORTER_V1")
                    self.assertEqual(discovery["reporter_id"], status["reporter_id"])
                    self.assertEqual(discovery["http_port"], port)
                    self.assertNotIn("pairing_token", discovery)
                    process.terminate()
                    process.wait(timeout=10)
                    self.assertEqual(process.returncode, 0)
                finally:
                    if process.poll() is None:
                        process.kill()
                    process.communicate(timeout=3)
            self.assertEqual(identities[0], identities[1])


if __name__ == "__main__":
    unittest.main()
