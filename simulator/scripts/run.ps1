$ErrorActionPreference = 'Stop'

& (Join-Path $PSScriptRoot 'build.ps1')

$simulatorExe = 'C:\ai-panel-build\simulator\bin\ai_panel_simulator.exe'
& $simulatorExe
if ($LASTEXITCODE -ne 0) {
    throw "Simulator exited with code $LASTEXITCODE"
}
