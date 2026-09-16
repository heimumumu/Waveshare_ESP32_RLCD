param([string]$Version = '1.0.0', [switch]$UseExistingExe)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$release = Join-Path $root 'release'
$stage = Join-Path $env:TEMP ("syna-reporter-package-{0}" -f [guid]::NewGuid().ToString('N'))
$dist = Join-Path $root 'dist'
$exe = Join-Path $dist 'SynaReporter.exe'
$python = Join-Path $root '.venv\Scripts\python.exe'
$temporarySetup = Join-Path $env:TEMP ("SynaReporter-Setup-{0}.exe" -f [guid]::NewGuid().ToString('N'))

Push-Location $root
try {
    if (-not $UseExistingExe) {
        if (-not (Test-Path -LiteralPath $python)) {
            python -m venv (Join-Path $root '.venv')
        }
        & $python -m pip install --disable-pip-version-check -r (Join-Path $root 'requirements-build.txt')
        if ($LASTEXITCODE -ne 0) { throw 'Could not install Reporter build dependencies.' }
        & $python -m PyInstaller --noconfirm --clean (Join-Path $root 'SynaReporter.spec')
        if ($LASTEXITCODE -ne 0) {
            throw 'PyInstaller failed to create SynaReporter.exe.'
        }
    }
    if (-not (Test-Path -LiteralPath $exe)) { throw 'SynaReporter.exe is missing.' }
    $selfTest = Start-Process -FilePath $exe -ArgumentList '--self-test' -WindowStyle Hidden -Wait -PassThru
    if ($selfTest.ExitCode -ne 0) { throw 'The packaged Reporter self-test failed.' }

    New-Item -ItemType Directory -Force -Path $stage | Out-Null
    Copy-Item -LiteralPath $exe -Destination (Join-Path $stage 'SynaReporter.exe') -Force
    Copy-Item -LiteralPath (Join-Path $root 'installer\install.cmd') -Destination $stage -Force
    Copy-Item -LiteralPath (Join-Path $root 'installer\uninstall.cmd') -Destination $stage -Force
    # cmd.exe scripts must have Windows line endings, including after chcp.
    foreach ($scriptName in @('install.cmd', 'uninstall.cmd')) {
        $scriptPath = Join-Path $stage $scriptName
        $scriptText = [IO.File]::ReadAllText($scriptPath)
        $scriptText = $scriptText.Replace("`r`n", "`n").Replace("`r", "`n").Replace("`n", "`r`n")
        [IO.File]::WriteAllText($scriptPath, $scriptText, (New-Object Text.UTF8Encoding($false)))
    }

    $sed = Join-Path $release 'SynaReporter.sed'
    $setup = Join-Path $release "SynaReporter-Setup-$Version.exe"
    $sedText = @"
[Version]
Class=IEXPRESS
SEDVersion=3
[Options]
PackagePurpose=InstallApp
ShowInstallProgramWindow=0
HideExtractAnimation=1
UseLongFileName=1
InsideCompressed=0
CAB_FixedSize=0
CAB_ResvCodeSigning=0
RebootMode=N
InstallPrompt=
DisplayLicense=
FinishMessage=
TargetName=$temporarySetup
FriendlyName=Syna Reporter Setup $Version
AppLaunched=install.cmd
PostInstallCmd=<None>
AdminQuietInstCmd=install.cmd /elevated
UserQuietInstCmd=install.cmd
SourceFiles=SourceFiles
[Strings]
FILE0=SynaReporter.exe
FILE1=install.cmd
FILE2=uninstall.cmd
[SourceFiles]
SourceFiles0=$stage\
[SourceFiles0]
%FILE0%=
%FILE1%=
%FILE2%=
"@
    Set-Content -LiteralPath $sed -Value $sedText -Encoding ASCII
    & "$env:SystemRoot\System32\iexpress.exe" /N /Q $sed
    # Windows 10 IExpress can return before its cabinet writer has created and
    # closed the output. It can also briefly close a small partial file, so
    # require a plausible size that remains unchanged for two seconds before
    # accepting the package.
    $deadline = [DateTime]::UtcNow.AddSeconds(60)
    $packageReady = $false
    $minimumPackageSize = [Math]::Max(1MB, [int64]((Get-Item -LiteralPath $exe).Length / 2))
    $lastPackageSize = -1L
    $stableSamples = 0
    while (-not $packageReady -and [DateTime]::UtcNow -lt $deadline) {
        if (Test-Path -LiteralPath $temporarySetup) {
            $currentPackageSize = (Get-Item -LiteralPath $temporarySetup).Length
            if ($currentPackageSize -ge $minimumPackageSize -and
                $currentPackageSize -eq $lastPackageSize) {
                ++$stableSamples
            } else {
                $stableSamples = 0
            }
            $lastPackageSize = $currentPackageSize
            $packageReady = $stableSamples -ge 8
        }
        if (-not $packageReady) { Start-Sleep -Milliseconds 250 }
    }
    if (-not $packageReady) {
        throw 'IExpress failed to create the Windows installer.'
    }
    Copy-Item -LiteralPath $temporarySetup -Destination $setup -Force
    Write-Host "Created $setup"
}
finally {
    if (Test-Path -LiteralPath $temporarySetup) {
        Remove-Item -LiteralPath $temporarySetup -Force -ErrorAction SilentlyContinue
    }
    if (Test-Path -LiteralPath $stage) {
        $resolvedStage = [IO.Path]::GetFullPath($stage)
        $resolvedTemp = [IO.Path]::GetFullPath($env:TEMP).TrimEnd('\') + '\'
        if ($resolvedStage.StartsWith($resolvedTemp, [StringComparison]::OrdinalIgnoreCase)) {
            Remove-Item -LiteralPath $resolvedStage -Recurse -Force -ErrorAction SilentlyContinue
        }
    }
    Pop-Location
}
