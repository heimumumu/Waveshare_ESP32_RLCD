"""Download versioned upstream source archives and collect their notices safely."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path, PurePosixPath
import tarfile
import urllib.request
import posixpath
import importlib.metadata

ROOT = Path(__file__).resolve().parents[1]
QT = 'https://download.qt.io/archive/qt/6.8/6.8.3/submodules/'
SOURCES = {
    **{f'{name}-everywhere-src-6.8.3.tar.xz': QT+f'{name}-everywhere-src-6.8.3.tar.xz'
       for name in ('qtbase', 'qtsvg', 'qtimageformats')},
    'pyside-setup-everywhere-src-6.8.3.tar.xz': 'https://download.qt.io/official_releases/QtForPython/pyside6/PySide6-6.8.3-src/pyside-setup-everywhere-src-6.8.3.tar.xz',
    'esptool-5.4.0.tar.gz': 'https://codeload.github.com/espressif/esptool/tar.gz/refs/tags/v5.4.0',
    'mesa-11.2.2.tar.xz': 'https://archive.mesa3d.org/older-versions/11.x/11.2.2/mesa-11.2.2.tar.xz',
    'llvm-3.6.2.src.tar.xz': 'https://releases.llvm.org/3.6.2/llvm-3.6.2.src.tar.xz',
    'openssl-1.1.1q.tar.gz': 'https://codeload.github.com/openssl/openssl/tar.gz/refs/tags/OpenSSL_1_1_1q',
    'Python-3.11.0.tar.xz': 'https://www.python.org/ftp/python/3.11.0/Python-3.11.0.tar.xz',
    'pywinrt-3.2.1.tar.gz': 'https://codeload.github.com/pywinrt/pywinrt/tar.gz/refs/tags/v3.2.1',
}

def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--python-sources',action='store_true')
    args=parser.parse_args()
    args.output.mkdir(parents=True,exist_ok=True)
    dest=ROOT/'release/licenses/upstream-source-notices'
    dest.mkdir(parents=True,exist_ok=True)
    source_urls = dict(SOURCES)
    expected_hashes = {}
    unavailable = []
    if args.python_sources:
        def pypi(dist):
            name = dist.metadata['Name']
            normalized = name.lower().replace('_','-')
            if normalized in ('pyside6-essentials','shiboken6','esptool') or normalized.startswith('winrt-'):return None
            url=f'https://pypi.org/pypi/{name}/{dist.version}/json'
            print('RESOLVE',name,dist.version,flush=True)
            data=json.load(urllib.request.urlopen(url,timeout=45))
            sdists=[row for row in data['urls'] if row['packagetype']=='sdist']
            if not sdists:
                return {'missing':{'name':name,'version':dist.version,'reason':'No PyPI sdist'}}
            return sdists[0]
        with ThreadPoolExecutor(max_workers=6) as pool:
            for item in pool.map(pypi,list(importlib.metadata.distributions())):
                if item is None:continue
                if 'missing' in item:
                    unavailable.append(item['missing']);continue
                source_urls[item['filename']]=item['url']
                expected_hashes[item['filename']]=item['digests']['sha256']
    def download(item):
        name,url=item
        target=args.output/name
        if not target.exists():
            temp=target.with_suffix(target.suffix+'.part')
            with urllib.request.urlopen(url,timeout=60) as response, temp.open('wb') as out:
                while data:=response.read(1024*1024):out.write(data)
            # Opening confirms a complete readable archive before accepting it.
            with tarfile.open(temp) as archive: archive.getmembers()
            temp.replace(target)
        actual=sha(target)
        if name in expected_hashes and actual != expected_hashes[name]:raise ValueError('PyPI hash mismatch: '+name)
        print('SOURCE',name,target.stat().st_size,flush=True)
        return {'archive':name,'url':url,'bytes':target.stat().st_size,'sha256':actual}
    with ThreadPoolExecutor(max_workers=3) as pool:
        sources=list(pool.map(download,source_urls.items()))
    notices=[]
    attributions=[]
    for source in sources:
        with tarfile.open(args.output/source['archive']) as archive:
            referenced = set()
            for member in archive.getmembers():
                if member.isfile() and PurePosixPath(member.name).name == 'qt_attribution.json':
                    data = json.loads(archive.extractfile(member).read().decode('utf-8'), strict=False)
                    for entry in data if isinstance(data,list) else [data]:
                        attributions.append({'archive':source['archive'],'member':member.name,'entry':entry})
                        files = entry.get('LicenseFile', [])
                        if isinstance(files,str):files=[files]
                        for name in files:
                            referenced.add(posixpath.normpath(posixpath.join(posixpath.dirname(member.name),name)))
            for member in archive:
                path=PurePosixPath(member.name)
                if not member.isfile() or path.is_absolute() or '..' in path.parts:continue
                if not (member.name in referenced or path.name=='qt_attribution.json' or any(x in path.name.lower() for x in ('license','licence','copying','copyright','notice'))):continue
                if (member.name not in referenced and path.suffix.lower() in ('.py','.c','.cpp','.h','.cmake','.js','.png','.svg')) or member.size>2_000_000:continue
                target=dest/source['archive']/Path(*path.parts[1:])
                if not target.resolve().is_relative_to(dest.resolve()):raise ValueError('Archive path escapes destination')
                target.parent.mkdir(parents=True,exist_ok=True)
                target.write_bytes(archive.extractfile(member).read())
                notices.append({'archive':source['archive'],'member':member.name,'path':target.relative_to(ROOT).as_posix(),'sha256':sha(target)})
    report={'sources':sources,'notices':notices,'attributions':attributions,'unavailable_python_sdists':unavailable,'scope':'Conservative module-level notices; not a claim that every bundled third-party library is used'}
    (ROOT/'docs/THIRD_PARTY_SOURCE_ARCHIVES.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    (args.output/'SOURCE_ARCHIVES.json').write_text(json.dumps({'sources':sources},indent=2),encoding='utf-8')
    print('Collected',len(notices),'notice/attribution files',flush=True)

if __name__=='__main__':main()
