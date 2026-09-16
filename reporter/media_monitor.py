# Syna project-specific code and modifications: Copyright (c) 2026 黑沐.
# SPDX-License-Identifier: MIT; third-party notices remain applicable.
from __future__ import annotations

import asyncio
import bisect
import ctypes
import json
import os
import re
import sqlite3
import sys
import threading
import time
import unicodedata
import urllib.parse
import urllib.request
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import websocket
import psutil
from macos_media import MacNeteaseTimeline
if os.name == "nt":
    import comtypes
    from pycaw.pycaw import AudioUtilities, IAudioMeterInformation


_NETEASE_HEADERS = {
    "User-Agent": "Mozilla/5.0 AI-Agent-Panel-Reporter/0.1",
    "Referer": "https://music.163.com/",
}
_TIMESTAMP_RE = re.compile(r"\[(\d{1,3}):(\d{1,2})(?:[.:](\d{1,3}))?\]")
_CACHE_ID_RE = re.compile(r"^(\d+)-")


class NeteaseCdpTimeline:
    """Read NetEase's player state directly when the local CDP channel is enabled."""

    def read(self) -> dict[str, Any] | None:
        try:
            with urllib.request.urlopen("http://127.0.0.1:9223/json", timeout=0.25) as response:
                targets = json.load(response)
            target = next(
                item for item in targets
                if item.get("type") == "page"
                and str(item.get("url") or "").startswith("orpheus://")
            )
            connection = websocket.create_connection(
                target["webSocketDebuggerUrl"], timeout=0.4, suppress_origin=True
            )
            try:
                connection.send(json.dumps({
                    "id": 1,
                    "method": "Runtime.evaluate",
                    "params": {
                        "expression": (
                            "(()=>{"
                            "const xs=[...document.querySelectorAll('audio')];"
                            "const a=xs.find(x=>!x.paused)||xs[0]||null;"
                            "let current=null,state='';"
                            "try{"
                            "if(typeof window.__ai_panel_require__!=='function'){"
                            "window.webpackJsonp.push([[],{'__ai_panel__':function(m,e,r){"
                            "window.__ai_panel_require__=r;}},[['__ai_panel__']]]);"
                            "}"
                            "const mod=window.__ai_panel_require__(12);"
                            "const root=mod&&(mod.a||mod.default||mod);"
                            "const store=root&&root.getStore?root.getStore():null;"
                            "current=store&&store.playing&&store.playing.curPlaying;"
                            "state=String(store&&store.playing&&store.playing.playingState||'');"
                            "}catch(e){}"
                            "const track=current&&(current.track||current.resource||{});"
                            "const artists=track&&(track.artists||track.ar)||[];"
                            "const stateLower=state.toLowerCase();"
                            "let status=a?(a.ended?'stopped':(a.paused?'paused':'playing')):'stopped';"
                            "if(!a&&(/play|playing/.test(stateLower)||state==='1'))status='playing';"
                            "return {position:a?(Number(a.currentTime)||0):0,"
                            "duration:a?(Number(a.duration)||0):0,"
                            "title:String(track&&track.name||current&&current.name||''),"
                            "artist:artists.map(x=>x&&x.name||'').filter(Boolean).join(' / '),"
                            "song_id:Number(current&&(current.resourceId||current.id)||track&&track.id)||null,"
                            "playback_status:status};})()"
                        ),
                        "returnByValue": True,
                    },
                }))
                while True:
                    message = json.loads(connection.recv())
                    if message.get("id") == 1:
                        value = (((message.get("result") or {}).get("result") or {}).get("value"))
                        if isinstance(value, dict):
                            value["position"] = max(0.0, float(value.get("position") or 0))
                            value["duration"] = max(0.0, float(value.get("duration") or 0))
                            return value
                        return None
            finally:
                connection.close()
        except Exception:
            return None


class NeteaseLocalState:
    """Fallback for builds that disable GSMTC and were started without CDP."""

    def __init__(self) -> None:
        self._path = (
            Path(os.environ.get("LOCALAPPDATA", ""))
            / "NetEase" / "CloudMusic" / "webdata" / "file" / "playingList"
        )
        self._mtime = -1.0
        self._tracks: list[dict[str, Any]] = []
        self._db_path = (
            Path(os.environ.get("LOCALAPPDATA", ""))
            / "NetEase" / "CloudMusic" / "Library" / "webdb.dat"
        )
        self._last_sound_at = 0.0
        self._playback_status = "paused"
        self._checkpoint_update: dict[int, int] = {}
        self._checkpoint_checked_at = 0.0

    def read(self) -> dict[str, Any] | None:
        self._refresh_tracks()
        window_title = self._window_title(self._tracks)
        if not window_title or window_title in ("网易云音乐", "NetEase CloudMusic"):
            return None
        playback_status = self._read_playback_status()
        matches = []
        for track in self._tracks:
            name = str(track.get("name") or "").strip()
            if name and (window_title == name or window_title.startswith(name + " - ")):
                matches.append(track)
        track = max(matches, key=lambda item: len(str(item.get("name") or "")), default=None)
        if track is None:
            parts = window_title.rsplit(" - ", 1)
            return {
                "position": 0.0,
                "duration": 0.0,
                "title": parts[0].strip(),
                "artist": parts[1].strip() if len(parts) > 1 else "",
                "song_id": None,
                "playback_status": playback_status,
            }
        artists = track.get("artists") or track.get("ar") or []
        song_id = int(track["id"]) if str(track.get("id") or "").isdigit() else None
        return {
            "position": self._read_position_checkpoint(song_id),
            "duration": max(0.0, float(track.get("duration") or 0) / 1000.0),
            "title": str(track.get("name") or "").strip(),
            "artist": " / ".join(
                str(item.get("name") or "").strip()
                for item in artists if isinstance(item, dict) and item.get("name")
            ),
            "song_id": song_id,
            "playback_status": playback_status,
        }

    def _read_playback_status(self) -> str:
        """Use the live stream meter instead of Core Audio's delayed state flag."""
        now = time.monotonic()
        sample = self._audio_session_sample()
        if sample is None:
            return self._playback_status
        active, peak = sample
        if peak > 0.00001:
            self._last_sound_at = now
            self._playback_status = "playing"
        elif active is False or now - self._last_sound_at >= 0.8:
            self._playback_status = "paused"
        return self._playback_status

    @staticmethod
    def _audio_session_sample() -> tuple[bool, float] | None:
        initialized = False
        try:
            try:
                comtypes.CoInitializeEx(comtypes.COINIT_MULTITHREADED)
                initialized = True
            except OSError as error:
                # An existing STA apartment is usable; do not uninitialize it.
                code = getattr(error, "hresult", getattr(error, "winerror", 0))
                if code != -2147417850:  # RPC_E_CHANGED_MODE
                    raise
            return NeteaseLocalState._initialized_audio_session_sample()
        except (OSError, psutil.Error, RuntimeError):
            return None
        finally:
            if initialized:
                comtypes.CoUninitialize()

    @staticmethod
    def _initialized_audio_session_sample() -> tuple[bool, float] | None:
        # Keep COM objects within this call so they are released before teardown.
        found = False
        active = False
        peak = 0.0
        for session in AudioUtilities.GetAllSessions():
            try:
                process = session.Process
                if process is None or process.name().casefold() != "cloudmusic.exe":
                    continue
                found = True
                active = active or int(session.State) == 1
                try:
                    meter = session._ctl.QueryInterface(IAudioMeterInformation)
                    peak = max(peak, float(meter.GetPeakValue()))
                except Exception:
                    pass
            except (OSError, psutil.Error, RuntimeError):
                # Windows can retain sessions whose processes have already exited.
                continue
        return (active, peak) if found else None

    def _read_position_checkpoint(self, song_id: int | None) -> float:
        """Consume NetEase's pause/end checkpoint once, then let the clock run."""
        now = time.monotonic()
        if song_id is None or now - self._checkpoint_checked_at < 0.5:
            return 0.0
        self._checkpoint_checked_at = now
        try:
            uri = "file:" + self._db_path.as_posix() + "?mode=ro"
            with sqlite3.connect(uri, uri=True, timeout=0.2) as connection:
                row = connection.execute(
                    "SELECT playDuration, updateTime FROM playingCount "
                    "WHERE resourceId=? ORDER BY id DESC LIMIT 1",
                    (str(song_id),),
                ).fetchone()
            if not row:
                return 0.0
            duration, updated_at = int(row[0] or 0), int(row[1] or 0)
            process_starts = [
                process.create_time() * 1000
                for process in psutil.process_iter(["name", "create_time"])
                if str(process.info.get("name") or "").casefold() == "cloudmusic.exe"
            ]
            if process_starts and updated_at < min(process_starts) - 5000:
                return 0.0
            if self._checkpoint_update.get(song_id) == updated_at:
                return 0.0
            self._checkpoint_update[song_id] = updated_at
            return max(0.0, float(duration))
        except (OSError, sqlite3.Error, ValueError):
            return 0.0

    def _refresh_tracks(self) -> None:
        try:
            mtime = self._path.stat().st_mtime
            if mtime == self._mtime:
                return
            data = json.loads(self._path.read_text(encoding="utf-8"))
            self._tracks = [
                item.get("track") or {} for item in data.get("list") or []
                if isinstance(item, dict)
            ]
            self._mtime = mtime
        except (OSError, ValueError, json.JSONDecodeError):
            self._tracks = []

    @staticmethod
    def _select_window_title(titles: list[str], tracks=()) -> str:
        auxiliary = {"网易云音乐", "netease cloudmusic", "桌面歌词",
                     "网易云音乐桌面歌词", "desktop lyrics"}
        candidates = [title.strip() for title in titles
                      if title.strip() and title.strip().casefold() not in auxiliary]
        # Prefer a known track over auxiliary windows regardless of Z-order.
        for title in candidates:
            for track in tracks:
                name = str(track.get("name") or "").strip()
                if name and (title == name or title.startswith(name + " - ")):
                    return title
        # Without a playlist match, only accept the player's song/artist form.
        return next((title for title in candidates
                     if " - " in title and all(part.strip() for part in title.rsplit(" - ", 1))), "")

    @staticmethod
    def _window_title(tracks=()) -> str:
        try:
            pids = {
                process.pid for process in psutil.process_iter(["name"])
                if str(process.info.get("name") or "").casefold() == "cloudmusic.exe"
            }
            if not pids:
                return ""
            titles: list[str] = []
            user32 = ctypes.windll.user32
            callback_type = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)

            @callback_type
            def collect(hwnd: int, _lparam: int) -> bool:
                pid = ctypes.c_ulong()
                user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
                if pid.value not in pids or not user32.IsWindowVisible(hwnd):
                    return True
                length = user32.GetWindowTextLengthW(hwnd)
                if length:
                    buffer = ctypes.create_unicode_buffer(length + 1)
                    user32.GetWindowTextW(hwnd, buffer, length + 1)
                    if buffer.value.strip():
                        titles.append(buffer.value.strip())
                return True

            user32.EnumWindows(collect, 0)
            return NeteaseLocalState._select_window_title(titles, tracks)
        except (OSError, psutil.Error):
            return ""


@dataclass
class MediaSnapshot:
    available: bool = False
    source: str = "netease_cloud_music"
    title: str = ""
    artist: str = ""
    playback_status: str = "stopped"
    position_seconds: int = 0
    duration_seconds: int = 0
    lyric: str = ""
    song_id: int | None = None
    updated_at: int = 0


def parse_lrc(text: str) -> list[tuple[float, str]]:
    lines: list[tuple[float, str]] = []
    for raw_line in text.splitlines():
        stamps = list(_TIMESTAMP_RE.finditer(raw_line))
        if not stamps:
            continue
        content = _TIMESTAMP_RE.sub("", raw_line).strip()
        if not content:
            continue
        for stamp in stamps:
            fraction = stamp.group(3) or "0"
            fraction_seconds = int(fraction) / (10 ** len(fraction))
            seconds = int(stamp.group(1)) * 60 + int(stamp.group(2)) + fraction_seconds
            lines.append((seconds, content))
    lines.sort(key=lambda item: item[0])
    return lines


def lyric_at(lines: list[tuple[float, str]], position_seconds: float) -> str:
    if not lines:
        return "暂无歌词"
    index = bisect.bisect_right([item[0] for item in lines], position_seconds) - 1
    return lines[index][1] if index >= 0 else "♪"


def _normalized(value: str) -> str:
    value = unicodedata.normalize("NFKC", value).casefold()
    return "".join(character for character in value if character.isalnum())


def _artists(song: dict[str, Any]) -> list[str]:
    artists = song.get("artists") or song.get("ar") or []
    return [str(item.get("name") or "") for item in artists if isinstance(item, dict)]


def _matches(song: dict[str, Any], title: str, artist: str) -> bool:
    if _normalized(str(song.get("name") or "")) != _normalized(title):
        return False
    wanted_artist = _normalized(artist)
    if not wanted_artist:
        return True
    actual = _normalized(" ".join(_artists(song)))
    return wanted_artist in actual or actual in wanted_artist


class NeteaseLyricsResolver:
    def __init__(self) -> None:
        self._key: tuple[str, str, int | None] | None = None
        self._song_id: int | None = None
        self._lines: list[tuple[float, str]] = []

    def resolve(
        self, title: str, artist: str, song_id_hint: int | None = None
    ) -> tuple[int | None, list[tuple[float, str]]]:
        key = (title.strip(), artist.strip(), song_id_hint)
        if key == self._key:
            return self._song_id, self._lines
        self._key = key
        self._song_id = None
        self._lines = []
        if not key[0]:
            return None, []
        try:
            song_id = song_id_hint or self._find_cached_song(key[0], key[1])
            if song_id is None:
                song_id = self._search_song(key[0], key[1])
            if song_id is not None:
                data = self._get_json(
                    "https://music.163.com/api/song/lyric?"
                    + urllib.parse.urlencode({"id": song_id, "lv": -1, "kv": -1, "tv": -1})
                )
                self._song_id = song_id
                self._lines = parse_lrc(str((data.get("lrc") or {}).get("lyric") or ""))
        except (OSError, ValueError, TimeoutError, json.JSONDecodeError):
            pass
        return self._song_id, self._lines

    def duration_seconds(self, song_id: int | None) -> int:
        if song_id is None:
            return 0
        try:
            data = self._get_json(
                "https://music.163.com/api/song/detail?"
                + urllib.parse.urlencode({"ids": f"[{song_id}]"})
            )
            songs = data.get("songs") or []
            if songs:
                return max(0, round(float(songs[0].get("duration") or 0) / 1000.0))
        except (OSError, ValueError, TimeoutError, json.JSONDecodeError):
            pass
        return 0

    def _find_cached_song(self, title: str, artist: str) -> int | None:
        if os.name != "nt":
            return None
        cache = Path(os.environ.get("LOCALAPPDATA", "")) / "Netease" / "CloudMusic" / "Cache" / "Cache"
        candidates: dict[int, float] = {}
        try:
            for entry in os.scandir(cache):
                match = _CACHE_ID_RE.match(entry.name)
                if match:
                    candidates[int(match.group(1))] = max(
                        candidates.get(int(match.group(1)), 0.0), entry.stat().st_mtime
                    )
        except OSError:
            return None
        ids = [item[0] for item in sorted(candidates.items(), key=lambda item: item[1], reverse=True)[:40]]
        if not ids:
            return None
        data = self._get_json(
            "https://music.163.com/api/song/detail?"
            + urllib.parse.urlencode({"ids": "[" + ",".join(map(str, ids)) + "]"})
        )
        for song in data.get("songs") or []:
            if _matches(song, title, artist):
                return int(song["id"])
        return None

    def _search_song(self, title: str, artist: str) -> int | None:
        body = urllib.parse.urlencode(
            {"s": f"{title} {artist}".strip(), "type": 1, "limit": 30, "offset": 0}
        ).encode("utf-8")
        data = self._get_json("https://music.163.com/api/search/get", body)
        for song in (data.get("result") or {}).get("songs") or []:
            if _matches(song, title, artist):
                return int(song["id"])
        return None

    @staticmethod
    def _get_json(url: str, body: bytes | None = None) -> dict[str, Any]:
        request = urllib.request.Request(url, data=body, headers=_NETEASE_HEADERS)
        with urllib.request.urlopen(request, timeout=6) as response:
            return json.load(response)


class NeteaseMediaMonitor:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._snapshot = MediaSnapshot()
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, name="netease-media", daemon=True)
        self._resolver = NeteaseLyricsResolver()
        self._cdp = NeteaseCdpTimeline()
        self._mac = MacNeteaseTimeline() if sys.platform == "darwin" else None
        self._lyrics_task: asyncio.Task | None = None
        self._lyrics_key: tuple | None = None
        self._local = NeteaseLocalState() if os.name == "nt" else None
        self._clock_title = ""
        self._clock_status = "stopped"
        self._clock_position = 0.0
        self._clock_updated = time.monotonic()
        self._duration_cache: dict[int, int] = {}
        self._duration_task: asyncio.Task | None = None
        self._duration_song_id: int | None = None

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        self._thread.join(timeout=3)

    def snapshot(self) -> MediaSnapshot:
        with self._lock:
            return MediaSnapshot(**asdict(self._snapshot))

    def _run(self) -> None:
        try:
            asyncio.run(self._poll())
        except Exception:
            with self._lock:
                self._snapshot = MediaSnapshot(updated_at=int(time.time()))

    async def _poll(self) -> None:
        manager = None
        if os.name == "nt":
            from winrt.windows.media.control import GlobalSystemMediaTransportControlsSessionManager
            manager = await GlobalSystemMediaTransportControlsSessionManager.request_async()
        while not self._stop.is_set():
            snapshot = await self._read(manager)
            with self._lock:
                self._snapshot = snapshot
            await asyncio.sleep(0.2)

    async def _read(self, manager: Any) -> MediaSnapshot:
        precise = await asyncio.to_thread(self._mac.read if self._mac is not None else self._cdp.read)
        if self._local is not None and (precise is None or not precise.get("title")):
            local = await asyncio.to_thread(self._local.read)
            if local is not None:
                precise = local
        session = next(
            (
                item for item in (manager.get_sessions() if manager is not None else [])
                if any(token in item.source_app_user_model_id.casefold()
                       for token in ("cloudmusic", "netease", "网易云音乐"))
            ),
            None,
        )
        if session is None and precise is None:
            return MediaSnapshot(updated_at=int(time.time()))
        try:
            title = str((precise or {}).get("title") or "").strip()
            artist = str((precise or {}).get("artist") or "").strip()
            status = str((precise or {}).get("playback_status") or "stopped")
            position = float((precise or {}).get("position") or 0)
            duration = float((precise or {}).get("duration") or 0)
            timeline = None
            if session is not None:
                properties = await session.try_get_media_properties_async()
                timeline = session.get_timeline_properties()
                playback = session.get_playback_info()
                if not title:
                    title = str(properties.title or "").strip()
                if not artist:
                    artist = str(properties.artist or "").strip()
                if precise is None:
                    status_value = int(playback.playback_status)
                    status = {4: "playing", 5: "paused"}.get(status_value, "stopped")
                    position = max(0.0, timeline.position.total_seconds())
                    duration = max(0.0, timeline.end_time.total_seconds())
            if (precise is None and status == "playing" and timeline is not None
                    and timeline.last_updated_time.year > 1601):
                position += max(
                    0.0,
                    (datetime.now(timezone.utc) - timeline.last_updated_time).total_seconds(),
                )
            if duration > 0:
                position = min(position, duration)
            song_id_hint = (
                int(precise["song_id"])
                if precise is not None and precise.get("song_id") else None
            )
            # Publish player state independently of network metadata on all OSes.
            # Keep one resolver job in flight: its cache is not thread-safe.
            key = (title, artist, song_id_hint)
            if self._lyrics_task is None or (self._lyrics_task.done() and key != self._lyrics_key):
                if self._lyrics_task is not None and not self._lyrics_task.cancelled():
                    self._lyrics_task.exception()  # Consume errors from obsolete songs.
                self._lyrics_key = key
                self._lyrics_task = asyncio.create_task(asyncio.to_thread(
                    self._resolver.resolve, title, artist, song_id_hint
                ))
            song_id, lines = song_id_hint, []
            if self._lyrics_task.done() and not self._lyrics_task.cancelled() and key == self._lyrics_key:
                try:
                    resolved_id, lines = self._lyrics_task.result()
                    song_id = resolved_id or song_id_hint
                except Exception:
                    pass
            if self._duration_task is not None and self._duration_task.done():
                try:
                    self._duration_cache[self._duration_song_id] = self._duration_task.result()
                except Exception:
                    self._duration_cache[self._duration_song_id] = 0
                self._duration_task = None
            if duration <= 0 and song_id is not None and self._mac is None:
                if song_id not in self._duration_cache and self._duration_task is None:
                    self._duration_song_id = song_id
                    self._duration_task = asyncio.create_task(asyncio.to_thread(
                        self._resolver.duration_seconds, song_id
                    ))
                duration = float(self._duration_cache.get(song_id, 0))
            if self._local is not None:
                position = self._track_position(title, status, position, duration)
            return MediaSnapshot(
                available=bool(title),
                title=title,
                artist=artist,
                playback_status=status,
                position_seconds=round(position),
                duration_seconds=round(duration),
                lyric=lyric_at(lines, position),
                song_id=song_id,
                updated_at=int(time.time()),
            )
        except Exception:
            return MediaSnapshot(updated_at=int(time.time()))

    def _track_position(
        self, title: str, status: str, reported: float, duration: float
    ) -> float:
        """Fill the zero timeline emitted by recent NetEase desktop builds.

        A real GSMTC position always wins. When NetEase reports zero, preserve a
        monotonic per-song clock across play/pause transitions so lyrics advance
        instead of remaining on the first timestamp forever.
        """
        now = time.monotonic()
        if title != self._clock_title:
            self._clock_title = title
            self._clock_position = max(0.0, reported)
        else:
            if self._clock_status == "playing":
                self._clock_position += max(0.0, now - self._clock_updated)
            if reported > 0.25:
                self._clock_position = max(0.0, reported)
        self._clock_status = status
        self._clock_updated = now
        if duration > 0:
            self._clock_position = min(self._clock_position, duration)
        return self._clock_position
