#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")"
if [[ "$(uname -s)" != Darwin ]]; then
    echo "此启动脚本用于 macOS。"
    exit 1
fi
if [[ $# -eq 0 && -d dist-macos/SynaReporter.app ]]; then
    open "$PWD/dist-macos/SynaReporter.app"
    exit 0
fi
if [[ ! -x .venv-macos/bin/python ]]; then
    "${SYNA_PYTHON:-python3}" -m venv .venv-macos
fi
# pip checks installed versions; subsequent launches work without downloads.
.venv-macos/bin/python -m pip install --disable-pip-version-check -r requirements.txt
exec .venv-macos/bin/python reporter.py "$@"
