param(
    [string]$ToolchainRoot = 'D:\syna-toolchains'
)

# Dot-source this script to activate the pinned environment in this terminal.
$ErrorActionPreference = 'Stop'
$synaIdfRoot = Join-Path $ToolchainRoot 'esp-idf-v6.0.2'
$synaPython = Join-Path $ToolchainRoot 'tools\python_env\idf6.0_py3.11_env\Scripts\python.exe'
$synaGit = 'D:\vs\Common7\IDE\CommonExtensions\Microsoft\TeamFoundation\Team Explorer\Git\cmd'
if (-not (Test-Path -LiteralPath $synaPython) -or
    -not (Test-Path -LiteralPath (Join-Path $synaIdfRoot 'export.ps1'))) {
    throw "Pinned ESP-IDF environment is not installed in $ToolchainRoot. See xiaozhi/WINDOWS-TOOLCHAIN.md."
}
if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
    if (-not (Test-Path -LiteralPath (Join-Path $synaGit 'git.exe'))) {
        throw 'Git is required. Add Git to PATH before activating ESP-IDF.'
    }
    $env:PATH = $synaGit + ';' + $env:PATH
}
$env:IDF_TOOLS_PATH = Join-Path $ToolchainRoot 'tools'
$env:IDF_PYTHON_ENV_PATH = Split-Path (Split-Path $synaPython -Parent) -Parent
$env:SYNA_IDF_ROOT = $synaIdfRoot
$env:PYTHONUTF8 = '1'
$env:IDF_GITHUB_ASSETS = 'dl.espressif.com/github_assets'
$env:PATH = (Split-Path $synaPython -Parent) + ';' + $env:PATH
. (Join-Path $synaIdfRoot 'export.ps1')
$synaVersion = & python (Join-Path $synaIdfRoot 'tools\idf.py') --version
if ($LASTEXITCODE -ne 0 -or $synaVersion -notmatch '^ESP-IDF v6\.0\.2$') {
    throw "Unexpected ESP-IDF version: $synaVersion"
}
Write-Host "Syna toolchain ready: $synaVersion"
