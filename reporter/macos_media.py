# Syna project-specific code and modifications: Copyright (c) 2026 黑沐.
# SPDX-License-Identifier: MIT; third-party notices remain applicable.
"""Read-only NetEase Now Playing bridge. No UI scripting or player control.

MediaRemote is a private, version-dependent API. Only the selected NetEase
player is accepted; unavailable/foreign media clears the result.
"""
from __future__ import annotations

import json
import math
import subprocess
import time
from typing import Any

# API references: https://gist.github.com/SKaplanOfficial/f9f5bdd6455436203d0d318c078358de
# Only Foundation/AppKit metadata APIs are used, never System Events or UI access.
_SCRIPT = r'''
ObjC.import('AppKit');
function run() {
    try {
        const apps = $.NSWorkspace.sharedWorkspace.runningApplications;
        let running = false;
        for (let i = 0; i < apps.count; i++) {
            if (ObjC.unwrap(apps.objectAtIndex(i).bundleIdentifier) === 'com.netease.163music') {
                running = true; break;
            }
        }
        if (!running) return '{}';
        $.NSBundle.bundleWithPath('/System/Library/PrivateFrameworks/MediaRemote.framework/').load;
        const request = $.NSClassFromString('MRNowPlayingRequest');
        const path = request.localNowPlayingPlayerPath;
        const bundle = ObjC.unwrap(path.client.bundleIdentifier);
        if (bundle !== 'com.netease.163music') return '{}';
        const item = request.localNowPlayingItem;
        const info = item.nowPlayingInfo;
        function field(name) { return ObjC.unwrap(info.valueForKey('kMRMediaRemoteNowPlayingInfo' + name)); }
        return JSON.stringify({
            bundle: bundle,
            title: field('Title'), artist: field('Artist'),
            duration: field('Duration'), rate: field('PlaybackRate'),
            position: Number(item.metadata.calculatedPlaybackPosition)
        });
    } catch (error) { return '{}'; }
}
'''


class MacNeteaseTimeline:
    def __init__(self) -> None:
        self._next_read = 0.0
        self._sample_at = 0.0
        self._sample: dict[str, Any] | None = None

    @staticmethod
    def normalize(data: Any) -> dict[str, Any] | None:
        if not isinstance(data, dict) or data.get('bundle') != 'com.netease.163music':
            return None
        title = str(data.get('title') or '').strip()
        if not title:
            return None
        try:
            position = float(data.get('position') or 0)
            duration = float(data.get('duration') or 0)
            rate = float(data.get('rate') or 0)
            if not all(math.isfinite(x) for x in (position, duration, rate)):
                return None
        except (ValueError, TypeError):
            return None
        duration = max(0.0, duration)
        position = max(0.0, position)
        if duration:
            position = min(position, duration)
        return dict(title=title, artist=str(data.get('artist') or '').strip(),
                    position=position, duration=duration, rate=max(0.0, rate),
                    playback_status='playing' if rate > 0 else 'paused')

    def read(self) -> dict[str, Any] | None:
        now = time.monotonic()
        if now >= self._next_read:
            try:
                result = subprocess.run(
                    ['/usr/bin/osascript', '-l', 'JavaScript', '-e', _SCRIPT],
                    capture_output=True, text=True, timeout=2, check=True,
                )
                self._sample = self.normalize(json.loads(result.stdout))
            except (OSError, subprocess.SubprocessError, ValueError):
                self._sample = None
            self._sample_at = time.monotonic()
            self._next_read = self._sample_at + 1.0
        if self._sample is None:
            return None
        sample = self._sample.copy()
        # Interpolate only between successful one-second observations. Every new
        # observation replaces the clock, including seek-to-zero and pause.
        if sample['playback_status'] == 'playing':
            sample['position'] += max(0.0, time.monotonic() - self._sample_at) * sample['rate']
            if sample['duration']:
                sample['position'] = min(sample['position'], sample['duration'])
        return sample
