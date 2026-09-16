#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")"
[[ "$(uname -s)" == Darwin ]] || { echo "请在 macOS 上构建。"; exit 1; }
[[ -x .venv-macos/bin/python ]] || "${SYNA_PYTHON:-python3}" -m venv .venv-macos
.venv-macos/bin/python -m pip install --disable-pip-version-check -r requirements.txt 'pyinstaller==6.16.0'
dist_dir="${SYNA_DIST_DIR:-dist-macos}"
build_dir="${SYNA_BUILD_DIR:-build-macos}"
.venv-macos/bin/python -m PyInstaller --noconfirm --clean --windowed --onedir \
    --name SynaReporter --osx-bundle-identifier local.syna.reporter \
    --distpath "$dist_dir" --workpath "$build_dir" --specpath "$build_dir" reporter.py
app_dir="$dist_dir/SynaReporter.app"
mv "$app_dir/Contents/MacOS/SynaReporter" "$app_dir/Contents/MacOS/ReporterBackend"
swiftc -O -target "$(uname -m)-apple-macos13.0" -framework Cocoa -framework Foundation -framework ServiceManagement native_ui.swift \
    -module-cache-path "$build_dir/swift-cache" -o "$app_dir/Contents/MacOS/SynaReporter"
clang -O2 -Wall -Wextra -framework IOKit macos_thermal.c -o "$app_dir/Contents/MacOS/MacThermalProbe"
/usr/libexec/PlistBuddy -c "Set :CFBundleShortVersionString 1.0.0" "$app_dir/Contents/Info.plist"
/usr/libexec/PlistBuddy -c "Set :CFBundleVersion 1.0.0" "$app_dir/Contents/Info.plist"
/usr/libexec/PlistBuddy -c "Add :LSMinimumSystemVersion string 13.0" "$app_dir/Contents/Info.plist"
mkdir -p "$app_dir/Contents/Resources/Legal"
cp ../LICENSE ../THIRD_PARTY_NOTICES.md "$app_dir/Contents/Resources/Legal/"
codesign --force --deep --sign - "$app_dir"
echo "已生成 $(pwd)/${app_dir}（本机架构、含状态窗口，未做 Developer ID 公证）。"
