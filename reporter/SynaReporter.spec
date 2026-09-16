# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_submodules, copy_metadata
from pathlib import Path

# Keep Qt/PySide notices in the bundle; the UI is dynamically linked.
notices = []
for package in ("PySide6_Essentials", "shiboken6"):
    notices += copy_metadata(package)
notices += [(str(Path(SPECPATH).parent / "LICENSE"), "Legal"),
            (str(Path(SPECPATH).parent / "THIRD_PARTY_NOTICES.md"), "Legal"),
            (str(Path(SPECPATH).parent / "release/licenses"), "Legal/third-party"),
            (str(Path(SPECPATH).parent / "docs/THIRD_PARTY_SOURCES.md"), "Legal")]

hiddenimports = []
for package in ("winrt", "pycaw", "comtypes"):
    hiddenimports += collect_submodules(package)

a = Analysis(
    ["reporter.py"],
    pathex=[SPECPATH],
    binaries=[],
    datas=notices,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="SynaReporter",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
)
