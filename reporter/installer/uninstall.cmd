@echo off
setlocal
net session >nul 2>&1
if errorlevel 1 (
  powershell.exe -NoProfile -Command "Start-Process -FilePath '%~f0' -ArgumentList '/elevated' -Verb RunAs -Wait"
  exit /b %errorlevel%
)
taskkill /f /im SynaReporter.exe >nul 2>&1
reg delete "HKCU\Software\Microsoft\Windows\CurrentVersion\Run" /v SynaReporter /f >nul 2>&1
reg delete "HKLM\Software\Microsoft\Windows\CurrentVersion\Run" /v SynaReporter /f >nul 2>&1
reg delete "HKLM\Software\Microsoft\Windows\CurrentVersion\Uninstall\SynaReporter" /f >nul 2>&1
netsh advfirewall firewall delete rule name="Syna Reporter Discovery" >nul 2>&1
start "" /min cmd.exe /d /c "timeout /t 2 /nobreak >nul & rmdir /s /q \"%ProgramFiles%\Syna Reporter\""
exit /b 0
