# Syna project-specific code and modifications: Copyright (c) 2026 黑沐.
# SPDX-License-Identifier: MIT; third-party notices remain applicable.
"""Apple Silicon GPU counters and read-only SMC temperatures (no sudo)."""
from __future__ import annotations

import json
import math
import plistlib
import re
import subprocess
import sys
import time
from pathlib import Path
from typing import Any
from xml.parsers.expat import ExpatError


def number(value: Any, minimum: float, maximum: float) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    result = float(value)
    return result if math.isfinite(result) and minimum <= result <= maximum else None


def gpu_from_registry(entries: Any) -> float | None:
    if not isinstance(entries, list):
        return None
    samples = []
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        stats = entry.get('PerformanceStatistics')
        if isinstance(stats, dict):
            value = number(stats.get('Device Utilization %'), 0, 100)
            if value is not None:
                samples.append(value)
    # Do not add renderer and tiler percentages: they overlap in time.
    return round(max(samples), 1) if samples else None


def temperature_groups(data: Any) -> tuple[float | None, float | None, list[str]]:
    groups: dict[str, list[float]] = {'cpu': [], 'gpu': []}
    keys = []
    if isinstance(data, dict):
        for key, raw in data.items():
            if not isinstance(key, str) or not re.fullmatch(r'T[peg][A-Za-z0-9]{2}', key):
                continue
            value = number(raw, 0.001, 129.999)
            if value is not None:
                groups['gpu' if key.startswith('Tg') else 'cpu'].append(value)
                keys.append(key)
    def average(values: list[float]) -> float | None:
        return round(sum(values) / len(values), 1) if values else None
    return average(groups['cpu']), average(groups['gpu']), keys


class MacMetrics:
    def __init__(self) -> None:
        self._next_temperature = 0.0
        self._next_discovery = 0.0
        self._keys: list[str] = []
        self._temperatures: tuple[float | None, float | None] = (None, None)
        self.probe = (Path(sys.executable).parent / 'MacThermalProbe' if getattr(sys, 'frozen', False)
                      else Path(__file__).parent / '.macos-tools' / 'MacThermalProbe')

    def read(self) -> tuple[float | None, float | None, float | None]:
        gpu = None
        try:
            result = subprocess.run(['/usr/sbin/ioreg', '-a', '-r', '-d', '1', '-c', 'AGXAccelerator'],
                                    capture_output=True, timeout=1, check=True)
            gpu = gpu_from_registry(plistlib.loads(result.stdout))
        except (OSError, ValueError, ExpatError, plistlib.InvalidFileException, subprocess.SubprocessError):
            pass
        now = time.monotonic()
        if now >= self._next_temperature:
            self._temperatures = (None, None)
            try:
                keys = self._keys if now < self._next_discovery else []
                result = subprocess.run([str(self.probe), *keys], capture_output=True,
                                        text=True, timeout=2, check=True)
                cpu, temp, available_keys = temperature_groups(json.loads(result.stdout))
                self._temperatures = cpu, temp
                self._keys = available_keys
                if not keys:
                    self._next_discovery = now + 300
            except (OSError, ValueError, subprocess.SubprocessError):
                self._keys = []
            self._next_temperature = time.monotonic() + 5
        return gpu, *self._temperatures
