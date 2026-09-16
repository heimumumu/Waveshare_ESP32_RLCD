"""Collect notices and inventory from a validation build, without executing binaries."""
import argparse
import ast
import hashlib
import importlib.metadata as metadata
import json
from pathlib import Path
import re
import shutil
import sys
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
SUPPLEMENTS = {
    'Qt-6.8.3/LGPL-3.0-only.txt': 'https://raw.githubusercontent.com/qt/qtbase/v6.8.3/LICENSES/LGPL-3.0-only.txt',
    'Qt-6.8.3/GPL-3.0-only.txt': 'https://raw.githubusercontent.com/qt/qtbase/v6.8.3/LICENSES/GPL-3.0-only.txt',
    'Qt-6.8.3/GPL-2.0-only.txt': 'https://raw.githubusercontent.com/qt/qtbase/v6.8.3/LICENSES/GPL-2.0-only.txt',
    'pyserial-3.5/LICENSE.txt': 'https://raw.githubusercontent.com/pyserial/pyserial/v3.5/LICENSE.txt',
    'pywinrt-3.2.1/LICENSE.txt': 'https://raw.githubusercontent.com/pywinrt/pywinrt/v3.2.1/LICENSE',
}

def digest(path): return hashlib.sha256(path.read_bytes()).hexdigest()

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--validation-root', type=Path, required=True)
    args = parser.parse_args()
    base = args.validation_root.resolve()
    dest = ROOT/'release/licenses/windows-audit'
    dest.mkdir(parents=True, exist_ok=True)
    report = {'scope': 'Inventory and notice collection, not a blanket compliance certification',
              'python_environment': [], 'bundled_files': {}, 'firmware_configured_components': [],
              'downloads': [], 'speech_models': []}
    def copy(source, relative):
        target = dest/relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        return {'path': target.relative_to(ROOT).as_posix(), 'sha256': digest(target)}
    def notice(path):
        return (any(word in path.name.lower() for word in ('license', 'licence', 'copying', 'notice', 'copyright'))
                and path.suffix.lower() not in ('.py', '.pyc', '.c', '.h', '.exe', '.dll', '.json'))
    for dist in sorted(metadata.distributions(), key=lambda d: d.metadata['Name'].lower()):
        name = dist.metadata['Name']
        row = {'name': name, 'version': dist.version,
               'license_metadata': dist.metadata.get('License-Expression') or dist.metadata.get('License'),
               'project_urls': dist.metadata.get_all('Project-URL') or [], 'notices': []}
        for item in dist.files or []:
            source = Path(dist.locate_file(item))
            if source.is_file() and notice(source):
                row['notices'].append(copy(source, Path('python')/name/str(item).replace('/', '_').replace('\\', '_')))
        report['python_environment'].append(row)
    for relative, url in SUPPLEMENTS.items():
        target = dest/'supplemental'/relative
        target.parent.mkdir(parents=True, exist_ok=True)
        data = urllib.request.urlopen(url, timeout=45).read()
        if len(data) < 100 or b'<html' in data[:200].lower(): raise ValueError('Invalid license response: '+url)
        target.write_bytes(data)
        report['downloads'].append({'url': url, 'path': target.relative_to(ROOT).as_posix(), 'sha256': digest(target)})
    runtime = Path(sys.base_prefix)/'LICENSE.txt'
    if runtime.exists(): copy(runtime, Path('python-runtime')/'LICENSE.txt')
    for name, toc in [('Reporter', base/'source/reporter/build/SynaReporter/Analysis-00.toc'),
                      ('Installer', base/'source/installer/windows/build/SynaInstaller-1.0.0/Analysis-00.toc'),
                      ('Worker', base/'source/installer/windows/build/SynaInstallerWorker/Analysis-00.toc')]:
        rows = []
        def walk(item):
            if not isinstance(item, (list, tuple)): return
            if len(item) == 3 and all(isinstance(x,str) for x in item) and item[2] in ('BINARY','EXTENSION','DATA','PYMODULE'):
                rows.append({'name': item[0], 'type': item[2]})
            else:
                for part in item: walk(part)
        walk(ast.literal_eval(toc.read_text(encoding='utf-8')))
        report['bundled_files'][name] = rows
    project = json.loads((base/'firmware/build/project_description.json').read_text())
    for name, component in project['build_component_info'].items():
        directory = Path(component['dir'])
        notices = []
        for p in directory.rglob('*'):
            if p.is_file() and notice(p) and p.stat().st_size < 2_000_000:
                notices.append(copy(p, Path('firmware')/name/p.relative_to(directory)))
        report['firmware_configured_components'].append({'name': name, 'notices': notices})
    for name in ('mn7_cn','fst'):
        directory = base/'firmware/managed_components/espressif__esp-sr/model/multinet_model'/name
        for p in directory.rglob('*'):
            if p.is_file(): report['speech_models'].append({'model':name,'file':p.relative_to(directory).as_posix(),'bytes':p.stat().st_size,'sha256':digest(p)})
    for name in ('LICENSE', 'NOTICE'):
        p=Path(project['idf_path'])/name
        if p.exists():copy(p,Path('esp-idf')/name)
    output=ROOT/'docs/THIRD_PARTY_AUDIT.json'
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2),encoding='utf-8')
    print('Inventoried',len(report['python_environment']),'Python distributions,',len(report['firmware_configured_components']),'configured components,',len(report['speech_models']),'model files')
    print('Collected notices under',dest)

if __name__ == '__main__': main()
