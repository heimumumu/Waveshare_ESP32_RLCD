# Syna project-specific code and modifications: Copyright (c) 2026 黑沐.
# SPDX-License-Identifier: MIT; third-party notices remain applicable.
"""Host-specific paths and process helpers shared by Reporter launchers."""
from __future__ import annotations

import os
from pathlib import Path
import platform
import shutil
import sys


def application_data_dir() -> Path:
    override = os.environ.get("SYNA_REPORTER_DATA_DIR")
    if override:
        return Path(override).expanduser()
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "SynaReporter"
    return Path(os.environ.get("LOCALAPPDATA", Path.home())) / "AIAgentPanel"


def disk_root() -> str:
    if os.name == "nt":
        return os.environ.get("SystemDrive", "C:") + "\\"
    if sys.platform == "darwin" and Path("/System/Volumes/Data").is_dir():
        return "/System/Volumes/Data"
    return "/"


def codex_executable() -> str | None:
    override = os.environ.get("SYNA_CODEX_EXECUTABLE")
    if override:
        path = Path(override).expanduser()
        return str(path) if path.is_file() and os.access(path, os.X_OK) else None
    executable = shutil.which("codex")
    if executable:
        return executable
    if sys.platform == "darwin":
        architecture = "aarch64" if platform.machine() == "arm64" else "x86_64"
        pattern = f"openai.chatgpt-*-darwin-*/bin/macos-{architecture}/codex"
        candidates = [
            Path("/Applications/Codex.app/Contents/Resources/codex"),
            Path.home() / "Applications/Codex.app/Contents/Resources/codex",
            Path("/opt/homebrew/bin/codex"), Path("/usr/local/bin/codex"),
        ]
    elif os.name == "nt":
        pattern = "openai.chatgpt-*-win32-x64/bin/windows-x86_64/codex.exe"
        candidates = []
    else:
        pattern = "openai.chatgpt-*/bin/linux-*/codex"
        candidates = []
    for name in (".vscode", ".vscode-insiders"):
        candidates.extend((Path.home() / name / "extensions").glob(pattern))
    candidates = [p for p in candidates if p.is_file() and os.access(p, os.X_OK)]
    return str(max(candidates, key=lambda p: p.stat().st_mtime)) if candidates else None


def acquire_posix_instance(role: str):
    """Keep the returned file open for the process lifetime. Never unlink it."""
    import fcntl

    root = application_data_dir()
    root.mkdir(parents=True, exist_ok=True)
    handle = (root / f"{role}.lock").open("a+")
    try:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        handle.close()
        return None
    return handle
