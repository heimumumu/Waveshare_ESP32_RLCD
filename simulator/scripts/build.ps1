$ErrorActionPreference = 'Stop'

& (Join-Path $PSScriptRoot 'configure.ps1')

$cmake = Join-Path ([Environment]::GetFolderPath('UserProfile')) 'Tools\msys64\ucrt64\bin\cmake.exe'
$buildDir = 'C:\ai-panel-build\simulator'

& $cmake --build $buildDir --parallel
if ($LASTEXITCODE -ne 0) {
    throw "Simulator build failed with exit code $LASTEXITCODE"
}
