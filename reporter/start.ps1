$ErrorActionPreference = 'Stop'

$reporterRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$python = Join-Path $reporterRoot '.venv\Scripts\python.exe'

if (-not (Test-Path -LiteralPath $python)) {
    python -m venv (Join-Path $reporterRoot '.venv')
}

& $python -m pip install --disable-pip-version-check -r (Join-Path $reporterRoot 'requirements.txt')
if ($LASTEXITCODE -ne 0) {
    throw "Reporter dependencies could not be installed."
}

& $python (Join-Path $reporterRoot 'reporter.py')
