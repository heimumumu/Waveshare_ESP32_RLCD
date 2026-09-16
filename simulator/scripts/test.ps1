$ErrorActionPreference = 'Stop'

& (Join-Path $PSScriptRoot 'build.ps1')

$simulatorExe = 'C:\ai-panel-build\simulator\bin\ai_panel_simulator.exe'
$dashboardScreenshotPath = 'C:\ai-panel-build\simulator\dashboard.bmp'
$computersScreenshotPath = 'C:\ai-panel-build\simulator\computers.bmp'
$performanceScreenshotPath = 'C:\ai-panel-build\simulator\performance.bmp'
$synaScreenshotPath = 'C:\ai-panel-build\simulator\syna.bmp'
$previousVideoDriver = $env:SDL_VIDEODRIVER
$previousAutoClose = $env:AI_PANEL_AUTOCLOSE_MS
$previousScreenshotPath = $env:AI_PANEL_SCREENSHOT_PATH
$previousStartPage = $env:AI_PANEL_START_PAGE
$previousMediaDemo = $env:AI_PANEL_MEDIA_DEMO

try {
    $env:SDL_VIDEODRIVER = 'dummy'
    $env:AI_PANEL_AUTOCLOSE_MS = '1000'

    foreach ($screenshotPath in @($dashboardScreenshotPath, $computersScreenshotPath, $performanceScreenshotPath, $synaScreenshotPath)) {
        if (Test-Path -LiteralPath $screenshotPath) {
            Remove-Item -LiteralPath $screenshotPath -Force
        }
    }

    $env:AI_PANEL_START_PAGE = 'dashboard'
    $env:AI_PANEL_MEDIA_DEMO = '1'
    $env:AI_PANEL_SCREENSHOT_PATH = $dashboardScreenshotPath
    & $simulatorExe
    if ($LASTEXITCODE -ne 0) {
        throw "Dashboard simulator test failed with exit code $LASTEXITCODE"
    }

    $env:AI_PANEL_START_PAGE = 'performance'
    $env:AI_PANEL_MEDIA_DEMO = '0'
    $env:AI_PANEL_SCREENSHOT_PATH = $performanceScreenshotPath
    & $simulatorExe
    if ($LASTEXITCODE -ne 0) {
        throw "Performance simulator test failed with exit code $LASTEXITCODE"
    }

    $env:AI_PANEL_START_PAGE = 'computers'
    $env:AI_PANEL_SCREENSHOT_PATH = $computersScreenshotPath
    & $simulatorExe
    if ($LASTEXITCODE -ne 0) {
        throw "Computer-list simulator test failed with exit code $LASTEXITCODE"
    }

    $env:AI_PANEL_START_PAGE = 'syna'
    $env:AI_PANEL_SCREENSHOT_PATH = $synaScreenshotPath
    & $simulatorExe
    if ($LASTEXITCODE -ne 0) {
        throw "Syna simulator test failed with exit code $LASTEXITCODE"
    }

    foreach ($screenshotPath in @($dashboardScreenshotPath, $computersScreenshotPath, $performanceScreenshotPath, $synaScreenshotPath)) {
        if (-not (Test-Path -LiteralPath $screenshotPath)) {
            throw "Simulator did not create the expected screenshot: $screenshotPath"
        }
    }
}
finally {
    $env:SDL_VIDEODRIVER = $previousVideoDriver
    $env:AI_PANEL_AUTOCLOSE_MS = $previousAutoClose
    $env:AI_PANEL_SCREENSHOT_PATH = $previousScreenshotPath
    $env:AI_PANEL_START_PAGE = $previousStartPage
    $env:AI_PANEL_MEDIA_DEMO = $previousMediaDemo
}
