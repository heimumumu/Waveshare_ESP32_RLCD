# Syna project-specific code and modifications: Copyright (c) 2026 黑沐.
# SPDX-License-Identifier: MIT; third-party notices remain applicable.
import json
import plistlib
import subprocess
import unittest
from unittest.mock import patch
from macos_metrics import MacMetrics, gpu_from_registry, temperature_groups

class MacMetricsTests(unittest.TestCase):
    def test_gpu_uses_device_counter_not_overlapping_engines(self):
        self.assertEqual(gpu_from_registry([{'PerformanceStatistics': {
            'Device Utilization %': 20, 'Renderer Utilization %': 70, 'Tiler Utilization %': 80}}]), 20)
        self.assertEqual(gpu_from_registry([{'PerformanceStatistics': {'Device Utilization %': 0}}]), 0)
        for bad in [None, {}, [{}], [{'PerformanceStatistics': {'Device Utilization %': 101}}],
                    [{'PerformanceStatistics': {'Device Utilization %': float('nan')}}]]:
            self.assertIsNone(gpu_from_registry(bad))

    def test_temperature_groups_only_valid_cpu_gpu_sensors(self):
        cpu, gpu, keys = temperature_groups({'Tp00':40, 'Te04':50, 'Tg04':30,
            'TB0T':99, 'TpAA':0, 'TpBB':float('nan'), 'TgCC':150, 'TgDD':True})
        self.assertEqual((cpu, gpu), (45, 30))
        self.assertEqual(set(keys), {'Tp00', 'Te04', 'Tg04'})
        self.assertEqual(temperature_groups({}), (None, None, []))

    def test_temperature_cache_and_failure_clear_preserve_gpu(self):
        registry = plistlib.dumps([{'PerformanceStatistics': {'Device Utilization %': 25}}])
        thermal = subprocess.CompletedProcess([], 0, json.dumps({'Tp00':40, 'Tg04':35}))
        with patch('macos_metrics.time.monotonic', return_value=10) as clock, patch(
            'macos_metrics.subprocess.run', side_effect=[subprocess.CompletedProcess([],0,registry), thermal,
                subprocess.CompletedProcess([],0,registry), subprocess.CompletedProcess([],0,registry),
                subprocess.TimeoutExpired('probe',2)]
        ) as run:
            m=MacMetrics()
            self.assertEqual(m.read(), (25,40,35))
            clock.return_value=11
            self.assertEqual(m.read(), (25,40,35))
            self.assertEqual(run.call_count,3)
            clock.return_value=16
            self.assertEqual(m.read(), (25,None,None))
            self.assertEqual(run.call_args_list[-1].args[0][1:], ['Tp00','Tg04'])

    def test_gpu_failure_does_not_discard_working_temperatures(self):
        with patch('macos_metrics.subprocess.run', side_effect=[OSError('missing'),
                  subprocess.CompletedProcess([],0,'{"Tp00":41}')]):
            self.assertEqual(MacMetrics().read(), (None,41,None))

    def test_malformed_registry_xml_is_unavailable(self):
        with patch('macos_metrics.subprocess.run', side_effect=[
            subprocess.CompletedProcess([], 0, b'<?xml version="1.0"?><plist><broken>'),
            subprocess.CompletedProcess([], 0, '{}')]):
            self.assertEqual(MacMetrics().read(), (None, None, None))
