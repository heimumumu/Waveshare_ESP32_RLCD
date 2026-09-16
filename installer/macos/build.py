#!/usr/bin/env python3
# Copyright (c) 2026 黑沐. MIT License.
"""Build an offline Apple Silicon installer and a signed DMG release."""
import argparse
import importlib.util
import json
import os
from pathlib import Path
import plistlib
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]


def run(*args):
    subprocess.run(list(map(str, args)), check=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--worker-python', type=Path, default=Path.home()/'.local/share/syna-toolchains/flash-tools/bin/python')
    parser.add_argument('--firmware-build', type=Path, default=Path.home()/'.local/share/syna-toolchains/xiaozhi-build/build')
    parser.add_argument('--reporter-app', type=Path, default=ROOT/'reporter/dist-macos/SynaReporter.app')
    args = parser.parse_args()
    os.chdir(ROOT)
    if sys.platform != 'darwin' or os.uname().machine != 'arm64':
        raise SystemExit('Build this package on an Apple Silicon Mac.')
    version = (ROOT/'VERSION').read_text().strip().removeprefix('v')
    work = ROOT/'.codex-tmp/macos-installer'
    work.mkdir(parents=True, exist_ok=True)
    stage = work/'volume'
    if stage.exists(): shutil.rmtree(stage)
    stage.mkdir()
    app = stage/'SynaInstaller.app'
    contents = app/'Contents'
    resources = contents/'Resources'
    payload = resources/'Payload'
    for p in [contents/'MacOS', contents/'Helpers', payload/'Firmware', payload/'Legal']:
        p.mkdir(parents=True, exist_ok=True)
    run(args.worker_python, '-m', 'PyInstaller', '--noconfirm', '--onedir', '--windowed', '--name', 'InstallerWorker',
        '--osx-bundle-identifier', 'local.syna.installer.worker',
        '--collect-all', 'esptool', '--distpath', work/'worker-dist', '--workpath', work/'worker-build',
        '--specpath', work, ROOT/'installer/macos/worker.py')
    shutil.copytree(work/'worker-dist/InstallerWorker.app', contents/'Helpers/InstallerWorker.app', symlinks=True)
    run('swiftc', '-O', '-target', 'arm64-apple-macos13.0', '-framework', 'Cocoa',
        ROOT/'installer/macos/Installer.swift', '-o', contents/'MacOS/SynaInstaller')
    info = {'CFBundleName': 'SynaInstaller', 'CFBundleDisplayName': '希娜 Syna 安装器',
            'CFBundleIdentifier': 'local.syna.installer', 'CFBundleExecutable': 'SynaInstaller',
            'CFBundlePackageType': 'APPL', 'CFBundleVersion': version, 'CFBundleShortVersionString': version,
            'LSMinimumSystemVersion': '13.0', 'NSHighResolutionCapable': True}
    (contents/'Info.plist').write_bytes(plistlib.dumps(info))
    reporter = payload/'SynaReporter.app'
    run('/usr/bin/ditto', args.reporter_app, reporter)
    # Rebuild only the native launcher; retain the tested self-contained backend.
    run('swiftc', '-O', '-target', 'arm64-apple-macos13.0', '-framework', 'Cocoa', '-framework', 'Foundation',
        '-framework', 'ServiceManagement', ROOT/'reporter/native_ui.swift', '-o', reporter/'Contents/MacOS/SynaReporter')
    run('clang', '-O2', '-target', 'arm64-apple-macos13.0', '-framework', 'IOKit',
        ROOT/'reporter/macos_thermal.c', '-o', reporter/'Contents/MacOS/MacThermalProbe')
    p = reporter/'Contents/Info.plist'; report_info = plistlib.loads(p.read_bytes())
    report_info['LSMinimumSystemVersion'] = '13.0'; p.write_bytes(plistlib.dumps(report_info))
    for name in ['LICENSE', 'THIRD_PARTY_NOTICES.md']:
        shutil.copy2(ROOT/name, reporter/'Contents/Resources/Legal'/name)
        shutil.copy2(ROOT/name, payload/'Legal'/name)
    for src, name in [('xiaozhi.bin', 'xiaozhi.bin'), ('generated_assets.bin', 'generated_assets.bin'),
                      ('bootloader/bootloader.bin', 'bootloader.bin'),
                      ('partition_table/partition-table.bin', 'partition-table.bin'), ('ota_data_initial.bin', 'ota_data_initial.bin')]:
        shutil.copy2(args.firmware_build/src, payload/'Firmware'/name)
    # Collect upstream license files, not source caches, keys or device backups.
    origins = [(ROOT/'simulator/assets/fonts', 'fonts'),
               (args.firmware_build.parent/'managed_components', 'firmware-components'),
               (args.firmware_build.parent/'local_components', 'firmware-local-components')]
    for origin, category in origins:
        for file in origin.rglob('*'):
            if file.is_file() and (file.name.lower().startswith(('license', 'copying', 'ofl', 'notice'))
                                   or file.name in ['Arimo-OFL.txt', 'Unifont-COPYING', 'SOURCE.md']):
                dest = payload/'Legal'/category/file.relative_to(origin)
                dest.parent.mkdir(parents=True, exist_ok=True); shutil.copy2(file, dest)
    for origin, name in [(args.firmware_build.parent/'LICENSE', 'Xiaozhi-LICENSE'),
                         (Path.home()/'.local/share/syna-toolchains/esp-idf-v6.0.2/LICENSE', 'ESP-IDF-LICENSE')]:
        shutil.copy2(origin, payload/'Legal'/name)
    # Runtime distribution notices (esptool, serial, Python support packages).
    collect = '''import importlib.metadata as m,json
print(json.dumps([str(d.locate_file(f)) for d in m.distributions() for f in (d.files or [])
 if any(w in str(f).lower() for w in ['license','copying','notice']) and d.locate_file(f).is_file()]))'''
    for python, category in [(args.worker_python, 'installer-runtime'), (ROOT/'reporter/.venv-macos/bin/python', 'reporter-runtime')]:
        python_license = Path(subprocess.check_output([str(python), '-c',
            'import sysconfig; from pathlib import Path; print(Path(sysconfig.get_path("stdlib"))/"LICENSE.txt")'], text=True).strip())
        if not python_license.is_file():
            raise SystemExit('Missing Python runtime license: '+str(python_license))
        dest = payload/'Legal'/category/'Python-LICENSE.txt'
        dest.parent.mkdir(parents=True, exist_ok=True); shutil.copy2(python_license, dest)
        files = json.loads(subprocess.check_output([str(python), '-c', collect], text=True))
        for i, name in enumerate(files):
            f = Path(name); dest = payload/'Legal'/category/(str(i)+'-'+f.parent.name+'-'+f.name)
            dest.parent.mkdir(parents=True, exist_ok=True); shutil.copy2(f, dest)
    shutil.copy2(ROOT/'installer/macos/使用说明.md', stage/'使用说明.md')
    shutil.copy2(ROOT/'installer/macos/使用说明.md', payload/'使用说明.md')
    shutil.copytree(payload/'Legal/reporter-runtime', reporter/'Contents/Resources/Legal/runtime', dirs_exist_ok=True)
    run('/usr/bin/codesign', '--force', '--deep', '--sign', '-', reporter)
    run('/usr/bin/codesign', '--verify', '--deep', '--strict', reporter)
    spec = importlib.util.spec_from_file_location('installer_worker', ROOT/'installer/macos/worker.py')
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    (resources/'manifest.json').write_text(json.dumps(module.inventory(payload), ensure_ascii=False, sort_keys=True, indent=2)+'\n')
    shutil.copy2(ROOT/'release/keys/syna-release-public.pem', resources/'public.pem')
    key = Path.home()/'Library/Application Support/SynaReleaseSigning/private.pem'
    run('/usr/bin/openssl', 'dgst', '-sha256', '-sign', key, '-out', resources/'manifest.sig', resources/'manifest.json')
    module.verify_payload(resources)
    run('/usr/bin/codesign', '--force', '--sign', '-', app)
    run('/usr/bin/codesign', '--verify', '--deep', '--strict', app)
    run(contents/'Helpers/InstallerWorker.app/Contents/MacOS/InstallerWorker', 'verify', '--resources', resources)
    out = ROOT/'release/artifacts'/('v'+version+'-macos-installer')
    out.mkdir(parents=True, exist_ok=True)
    dmg = out/('Syna-v'+version+'-macOS-arm64.dmg')
    run('/usr/bin/hdiutil', 'create', '-volname', 'Syna v'+version, '-srcfolder', stage, '-format', 'UDZO', '-ov', dmg)
    shutil.copy2(ROOT/'installer/macos/使用说明.md', out/'使用说明.md')
    run(sys.executable, ROOT/'release/sign_release.py', 'sign', out)
    print('Installer:', dmg)


if __name__ == '__main__':
    main()
