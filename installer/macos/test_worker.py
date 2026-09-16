# Copyright (c) 2026 黑沐. MIT License.
import hashlib
import importlib.util
import json
from pathlib import Path
import plistlib
import struct
import tempfile
import unittest
from unittest.mock import patch
import zlib

spec = importlib.util.spec_from_file_location('worker', Path(__file__).with_name('worker.py'))
w = importlib.util.module_from_spec(spec); spec.loader.exec_module(w)


def table():
    records = [(1, 2, 0x9000, 0x4000, b'nvs'), (1, 0, 0xd000, 0x2000, b'otadata'),
               (1, 1, 0xf000, 0x1000, b'phy_init'), (0, 0x10, 0x20000, 0x3f0000, b'ota_0'),
               (0, 0x11, 0x410000, 0x3f0000, b'ota_1'), (1, 0x82, 0x800000, 0x800000, b'assets')]
    b = b''.join(struct.pack('<HBBII16sI', 0x50aa, *record, 0) for record in records)
    return (b + b'\xeb\xeb' + b'\xff' * 14 + hashlib.md5(b).digest()).ljust(0xc00, b'\xff')


def device(slot=0):
    b = bytearray(b'\xff' * w.FLASH_SIZE)
    b[0x8000:0x8c00] = table()
    seq = slot + 1
    record = struct.pack('<I20sII', seq, b'\xff' * 20, 2, zlib.crc32(struct.pack('<I', seq), 0xffffffff))
    b[0xd000:0xd020] = record
    offset = [0x20000, 0x410000][slot]
    app = b'\xe9' + b'old esp32-s3-rlcd-4.2'
    b[offset:offset + len(app)] = app
    return bytes(b)


class SafetyTests(unittest.TestCase):
    def test_select_both_ota_slots(self):
        for slot in (0, 1):
            self.assertEqual(w.upgrade_offset(device(slot), table()), [0x20000, 0x410000][slot])

    def test_reject_damaged_partition_table(self):
        b = bytearray(table()); b[12] ^= 1
        with self.assertRaises(ValueError): w.parse_partitions(bytes(b))

    def test_reject_damaged_ota_record(self):
        b = bytearray(device()); b[0xd01f] ^= 1
        with self.assertRaises(ValueError): w.upgrade_offset(bytes(b), table())

    def test_reject_wrong_board(self):
        b = bytearray(device()); b[0x20000:0x20100] = b'\xe9' + b'x' * 255
        with self.assertRaises(ValueError): w.upgrade_offset(bytes(b), table())

    def test_reject_symlink_escape(self):
        with tempfile.TemporaryDirectory() as t:
            p = Path(t); (p/'bad').symlink_to('/etc/passwd')
            with self.assertRaises(ValueError): w.inventory(p)

    def test_inventory_detects_bytes_permissions_and_links(self):
        with tempfile.TemporaryDirectory() as t:
            p = Path(t); f = p/'one'; f.write_text('original'); f.chmod(0o644)
            (p/'link').symlink_to('one'); first = w.inventory(p)
            f.write_text('changed'); self.assertNotEqual(first, w.inventory(p))
            f.write_text('original'); f.chmod(0o755); self.assertNotEqual(first, w.inventory(p))

    def test_refuse_overwrite_unrelated_application(self):
        with tempfile.TemporaryDirectory() as t:
            p = Path(t); dest = p/'Other.app'; (dest/'Contents').mkdir(parents=True)
            (dest/'Contents/Info.plist').write_bytes(plistlib.dumps({'CFBundleIdentifier': 'other.app'}))
            with self.assertRaises(ValueError): w.install_reporter(p, dest, p)
            self.assertTrue((dest/'Contents/Info.plist').exists())

    def exercise_flash(self, mode, fail_verify=False):
        temp = tempfile.TemporaryDirectory(); self.addCleanup(temp.cleanup)
        p = Path(temp.name); fw = p/'Payload/Firmware'; fw.mkdir(parents=True); session = p/'session'; session.mkdir()
        (fw/'partition-table.bin').write_bytes(table())
        (fw/'xiaozhi.bin').write_bytes(b'\xe9new firmware')
        (fw/'generated_assets.bin').write_bytes(b'assets')
        calls = []
        def fake(port, args, log, timeout=600):
            calls.append(args)
            if 'read-flash' in args: Path(args[-1]).write_bytes(device(1))
            if fail_verify and 'verify-flash' in args: raise RuntimeError('backup mismatch')
        # Supply an existing local path while preserving the /dev/cu. restriction.
        original_exists = Path.exists
        def exists(path): return str(path) == '/dev/cu.fake-test' or original_exists(path)
        with patch.object(w, 'esptool_command', side_effect=fake), patch.object(Path, 'exists', exists), patch.object(w, 'emit'):
            if fail_verify:
                with self.assertRaises(RuntimeError): w.flash(p, '/dev/cu.fake-test', mode, session)
            else: w.flash(p, '/dev/cu.fake-test', mode, session)
        return calls

    def test_no_write_when_backup_verification_fails(self):
        for mode in ('upgrade', 'fresh'):
            calls = self.exercise_flash(mode, fail_verify=True)
            self.assertFalse(any('write-flash' in c or 'erase-flash' in c for c in calls))

    def test_upgrade_only_writes_active_app_and_assets(self):
        calls = self.exercise_flash('upgrade')
        writes = [c for c in calls if 'write-flash' in c]
        self.assertEqual(len(writes), 1)
        self.assertEqual(writes[0][3], '0x410000')
        self.assertNotIn('0x8000', writes[0]); self.assertNotIn('0xd000', writes[0])
        self.assertFalse(any('erase-flash' in c for c in calls))

    def test_fresh_erases_only_after_full_backup_verified(self):
        calls = self.exercise_flash('fresh')
        erase = next(i for i,c in enumerate(calls) if 'erase-flash' in c)
        verify = next(i for i,c in enumerate(calls) if 'verify-flash' in c)
        self.assertLess(verify, erase)


if __name__ == '__main__': unittest.main()
