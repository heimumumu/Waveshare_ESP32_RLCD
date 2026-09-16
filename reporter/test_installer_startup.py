"""Run the actual installer startup block against an isolated HKCU test key."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
import uuid

if os.name == 'nt':
    import winreg


@unittest.skipUnless(os.name == 'nt', 'Windows registry')
class InstallerStartupTests(unittest.TestCase):
    def test_packaged_batch_format_and_elevation_control_flow(self):
        path = Path(__file__).parent / 'installer/install.cmd'
        raw = path.read_bytes()
        self.assertNotIn(b'\n', raw.replace(b'\r\n', b''))
        preamble = raw.decode('utf-8').split('set "INSTALL_DIR=', 1)[0]
        self.assertIn('$p.WaitForExit()', preamble)
        self.assertNotIn('-Wait -PassThru', preamble)
        # Exercise the real batch control flow; replace only the external
        # privilege probe and elevation action, so tests cannot elevate.
        lines = []
        for line in preamble.splitlines():
            if line.lstrip().startswith('powershell.exe'):
                line = ('call "%~dp0probe.cmd"' if 'IsInRole' in line
                        else 'call "%~dp0elevate.cmd"')
            lines.append(line)
        script_text = '\r\n'.join(lines) + '\r\necho INSTALL_BODY_REACHED\r\nexit /b 0\r\n'
        for admin, elevated, expected, attempts in [(False, False, 37, 1),
                                                   (False, True, 1, 0),
                                                   (True, True, 0, 0)]:
            with self.subTest(admin=admin, elevated=elevated), tempfile.TemporaryDirectory(prefix='syna-elevation-test-') as tmp:
                root = Path(tmp)
                (root/'check.cmd').write_bytes(script_text.encode('utf-8'))
                (root/'probe.cmd').write_bytes(f'@exit /b {0 if admin else 1}\r\n'.encode())
                (root/'elevate.cmd').write_bytes(b'@echo ATTEMPT>>"%~dp0attempts.txt"\r\n@exit /b 37\r\n')
                command = ['cmd.exe', '/d', '/c', str(root/'check.cmd')]
                if elevated:
                    command.append('/elevated')
                result = subprocess.run(command, capture_output=True, timeout=10)
                self.assertEqual(result.returncode, expected, result.stdout + result.stderr)
                recorded = (root/'attempts.txt').read_text().splitlines() if (root/'attempts.txt').exists() else []
                self.assertEqual(len(recorded), attempts)
                self.assertEqual(b'INSTALL_BODY_REACHED' in result.stdout, admin)

    def test_enabled_disabled_and_first_install(self):
        source = (Path(__file__).parent / 'installer/install.cmd').read_text(encoding='utf-8')
        block = source.split('rem BEGIN PRESERVE USER STARTUP', 1)[1].split('rem END PRESERVE USER STARTUP', 1)[0]
        for mode in ('enabled', 'disabled', 'first_install'):
            with self.subTest(mode=mode):
                key_path = 'Software\\SynaInstallerTest_' + uuid.uuid4().hex
                try:
                    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, key_path) as key:
                        winreg.SetValueEx(key, 'UnrelatedApp', 0, winreg.REG_SZ, 'untouched')
                        if mode == 'enabled':
                            winreg.SetValueEx(key, 'SynaReporter', 0, winreg.REG_SZ, '"C:\\Old Path\\SynaReporter.exe"')
                    test_block = block.replace('HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Run', 'HKCU\\' + key_path)
                    with tempfile.TemporaryDirectory(prefix='syna-startup-test-') as tmp:
                        script = Path(tmp) / 'check.cmd'
                        script.write_text('@echo off\nset "INSTALL_DIR=C:\\Program Files\\Syna Reporter"\n' + test_block + '\nexit /b 0\n', encoding='utf-8')
                        subprocess.run(['cmd.exe', '/d', '/c', str(script)], check=True, capture_output=True)
                    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path) as key:
                        self.assertEqual(winreg.QueryValueEx(key, 'UnrelatedApp')[0], 'untouched')
                        if mode == 'enabled':
                            self.assertEqual(winreg.QueryValueEx(key, 'SynaReporter'), ('"C:\\Program Files\\Syna Reporter\\SynaReporter.exe"', winreg.REG_SZ))
                        else:
                            with self.assertRaises(FileNotFoundError):
                                winreg.QueryValueEx(key, 'SynaReporter')
                finally:
                    winreg.DeleteKey(winreg.HKEY_CURRENT_USER, key_path)


if __name__ == '__main__':
    unittest.main()
