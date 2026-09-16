"""Read-only smoke tests and embedded-notice checks for a rebuilt candidate."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile
from PyInstaller.archive.readers import CArchiveReader

ROOT=Path(__file__).resolve().parents[1]
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--validation-root',type=Path,required=True)
    args=parser.parse_args();base=args.validation_root.resolve()
    reporter=base/'source/reporter/dist/SynaReporter.exe'
    installer=base/'source/installer/windows/dist/SynaInstaller-1.0.0.exe'
    env=os.environ.copy()
    env['PATH']=os.environ['SystemRoot']+'/System32;'+os.environ['SystemRoot']
    env['PYTHONUTF8']='0';env['PYTHONIOENCODING']='cp936'
    for key in ('PYTHONHOME','PYTHONPATH','VIRTUAL_ENV','IDF_PATH','IDF_TOOLS_PATH'):env.pop(key,None)
    report={'passed':False,'installed_or_flashed':False,'artifacts':{},'embedded_notices':{}}
    with tempfile.TemporaryDirectory(prefix='syna-candidate-test-') as folder:
        env['LOCALAPPDATA']=folder
        subprocess.run([str(reporter),'--self-test'],env=env,cwd=folder,timeout=90,check=True,creationflags=subprocess.CREATE_NO_WINDOW)
        output=Path(folder)/'installer-test.json'
        subprocess.run([str(installer),'--self-test',str(output)],env=env,cwd=folder,timeout=150,check=True,creationflags=subprocess.CREATE_NO_WINDOW)
        report['installer_self_test']=json.loads(output.read_text(encoding='utf-8'))
    for name,path,prefix in [('reporter',reporter,'Legal/third-party/'),('installer',installer,'Licenses/Syna-third-party/')]:
        archive=CArchiveReader(str(path))
        names={x.replace('\\','/'):x for x in archive.toc}
        count=0
        for source in (ROOT/'release/licenses').rglob('*'):
            if not source.is_file():continue
            key=prefix+source.relative_to(ROOT/'release/licenses').as_posix()
            if key not in names:raise ValueError('Missing embedded notice: '+key)
            if hashlib.sha256(archive.extract(names[key])).hexdigest()!=sha(source):raise ValueError('Notice content mismatch: '+key)
            count+=1
        report['embedded_notices'][name]=count
    for name,path in [('reporter',reporter),('installer',installer),('firmware',base/'firmware/build/xiaozhi.bin')]:
        report['artifacts'][name]={'path':path.relative_to(base).as_posix(),'bytes':path.stat().st_size,'sha256':sha(path)}
    report['passed']=True
    (base/'candidate-verification.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    (ROOT/'docs/RELEASE_CANDIDATE.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps(report,indent=2))

if __name__=='__main__':main()
