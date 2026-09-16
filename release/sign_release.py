#!/usr/bin/env python3
# Copyright (c) 2026 黑沐. MIT License.
"""Sign/verify a SHA-256 release manifest with a local P-256 release key."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parent
KEY = Path.home() / 'Library/Application Support/SynaReleaseSigning/private.pem'
PUBLIC = ROOT / 'keys/syna-release-public.pem'

def run(*args):
    subprocess.run(['openssl', *map(str,args)], check=True)

def digest(path):
    with path.open('rb') as f:
        h=hashlib.sha256()
        for chunk in iter(lambda:f.read(1024*1024), b''): h.update(chunk)
        return h.hexdigest()

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('action', choices=['init','sign','verify'])
    parser.add_argument('directory', nargs='?', type=Path)
    args=parser.parse_args()
    if args.action=='init':
        if KEY.exists() or PUBLIC.exists():
            raise SystemExit('Existing signing identity found; refusing to overwrite.')
        KEY.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        old=os.umask(0o077)
        try: run('genpkey','-algorithm','EC','-pkeyopt','ec_paramgen_curve:P-256','-out',KEY)
        finally: os.umask(old)
        PUBLIC.parent.mkdir(parents=True, exist_ok=True)
        run('pkey','-in',KEY,'-pubout','-out',PUBLIC)
        print('Created local private key and distributable public key.')
        return
    if args.directory is None: parser.error('directory required')
    folder=args.directory.resolve()
    manifest=folder/'SHA256SUMS.json';signature=folder/'SHA256SUMS.sig'
    if args.action=='sign':
        files=sorted(p for p in folder.iterdir() if p.is_file() and p.name not in [manifest.name, signature.name])
        if not files: raise SystemExit('No release artifacts')
        if any(p.is_symlink() or p.suffix in ['.pem','.key'] for p in files):
            raise SystemExit('Refusing symlinks or key files in release artifacts')
        manifest.write_text(json.dumps({p.name:digest(p) for p in files},ensure_ascii=False,indent=2)+'\n')
        run('dgst','-sha256','-sign',KEY,'-out',signature,manifest)
    run('dgst','-sha256','-verify',PUBLIC,'-signature',signature,manifest)
    files=json.loads(manifest.read_text())
    if not isinstance(files,dict) or not files: raise SystemExit('Invalid manifest')
    for name, expected in files.items():
        if name in ['.','..'] or '/' in name or '\\' in name or Path(name).name!=name:
            raise SystemExit('Invalid artifact name')
        path=folder/name
        if path.is_symlink() or digest(path)!=expected: raise SystemExit('Artifact verification failed: '+name)
    print('All signed artifacts verified.')

if __name__=='__main__': main()
