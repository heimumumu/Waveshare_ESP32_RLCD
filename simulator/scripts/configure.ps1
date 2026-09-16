param(
    [switch]$Fresh
)

$ErrorActionPreference = 'Stop'

$simulatorDir = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$toolchainRoot = Join-Path ([Environment]::GetFolderPath('UserProfile')) 'Tools\msys64\ucrt64\bin'
$buildDir = 'C:\ai-panel-build\simulator'

$cmake = Join-Path $toolchainRoot 'cmake.exe'
$gcc = Join-Path $toolchainRoot 'gcc.exe'
$gxx = Join-Path $toolchainRoot 'g++.exe'
$ninja = Join-Path $toolchainRoot 'ninja.exe'

foreach ($requiredTool in @($cmake, $gcc, $gxx, $ninja)) {
    if (-not (Test-Path -LiteralPath $requiredTool)) {
        throw "Simulator tool is missing: $requiredTool"
    }
}

# GCC helper processes (cc1, ld) load their runtime DLLs from this directory.
$env:Path = "$toolchainRoot;$env:Path"

$cmakeArguments = @()
if ($Fresh) {
    $cmakeArguments += '--fresh'
}

$cmakeArguments += @(
    '-S', $simulatorDir,
    '-B', $buildDir,
    '-G', 'Ninja',
    '-DCMAKE_BUILD_TYPE=Debug',
    "-DCMAKE_C_COMPILER=$gcc",
    "-DCMAKE_CXX_COMPILER=$gxx",
    "-DCMAKE_MAKE_PROGRAM=$ninja",
    "-DCMAKE_PREFIX_PATH=$toolchainRoot\.."
)

& $cmake @cmakeArguments

if ($LASTEXITCODE -ne 0) {
    throw "CMake configuration failed with exit code $LASTEXITCODE"
}
