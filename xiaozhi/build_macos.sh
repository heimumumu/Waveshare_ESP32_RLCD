#!/bin/bash
# Copyright (c) 2026 黑沐. MIT License; upstream notices retained.
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
SOURCE="${1:-$HOME/.local/share/syna-toolchains/xiaozhi-build}"
IDF_ROOT="${SYNA_IDF_ROOT:-$HOME/.local/share/syna-toolchains/esp-idf-v6.0.2}"
export PATH="$HOME/.local/share/syna-toolchains/bootstrap/bin:$HOME/.local/bin:$PATH"
if [[ ! -f "$SOURCE/main/CMakeLists.txt" || ! -f "$IDF_ROOT/export.sh" ]]; then
    echo 'Missing pinned Xiaozhi source or ESP-IDF v6.0.2. See xiaozhi/README.md.' >&2
    exit 1
fi
# ESP-IDF environment scripts do not support nounset.
set +u
source "$IDF_ROOT/export.sh"
set -u
idf.py --version | grep -F 'v6.0.2' >/dev/null || {
    echo 'This build requires ESP-IDF v6.0.2.' >&2; exit 1;
}
python "$HERE/apply_ui_overlay.py" "$SOURCE" --phase source
cd "$SOURCE"
python -c 'from pathlib import Path; p=str(Path.cwd()); assert p.isascii() and not any(c.isspace() for c in p), "Use an ASCII source path without spaces for the Xtensa toolchain"'
# Resolve managed dependencies before applying the existing Wi-Fi extension hooks.
idf.py -DIDF_TARGET=esp32s3 '-DSDKCONFIG_DEFAULTS=sdkconfig.defaults;syna.sdkconfig.defaults' -DBOARD_NAME=esp32-s3-rlcd-4.2 reconfigure
python "$HERE/apply_ui_overlay.py" "$SOURCE" --phase components
python scripts/build.py waveshare/esp32-s3-rlcd-4.2 --name esp32-s3-rlcd-4.2 --language zh-CN
echo "Build complete: $SOURCE/build/xiaozhi.bin"
echo 'No device was flashed. Back up flash and check partitions before installation.'
