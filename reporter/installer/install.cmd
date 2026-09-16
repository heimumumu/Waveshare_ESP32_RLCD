@echo off
chcp 65001 >nul
setlocal EnableExtensions EnableDelayedExpansion
powershell.exe -NoProfile -Command "if (([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) { exit 0 } else { exit 1 }"
if not errorlevel 1 goto administrator_ready
if /i "%~1"=="/elevated" goto permission_failed
set "SYNA_INSTALL_SCRIPT=%~f0"
powershell.exe -NoProfile -Command "try { $p = Start-Process -FilePath $env:SYNA_INSTALL_SCRIPT -ArgumentList '/elevated' -Verb RunAs -WindowStyle Hidden -PassThru -ErrorAction Stop; $p.WaitForExit(); exit $p.ExitCode } catch { Write-Error $_; exit 1 }"
exit /b %errorlevel%

:permission_failed
echo Administrator permission was not obtained. Installation stopped.
exit /b 1

:administrator_ready

set "INSTALL_DIR=%ProgramFiles%\Syna Reporter"
taskkill /f /im SynaReporter.exe >nul 2>&1
set /a WAIT_COUNT=0
:wait_for_reporter_exit
tasklist /fi "IMAGENAME eq SynaReporter.exe" /nh 2>nul | find /i "SynaReporter.exe" >nul
if errorlevel 1 goto reporter_stopped
if !WAIT_COUNT! geq 15 (
  echo Could not stop the existing Syna Reporter process.
  exit /b 1
)
set /a WAIT_COUNT+=1
timeout /t 1 /nobreak >nul
goto wait_for_reporter_exit

:reporter_stopped
if not exist "%INSTALL_DIR%" (
  mkdir "%INSTALL_DIR%"
  if errorlevel 1 (
    echo Could not create the Syna Reporter installation directory.
    exit /b 1
  )
)
copy /y "%~dp0SynaReporter.exe" "%INSTALL_DIR%\SynaReporter.exe" >nul
if errorlevel 1 (
  echo Could not update SynaReporter.exe.
  exit /b 1
)
copy /y "%~dp0uninstall.cmd" "%INSTALL_DIR%\uninstall.cmd" >nul
if errorlevel 1 (
  echo Could not update uninstall.cmd.
  exit /b 1
)

rem Remove legacy machine-wide startup; the UI manages per-user startup.
reg delete "HKLM\Software\Microsoft\Windows\CurrentVersion\Run" /v SynaReporter /f >nul 2>&1
rem BEGIN PRESERVE USER STARTUP
rem Update an existing startup command without enabling a missing entry.
rem Fresh installations leave startup opt-in through the Reporter window.
reg query "HKCU\Software\Microsoft\Windows\CurrentVersion\Run" /v SynaReporter >nul 2>&1
if not errorlevel 1 (
  reg add "HKCU\Software\Microsoft\Windows\CurrentVersion\Run" /v SynaReporter /t REG_SZ /d "\"%INSTALL_DIR%\SynaReporter.exe\"" /f >nul
  if errorlevel 1 exit /b 1
)
rem END PRESERVE USER STARTUP
reg add "HKLM\Software\Microsoft\Windows\CurrentVersion\Uninstall\SynaReporter" /v DisplayName /t REG_SZ /d "Syna Reporter" /f >nul
if errorlevel 1 exit /b 1
reg add "HKLM\Software\Microsoft\Windows\CurrentVersion\Uninstall\SynaReporter" /v DisplayVersion /t REG_SZ /d "1.0.0" /f >nul
if errorlevel 1 exit /b 1
reg add "HKLM\Software\Microsoft\Windows\CurrentVersion\Uninstall\SynaReporter" /v Publisher /t REG_SZ /d "黑沐" /f >nul
if errorlevel 1 exit /b 1
reg add "HKLM\Software\Microsoft\Windows\CurrentVersion\Uninstall\SynaReporter" /v UninstallString /t REG_SZ /d "\"%INSTALL_DIR%\uninstall.cmd\"" /f >nul
if errorlevel 1 exit /b 1

netsh advfirewall firewall delete rule name="Syna Reporter Discovery" >nul 2>&1
netsh advfirewall firewall add rule name="Syna Reporter Discovery" dir=in action=allow program="%INSTALL_DIR%\SynaReporter.exe" protocol=UDP localport=8766 profile=private enable=yes >nul
if errorlevel 1 (
  echo Could not configure the Syna Reporter firewall rule.
  exit /b 1
)

start "" "%INSTALL_DIR%\SynaReporter.exe"
echo Syna Reporter installation completed.
exit /b 0
