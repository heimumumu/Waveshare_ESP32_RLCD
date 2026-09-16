# Syna project-specific code and modifications: Copyright (c) 2026 黑沐.
# SPDX-License-Identifier: MIT; third-party notices remain applicable.
from __future__ import annotations

import argparse
import ctypes
import hashlib
import json
import logging
from logging.handlers import RotatingFileHandler
import os
import queue
import secrets
import signal
import sqlite3
import socket
import socketserver
import subprocess
import sys
import threading
import time
import uuid
from dataclasses import dataclass, asdict
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

import psutil

from media_monitor import NeteaseMediaMonitor
from macos_metrics import MacMetrics
from codex_runtime import read_activity
from platform_support import application_data_dir, disk_root, codex_executable, acquire_posix_instance


HTTP_PORT = 8765
DISCOVERY_PORT = 8766
DISCOVERY_REQUEST = b"AI_PANEL_DISCOVER_V1"
PROTOCOL_VERSION = 1

_cpu_temp_cached: float | None = None
_cpu_temp_checked_at = 0.0


def config_path() -> Path:
    root = application_data_dir()
    root.mkdir(parents=True, exist_ok=True)
    return root / "reporter.json"


def data_root() -> Path:
    return config_path().parent


def configure_logging() -> None:
    handler = RotatingFileHandler(
        data_root() / "reporter.log", maxBytes=1_000_000, backupCount=3,
        encoding="utf-8",
    )
    handler.setFormatter(logging.Formatter(
        "%(asctime)s %(levelname)s %(threadName)s %(message)s"
    ))
    logging.basicConfig(level=logging.INFO, handlers=[handler], force=True)


def agent_state_root() -> Path:
    return config_path().parent / "agents"


def load_identity() -> dict[str, str]:
    path = config_path()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        data = {}
    changed = False
    if not data.get("reporter_id"):
        data["reporter_id"] = str(uuid.uuid4())
        changed = True
    if not data.get("computer_name"):
        data["computer_name"] = socket.gethostname()
        changed = True
    if not data.get("pairing_token"):
        data["pairing_token"] = secrets.token_urlsafe(18)
        changed = True
    if changed:
        temporary = path.with_suffix(".tmp")
        temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        temporary.replace(path)
    return data


def codex_auth_available() -> bool | None:
    """None means login must be checked through app-server (macOS Keychain)."""
    if sys.platform == "darwin":
        return None
    if os.environ.get("OPENAI_API_KEY", "").strip():
        return True
    auth_path = Path(os.environ.get("CODEX_HOME", Path.home() / ".codex")) / "auth.json"
    try:
        payload = json.loads(auth_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    return bool(payload.get("OPENAI_API_KEY") or payload.get("tokens"))


def local_ip_for(peer_ip: str) -> str:
    probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        probe.connect((peer_ip, 9))
        return probe.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        probe.close()


def nvidia_metrics() -> tuple[float | None, float | None]:
    if sys.platform == "darwin":
        return None, None
    command = [
        "nvidia-smi",
        "--query-gpu=utilization.gpu,temperature.gpu",
        "--format=csv,noheader,nounits",
    ]
    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=1.5,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            check=False,
        )
        if result.returncode != 0 or not result.stdout.strip():
            return None, None
        utilization, temperature = result.stdout.splitlines()[0].split(",", 1)
        return float(utilization.strip()), float(temperature.strip())
    except (OSError, ValueError, subprocess.SubprocessError):
        return None, None


def cpu_temperature() -> float | None:
    global _cpu_temp_cached, _cpu_temp_checked_at
    now = time.monotonic()
    if now - _cpu_temp_checked_at < 5.0:
        return _cpu_temp_cached

    candidates: list[float] = []
    try:
        groups = psutil.sensors_temperatures(fahrenheit=False)
    except (AttributeError, OSError):
        groups = {}
    candidates.extend(
        float(entry.current)
        for entries in groups.values()
        for entry in entries
        if entry.current is not None and 0 < float(entry.current) < 130
    )

    # psutil does not expose temperatures on most Windows machines. Windows'
    # formatted ACPI thermal-zone counter reports whole Kelvin and gives us a
    # useful hardware fallback without requiring another monitoring program.
    if not candidates and os.name == "nt":
        try:
            result = subprocess.run(
                [
                    "wmic",
                    "path",
                    "Win32_PerfFormattedData_Counters_ThermalZoneInformation",
                    "get",
                    "Temperature",
                    "/value",
                ],
                capture_output=True,
                text=True,
                timeout=1.5,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                check=False,
            )
            for line in result.stdout.splitlines():
                if not line.startswith("Temperature="):
                    continue
                raw = float(line.split("=", 1)[1].strip())
                temperature = raw / 10.0 - 273.15 if raw > 1000 else raw - 273.15
                if 0 < temperature < 130:
                    candidates.append(temperature)
        except (OSError, ValueError, subprocess.SubprocessError):
            pass

    _cpu_temp_cached = round(max(candidates), 1) if candidates else None
    _cpu_temp_checked_at = now
    return _cpu_temp_cached


@dataclass
class PerformanceSnapshot:
    cpu_percent: float = 0.0
    memory_percent: float = 0.0
    gpu_percent: float | None = None
    disk_percent: float = 0.0
    cpu_temp_c: float | None = None
    gpu_temp_c: float | None = None
    upload_bytes_per_sec: float = 0.0
    download_bytes_per_sec: float = 0.0


class MetricsCollector:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._snapshot = PerformanceSnapshot()
        self._mac_metrics = MacMetrics() if sys.platform == "darwin" else None
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, name="metrics", daemon=True)

    def start(self) -> None:
        psutil.cpu_percent(interval=None)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        self._thread.join(timeout=2)

    def snapshot(self) -> PerformanceSnapshot:
        with self._lock:
            return PerformanceSnapshot(**asdict(self._snapshot))

    def _run(self) -> None:
        psutil.cpu_percent(interval=None)
        previous_net = psutil.net_io_counters()
        previous_time = time.monotonic()
        while not self._stop.wait(1.0):
            now = time.monotonic()
            current_net = psutil.net_io_counters()
            elapsed = max(now - previous_time, 0.001)
            if self._mac_metrics is not None:
                gpu_percent, cpu_temp, gpu_temp = self._mac_metrics.read()
            else:
                gpu_percent, gpu_temp = nvidia_metrics()
                cpu_temp = cpu_temperature()
            snapshot = PerformanceSnapshot(
                cpu_percent=round(psutil.cpu_percent(interval=None), 1),
                memory_percent=round(psutil.virtual_memory().percent, 1),
                gpu_percent=gpu_percent,
                disk_percent=round(psutil.disk_usage(disk_root()).percent, 1),
                cpu_temp_c=cpu_temp,
                gpu_temp_c=gpu_temp,
                upload_bytes_per_sec=max(0.0, (current_net.bytes_sent - previous_net.bytes_sent) / elapsed),
                download_bytes_per_sec=max(0.0, (current_net.bytes_recv - previous_net.bytes_recv) / elapsed),
            )
            with self._lock:
                self._snapshot = snapshot
            previous_net = current_net
            previous_time = now


@dataclass
class AgentSnapshot:
    state: str = "offline"
    task: str = ""
    active_count: int = 0
    updated_at: int = 0
    source: str = "process"


class CodexAgentMonitor:
    """Prefer live lifecycle markers; fall back to the persisted turn history."""

    _DONE_VISIBLE_SECONDS = 120
    _ACTIVE_STALE_SECONDS = 30 * 60

    def __init__(self) -> None:
        self._runtime_lock = threading.Lock()
        self._runtime_checked_at = float("-inf")
        self._runtime_activity = None

    def _runtime_snapshot(self):
        with self._runtime_lock:
            if time.monotonic() - self._runtime_checked_at < 0.5:
                return self._runtime_activity
            processes = {}
            for process in psutil.process_iter(["name", "ppid", "create_time"]):
                try:
                    if ((process.info.get("name") or "").lower() in {"codex", "codex.exe"}
                            and process.info.get("ppid") != os.getpid()
                            and process.info.get("create_time") is not None):
                        processes[process.pid] = process.info["create_time"]
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    continue
            self._runtime_activity = read_activity(self._codex_home(), processes, time.time())
            self._runtime_checked_at = time.monotonic()
            return self._runtime_activity

    @staticmethod
    def _codex_home() -> Path:
        return Path(os.environ.get("CODEX_HOME", Path.home() / ".codex"))

    @staticmethod
    def _codex_running() -> bool:
        for process in psutil.process_iter(["name", "ppid"]):
            try:
                if ((process.info.get("name") or "").lower() in {"codex.exe", "codex"}
                        and process.info.get("ppid") != os.getpid()):
                    return True
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
        return False

    def snapshot(self) -> AgentSnapshot:
        now = time.time()
        if codex_auth_available() is False:
            return AgentSnapshot(
                state="login_required", task="请登录 Codex", source="auth"
            )
        running = self._codex_running()
        if not running:
            return AgentSnapshot()

        runtime = self._runtime_snapshot()
        if runtime is not None:
            return AgentSnapshot(
                state=runtime.state,
                task="Codex" if runtime.state in {"working", "done"} else "",
                active_count=runtime.active_count,
                updated_at=runtime.updated_at,
                source="codex_lifecycle",
            )

        history_path = self._codex_home() / "thread_history_1.sqlite"
        if not history_path.exists():
            return AgentSnapshot(state="idle", source="process")

        try:
            connection = sqlite3.connect(
                history_path.resolve().as_uri() + "?mode=ro",
                uri=True,
                timeout=0.25,
            )
            turns = connection.execute(
                "SELECT thread_id, status, started_at, completed_at "
                "FROM thread_turns "
                "ORDER BY COALESCE(completed_at, started_at, 0) DESC LIMIT 64"
            ).fetchall()
            connection.close()
        except sqlite3.Error:
            return AgentSnapshot(state="idle", source="process")

        active = [
            turn for turn in turns
            if str(turn[1]).lower() in {"inprogress", "in_progress", "running"}
            and now - float(turn[2] or 0) <= self._ACTIVE_STALE_SECONDS
        ]
        if active:
            selected = max(active, key=lambda turn: float(turn[2] or 0))
            workspace = self._workspace_for_thread(str(selected[0]))
            return AgentSnapshot(
                state="working",
                task=f"Codex · {workspace}" if workspace else "Codex",
                active_count=len(active),
                updated_at=int(float(selected[2] or now)),
                source="codex_store",
            )

        completed = [turn for turn in turns if turn[3] is not None]
        if completed:
            selected = max(completed, key=lambda turn: float(turn[3] or 0))
            completed_at = float(selected[3] or 0)
            if now - completed_at <= self._DONE_VISIBLE_SECONDS:
                workspace = self._workspace_for_thread(str(selected[0]))
                return AgentSnapshot(
                    state="done",
                    task=f"Codex · {workspace}" if workspace else "Codex",
                    updated_at=int(completed_at),
                    source="codex_store",
                )
        return AgentSnapshot(state="idle", source="codex_store")

    def _workspace_for_thread(self, thread_id: str) -> str:
        state_path = self._codex_home() / "state_5.sqlite"
        if not state_path.exists():
            return ""
        try:
            connection = sqlite3.connect(
                state_path.resolve().as_uri() + "?mode=ro",
                uri=True,
                timeout=0.25,
            )
            row = connection.execute(
                "SELECT cwd FROM threads WHERE id = ?", (thread_id,)
            ).fetchone()
            connection.close()
            if row and row[0]:
                return Path(str(row[0]).removeprefix("\\\\?\\")).name[:48]
        except (sqlite3.Error, OSError):
            pass
        return ""


@dataclass
class QuotaSnapshot:
    short_remaining_percent: int | None = None
    week_remaining_percent: int | None = None
    short_resets_at: int | None = None
    week_resets_at: int | None = None
    updated_at: int = 0
    source: str = "unavailable"
    stale: bool = False


class CodexQuotaCollector:
    """Poll the local Codex app-server account rate-limit snapshot."""

    _POLL_SECONDS = 30
    _CACHE_SECONDS = 120

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._process_lock = threading.Lock()
        self._process = None
        self._snapshot = QuotaSnapshot()
        self._success_at = float('-inf')
        self._failures = 0
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, name="codex-quota", daemon=True)

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        with self._process_lock:
            process = self._process
            if process is not None and process.poll() is None:
                try:
                    process.terminate()
                except ProcessLookupError:
                    pass
        if process is not None:
            try:
                process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=2)
        self._thread.join(timeout=3)

    def snapshot(self) -> QuotaSnapshot:
        with self._lock:
            result = QuotaSnapshot(**asdict(self._snapshot))
            if result.stale:
                if time.monotonic() - self._success_at >= self._CACHE_SECONDS:
                    return QuotaSnapshot(source="unavailable", updated_at=result.updated_at)
                now = time.time()
                if result.short_resets_at is not None and now >= result.short_resets_at:
                    result.short_remaining_percent = None
                if result.week_resets_at is not None and now >= result.week_resets_at:
                    result.week_remaining_percent = None
            return result

    def _accept_snapshot(self, snapshot: QuotaSnapshot) -> int:
        with self._lock:
            if snapshot.source == "unavailable":
                self._failures = min(self._failures + 1, 4)
                previous = self._snapshot
                if (time.monotonic() - self._success_at < self._CACHE_SECONDS
                        and (previous.short_remaining_percent is not None
                             or previous.week_remaining_percent is not None)):
                    self._snapshot = QuotaSnapshot(**{**asdict(previous), "stale": True})
                else:
                    self._snapshot = snapshot
                return min(5 * 2 ** (self._failures - 1), self._POLL_SECONDS)
            self._failures = 0
            self._snapshot = snapshot
            # Authentication failures and missing Codex must invalidate the cache.
            self._success_at = time.monotonic() if snapshot.source == "codex_app_server" else float('-inf')
            return self._POLL_SECONDS

    def _run(self) -> None:
        while not self._stop.is_set():
            snapshot = self._read_snapshot()
            delay = self._accept_snapshot(snapshot)
            if self._stop.wait(delay):
                break

    @staticmethod
    def _codex_executable() -> str | None:
        return codex_executable()

    def _read_snapshot(self) -> QuotaSnapshot:
        if codex_auth_available() is False:
            return QuotaSnapshot(
                updated_at=int(time.time()), source="login_required"
            )
        executable = self._codex_executable()
        if executable is None:
            return QuotaSnapshot(
                updated_at=int(time.time()), source="codex_not_found"
            )
        process: subprocess.Popen[str] | None = None
        try:
            process = subprocess.Popen(
                [executable, "app-server", "--stdio"],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                text=True,
                encoding="utf-8",
                errors="replace",
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            with self._process_lock:
                self._process = process
                if self._stop.is_set():
                    process.terminate()
            responses: queue.Queue[str] = queue.Queue()

            def read_stdout() -> None:
                assert process is not None and process.stdout is not None
                for line in process.stdout:
                    responses.put(line)
                # Wake the response waiter if the app-server exits or is stopped.
                responses.put("")

            threading.Thread(target=read_stdout, name="codex-quota-output", daemon=True).start()

            def send(message: dict[str, Any]) -> None:
                assert process is not None and process.stdin is not None
                process.stdin.write(json.dumps(message, separators=(",", ":")) + "\n")
                process.stdin.flush()

            send({
                "id": 1,
                "method": "initialize",
                "params": {
                    "clientInfo": {
                        "name": "ai-agent-panel-reporter",
                        "title": "AI Agent Panel Reporter",
                        "version": "0.1.0",
                    },
                    "capabilities": {"experimentalApi": True},
                },
            })
            self._wait_for_response(responses, 1, 10)
            send({"method": "initialized"})
            send({"id": 3, "method": "account/read", "params": {"refreshToken": False}})
            account = self._wait_for_response(responses, 3, 10).get("result", {})
            if account.get("account") is None:
                return QuotaSnapshot(updated_at=int(time.time()), source="login_required")
            send({"id": 2, "method": "account/rateLimits/read", "params": None})
            response = self._wait_for_response(responses, 2, 15)
            return self._parse_snapshot(response.get("result", {}))
        except ValueError as error:
            message = str(error).casefold()
            source = "login_required" if any(
                token in message for token in ("login", "auth", "unauthorized", "account")
            ) else "unavailable"
            logging.warning("Codex quota unavailable: %s", error)
            return QuotaSnapshot(updated_at=int(time.time()), source=source)
        except (OSError, queue.Empty, subprocess.SubprocessError) as error:
            logging.warning("Codex quota unavailable: %s", error)
            return QuotaSnapshot(
                updated_at=int(time.time()), source="unavailable"
            )
        finally:
            if process is not None and process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=2)
            with self._process_lock:
                self._process = None
            if process is not None:
                for pipe in (process.stdin, process.stdout):
                    if pipe is not None:
                        try:
                            pipe.close()
                        except OSError:
                            pass

    @staticmethod
    def _wait_for_response(responses: queue.Queue[str], request_id: int,
                           timeout: float) -> dict[str, Any]:
        deadline = time.monotonic() + timeout
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise queue.Empty
            message = json.loads(responses.get(timeout=remaining))
            if message.get("id") == request_id:
                if "error" in message:
                    raise ValueError(str(message["error"]))
                return message

    @staticmethod
    def _parse_snapshot(result: dict[str, Any]) -> QuotaSnapshot:
        buckets = result.get("rateLimitsByLimitId") or {}
        limits = buckets.get("codex") if isinstance(buckets, dict) else None
        if not isinstance(limits, dict):
            limits = result.get("rateLimits") or {}

        short: tuple[int, int | None] | None = None
        week: tuple[int, int | None] | None = None
        unknown: list[tuple[int, int | None]] = []
        for key in ("primary", "secondary"):
            window = limits.get(key) if isinstance(limits, dict) else None
            if not isinstance(window, dict) or "usedPercent" not in window:
                continue
            remaining = max(0, min(100, 100 - int(window["usedPercent"])))
            resets_at = window.get("resetsAt")
            resets_at = int(resets_at) if resets_at is not None else None
            duration = window.get("windowDurationMins")
            item = (remaining, resets_at)
            if duration is None:
                unknown.append(item)
            elif int(duration) < 24 * 60:
                short = item
            else:
                week = item
        if short is None and unknown:
            short = unknown.pop(0)
        if week is None and unknown:
            week = unknown.pop(0)
        return QuotaSnapshot(
            short_remaining_percent=short[0] if short else None,
            week_remaining_percent=week[0] if week else None,
            short_resets_at=short[1] if short else None,
            week_resets_at=week[1] if week else None,
            updated_at=int(time.time()),
            source="codex_app_server",
        )


class ReporterState:
    def __init__(self, identity: dict[str, str], collector: MetricsCollector,
                 agent_monitor: CodexAgentMonitor,
                 quota_collector: CodexQuotaCollector,
                 media_monitor: NeteaseMediaMonitor, http_port: int = HTTP_PORT) -> None:
        self.http_port = http_port
        self.reporter_id = identity["reporter_id"]
        self.computer_name = identity["computer_name"]
        self.pairing_token = identity["pairing_token"]
        self.pairing_hash = hashlib.sha256(self.pairing_token.encode("utf-8")).hexdigest()
        self.collector = collector
        self.agent_monitor = agent_monitor
        self.quota_collector = quota_collector
        self.media_monitor = media_monitor
        self.started_at = int(time.time())
        self._devices_lock = threading.Lock()
        self._devices = {}

    def record_device(self, peer_ip: str, board_id: str = "") -> None:
        if peer_ip.startswith("127."):
            return
        now = time.monotonic()
        with self._devices_lock:
            self._devices = {ip: entry for ip, entry in self._devices.items()
                             if now - entry["seen"] < 15}
            self._devices[peer_ip] = {"seen": now, "board_id": board_id[:32]}
            if len(self._devices) > 32:
                oldest = min(self._devices, key=lambda ip: self._devices[ip]["seen"])
                del self._devices[oldest]

    def recent_devices(self) -> list[dict[str, Any]]:
        now = time.monotonic()
        with self._devices_lock:
            return [{"ip": ip, "last_seen_seconds": round(now - entry["seen"], 1)}
                    for ip, entry in self._devices.items() if now - entry["seen"] < 15]

    def _agent_snapshot(self) -> AgentSnapshot:
        if self.quota_collector.snapshot().source == "login_required":
            return AgentSnapshot(state="login_required", task="请登录 Codex", source="auth")
        return self.agent_monitor.snapshot()

    def status(self) -> dict[str, Any]:
        return {
            "version": PROTOCOL_VERSION,
            "reporter_id": self.reporter_id,
            "pairing_hash": self.pairing_hash,
            "computer_name": self.computer_name,
            "online": True,
            "timestamp": int(time.time()),
            "service": {"pid": os.getpid(), "started_at": self.started_at},
            "devices": self.recent_devices(),
            "performance": asdict(self.collector.snapshot()),
            "agent": asdict(self._agent_snapshot()),
            "codex_quota": asdict(self.quota_collector.snapshot()),
            "media": asdict(self.media_monitor.snapshot()),
        }

    def discovery(self, peer_ip: str) -> dict[str, Any]:
        agent = self._agent_snapshot()
        quota = self.quota_collector.snapshot()
        media = self.media_monitor.snapshot()
        return {
            "type": "AI_PANEL_REPORTER_V1",
            "version": PROTOCOL_VERSION,
            "reporter_id": self.reporter_id,
            "pairing_hash": self.pairing_hash,
            "computer_name": self.computer_name,
            "agent_state": agent.state,
            "agent_task": agent.task,
            "agent_count": agent.active_count,
            "codex_login_required": agent.state == "login_required" or
                                      quota.source == "login_required",
            "codex_short_remaining": quota.short_remaining_percent
            if quota.short_remaining_percent is not None else -1,
            "codex_week_remaining": quota.week_remaining_percent
            if quota.week_remaining_percent is not None else -1,
            "codex_quota_stale": quota.stale,
            "media_available": media.available,
            "media_source": media.source,
            "media_title": media.title[:48],
            "media_artist": media.artist[:32],
            "media_status": media.playback_status,
            "media_position": media.position_seconds,
            "media_duration": media.duration_seconds,
            "media_lyric": media.lyric[:64],
            "performance": asdict(self.collector.snapshot()),
            "ip": local_ip_for(peer_ip),
            "http_port": self.http_port,
        }


def make_handler(state: ReporterState):
    class Handler(BaseHTTPRequestHandler):
        server_version = "AIPanelReporter/0.1"

        def do_GET(self) -> None:  # noqa: N802
            if os.environ.get("AI_PANEL_REPORTER_LOG_REQUESTS") == "1":
                print(f"HTTP {self.client_address[0]} {self.path}", flush=True)
            if self.path in ("/", "/api/v1/health"):
                self._send_json({"ok": True, "service": "ai-panel-reporter", "version": PROTOCOL_VERSION})
            elif self.path == "/api/v1/status":
                self._send_json(state.status())
            elif self.path == "/api/v1/pairing" and self.client_address[0] in {"127.0.0.1", "::1"}:
                self._send_json({"pairing_token": state.pairing_token})
            else:
                self._send_json({"error": "not_found"}, status=404)

        def _send_json(self, payload: dict[str, Any], status: int = 200) -> None:
            body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, format: str, *args: Any) -> None:
            return

    return Handler


class DiscoveryServer:
    def __init__(self, state: ReporterState) -> None:
        self._state = state
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run_guarded, name="discovery", daemon=True)

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        self._thread.join(timeout=2)

    def _run_guarded(self) -> None:
        try:
            self._run()
        except Exception:
            logging.exception("Discovery server stopped unexpectedly")
            if not self._stop.is_set():
                # A silent dead discovery thread leaves HTTP looking healthy
                # while every panel is offline. Exit the worker so the
                # supervisor can rebuild the complete service.
                os._exit(70)

    def _run(self) -> None:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        sock.bind(("0.0.0.0", DISCOVERY_PORT))
        sock.settimeout(0.5)
        try:
            while not self._stop.is_set():
                try:
                    payload, address = sock.recvfrom(1024)
                except socket.timeout:
                    continue
                request = payload.strip()
                board_id = ""
                if request != DISCOVERY_REQUEST:
                    try:
                        decoded = json.loads(request.decode("utf-8"))
                    except (UnicodeDecodeError, ValueError):
                        continue
                    if not isinstance(decoded, dict) or decoded.get("type") != DISCOVERY_REQUEST.decode("ascii"):
                        continue
                    board_id = str(decoded.get("board_id") or "")
                self._state.record_device(address[0], board_id)
                response = json.dumps(
                    self._state.discovery(address[0]),
                    ensure_ascii=False,
                    separators=(",", ":"),
                ).encode("utf-8")
                sock.sendto(response, address)
        finally:
            sock.close()


class ReporterHTTPServer(ThreadingHTTPServer):
    def server_bind(self) -> None:
        # HTTPServer resolves getfqdn() here. On macOS, a missing local DNS/mDNS
        # record can block startup before any collector or discovery thread runs.
        socketserver.TCPServer.server_bind(self)
        self.server_name = self.server_address[0]
        self.server_port = self.server_address[1]


def run_worker(port: int) -> int:
    identity = load_identity()
    collector = MetricsCollector()
    agent_monitor = CodexAgentMonitor()
    quota_collector = CodexQuotaCollector()
    media_monitor = NeteaseMediaMonitor()
    state = ReporterState(identity, collector, agent_monitor, quota_collector, media_monitor, port)
    discovery = DiscoveryServer(state)
    http_server = ReporterHTTPServer(("0.0.0.0", port), make_handler(state))
    http_server.daemon_threads = True

    collector.start()
    quota_collector.start()
    media_monitor.start()
    discovery.start()
    print(f"Reporter ID: {state.reporter_id}", flush=True)
    print(f"Computer: {state.computer_name}", flush=True)
    print(f"HTTP: http://127.0.0.1:{port}/api/v1/status", flush=True)
    print(f"Discovery UDP: {DISCOVERY_PORT}", flush=True)
    try:
        http_server.serve_forever(poll_interval=0.25)
    except KeyboardInterrupt:
        pass
    finally:
        http_server.shutdown()
        http_server.server_close()
        discovery.stop()
        quota_collector.stop()
        media_monitor.stop()
        collector.stop()
    return 0


def worker_command(port: int) -> list[str]:
    if getattr(sys, "frozen", False):
        return [sys.executable, "--worker", "--port", str(port)]
    return [sys.executable, str(Path(__file__).resolve()), "--worker", "--port", str(port)]


def supervise(port: int) -> int:
    """Restart the serving worker after crashes with a bounded backoff."""
    backoff = 1.0
    while True:
        started = time.monotonic()
        logging.info("Starting Reporter worker")
        try:
            process = subprocess.Popen(
                worker_command(port),
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            exit_code = process.wait()
        except KeyboardInterrupt:
            if "process" in locals() and process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=8)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()
            return 0
        except OSError as error:
            exit_code = -1
            logging.exception("Could not start Reporter worker: %s", error)
        runtime = time.monotonic() - started
        logging.warning("Reporter worker exited with %s after %.1fs", exit_code, runtime)
        backoff = 1.0 if runtime >= 30 else min(backoff * 2, 30.0)
        try:
            time.sleep(backoff)
        except KeyboardInterrupt:
            return 0


def acquire_single_instance(role: str):
    if os.name != "nt":
        return acquire_posix_instance(role)
    handle = ctypes.windll.kernel32.CreateMutexW(None, False, f"Local\\SynaReporter-{role}")
    if not handle or ctypes.windll.kernel32.GetLastError() == 183:
        if handle:
            ctypes.windll.kernel32.CloseHandle(handle)
        return None
    return handle


def self_test() -> int:
    identity = load_identity()
    assert identity["reporter_id"] == load_identity()["reporter_id"]
    assert len(hashlib.sha256(identity["pairing_token"].encode()).hexdigest()) == 64
    print(json.dumps({
        "ok": True,
        "reporter_id": identity["reporter_id"],
        "codex_logged_in": codex_auth_available(),
    }, ensure_ascii=False))
    return 0


def main() -> int:
    if os.name == "nt" and len(sys.argv) == 1:
        from windows_ui import run
        return run()
    if os.name != "nt":
        def terminate(signum, frame):
            raise KeyboardInterrupt
        signal.signal(signal.SIGTERM, terminate)
    parser = argparse.ArgumentParser(description="Syna 状态屏 Reporter（Windows / macOS）")
    parser.add_argument("--port", type=int, default=HTTP_PORT)
    parser.add_argument("--worker", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--no-supervisor", action="store_true")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    configure_logging()
    if args.self_test:
        return self_test()
    role = "worker" if args.worker or args.no_supervisor else "supervisor"
    instance = acquire_single_instance(role)
    if instance is None:
        logging.info("A %s instance is already running", role)
        return 0
    if args.worker or args.no_supervisor:
        return run_worker(args.port)
    return supervise(args.port)


if __name__ == "__main__":
    raise SystemExit(main())
