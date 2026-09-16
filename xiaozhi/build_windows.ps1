param(
    [string]$SourceRoot = 'D:\syna-toolchains\xiaozhi-build',
    [string]$ToolchainRoot = 'D:\syna-toolchains'
)

$ErrorActionPreference = 'Stop'
$SourceRoot = [IO.Path]::GetFullPath($SourceRoot)
if ($SourceRoot -match '[^\x00-\x7F]|\s') {
    throw 'Use an ASCII source path without spaces for the Xtensa toolchain.'
}
. (Join-Path $PSScriptRoot 'enter-idf.ps1') -ToolchainRoot $ToolchainRoot
& python -c "import numpy; from PIL import Image"
if ($LASTEXITCODE -ne 0) {
    throw 'Missing asset dependencies. In the activated IDF environment run: python -m pip install -r xiaozhi/requirements-firmware.txt'
}
$synaOverlay = Join-Path $PSScriptRoot 'apply_ui_overlay.py'
$synaIdf = Join-Path $env:IDF_PATH 'tools\idf.py'
& python $synaOverlay $SourceRoot --phase source
if ($LASTEXITCODE -ne 0) { throw 'Could not apply the pinned source overlay.' }
Push-Location $SourceRoot
try {
    & python $synaIdf '-DIDF_TARGET=esp32s3' '-DSDKCONFIG_DEFAULTS=sdkconfig.defaults;syna.sdkconfig.defaults' '-DBOARD_NAME=esp32-s3-rlcd-4.2' reconfigure
    if ($LASTEXITCODE -ne 0) { throw 'ESP-IDF dependency resolution failed.' }
    & python $synaOverlay $SourceRoot --phase components
    if ($LASTEXITCODE -ne 0) { throw 'Could not apply the Wi-Fi component overlay.' }
    & python scripts/build.py 'waveshare/esp32-s3-rlcd-4.2' --name 'esp32-s3-rlcd-4.2' --language zh-CN
    if ($LASTEXITCODE -ne 0) { throw 'Firmware build failed.' }
    Write-Host "Build complete: $SourceRoot\build\xiaozhi.bin"
    Write-Host 'No device was flashed. Back up flash and check partitions before installation.'
}
finally {
    Pop-Location
}
