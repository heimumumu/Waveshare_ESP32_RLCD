"""Stage locally verified artifacts; no install, elevation, or device access."""
from pathlib import Path
import hashlib
import json
import shutil
import argparse

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]


def prepare(firmware_build, reporter_exe):
    payload = HERE / 'Payload'
    payload.mkdir(exist_ok=True)
    firmware = payload / 'Firmware'
    firmware.mkdir(exist_ok=True)
    build = Path(firmware_build).resolve()
    source = build/'xiaozhi.bin'
    reporter = Path(reporter_exe).resolve()
    app = source.read_bytes()
    if not app or app[0] != 0xe9 or b'esp32-s3-rlcd-4.2' not in app or len(app) > 0x3f0000:
        raise ValueError('Unsupported firmware image')
    if reporter.read_bytes()[:2] != b'MZ':
        raise ValueError('Reporter must be a Windows executable')
    files = {'SynaReporter.exe': reporter, 'uninstall.cmd': ROOT/'reporter/installer/uninstall.cmd',
             'install_reporter.ps1': HERE/'install_reporter.ps1', 'Firmware/xiaozhi.bin': source,
             'Firmware/partition-table.bin': build/'partition_table/partition-table.bin',
             'Firmware/bootloader.bin': build/'bootloader/bootloader.bin',
             'Firmware/ota_data_initial.bin': build/'ota_data_initial.bin',
             'Firmware/generated_assets.bin': build/'generated_assets.bin'}
    manifest = {}
    for name, path in files.items():
        shutil.copy2(path, payload/name)
        manifest[name] = hashlib.sha256((payload/name).read_bytes()).hexdigest()
    data = json.dumps(manifest, sort_keys=True, indent=2).encode('utf-8')
    (HERE/'manifest.json').write_bytes(data)
    (HERE/'payload_manifest.py').write_text('MANIFEST_SHA256 = '+repr(hashlib.sha256(data).hexdigest())+'\n', encoding='utf-8')
    print('Prepared', len(files), 'locally verified files; no release signature claimed.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--firmware-build', type=Path, required=True)
    parser.add_argument('--reporter-exe', type=Path, required=True)
    args = parser.parse_args()
    prepare(args.firmware_build, args.reporter_exe)
