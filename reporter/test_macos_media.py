# Syna project-specific code and modifications: Copyright (c) 2026 黑沐.
# SPDX-License-Identifier: MIT; third-party notices remain applicable.
import asyncio
import json
import subprocess
import unittest
from unittest.mock import patch

from macos_media import MacNeteaseTimeline
from media_monitor import NeteaseMediaMonitor


def data(**changes):
    result = dict(bundle='com.netease.163music', title='Song', artist='Artist',
                  position=30, duration=200, rate=1)
    result.update(changes)
    return result


class MacMediaTests(unittest.TestCase):
    def test_rejects_other_players_empty_and_invalid_numbers(self):
        for value in [{}, [], data(bundle='com.apple.Music'), data(title=''),
                      data(position=float('nan')), data(rate='bad')]:
            self.assertIsNone(MacNeteaseTimeline.normalize(value))

    def test_timeline_clamps_and_pauses(self):
        value = MacNeteaseTimeline.normalize(data(position=900, rate=0))
        self.assertEqual(value['position'], 200)
        self.assertEqual(value['playback_status'], 'paused')
        self.assertEqual(MacNeteaseTimeline.normalize(data(position=-9))['position'], 0)

    def test_poll_throttling_seek_pause_and_failure_clear(self):
        reader = MacNeteaseTimeline()
        def reply(**changes):
            return subprocess.CompletedProcess([], 0, json.dumps(data(**changes)))
        with patch('macos_media.time.monotonic', return_value=10) as clock, patch(
            'macos_media.subprocess.run', side_effect=[reply(), reply(position=0, rate=0),
                                                      subprocess.TimeoutExpired('osascript', 2)]
        ) as run:
            self.assertEqual(reader.read()['position'], 30)
            clock.return_value = 10.5
            self.assertEqual(reader.read()['position'], 30.5)
            self.assertEqual(run.call_count, 1)
            clock.return_value = 12
            self.assertEqual(reader.read()['position'], 0)
            clock.return_value = 12.5
            self.assertEqual(reader.read()['position'], 0)
            clock.return_value = 14
            self.assertIsNone(reader.read())

    def test_lyrics_do_not_block_or_leak_previous_track(self):
        async def check():
            monitor = NeteaseMediaMonitor()
            monitor._mac = MacNeteaseTimeline()
            pending = asyncio.get_running_loop().create_future()
            monitor._lyrics_task = pending
            monitor._lyrics_key = ('Old Song', 'Artist', None)
            with patch.object(monitor._mac, 'read', return_value=MacNeteaseTimeline.normalize(data())):
                result = await asyncio.wait_for(monitor._read(None), timeout=0.5)
                self.assertTrue(result.available)
                self.assertEqual(result.title, 'Song')
                self.assertEqual(result.position_seconds, 30)
                self.assertEqual(result.lyric, '暂无歌词')
            pending.cancel()
        asyncio.run(check())


if __name__ == '__main__':
    unittest.main()
