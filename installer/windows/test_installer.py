"""No elevation or serial writes: exercise safety gates and simulated readback."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
import tempfile
import io
import json
import subprocess
import unittest
from pathlib import Path
from unittest.mock import patch
import worker
from installer_ui import InstallerWindow
from PySide6.QtWidgets import QApplication


class WorkerTests(unittest.TestCase):
    def test_json_protocol_survives_windows_codepage(self):
        raw = io.BytesIO()
        stream = io.TextIOWrapper(raw, encoding='cp936')
        with patch.object(worker.sys, 'stdout', stream):
            worker.emit('done', '安装完成：希娜 🐱', progress=100)
        data = raw.getvalue()
        self.assertTrue(data.isascii())
        result = json.loads(data)
        self.assertEqual(result['message'], '安装完成：希娜 🐱')
        self.assertEqual(result['progress'], 100)

    def test_final_run_resets_device(self):
        with tempfile.TemporaryDirectory() as folder, patch.object(worker.subprocess, 'run') as run:
            run.return_value.returncode = 0
            for args, expected in [(['run'], 'hard-reset'), (['read-flash', '0', 'ALL', 'backup.bin'], 'no-reset')]:
                worker.tool('COM9', args, Path(folder))
                command = run.call_args.args[0]
                self.assertEqual(command[command.index('--after')+1], expected)

    def test_powershell_replacement(self):
        # Execute the actual replacement branch against disposable files only.
        script = (worker.HERE/'install_reporter.ps1').read_text(encoding='utf-8')
        branch = script[script.index('    $replacementBackup ='):script.index('    Copy-Item -LiteralPath (Join-Path $Payload')]
        with tempfile.TemporaryDirectory(prefix='Syna replace ') as folder:
            base = Path(folder)
            harness = base/'test.ps1'
            harness.write_text("$ErrorActionPreference='Stop'\n"
                "$staged=Join-Path $PSScriptRoot 'new.exe'\n"
                "$exe=Join-Path $PSScriptRoot 'old.exe'\n"
                "[IO.File]::WriteAllText($staged,'new')\n"
                "[IO.File]::WriteAllText($exe,'old')\n" + branch, encoding='utf-8')
            subprocess.run(['powershell.exe','-NoProfile','-File',str(harness)],
                           check=True, capture_output=True, creationflags=worker.CREATE_NO_WINDOW)
            self.assertEqual((base/'old.exe').read_text(), 'new')
            self.assertEqual((base/'new.exe.previous').read_text(), 'old')

    def test_payload(self):
        self.assertEqual(len(worker.verify_payload()), 8)

    def test_confirmation_before_device_access(self):
        with patch.object(worker, 'tool') as tool:
            with self.assertRaises(ValueError):
                worker.flash(worker.HERE, 'COM9', 'fresh', Path('.'))
            tool.assert_not_called()

    def simulate(self, mode='upgrade', damage=False, backup_failure=False):
        fw = worker.HERE/'Payload/Firmware'
        before = bytearray(b'\xff' * worker.FLASH_SIZE)
        for offset, name in [(0x8000, 'partition-table.bin'), (0x20000, 'xiaozhi.bin'),
                             (0x800000, 'generated_assets.bin')]:
            data = (fw/name).read_bytes()
            before[offset:offset+len(data)] = data
        current = bytearray(before)
        commands = []
        def fake(port, args, session):
            commands.append(args[0])
            if args[0] == 'read-flash':
                Path(args[-1]).write_bytes(current)
            elif args[0] == 'verify-flash' and backup_failure:
                raise RuntimeError('backup mismatch')
            elif args[0] == 'erase-flash':
                current[:] = b'\xff' * len(current)
            elif args[0] == 'write-flash':
                for i in range(1, len(args), 2):
                    offset = int(args[i], 0)
                    data = Path(args[i+1]).read_bytes()
                    current[offset:offset+len(data)] = data
                if damage:
                    current[0x9000] = 0
        with tempfile.TemporaryDirectory() as folder, patch.object(worker, 'tool', side_effect=fake), patch.object(worker, 'emit'):
            if damage or backup_failure:
                with self.assertRaises((ValueError, RuntimeError)):
                    worker.flash(worker.HERE, 'COM9', mode, Path(folder), True)
                self.assertNotIn('run', commands)
            else:
                worker.flash(worker.HERE, 'COM9', mode, Path(folder), True)
                self.assertTrue((Path(folder)/'firmware-complete.json').exists())
            if backup_failure:
                self.assertNotIn('write-flash', commands)
                self.assertNotIn('erase-flash', commands)
            if mode == 'fresh' and not backup_failure:
                self.assertLess(commands.index('verify-flash'), commands.index('erase-flash'))
    def test_upgrade(self): self.simulate()
    def test_preserved_region_damage(self): self.simulate(damage=True)
    def test_fresh(self): self.simulate(mode='fresh')
    def test_backup_failure(self): self.simulate(mode='fresh', backup_failure=True)


class UiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls): cls.app = QApplication.instance() or QApplication([])
    def setUp(self): self.window = InstallerWindow(scan=False)
    def tearDown(self): self.window.close()
    def test_mode_gates(self):
        w = self.window
        self.assertFalse(w.start.isEnabled())
        w.mode.setCurrentIndex(2)
        self.assertTrue(w.start.isEnabled())
        w.show_ports([{'port':'COM9', 'name':'Test COM9'}])
        w.mode.setCurrentIndex(1)
        self.assertFalse(w.start.isEnabled())
        w.reset.setChecked(True)
        self.assertTrue(w.start.isEnabled())
        w.mode.setCurrentIndex(0)
        self.assertFalse(w.reset.isChecked())
    def test_done_requires_process_exit(self):
        self.window.handle_event({'event':'done', 'progress':100})
        self.assertTrue(self.window.completed)
        self.assertLess(self.window.progress.value(), 100)

if __name__ == '__main__': unittest.main()
