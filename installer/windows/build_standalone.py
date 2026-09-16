"""Build worker then a single windowed installer EXE. Never install or flash."""
from pathlib import Path
import subprocess
import sys
import shutil
import json
import hashlib
import importlib.metadata
import argparse
from prepare_payload import prepare

HERE = Path(__file__).resolve().parent
OUT = HERE/'dist'

def build(firmware_build, reporter_exe):
    prepare(firmware_build, reporter_exe)
    licenses = HERE/'Licenses'
    licenses.mkdir(exist_ok=True)
    packages = {}
    for dist in importlib.metadata.distributions():
        name = dist.metadata['Name']
        packages[name] = dist.version
        for item in dist.files or []:
            if any(word in item.name.lower() for word in ('license', 'copying', 'notice')):
                source = Path(dist.locate_file(item))
                if source.is_file() and source.suffix.lower() not in ('.py', '.pyc', '.exe', '.dll'):
                    target = licenses/name/str(item).replace('/', '_').replace('\\', '_')
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(source, target)
    (licenses/'build-environment.json').write_text(json.dumps(packages, indent=2), encoding='utf-8')
    # Wheel metadata alone omits several runtime licenses (notably Qt/WinRT).
    root = HERE.parents[1]
    required = root/'release/licenses/windows-audit/supplemental/Qt-6.8.3/LGPL-3.0-only.txt'
    if not required.is_file():
        raise RuntimeError('Missing audited notices; see docs/THIRD_PARTY_AUDIT.md')
    shutil.copytree(root/'release/licenses', licenses/'Syna-third-party', dirs_exist_ok=True)
    for name in ('LICENSE', 'THIRD_PARTY_NOTICES.md'):
        shutil.copy2(root/name, licenses/name)
    shutil.copy2(root/'docs/THIRD_PARTY_SOURCES.md', licenses/'THIRD_PARTY_SOURCES.md')
    common = [sys.executable, '-m', 'PyInstaller', '--noconfirm', '--clean', '--onefile',
              '--distpath', str(OUT), '--workpath', str(HERE/'build'), '--specpath', str(HERE/'build')]
    subprocess.run(common + ['--name', 'SynaInstallerWorker', '--collect-all', 'esptool',
        '--collect-all', 'esp_pylib', '--hidden-import', 'payload_manifest', str(HERE/'backend_entry.py')], cwd=HERE, check=True)
    subprocess.run(common + ['--windowed', '--name', 'SynaInstaller-1.0.0',
        '--add-binary', str(OUT/'SynaInstallerWorker.exe')+';.',
        '--add-data', str(HERE/'Payload')+';Payload',
        '--add-data', str(HERE/'manifest.json')+';.',
        '--add-data', str(licenses)+';Licenses', str(HERE/'installer_ui.py')], cwd=HERE, check=True)
    exe = OUT/'SynaInstaller-1.0.0.exe'
    (OUT/'SHA256.txt').write_text(hashlib.sha256(exe.read_bytes()).hexdigest()+'  '+exe.name+'\n')
    print('BUILT', exe, flush=True)

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--firmware-build', type=Path, required=True)
    parser.add_argument('--reporter-exe', type=Path, required=True)
    args = parser.parse_args()
    build(args.firmware_build, args.reporter_exe)
