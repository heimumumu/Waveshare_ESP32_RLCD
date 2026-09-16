"""Windows installer worker. JSONL progress, no shell commands for flashing."""
import argparse
import ctypes
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time
import uuid

from partitions import FLASH_SIZE, parse_partitions, upgrade_offset

HERE = Path(__file__).resolve().parent
SUPPORT = Path(os.environ.get('LOCALAPPDATA', str(Path.home()))) / 'SynaInstaller'
CREATE_NO_WINDOW = getattr(subprocess, 'CREATE_NO_WINDOW', 0)


def emit(event, message='', **extra):
    # ASCII JSON survives Windows console code pages; json.loads restores Unicode.
    print(json.dumps(dict(event=event, message=message, **extra), ensure_ascii=True), flush=True)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def verify_payload(resources=HERE):
    from payload_manifest import MANIFEST_SHA256
    if sha(resources/'manifest.json') != MANIFEST_SHA256:
        raise ValueError('安装清单校验失败。')
    manifest = json.loads((resources/'manifest.json').read_text(encoding='utf-8'))
    base = (resources/'Payload').resolve()
    for name, digest in manifest.items():
        path = base/name
        if not path.resolve().is_relative_to(base) or path.is_symlink() or sha(path) != digest:
            raise ValueError('安装文件校验失败：'+name)
    return manifest


def tool(port, args, session):
    after = 'hard-reset' if args == ['run'] else 'no-reset'
    command = [sys.executable, '--esptool'] if getattr(sys, 'frozen', False) else [sys.executable, '-m', 'esptool']
    with (session/'device.log').open('ab') as log:
        result = subprocess.run([*command, '--chip', 'esp32s3',
            '--port', port, '--baud', '921600', '--after', after, *args],
            stdout=log, stderr=subprocess.STDOUT, timeout=600, creationflags=CREATE_NO_WINDOW)
    if result.returncode:
        raise RuntimeError('开发板操作失败，请查看 device.log。请勿清除备份；检查 USB 或按住 BOOT 重新连接。')


def flash(resources, port, mode, session, confirm_reset=False):
    if mode not in ('upgrade', 'fresh') or not re.fullmatch(r'COM[1-9]\d*', port or '', re.I):
        raise ValueError('请选择有效的开发板 COM 串口。')
    if mode == 'fresh' and not confirm_reset:
        raise ValueError('首次安装必须确认清除数据。')
    fw = resources/'Payload/Firmware'
    entries = parse_partitions((fw/'partition-table.bin').read_bytes())
    app = (fw/'xiaozhi.bin').read_bytes()
    if len(app) > 0x3f0000 or not app or app[0] != 0xe9 or b'esp32-s3-rlcd-4.2' not in app:
        raise ValueError('应用固件板型或容量错误。')
    segments = [(0, fw/'bootloader.bin'), (0x8000, fw/'partition-table.bin'),
                (0xd000, fw/'ota_data_initial.bin'), (0x20000, fw/'xiaozhi.bin'),
                (0x800000, fw/'generated_assets.bin')]
    limits = [0x8000, 0x1000, 0x2000, 0x3f0000, 0x800000]
    if any(path.stat().st_size > limit for (_, path), limit in zip(segments, limits)):
        raise ValueError('固件文件超出分区容量。')
    backup = session/'full-flash.bin'
    emit('progress', '读取完整 Flash 备份，请勿拔线。', progress=25)
    tool(port, ['read-flash', '0', 'ALL', str(backup)], session)
    if backup.stat().st_size != FLASH_SIZE:
        raise ValueError('只支持 16 MB Flash，未写入固件。')
    emit('progress', '校验设备备份。', progress=45)
    tool(port, ['verify-flash', '0', str(backup)], session)
    before = backup.read_bytes()
    (session/'backup.json').write_text(json.dumps({'sha256': sha(backup), 'bytes': len(before), 'verified': True}), encoding='utf-8')
    if mode == 'upgrade':
        offset = upgrade_offset(before, (fw/'partition-table.bin').read_bytes())
        entry = next(row for row in entries if row[2] == offset)
        if len(app) > entry[3]:
            raise ValueError('应用超出启动分区。')
        # Upgrade only the app. Incompatible assets need an explicit fresh install.
        assets = (fw/'generated_assets.bin').read_bytes()
        legacy_assets = hashlib.sha256(before[0x800000:0x800000+5291108]).hexdigest()
        if (before[0x800000:0x800000+len(assets)] != assets and
                legacy_assets != 'edb46341839d893b0fac986acb8198d24c3408d4c481fdc6e1780dd234286f55'):
            raise ValueError('资源版本与本包不一致，保留配置升级未写入。请先确认兼容资源方案。')
        segments = [(offset, fw/'xiaozhi.bin')]
    else:
        emit('progress', '备份已校验，清除开发板原有数据。', progress=50)
        tool(port, ['erase-flash'], session)
    emit('progress', '写入固件，请勿断电或拔线。', progress=60)
    args = ['write-flash']
    for offset, path in segments:
        args.extend([hex(offset), str(path)])
    tool(port, args, session)
    emit('progress', '完整读回验证固件与保留区域。', progress=75)
    after_path = session/'after-flash.bin'
    tool(port, ['read-flash', '0', 'ALL', str(after_path)], session)
    after = after_path.read_bytes()
    if len(after) != FLASH_SIZE:
        raise ValueError('读回文件不完整。')
    for offset, path in segments:
        data = path.read_bytes()
        if after[offset:offset+len(data)] != data:
            raise ValueError('固件读回内容不一致。')
    if mode == 'upgrade':
        offset = segments[0][0]
        end = (offset + len(app) + 4095) // 4096 * 4096
        if before[:offset] != after[:offset] or before[end:] != after[end:]:
            raise ValueError('应用范围之外的数据发生变化，请保留备份并检查。')
    (session/'firmware-complete.json').write_text(json.dumps({'mode': mode, 'sha256': sha(fw/'xiaozhi.bin'),
        'readback_verified': True, 'configuration_preserved': mode == 'upgrade'}), encoding='utf-8')
    emit('progress', '校验通过，重启开发板。', progress=95)
    tool(port, ['run'], session)


def install_reporter(resources, session, login, manifest):
    emit('progress', '安装 Reporter；如出现 Windows 权限提示，请确认。', progress=10)
    powershell = 'powershell.exe'
    sid = subprocess.check_output([powershell, '-NoProfile', '-NonInteractive', '-Command',
        '[Security.Principal.WindowsIdentity]::GetCurrent().User.Value'],
        creationflags=CREATE_NO_WINDOW, text=True).strip()
    helper = resources/'Payload/install_reporter.ps1'
    # Pass paths through a JSON parameter file, not interpolated shell code.
    params = {'Payload': str(resources/'Payload'), 'Session': str(session),
              'ExpectedHash': manifest['SynaReporter.exe'], 'UserSid': sid, 'Login': 'on' if login else 'off'}
    params_path = session/'install-params.json'
    params_path.write_text(json.dumps(params), encoding='utf-8')
    launcher = session/'elevated-launch.ps1'
    launcher.write_text("$ErrorActionPreference='Stop'\n"
        "$p = Get-Content -LiteralPath (Join-Path $PSScriptRoot 'install-params.json') -Raw | ConvertFrom-Json\n"
        "$argsMap=@{}; $p.PSObject.Properties | ForEach-Object { $argsMap[$_.Name]=$_.Value }\n"
        "& (Join-Path $p.Payload 'install_reporter.ps1') @argsMap\nexit $LASTEXITCODE\n", encoding='utf-8')
    # Launch the fixed script through ShellExecuteEx, and wait for that process
    # alone. No recursive batch files and no waiting for Reporter descendants.
    from ctypes import wintypes
    class SHELLEXECUTEINFO(ctypes.Structure):
        _fields_ = [('cbSize', wintypes.DWORD), ('fMask', ctypes.c_ulong), ('hwnd', wintypes.HWND),
            ('lpVerb', wintypes.LPCWSTR), ('lpFile', wintypes.LPCWSTR), ('lpParameters', wintypes.LPCWSTR),
            ('lpDirectory', wintypes.LPCWSTR), ('nShow', ctypes.c_int), ('hInstApp', wintypes.HINSTANCE),
            ('lpIDList', ctypes.c_void_p), ('lpClass', wintypes.LPCWSTR), ('hkeyClass', wintypes.HKEY),
            ('dwHotKey', wintypes.DWORD), ('hIcon', wintypes.HANDLE), ('hProcess', wintypes.HANDLE)]
    info = SHELLEXECUTEINFO()
    info.cbSize = ctypes.sizeof(info)
    info.fMask = 0x40 | 0x100  # NOCLOSEPROCESS | NOASYNC
    info.lpVerb = 'runas'
    info.lpFile = powershell
    info.lpParameters = subprocess.list2cmdline(['-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', str(launcher)])
    info.nShow = 0
    shell = ctypes.WinDLL('shell32', use_last_error=True)
    shell.ShellExecuteExW.argtypes = [ctypes.POINTER(SHELLEXECUTEINFO)]
    shell.ShellExecuteExW.restype = wintypes.BOOL
    if not shell.ShellExecuteExW(ctypes.byref(info)):
        raise ctypes.WinError(ctypes.get_last_error())
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
    kernel.GetExitCodeProcess.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    try:
        kernel.WaitForSingleObject(info.hProcess, 0xffffffff)
        code = wintypes.DWORD()
        if not kernel.GetExitCodeProcess(info.hProcess, ctypes.byref(code)):
            raise ctypes.WinError(ctypes.get_last_error())
    finally:
        kernel.CloseHandle(info.hProcess)
    result_file = session/'reporter-result.json'
    result = json.loads(result_file.read_text(encoding='utf-8-sig')) if result_file.exists() else {}
    if code.value or not result.get('success'):
        raise RuntimeError(result.get('error') or 'Reporter 安装未完成或权限已取消。')
    app = Path(result['app'])
    if sha(app) != manifest['SynaReporter.exe']:
        raise ValueError('安装后的 Reporter 校验失败。')
    return app


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--mode', choices=['upgrade', 'fresh', 'reporter'])
    parser.add_argument('--resources', type=Path, default=HERE)
    parser.add_argument('--verify-only', action='store_true')
    parser.add_argument('--port', default='')
    parser.add_argument('--confirm-reset', action='store_true')
    parser.add_argument('--login', choices=['on','off'])
    args = parser.parse_args()
    resources = args.resources.resolve()
    manifest = verify_payload(resources)
    if args.verify_only:
        emit('verified', 'Payload verified', files=len(manifest))
        return
    if not args.mode or not args.login:
        parser.error('--mode and --login are required for installation')
    if args.mode == 'fresh' and not args.confirm_reset:
        raise ValueError('首次安装尚未确认清除。')
    if args.mode != 'reporter':
        from serial.tools import list_ports
        if args.port not in {p.device for p in list_ports.comports()}:
            raise ValueError('所选串口已断开，请刷新设备。')
        import esptool  # Check runtime before any installation changes.
    SUPPORT.mkdir(parents=True, exist_ok=True)
    import msvcrt
    with (SUPPORT/'install.lock').open('a+b') as lock:
        lock.seek(0)
        if not lock.read(1):
            lock.write(b'0'); lock.flush()
        lock.seek(0)
        msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
        session = SUPPORT/'Backups'/(time.strftime('%Y%m%d-%H%M%S-')+uuid.uuid4().hex[:6])
        session.mkdir(parents=True)
        emit('backup', '安装文件完整性校验通过，备份与日志目录已创建。', path=str(session))
        config = Path(os.environ['LOCALAPPDATA'])/'AIAgentPanel/reporter.json'
        if config.exists():
            shutil.copy2(config, session/'reporter.json')
        try:
            app = install_reporter(resources, session, args.login == 'on', manifest)
            emit('reporter_installed', 'Reporter 安装与校验完成。', app=str(app))
            if args.mode != 'reporter':
                flash(resources, args.port, args.mode, session, args.confirm_reset)
            (session/'result.json').write_text(json.dumps({'success': True, 'mode': args.mode, 'app': str(app)}), encoding='utf-8')
            emit('done', '安装完成，校验通过。', app=str(app), progress=100)
        except Exception as error:
            (session/'error.txt').write_text(str(error), encoding='utf-8')
            raise


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        emit('error', str(error))
        sys.exit(1)
