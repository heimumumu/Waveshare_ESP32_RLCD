"""Exercise the actual firmware quota renderer with a small LVGL host stub."""
from pathlib import Path
import re
import subprocess
import tempfile
import os
from check_panel_buttons import method, BOARD, ROOT

support = r'''
#include <cstdio>
#include <cassert>
#include <string>
struct lv_obj_t { std::string text; int width=0; bool hidden=false; };
lv_obj_t labels[2], fills[2];
lv_obj_t *dashboard_short_quota_label=&labels[0], *dashboard_week_quota_label=&labels[1];
lv_obj_t *dashboard_short_quota_fill=&fills[0], *dashboard_week_quota_fill=&fills[1];
const int LV_OBJ_FLAG_HIDDEN=1;
bool lv_obj_is_valid(lv_obj_t *p) {return p != nullptr;}
void lv_label_set_text(lv_obj_t *p,const char *s) {p->text=s;}
void lv_obj_set_width(lv_obj_t *p,int n) {p->width=n;}
void lv_obj_remove_flag(lv_obj_t *p,int) {p->hidden=false;}
void lv_obj_add_flag(lv_obj_t *p,int) {p->hidden=true;}
'''
scenarios = r'''
int main() {
 ui_update_codex_quota(-1,64,true,true);
 assert(labels[0].text=="--" && labels[1].text=="~64%");
 ui_update_codex_quota(0,100,true,true);
 assert(labels[0].text=="~0%" && labels[1].text=="~100%");
 assert(fills[0].hidden && !fills[1].hidden);
 ui_update_codex_quota(10,60,true,false);
 assert(labels[0].text=="10%" && labels[1].text=="60%");
 ui_update_codex_quota(-1,-1,true,false);
 assert(labels[0].text=="--" && labels[1].text=="--");
 ui_update_codex_quota(10,60,false,true);
 assert(labels[0].text=="--" && labels[1].text=="--");
 assert(fills[0].hidden && fills[1].hidden);
 puts("PASS: stale, recovery, missing, expiry, zero, full, disconnected");
}
'''

def main():
    font = (BOARD / 'ui_font_18_regular.c').read_text(encoding='utf-8')
    offsets = [int(x) for x in re.findall(r'\d+', re.search(r'unicode_list\[\]\s*=\s*\{(.*?)\}', font, re.S)[1])]
    advances = [int(x) / 16 for x in re.findall(r'\.adv_w=(\d+)', font)]
    width = sum(advances[offsets.index(ord(c)-32)+1] for c in '~100%')
    assert width <= 57, f'Cached quota text exceeds label width: {width}'
    print('Maximum cached quota advance:', width)
    with tempfile.TemporaryDirectory(prefix='syna-quota-', ignore_cleanup_errors=True) as tmp:
        directory = Path(tmp)
        source = directory / 'test.cpp'
        source.write_text(support + method(BOARD/'ui.c', 'void ui_update_codex_quota(') + scenarios, encoding='utf-8')
        exe = directory / 'test.exe'
        command = ['cl.exe', '/nologo', '/EHsc', '/std:c++17', '/utf-8', str(source), '/Fe:'+str(exe), '/Fo:'+str(directory/'test.obj')]
        batch = directory/'build.cmd'
        vcvars = Path(os.environ.get('SYNA_VCVARS', r'D:\vs\VC\Auxiliary\Build\vcvars64.bat'))
        batch.write_text('@echo off\nchcp 65001 >nul\nset VSCMD_SKIP_SENDTELEMETRY=1\ncall "'+str(vcvars)+'" >nul\n'+subprocess.list2cmdline(command)+'\nexit /b %errorlevel%\n', encoding='utf-8')
        subprocess.run(['cmd.exe','/d','/c',str(batch)],cwd=ROOT,check=True)
        subprocess.run([str(exe)],check=True)

if __name__ == '__main__':
    main()
