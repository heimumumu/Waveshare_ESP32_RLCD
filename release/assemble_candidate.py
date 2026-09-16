"""Assemble a local candidate from verified build outputs; never upload or install."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import zipfile

ROOT=Path(__file__).resolve().parents[1]

def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--validation-root',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    base=args.validation_root.resolve();out=args.output.resolve()
    if out==ROOT or out.is_relative_to(ROOT):raise ValueError('Candidate must be outside the source tree')
    if out.exists() and any(out.iterdir()):raise ValueError('Use a new empty output directory')
    out.mkdir(parents=True,exist_ok=True)
    verification=json.loads((base/'candidate-verification.json').read_text(encoding='utf-8'))
    if not verification.get('passed'):raise ValueError('Candidate verification has not passed')
    for name,item in verification['artifacts'].items():
        source=base/item['path']
        if sha(source)!=item['sha256']:raise ValueError('Artifact changed: '+name)
        shutil.copy2(source,out/source.name)
    shutil.copytree(ROOT/'release/licenses',out/'LICENSES')
    shutil.copytree(ROOT/'docs',out/'docs')
    for name in ('LICENSE','THIRD_PARTY_NOTICES.md'):
        shutil.copy2(ROOT/name,out/name)
    sources=json.loads((ROOT/'docs/THIRD_PARTY_SOURCE_ARCHIVES.json').read_text())
    (out/'third-party-sources').mkdir()
    for item in sources['sources']:
        source=base/'third-party-sources'/item['archive']
        if sha(source)!=item['sha256']:raise ValueError('Source archive changed: '+item['archive'])
        shutil.copy2(source,out/'third-party-sources'/item['archive'])
    shutil.copy2(base/'third-party-sources/SOURCE_ARCHIVES.json',out/'third-party-sources/SOURCE_ARCHIVES.json')
    with zipfile.ZipFile(out/'Syna-source-1.0.0.zip','w',zipfile.ZIP_DEFLATED,compresslevel=6) as archive:
        for path in sorted(ROOT.rglob('*')):
            if not path.is_file():continue
            rel=path.relative_to(ROOT)
            if any(part.startswith(('.venv','__pycache__','.git')) or part in ('build','dist','Payload','Licenses') for part in rel.parts[:-1]):continue
            if path.name in ('reporter.json','.DS_Store','private.pem') or path.suffix in ('.pyc','.log','.key'):continue
            archive.write(path,Path('Syna-1.0.0')/rel)
    with zipfile.ZipFile(out/'Syna-source-1.0.0.zip') as archive:
        if archive.testzip():raise ValueError('Source ZIP integrity check failed')
    (out/'README.txt').write_text('''Syna 1.0.0 - LOCAL RELEASE CANDIDATE / NOT PUBLISHED

SynaInstaller-1.0.0.exe: unified Windows installer.
SynaReporter.exe: standalone Reporter.
xiaozhi.bin: application image only; not a full-flash image.
Syna-source-1.0.0.zip: application source, build scripts and notices.
third-party-sources/: upstream source archives; distribute alongside the binaries.
LICENSES/: original third-party notices.
docs/: build, source delivery and outstanding acceptance records.

SHA256SUMS.json verifies integrity only; it is not a publisher signature.
No installation or flashing was performed during this assembly.
See docs/HARDWARE_ACCEPTANCE.json for completed local hardware checks,
and docs/RELEASE_CHECKLIST.md for outstanding acceptance requirements.
Do not present this directory as a signed official release or blanket license approval.
''',encoding='utf-8')
    files={p.relative_to(out).as_posix():sha(p) for p in sorted(out.rglob('*')) if p.is_file()}
    (out/'SHA256SUMS.json').write_text(json.dumps(files,indent=2),encoding='utf-8')
    print('CANDIDATE',out,'FILES',len(files),'BYTES',sum(p.stat().st_size for p in out.rglob('*') if p.is_file()))

if __name__=='__main__':main()
