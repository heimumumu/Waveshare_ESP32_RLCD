param(
    [Parameter(Mandatory=$true)][string]$Payload,
    [Parameter(Mandatory=$true)][string]$Session,
    [Parameter(Mandatory=$true)][string]$ExpectedHash,
    [Parameter(Mandatory=$true)][string]$UserSid,
    [Parameter(Mandatory=$true)][ValidateSet('on','off')][string]$Login
)
$ErrorActionPreference = 'Stop'
$resultPath = Join-Path $Session 'reporter-result.json'
try {
    $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = New-Object Security.Principal.WindowsPrincipal($identity)
    if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
        throw 'Administrator permission was not obtained.'
    }
    if ($identity.User.Value -ne $UserSid) { throw 'Use the same Windows account to authorize installation.' }
    $source = Join-Path $Payload 'SynaReporter.exe'
    if ((Get-FileHash -LiteralPath $source -Algorithm SHA256).Hash -ne $ExpectedHash) {
        throw 'Reporter payload hash mismatch.'
    }
    $destination = Join-Path $env:ProgramFiles 'Syna Reporter'
    if (Test-Path -LiteralPath $destination) {
        if ((Get-Item -LiteralPath $destination).Attributes -band [IO.FileAttributes]::ReparsePoint) {
            throw 'The installation directory is a reparse point.'
        }
    }
    New-Item -ItemType Directory -Path $destination -Force | Out-Null
    $exe = Join-Path $destination 'SynaReporter.exe'
    $old = Join-Path $Session 'Previous-SynaReporter.exe'
    if (Test-Path -LiteralPath $exe) {
        if ((Get-Item -LiteralPath $exe).Attributes -band [IO.FileAttributes]::ReparsePoint) {
            throw 'The installed executable is a reparse point.'
        }
        Copy-Item -LiteralPath $exe -Destination $old -Force
    }
    # Stop only processes running from the managed installation path.
    $owned = @(Get-CimInstance Win32_Process -Filter "Name='SynaReporter.exe'" |
        Where-Object { $_.ExecutablePath -eq $exe })
    foreach ($process in $owned) { Stop-Process -Id $process.ProcessId -Force -ErrorAction SilentlyContinue }
    $deadline = [DateTime]::UtcNow.AddSeconds(10)
    do {
        $remaining = @(Get-CimInstance Win32_Process -Filter "Name='SynaReporter.exe'" |
            Where-Object { $_.ExecutablePath -eq $exe })
        if (-not $remaining.Count) { break }
        Start-Sleep -Milliseconds 200
    } while ([DateTime]::UtcNow -lt $deadline)
    if ($remaining.Count) { throw 'Could not stop the installed Reporter.' }
    $staged = Join-Path $destination ('SynaReporter-' + [guid]::NewGuid().ToString('N') + '.new')
    Copy-Item -LiteralPath $source -Destination $staged
    if ((Get-FileHash -LiteralPath $staged -Algorithm SHA256).Hash -ne $ExpectedHash) { throw 'Copied file verification failed.' }
    # Windows PowerShell converts $null to an empty string for this overload.
    # Use a real same-volume backup path instead of an invalid empty path.
    $replacementBackup = $staged + '.previous'
    if (Test-Path -LiteralPath $exe) { [IO.File]::Replace($staged, $exe, $replacementBackup) }
    else { [IO.File]::Move($staged, $exe) }
    Copy-Item -LiteralPath (Join-Path $Payload 'uninstall.cmd') -Destination $destination -Force
    $run = 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Run'
    New-Item -Path $run -Force | Out-Null
    if ($Login -eq 'on') {
        New-ItemProperty -Path $run -Name SynaReporter -Value ('"' + $exe + '"') -PropertyType String -Force | Out-Null
        # A deliberate checked option should also clear a prior Task Manager disable flag.
        $approval = 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Explorer\StartupApproved\Run'
        if (Test-Path $approval) { Remove-ItemProperty -Path $approval -Name SynaReporter -ErrorAction SilentlyContinue }
    } else { Remove-ItemProperty -Path $run -Name SynaReporter -ErrorAction SilentlyContinue }
    Remove-ItemProperty -Path 'HKLM:\Software\Microsoft\Windows\CurrentVersion\Run' -Name SynaReporter -ErrorAction SilentlyContinue
    $uninstall = 'HKLM:\Software\Microsoft\Windows\CurrentVersion\Uninstall\SynaReporter'
    New-Item -Path $uninstall -Force | Out-Null
    $values = @{DisplayName='Syna Reporter'; DisplayVersion='1.0.0'; Publisher='Syna';
        UninstallString=('"' + (Join-Path $destination 'uninstall.cmd') + '"')}
    foreach ($name in $values.Keys) {
        New-ItemProperty -Path $uninstall -Name $name -Value $values[$name] -PropertyType String -Force | Out-Null
    }
    Get-NetFirewallRule -DisplayName 'Syna Reporter Discovery' -ErrorAction SilentlyContinue | Remove-NetFirewallRule
    New-NetFirewallRule -DisplayName 'Syna Reporter Discovery' -Direction Inbound -Action Allow -Program $exe -Protocol UDP -LocalPort 8766 -Profile Private | Out-Null
    @{success=$true; app=$exe; sha256=$ExpectedHash} | ConvertTo-Json | Set-Content -LiteralPath $resultPath -Encoding UTF8
    exit 0
} catch {
    @{success=$false; error=$_.Exception.Message} | ConvertTo-Json | Set-Content -LiteralPath $resultPath -Encoding UTF8
    exit 1
}
