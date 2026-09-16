# Syna project-specific code and modifications: Copyright (c) 2026 黑沐.
# SPDX-License-Identifier: MIT; third-party notices remain applicable.
import unittest
import os
import psutil
import asyncio
import threading

from media_monitor import lyric_at, parse_lrc, NeteaseLocalState
from media_monitor import NeteaseMediaMonitor
from unittest.mock import patch, Mock


class AsyncMetadataTests(unittest.IsolatedAsyncioTestCase):
    def monitor(self, duration=200):
        monitor = NeteaseMediaMonitor()
        monitor._mac = None
        monitor._cdp = Mock()
        monitor._cdp.read.return_value = None
        monitor._local = Mock()
        monitor._local.read.return_value = dict(title="Old", artist="Artist", song_id=1,
            playback_status="playing", position=0, duration=duration)
        return monitor

    async def test_slow_lyrics_do_not_block_switch_pause_or_leak_old_song(self):
        monitor = self.monitor()
        release = threading.Event()
        def resolve(title, artist, song):
            release.wait(3)
            return song, [(0, title + " lyric")]
        monitor._resolver.resolve = resolve
        try:
            first = await asyncio.wait_for(monitor._read(None), 0.5)
            self.assertEqual((first.title, first.playback_status, first.song_id), ("Old", "playing", 1))
            monitor._local.read.return_value.update(title="New", song_id=2, playback_status="paused", position=42)
            new = await asyncio.wait_for(monitor._read(None), 0.5)
            self.assertEqual((new.title, new.playback_status, new.position_seconds, new.song_id), ("New", "paused", 42, 2))
            self.assertEqual(new.lyric, "暂无歌词")
            release.set()
            await monitor._lyrics_task
            new = await monitor._read(None)
            self.assertNotEqual(new.lyric, "Old lyric")
            await monitor._lyrics_task
            self.assertEqual((await monitor._read(None)).lyric, "New lyric")
        finally:
            release.set()
            if monitor._lyrics_task is not None:
                await monitor._lyrics_task

    async def test_slow_duration_does_not_block_or_apply_to_different_song(self):
        monitor = self.monitor(duration=0)
        release = threading.Event()
        monitor._resolver.resolve = lambda title, artist, song: (song, [])
        def duration(song):
            release.wait(3)
            return 100 + song
        monitor._resolver.duration_seconds = duration
        try:
            first = await asyncio.wait_for(monitor._read(None), 0.5)
            self.assertEqual(first.duration_seconds, 0)
            monitor._local.read.return_value.update(title="New", song_id=2)
            new = await asyncio.wait_for(monitor._read(None), 0.5)
            self.assertEqual((new.title, new.duration_seconds), ("New", 0))
            release.set()
            await monitor._duration_task
            new = await monitor._read(None)
            self.assertEqual(new.duration_seconds, 0)
            await monitor._duration_task
            self.assertEqual((await monitor._read(None)).duration_seconds, 102)
        finally:
            release.set()
            for task in (monitor._lyrics_task, monitor._duration_task):
                if task is not None:
                    await task


@unittest.skipUnless(os.name == "nt", "Windows audio sessions")
class AudioSessionTests(unittest.TestCase):
    def test_stale_session_does_not_hide_playing_netease(self):
        stale = Mock()
        stale.Process.name.side_effect = psutil.NoSuchProcess(42)
        live = Mock()
        live.Process.name.return_value = "cloudmusic.exe"
        live.State = 1
        live._ctl.QueryInterface.return_value.GetPeakValue.return_value = 0.5
        with patch("media_monitor.comtypes.CoInitializeEx") as init, \
                patch("media_monitor.comtypes.CoUninitialize") as uninit, \
                patch("media_monitor.AudioUtilities.GetAllSessions", return_value=[stale, live]):
            self.assertEqual(NeteaseLocalState._audio_session_sample(), (True, 0.5))
        init.assert_called_once()
        uninit.assert_called_once()

    def test_com_is_released_when_enumeration_fails(self):
        with patch("media_monitor.comtypes.CoInitializeEx"), \
                patch("media_monitor.comtypes.CoUninitialize") as uninit, \
                patch("media_monitor.AudioUtilities.GetAllSessions", side_effect=OSError("device lost")):
            self.assertIsNone(NeteaseLocalState._audio_session_sample())
        uninit.assert_called_once()

    def test_existing_apartment_is_not_uninitialized(self):
        error = OSError("existing STA")
        error.hresult = -2147417850
        with patch("media_monitor.comtypes.CoInitializeEx", side_effect=error), \
                patch("media_monitor.comtypes.CoUninitialize") as uninit, \
                patch("media_monitor.AudioUtilities.GetAllSessions", return_value=[]):
            self.assertIsNone(NeteaseLocalState._audio_session_sample())
        uninit.assert_not_called()

    def test_play_pause_and_resume_follow_samples(self):
        local = NeteaseLocalState()
        with patch.object(local, "_audio_session_sample", side_effect=[(True, 0.5), (True, 0), (True, 0), (True, 0.5)]), \
                patch("media_monitor.time.monotonic", side_effect=[100, 100.4, 101, 102]):
            self.assertEqual([local._read_playback_status() for _ in range(4)],
                             ["playing", "playing", "paused", "playing"])


class WindowTitleTests(unittest.TestCase):
    def test_desktop_lyrics_does_not_replace_song_in_either_order(self):
        song = "Episode 33 - She Her Her Hers"
        for titles in (["桌面歌词", song], [song, "桌面歌词"]):
            self.assertEqual(NeteaseLocalState._select_window_title(titles), song)

    def test_auxiliary_windows_alone_are_not_tracks(self):
        self.assertEqual(NeteaseLocalState._select_window_title(
            ["网易云音乐", "桌面歌词", "设置", "Desktop Lyrics"]), "")

    def test_known_track_takes_priority_over_other_window(self):
        self.assertEqual(NeteaseLocalState._select_window_title(
            ["帮助 - 网易云音乐", "Episode 33 - She Her Her Hers"],
            [{"name": "Episode 33"}]), "Episode 33 - She Her Her Hers")

    def test_known_title_without_artist_is_supported(self):
        self.assertEqual(NeteaseLocalState._select_window_title(
            ["桌面歌词", "Episode 33"], [{"name": "Episode 33"}]), "Episode 33")

    def test_read_refreshes_playlist_before_selecting_window(self):
        local = NeteaseLocalState()
        tracks = [{"name": "Episode 33", "id": 123, "duration": 258000}]
        def refresh():
            local._tracks = tracks
        with patch.object(local, "_refresh_tracks", side_effect=refresh), \
                patch.object(local, "_window_title", return_value="Episode 33") as title, \
                patch.object(local, "_read_playback_status", return_value="paused"), \
                patch.object(local, "_read_position_checkpoint", return_value=0):
            snapshot = local.read()
        title.assert_called_once_with(tracks)
        self.assertEqual(snapshot["title"], "Episode 33")


class LyricsTests(unittest.TestCase):
    def test_parse_and_select_current_line(self):
        lines = parse_lrc("[00:01.00]第一句\n[00:03.500][00:05.00]第二句")
        self.assertEqual([(1.0, "第一句"), (3.5, "第二句"), (5.0, "第二句")], lines)
        self.assertEqual("♪", lyric_at(lines, 0.5))
        self.assertEqual("第一句", lyric_at(lines, 2.0))
        self.assertEqual("第二句", lyric_at(lines, 4.0))

    def test_empty_lyrics(self):
        self.assertEqual("暂无歌词", lyric_at([], 10))


if __name__ == "__main__":
    unittest.main()
