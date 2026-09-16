"""Compile actual patched completion blocks against a minimal audio/state stub."""
from pathlib import Path
import subprocess
import tempfile
import sys
import os

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'xiaozhi'))
from apply_ui_overlay import single_turn

def main():
    source_root = Path(os.environ.get('SYNA_FIRMWARE_SOURCE', 'D:/syna-toolchains/xiaozhi-build'))
    text = (source_root/'main/application.cc').read_text(encoding='utf-8')
    stop = text.split('// Syna single-turn: server STOP may precede the last speaker samples.', 1)[1].split('\n                    }', 1)[0]
    drain = text.split('// Syna single-turn: finish only after playback drains.', 1)[1].split('        if (bits & MAIN_EVENT_PLAYBACK_DRAINED)', 1)[0]
    cpp = '''#include <cassert>
const int kDeviceStateIdle=0, kDeviceStateSpeaking=1;
const int MAIN_EVENT_PLAYBACK_DRAINED=1, MAIN_EVENT_CLOCK_TICK=2;
bool syna_reply_finished_=false; int state=1;
struct Audio { bool idle=false; bool IsPlaybackIdle(){return idle;} } audio_service_;
int GetDeviceState(){return state;} void SetDeviceState(int s){state=s;}
void stop(){''' + stop + '''}
void event(int bits){''' + drain + '''}
int main(){
 stop(); assert(state==1 && syna_reply_finished_);
 event(1); assert(state==1);
 audio_service_.idle=true; event(1); assert(state==0 && !syna_reply_finished_);
 state=1; stop(); assert(state==0 && !syna_reply_finished_);
 state=1; audio_service_.idle=false; stop(); audio_service_.idle=true;
 event(2); assert(state==0 && !syna_reply_finished_);
 state=1; event(1); assert(state==1);
}
'''
    with tempfile.TemporaryDirectory(prefix='syna-single-turn-') as folder:
        tmp=Path(folder)
        (tmp/'main').mkdir()
        for name in ('application.cc','application.h'):
            (tmp/'main'/name).write_bytes((source_root/'main'/name).read_bytes())
        single_turn(tmp)
        assert (tmp/'main/application.cc').read_text(encoding='utf-8') == text
        src=tmp/'test.cpp'; src.write_text(cpp, encoding='utf-8')
        exe=tmp/'test.exe'
        command=['cl.exe','/nologo','/EHsc',str(src),'/Fe:'+str(exe),'/Fo:'+str(tmp/'test.obj')]
        batch=tmp/'build.cmd'
        vcvars = Path(os.environ.get('SYNA_VCVARS', r'D:\vs\VC\Auxiliary\Build\vcvars64.bat'))
        batch.write_text('@echo off\nset VSCMD_SKIP_SENDTELEMETRY=1\ncall "'+str(vcvars)+'" >nul\n'+subprocess.list2cmdline(command)+'\nexit /b %errorlevel%\n')
        subprocess.run(['cmd.exe','/d','/c',str(batch)],check=True)
        subprocess.run([str(exe)],check=True)
    print('PASS: overlay idempotence, pending playback, immediate completion, clock fallback, no premature idle')

if __name__=='__main__': main()
