$ErrorActionPreference = 'Stop'

Add-Type -AssemblyName System.Drawing

$generatedDir = Join-Path $PSScriptRoot 'generated'
$cAssetDir = Join-Path $PSScriptRoot '..\src\assets'
$iconDir = Join-Path $PSScriptRoot 'source\music_ui_icons'
$synaIconDir = Join-Path $PSScriptRoot 'source\syna_icons'
$lvglConverter = Join-Path $PSScriptRoot '..\vendor\lvgl-9.5.0\scripts\LVGLImage.py'
$python = (Get-Command python -ErrorAction Stop).Source
$toolchainBin = Join-Path ([Environment]::GetFolderPath('UserProfile')) 'Tools\msys64\ucrt64\bin'
$env:Path = "$toolchainBin;$env:Path"

New-Item -ItemType Directory -Path $generatedDir -Force | Out-Null
New-Item -ItemType Directory -Path $cAssetDir -Force | Out-Null

$icons = [ordered]@{
    Clock       = @{ Path = Join-Path $iconDir 'clock.png';       Source = [System.Drawing.Rectangle]::new(328, 296, 601, 641) }
    Thermometer = @{ Path = Join-Path $iconDir 'thermometer.png'; Source = [System.Drawing.Rectangle]::new(280, 292, 381, 1085) }
    Humidity    = @{ Path = Join-Path $iconDir 'humidity.png';    Source = [System.Drawing.Rectangle]::new(120, 220, 749, 1145) }
    AgentStatus = @{ Path = Join-Path $iconDir 'agent_status-v2.png'; Source = [System.Drawing.Rectangle]::new(280, 274, 675, 683) }
    Waveform    = @{ Path = Join-Path $iconDir 'waveform.png';    Source = [System.Drawing.Rectangle]::new(300, 140, 933, 709) }
    MusicNote   = @{ Path = Join-Path $iconDir 'music_note.png';  Source = [System.Drawing.Rectangle]::new(120, 188, 893, 1013) }
    Artist      = @{ Path = Join-Path $iconDir 'artist.png';      Source = [System.Drawing.Rectangle]::new(376, 308, 501, 641) }
    Wifi        = @{ Path = Join-Path $iconDir 'wifi.png';        Source = [System.Drawing.Rectangle]::new(248, 132, 1001, 785) }
    Desktop     = @{ Path = Join-Path $iconDir 'desktop.png';     Source = [System.Drawing.Rectangle]::new(176, 68, 1109, 905) }
    Laptop      = @{ Path = Join-Path $iconDir 'laptop.png';      Source = [System.Drawing.Rectangle]::new(128, 88, 1165, 921) }
    Battery     = @{ Path = Join-Path $iconDir 'battery-v2.png';  Source = [System.Drawing.Rectangle]::new(420, 160, 1165, 440) }
}

$performanceIconSheet = Join-Path $PSScriptRoot 'source\performance_icon_sheet.png'
$performanceIcons = [ordered]@{
    CpuTemperature = @{ Path = $performanceIconSheet; Source = [System.Drawing.Rectangle]::new(205, 75, 210, 235) }
    GpuTemperature = @{ Path = $performanceIconSheet; Source = [System.Drawing.Rectangle]::new(580, 95, 275, 220) }
    Performance    = @{ Path = $performanceIconSheet; Source = [System.Drawing.Rectangle]::new(1045, 120, 225, 145) }
    Realtime       = @{ Path = $performanceIconSheet; Source = [System.Drawing.Rectangle]::new(185, 430, 235, 165) }
    Host           = @{ Path = $performanceIconSheet; Source = [System.Drawing.Rectangle]::new(600, 395, 260, 285) }
    Healthy        = @{ Path = $performanceIconSheet; Source = [System.Drawing.Rectangle]::new(1060, 410, 185, 215) }
    Network        = @{ Path = $performanceIconSheet; Source = [System.Drawing.Rectangle]::new(205, 745, 195, 195) }
    Upload         = @{ Path = $performanceIconSheet; Source = [System.Drawing.Rectangle]::new(655, 750, 140, 185) }
    Download       = @{ Path = $performanceIconSheet; Source = [System.Drawing.Rectangle]::new(1090, 750, 135, 190) }
}

$synaIcons = [ordered]@{
    Wallet        = Join-Path $synaIconDir 'api_wallet.png'
    Speech        = Join-Path $synaIconDir 'speech_bubble.png'
    TodoChecked   = Join-Path $synaIconDir 'todo_checked.png'
    TodoUnchecked = Join-Path $synaIconDir 'todo_unchecked.png'
}

foreach($icon in $icons.GetEnumerator()) {
    if(-not (Test-Path -LiteralPath $icon.Value.Path)) {
        throw "Generated $($icon.Key) icon is missing: $($icon.Value.Path)"
    }
}
if(-not (Test-Path -LiteralPath $performanceIconSheet)) {
    throw "Generated performance icon sheet is missing: $performanceIconSheet"
}
foreach($icon in $synaIcons.GetEnumerator()) {
    if(-not (Test-Path -LiteralPath $icon.Value)) {
        throw "Generated Syna $($icon.Key) icon is missing: $($icon.Value)"
    }
}

function New-PixelFont {
    param([string]$Family, [single]$Size,
          [System.Drawing.FontStyle]$Style = [System.Drawing.FontStyle]::Regular)
    return [System.Drawing.Font]::new($Family, $Size, $Style, [System.Drawing.GraphicsUnit]::Pixel)
}

function Draw-Text {
    param([System.Drawing.Graphics]$Graphics, [string]$Text, [System.Drawing.Font]$Font,
          [single]$X, [single]$Y,
          [System.Drawing.Color]$Color = [System.Drawing.Color]::Black)
    $format = [System.Drawing.StringFormat]::GenericTypographic.Clone()
    $brush = [System.Drawing.SolidBrush]::new($Color)
    try {
        $format.FormatFlags = $format.FormatFlags -bor [System.Drawing.StringFormatFlags]::MeasureTrailingSpaces
        $Graphics.DrawString($Text, $Font, $brush, $X, $Y, $format)
    }
    finally { $brush.Dispose(); $format.Dispose() }
}

function Draw-CenteredText {
    param([System.Drawing.Graphics]$Graphics, [string]$Text, [System.Drawing.Font]$Font,
          [System.Drawing.RectangleF]$Bounds,
          [System.Drawing.Color]$Color = [System.Drawing.Color]::Black)
    $format = [System.Drawing.StringFormat]::GenericTypographic.Clone()
    $brush = [System.Drawing.SolidBrush]::new($Color)
    try {
        $format.Alignment = [System.Drawing.StringAlignment]::Center
        $format.LineAlignment = [System.Drawing.StringAlignment]::Near
        $format.FormatFlags = $format.FormatFlags -bor [System.Drawing.StringFormatFlags]::NoWrap
        $Graphics.DrawString($Text, $Font, $brush, $Bounds, $format)
    }
    finally { $brush.Dispose(); $format.Dispose() }
}

function New-RoundedPath {
    param([single]$X, [single]$Y, [single]$Width, [single]$Height, [single]$Radius)
    $diameter = $Radius * 2
    $path = [System.Drawing.Drawing2D.GraphicsPath]::new()
    $path.AddArc($X, $Y, $diameter, $diameter, 180, 90)
    $path.AddArc($X + $Width - $diameter, $Y, $diameter, $diameter, 270, 90)
    $path.AddArc($X + $Width - $diameter, $Y + $Height - $diameter, $diameter, $diameter, 0, 90)
    $path.AddArc($X, $Y + $Height - $diameter, $diameter, $diameter, 90, 90)
    $path.CloseFigure()
    return $path
}

function Draw-RoundedOutline {
    param([System.Drawing.Graphics]$Graphics, [System.Drawing.Pen]$Pen,
          [single]$X, [single]$Y, [single]$Width, [single]$Height, [single]$Radius)
    $path = New-RoundedPath $X $Y $Width $Height $Radius
    try { $Graphics.DrawPath($Pen, $path) } finally { $path.Dispose() }
}

function Fill-RoundedRectangle {
    param([System.Drawing.Graphics]$Graphics, [System.Drawing.Brush]$Brush,
          [single]$X, [single]$Y, [single]$Width, [single]$Height, [single]$Radius)
    $path = New-RoundedPath $X $Y $Width $Height $Radius
    try { $Graphics.FillPath($Brush, $path) } finally { $path.Dispose() }
}

function Draw-GeneratedAsset {
    param([System.Drawing.Graphics]$Graphics, [hashtable]$Asset,
          [System.Drawing.Rectangle]$Destination, [switch]$White)
    $bitmap = [System.Drawing.Bitmap]::FromFile($Asset.Path)
    $previousInterpolation = $Graphics.InterpolationMode
    $attributes = $null
    try {
        $Graphics.InterpolationMode = [System.Drawing.Drawing2D.InterpolationMode]::HighQualityBicubic
        if($White) {
            $matrix = [System.Drawing.Imaging.ColorMatrix]::new(@(
                [single[]]@(0, 0, 0, 0, 0), [single[]]@(0, 0, 0, 0, 0),
                [single[]]@(0, 0, 0, 0, 0), [single[]]@(0, 0, 0, 1, 0),
                [single[]]@(1, 1, 1, 0, 1)))
            $attributes = [System.Drawing.Imaging.ImageAttributes]::new()
            $attributes.SetColorKey(
                [System.Drawing.Color]::FromArgb(200, 200, 200),
                [System.Drawing.Color]::White)
            $attributes.SetColorMatrix($matrix)
            $Graphics.DrawImage($bitmap, $Destination, $Asset.Source.X, $Asset.Source.Y,
                $Asset.Source.Width, $Asset.Source.Height, [System.Drawing.GraphicsUnit]::Pixel,
                $attributes)
        }
        else {
            $Graphics.DrawImage($bitmap, $Destination, $Asset.Source.X, $Asset.Source.Y,
                $Asset.Source.Width, $Asset.Source.Height, [System.Drawing.GraphicsUnit]::Pixel)
        }
    }
    finally {
        if($null -ne $attributes) { $attributes.Dispose() }
        $Graphics.InterpolationMode = $previousInterpolation
        $bitmap.Dispose()
    }
}

function Convert-ToOneBitPreview {
    param([System.Drawing.Bitmap]$Bitmap)
    for($y = 0; $y -lt $Bitmap.Height; $y++) {
        for($x = 0; $x -lt $Bitmap.Width; $x++) {
            $pixel = $Bitmap.GetPixel($x, $y)
            $luma = (0.2126 * $pixel.R) + (0.7152 * $pixel.G) + (0.0722 * $pixel.B)
            $Bitmap.SetPixel($x, $y, $(if($luma -lt 170) { [System.Drawing.Color]::Black } else { [System.Drawing.Color]::White }))
        }
    }
}

function Export-GeneratedIcon {
    param([string]$SourcePath, [string]$DestinationPath,
          [int]$Width, [int]$Height)
    $source = [System.Drawing.Bitmap]::FromFile($SourcePath)
    try {
        $minX = $source.Width; $minY = $source.Height; $maxX = -1; $maxY = -1
        for($y = 0; $y -lt $source.Height; $y += 2) {
            for($x = 0; $x -lt $source.Width; $x += 2) {
                $pixel = $source.GetPixel($x, $y)
                $luma = (0.2126 * $pixel.R) + (0.7152 * $pixel.G) + (0.0722 * $pixel.B)
                if($pixel.A -gt 32 -and $luma -lt 150) {
                    if($x -lt $minX) { $minX = $x }; if($x -gt $maxX) { $maxX = $x }
                    if($y -lt $minY) { $minY = $y }; if($y -gt $maxY) { $maxY = $y }
                }
            }
        }
        if($maxX -lt $minX -or $maxY -lt $minY) { throw "No dark icon pixels found in $SourcePath" }
        $padding = [Math]::Max(4, [int]([Math]::Max($maxX - $minX, $maxY - $minY) * 0.035))
        $cropX = [Math]::Max(0, $minX - $padding)
        $cropY = [Math]::Max(0, $minY - $padding)
        $cropRight = [Math]::Min($source.Width - 1, $maxX + $padding)
        $cropBottom = [Math]::Min($source.Height - 1, $maxY + $padding)
        $destination = [System.Drawing.Bitmap]::new($Width, $Height, [System.Drawing.Imaging.PixelFormat]::Format32bppArgb)
        $graphics = [System.Drawing.Graphics]::FromImage($destination)
        try {
            $graphics.Clear([System.Drawing.Color]::White)
            $graphics.InterpolationMode = [System.Drawing.Drawing2D.InterpolationMode]::HighQualityBicubic
            $graphics.DrawImage($source, [System.Drawing.Rectangle]::new(0, 0, $Width, $Height),
                $cropX, $cropY, $cropRight - $cropX + 1, $cropBottom - $cropY + 1,
                [System.Drawing.GraphicsUnit]::Pixel)
            Convert-ToOneBitPreview $destination
            $destination.Save($DestinationPath, [System.Drawing.Imaging.ImageFormat]::Png)
        }
        finally { $graphics.Dispose(); $destination.Dispose() }
    }
    finally { $source.Dispose() }
}

$screen = [System.Drawing.Bitmap]::new(400, 300, [System.Drawing.Imaging.PixelFormat]::Format32bppArgb)
$graphics = [System.Drawing.Graphics]::FromImage($screen)
$graphics.Clear([System.Drawing.Color]::White)
$graphics.SmoothingMode = [System.Drawing.Drawing2D.SmoothingMode]::None
$graphics.PixelOffsetMode = [System.Drawing.Drawing2D.PixelOffsetMode]::Half
$graphics.TextRenderingHint = [System.Drawing.Text.TextRenderingHint]::SingleBitPerPixelGridFit
$pen1 = [System.Drawing.Pen]::new([System.Drawing.Color]::Black, 1)
$cjk12 = New-PixelFont 'Microsoft YaHei UI' 12
$cjk13 = New-PixelFont 'Microsoft YaHei UI' 13
$cjk14 = New-PixelFont 'Microsoft YaHei UI' 14
$cjk16 = New-PixelFont 'Microsoft YaHei UI' 16
$cjk17 = New-PixelFont 'Microsoft YaHei UI' 17
$latin11 = New-PixelFont 'Consolas' 11
$latin18 = New-PixelFont 'Arial' 18
$textTemperature = -join [char[]](0x6E29, 0x5EA6)
$textHumidity = -join [char[]](0x6E7F, 0x5EA6)
$textRunning = -join [char[]](0x8FD0, 0x884C, 0x4E2D)
$textNowPlaying = -join [char[]](0x6B63, 0x5728, 0x64AD, 0x653E)
$textFiveHourQuota = '5' + (-join [char[]](0x5C0F, 0x65F6, 0x989D, 0x5EA6))
$textWeekQuota = -join [char[]](0x5468, 0x989D, 0x5EA6)
$textSong = -join [char[]](0x591C, 0x7684, 0x7B2C, 0x4E03, 0x7AE0)
$textArtist = -join [char[]](0x5468, 0x6770, 0x4F26)
$textLyric = -join [char[]](0x591C, 0x5E55, 0x964D, 0x4E34, 0x0020, 0x534E, 0x706F, 0x521D, 0x4E0A)
$textWifi = 'WiFi' + (-join [char[]](0x5DF2, 0x8FDE, 0x63A5))
$textDevice = -join [char[]](0x8BBE, 0x5907, 0x6B63, 0x5E38)
$textConnectedPc = (-join [char[]](0x5DF2, 0x8FDE, 0x63A5, 0x5230)) + 'PC'

try {
    Draw-RoundedOutline $graphics $pen1 6 7 388 55 11
    Draw-RoundedOutline $graphics $pen1 6 69 169 182 8
    Draw-RoundedOutline $graphics $pen1 178 69 216 182 8
    Draw-RoundedOutline $graphics $pen1 6 259 388 35 10
    $graphics.DrawLine($pen1, 189, 13, 189, 56)
    $graphics.DrawLine($pen1, 288, 13, 288, 56)

    Draw-GeneratedAsset $graphics $icons.Clock ([System.Drawing.Rectangle]::new(20, 23, 22, 22))
    Draw-GeneratedAsset $graphics $icons.Thermometer ([System.Drawing.Rectangle]::new(205, 15, 18, 32))
    Draw-GeneratedAsset $graphics $icons.Humidity ([System.Drawing.Rectangle]::new(306, 16, 18, 29))
    Draw-Text $graphics $textTemperature $cjk14 230 15
    Draw-Text $graphics $textHumidity $cjk14 331 15
    Draw-Text $graphics 'AI AGENT' $latin18 49 82

    Fill-RoundedRectangle $graphics ([System.Drawing.Brushes]::Black) 46 108 88 29 5
    Draw-GeneratedAsset $graphics $icons.AgentStatus ([System.Drawing.Rectangle]::new(52, 111, 23, 23)) -White
    Draw-Text $graphics $textRunning $cjk16 81 112 ([System.Drawing.Color]::White)
    $graphics.DrawLine($pen1, 17, 146, 162, 146)
    Draw-Text $graphics $textFiveHourQuota $cjk13 17 159
    Draw-Text $graphics $textWeekQuota $cjk13 17 202
    Draw-RoundedOutline $graphics $pen1 17 177 146 15 4
    Draw-RoundedOutline $graphics $pen1 17 220 146 15 4

    Draw-GeneratedAsset $graphics $icons.Waveform ([System.Drawing.Rectangle]::new(193, 82, 24, 16))
    Draw-Text $graphics $textNowPlaying $cjk14 223 82
    $graphics.DrawLine($pen1, 193, 103, 380, 103)
    Draw-RoundedOutline $graphics $pen1 193 114 52 55 4
    Draw-GeneratedAsset $graphics $icons.MusicNote ([System.Drawing.Rectangle]::new(205, 124, 28, 35))
    Draw-Text $graphics $textSong $cjk16 258 115
    Draw-GeneratedAsset $graphics $icons.Artist ([System.Drawing.Rectangle]::new(259, 143, 12, 12))
    Draw-Text $graphics $textArtist $cjk13 278 141

    $progressPen = [System.Drawing.Pen]::new([System.Drawing.Color]::Black, 1)
    try { $progressPen.DashStyle = [System.Drawing.Drawing2D.DashStyle]::Dot; $graphics.DrawLine($progressPen, 193, 181, 380, 181) }
    finally { $progressPen.Dispose() }
    $graphics.FillEllipse([System.Drawing.Brushes]::Black, 268, 178, 7, 7)
    Draw-Text $graphics '01:54' $latin11 193 188
    Draw-Text $graphics '04:31' $latin11 353 188
    Draw-CenteredText $graphics $textLyric $cjk17 ([System.Drawing.RectangleF]::new(184, 215, 204, 25))

    Draw-GeneratedAsset $graphics $icons.Wifi ([System.Drawing.Rectangle]::new(20, 270, 20, 14))
    Draw-Text $graphics $textWifi $cjk12 48 270
    Draw-GeneratedAsset $graphics $icons.Desktop ([System.Drawing.Rectangle]::new(126, 270, 19, 14))
    Draw-Text $graphics $textDevice $cjk12 150 270
    Draw-GeneratedAsset $graphics $icons.Laptop ([System.Drawing.Rectangle]::new(216, 270, 18, 14))
    Draw-Text $graphics $textConnectedPc $cjk12 238 270
    Draw-GeneratedAsset $graphics $icons.Battery ([System.Drawing.Rectangle]::new(314, 270, 35, 14))
    Draw-Text $graphics '87%' $cjk13 358 270

    Convert-ToOneBitPreview $screen
    $screen.Save((Join-Path $generatedDir 'screen_base.png'), [System.Drawing.Imaging.ImageFormat]::Png)
}
finally {
    $latin18.Dispose(); $latin11.Dispose(); $cjk17.Dispose(); $cjk16.Dispose()
    $cjk14.Dispose(); $cjk13.Dispose(); $cjk12.Dispose(); $pen1.Dispose()
    $graphics.Dispose(); $screen.Dispose()
}

$performanceScreen = [System.Drawing.Bitmap]::new(400, 300, [System.Drawing.Imaging.PixelFormat]::Format32bppArgb)
$performanceGraphics = [System.Drawing.Graphics]::FromImage($performanceScreen)
$performanceGraphics.Clear([System.Drawing.Color]::White)
$performanceGraphics.SmoothingMode = [System.Drawing.Drawing2D.SmoothingMode]::None
$performanceGraphics.PixelOffsetMode = [System.Drawing.Drawing2D.PixelOffsetMode]::Half
$performanceGraphics.TextRenderingHint = [System.Drawing.Text.TextRenderingHint]::SingleBitPerPixelGridFit
$performancePen = [System.Drawing.Pen]::new([System.Drawing.Color]::Black, 1)
$performanceCjk12 = New-PixelFont 'Microsoft YaHei UI' 12
$performanceCjk13 = New-PixelFont 'Microsoft YaHei UI' 13
$performanceCjk14 = New-PixelFont 'Microsoft YaHei UI' 14
$performanceLatin11 = New-PixelFont 'Consolas' 11
$performanceLatin12 = New-PixelFont 'Consolas' 12

$textSystemPerformance = -join [char[]](0x7CFB, 0x7EDF, 0x6027, 0x80FD)
$textRealtimeStatus = -join [char[]](0x5B9E, 0x65F6, 0x72B6, 0x6001)
$textCpuTemperature = 'CPU' + (-join [char[]](0x6E29, 0x5EA6))
$textGpuTemperature = 'GPU' + (-join [char[]](0x6E29, 0x5EA6))
$textHostHealthy = -join [char[]](0x4E3B, 0x673A, 0x8FD0, 0x884C, 0x6B63, 0x5E38)
$textNetworkLatency = -join [char[]](0x7F51, 0x7EDC, 0x5EF6, 0x8FDF)
$textUpload = -join [char[]](0x4E0A, 0x4F20)
$textDownload = -join [char[]](0x4E0B, 0x8F7D)

try {
    Draw-RoundedOutline $performanceGraphics $performancePen 6 7 388 50 11
    Draw-RoundedOutline $performanceGraphics $performancePen 6 64 175 190 9
    Draw-RoundedOutline $performanceGraphics $performancePen 188 64 206 190 9
    Draw-RoundedOutline $performanceGraphics $performancePen 6 259 388 35 10
    $performanceGraphics.DrawLine($performancePen, 156, 13, 156, 51)
    $performanceGraphics.DrawLine($performancePen, 262, 13, 262, 51)

    Draw-GeneratedAsset $performanceGraphics $icons.Clock ([System.Drawing.Rectangle]::new(20, 22, 22, 22))
    Draw-GeneratedAsset $performanceGraphics $performanceIcons.CpuTemperature ([System.Drawing.Rectangle]::new(166, 16, 29, 32))
    Draw-GeneratedAsset $performanceGraphics $performanceIcons.GpuTemperature ([System.Drawing.Rectangle]::new(272, 17, 38, 30))
    Draw-Text $performanceGraphics $textCpuTemperature $performanceCjk12 201 16
    Draw-Text $performanceGraphics $textGpuTemperature $performanceCjk12 319 16

    Draw-GeneratedAsset $performanceGraphics $performanceIcons.Performance ([System.Drawing.Rectangle]::new(17, 75, 20, 15))
    Draw-Text $performanceGraphics $textSystemPerformance $performanceCjk14 42 72
    $performanceGraphics.DrawLine($performancePen, 16, 92, 170, 92)

    Draw-Text $performanceGraphics 'CPU' $performanceLatin12 17 103
    Draw-Text $performanceGraphics 'Memory' $performanceLatin12 17 143
    Draw-Text $performanceGraphics 'GPU' $performanceLatin12 17 182
    Draw-Text $performanceGraphics 'Disk' $performanceLatin12 17 222
    foreach($barY in @(117, 156, 196, 235)) {
        Draw-RoundedOutline $performanceGraphics $performancePen 16 $barY 154 13 4
    }

    Draw-GeneratedAsset $performanceGraphics $performanceIcons.Realtime ([System.Drawing.Rectangle]::new(199, 74, 25, 17))
    Draw-Text $performanceGraphics $textRealtimeStatus $performanceCjk14 230 72
    $performanceGraphics.DrawLine($performancePen, 199, 92, 383, 92)
    Draw-GeneratedAsset $performanceGraphics $performanceIcons.Host ([System.Drawing.Rectangle]::new(200, 106, 58, 62))
    Draw-GeneratedAsset $performanceGraphics $performanceIcons.Healthy ([System.Drawing.Rectangle]::new(268, 102, 16, 18))
    Draw-GeneratedAsset $performanceGraphics $performanceIcons.Network ([System.Drawing.Rectangle]::new(268, 123, 16, 17))
    Draw-GeneratedAsset $performanceGraphics $performanceIcons.Upload ([System.Drawing.Rectangle]::new(269, 145, 14, 17))
    Draw-GeneratedAsset $performanceGraphics $performanceIcons.Download ([System.Drawing.Rectangle]::new(269, 167, 14, 17))
    Draw-Text $performanceGraphics $textHostHealthy $performanceCjk12 291 103
    Draw-Text $performanceGraphics $textNetworkLatency $performanceCjk12 291 124
    Draw-Text $performanceGraphics $textUpload $performanceCjk12 291 146
    Draw-Text $performanceGraphics $textDownload $performanceCjk12 291 168

    $graphPen = [System.Drawing.Pen]::new([System.Drawing.Color]::Black, 1)
    try {
        $graphPen.DashStyle = [System.Drawing.Drawing2D.DashStyle]::Dash
        Draw-RoundedOutline $performanceGraphics $graphPen 196 187 190 59 4
    }
    finally { $graphPen.Dispose() }

    $performanceGraphics.DrawLine($performancePen, 200, 239, 382, 239)

    Draw-GeneratedAsset $performanceGraphics $icons.Wifi ([System.Drawing.Rectangle]::new(20, 270, 20, 14))
    Draw-Text $performanceGraphics $textWifi $performanceCjk12 48 270
    Draw-GeneratedAsset $performanceGraphics $icons.Desktop ([System.Drawing.Rectangle]::new(126, 270, 19, 14))
    Draw-Text $performanceGraphics $textDevice $performanceCjk12 150 270
    Draw-GeneratedAsset $performanceGraphics $icons.Laptop ([System.Drawing.Rectangle]::new(216, 270, 18, 14))
    Draw-Text $performanceGraphics $textConnectedPc $performanceCjk12 238 270
    Draw-GeneratedAsset $performanceGraphics $icons.Battery ([System.Drawing.Rectangle]::new(314, 270, 35, 14))
    Draw-Text $performanceGraphics '87%' $performanceCjk13 358 270

    Convert-ToOneBitPreview $performanceScreen
    $performanceScreen.Save((Join-Path $generatedDir 'performance_base.png'), [System.Drawing.Imaging.ImageFormat]::Png)
}
finally {
    $performanceLatin12.Dispose(); $performanceLatin11.Dispose()
    $performanceCjk14.Dispose(); $performanceCjk13.Dispose(); $performanceCjk12.Dispose()
    $performancePen.Dispose(); $performanceGraphics.Dispose(); $performanceScreen.Dispose()
}

Export-GeneratedIcon $synaIcons.Wallet (Join-Path $generatedDir 'syna_wallet.png') 26 26
Export-GeneratedIcon $synaIcons.Speech (Join-Path $generatedDir 'syna_speech.png') 20 18
Export-GeneratedIcon $synaIcons.TodoChecked (Join-Path $generatedDir 'syna_todo_checked.png') 15 15
Export-GeneratedIcon $synaIcons.TodoUnchecked (Join-Path $generatedDir 'syna_todo_unchecked.png') 15 15

$synaScreen = [System.Drawing.Bitmap]::new(400, 300, [System.Drawing.Imaging.PixelFormat]::Format32bppArgb)
$synaGraphics = [System.Drawing.Graphics]::FromImage($synaScreen)
$synaGraphics.Clear([System.Drawing.Color]::White)
$synaGraphics.SmoothingMode = [System.Drawing.Drawing2D.SmoothingMode]::None
$synaGraphics.PixelOffsetMode = [System.Drawing.Drawing2D.PixelOffsetMode]::Half
$synaGraphics.TextRenderingHint = [System.Drawing.Text.TextRenderingHint]::SingleBitPerPixelGridFit
$synaPen = [System.Drawing.Pen]::new([System.Drawing.Color]::Black, 1)
$synaCjk12 = New-PixelFont 'Microsoft YaHei UI' 12
$synaCjk14 = New-PixelFont 'Microsoft YaHei UI' 14
$synaLatin14 = New-PixelFont 'Arial' 14
$textApiBalance = 'API' + (-join [char[]](0x4F59, 0x989D))
$textTodayTodo = -join [char[]](0x4ECA, 0x65E5, 0x5F85, 0x529E)
try {
    Draw-RoundedOutline $synaGraphics $synaPen 6 7 388 55 11
    Draw-RoundedOutline $synaGraphics $synaPen 6 69 198 182 8
    Draw-RoundedOutline $synaGraphics $synaPen 210 69 184 182 8
    Draw-RoundedOutline $synaGraphics $synaPen 6 259 388 35 10
    $synaGraphics.DrawLine($synaPen, 190, 13, 190, 56)

    Draw-GeneratedAsset $synaGraphics $icons.Clock ([System.Drawing.Rectangle]::new(20, 23, 22, 22))
    Draw-Text $synaGraphics $textApiBalance $synaCjk14 243 13
    Draw-Text $synaGraphics 'Syna-sama' $synaLatin14 43 79
    $synaGraphics.DrawLine($synaPen, 17, 103, 193, 103)
    Draw-Text $synaGraphics $textTodayTodo $synaCjk14 244 79
    $synaGraphics.DrawLine($synaPen, 221, 103, 383, 103)

    Draw-GeneratedAsset $synaGraphics $icons.Wifi ([System.Drawing.Rectangle]::new(20, 270, 20, 14))
    Draw-Text $synaGraphics $textWifi $synaCjk12 48 270
    Draw-GeneratedAsset $synaGraphics $icons.Desktop ([System.Drawing.Rectangle]::new(126, 270, 19, 14))
    Draw-Text $synaGraphics $textDevice $synaCjk12 150 270
    Draw-GeneratedAsset $synaGraphics $icons.Laptop ([System.Drawing.Rectangle]::new(216, 270, 18, 14))
    Draw-Text $synaGraphics $textConnectedPc $synaCjk12 238 270
    Draw-GeneratedAsset $synaGraphics $icons.Battery ([System.Drawing.Rectangle]::new(314, 270, 35, 14))
    Draw-Text $synaGraphics '87%' $synaCjk12 358 270

    Convert-ToOneBitPreview $synaScreen
    $synaScreen.Save((Join-Path $generatedDir 'syna_base.png'), [System.Drawing.Imaging.ImageFormat]::Png)
}
finally {
    $synaLatin14.Dispose(); $synaCjk14.Dispose(); $synaCjk12.Dispose()
    $synaPen.Dispose(); $synaGraphics.Dispose(); $synaScreen.Dispose()
}

$statusDefinitions = [ordered]@{
    'status_working' = (-join [char[]](0x8FD0, 0x884C, 0x4E2D))
    'status_waiting' = (-join [char[]](0x7B49, 0x5F85, 0x4E2D))
    'status_done' = (-join [char[]](0x5DF2, 0x5B8C, 0x6210))
    'status_idle' = (-join [char[]](0x7A7A, 0x95F2))
    'status_offline' = (-join [char[]](0x79BB, 0x7EBF))
}
foreach($status in $statusDefinitions.GetEnumerator()) {
    $bitmap = [System.Drawing.Bitmap]::new(88, 29, [System.Drawing.Imaging.PixelFormat]::Format32bppArgb)
    $statusGraphics = [System.Drawing.Graphics]::FromImage($bitmap)
    $statusFont = New-PixelFont 'Microsoft YaHei UI' 16
    try {
        $statusGraphics.Clear([System.Drawing.Color]::White)
        $statusGraphics.SmoothingMode = [System.Drawing.Drawing2D.SmoothingMode]::None
        $statusGraphics.TextRenderingHint = [System.Drawing.Text.TextRenderingHint]::SingleBitPerPixelGridFit
        Fill-RoundedRectangle $statusGraphics ([System.Drawing.Brushes]::Black) 0 0 88 29 5
        Draw-GeneratedAsset $statusGraphics $icons.AgentStatus ([System.Drawing.Rectangle]::new(6, 3, 23, 23)) -White
        Draw-Text $statusGraphics $status.Value $statusFont 35 4 ([System.Drawing.Color]::White)
        Convert-ToOneBitPreview $bitmap
        $bitmap.Save((Join-Path $generatedDir "$($status.Key).png"), [System.Drawing.Imaging.ImageFormat]::Png)
    }
    finally { $statusFont.Dispose(); $statusGraphics.Dispose(); $bitmap.Dispose() }
}

$wifiStatusDefinitions = [ordered]@{
    'wifi_unconfigured' = 'WiFi' + (-join [char[]](0x672A, 0x914D, 0x7F6E))
    'wifi_connecting'   = 'WiFi' + (-join [char[]](0x8FDE, 0x63A5, 0x4E2D))
    'wifi_provisioning' = -join [char[]](0x7B49, 0x5F85, 0x914D, 0x7F51)
    'wifi_connected'    = 'WiFi' + (-join [char[]](0x5DF2, 0x8FDE, 0x63A5))
}
foreach($wifiStatus in $wifiStatusDefinitions.GetEnumerator()) {
    $bitmap = [System.Drawing.Bitmap]::new(78, 18, [System.Drawing.Imaging.PixelFormat]::Format32bppArgb)
    $statusGraphics = [System.Drawing.Graphics]::FromImage($bitmap)
    $statusFont = New-PixelFont 'Microsoft YaHei UI' 12
    try {
        $statusGraphics.Clear([System.Drawing.Color]::White)
        $statusGraphics.TextRenderingHint = [System.Drawing.Text.TextRenderingHint]::SingleBitPerPixelGridFit
        Draw-Text $statusGraphics $wifiStatus.Value $statusFont 2 0
        Convert-ToOneBitPreview $bitmap
        $bitmap.Save((Join-Path $generatedDir "$($wifiStatus.Key).png"), [System.Drawing.Imaging.ImageFormat]::Png)
    }
    finally { $statusFont.Dispose(); $statusGraphics.Dispose(); $bitmap.Dispose() }
}

$pcStatusDefinitions = [ordered]@{
    'pc_disconnected' = (-join [char[]](0x672A, 0x8FDE, 0x63A5, 0x5230)) + 'PC'
    'pc_connected'    = (-join [char[]](0x5DF2, 0x8FDE, 0x63A5, 0x5230)) + 'PC'
}
foreach($pcStatus in $pcStatusDefinitions.GetEnumerator()) {
    $bitmap = [System.Drawing.Bitmap]::new(76, 18, [System.Drawing.Imaging.PixelFormat]::Format32bppArgb)
    $statusGraphics = [System.Drawing.Graphics]::FromImage($bitmap)
    $statusFont = New-PixelFont 'Microsoft YaHei UI' 12
    try {
        $statusGraphics.Clear([System.Drawing.Color]::White)
        $statusGraphics.TextRenderingHint = [System.Drawing.Text.TextRenderingHint]::SingleBitPerPixelGridFit
        Draw-Text $statusGraphics $pcStatus.Value $statusFont 2 0
        Convert-ToOneBitPreview $bitmap
        $bitmap.Save((Join-Path $generatedDir "$($pcStatus.Key).png"), [System.Drawing.Imaging.ImageFormat]::Png)
    }
    finally { $statusFont.Dispose(); $statusGraphics.Dispose(); $bitmap.Dispose() }
}

& $python $lvglConverter --ofmt C --cf I1 --background 0xffffff --align 1 `
    --output $cAssetDir --name ui_screen_base (Join-Path $generatedDir 'screen_base.png')
if($LASTEXITCODE -ne 0) { throw 'Could not convert the screen base to an LVGL image.' }
& $python $lvglConverter --ofmt C --cf I1 --background 0xffffff --align 1 `
    --output $cAssetDir --name ui_performance_base (Join-Path $generatedDir 'performance_base.png')
if($LASTEXITCODE -ne 0) { throw 'Could not convert the performance base to an LVGL image.' }
& $python $lvglConverter --ofmt C --cf I1 --background 0xffffff --align 1 `
    --output $cAssetDir --name ui_syna_base (Join-Path $generatedDir 'syna_base.png')
if($LASTEXITCODE -ne 0) { throw 'Could not convert the Syna base to an LVGL image.' }
foreach($synaAssetName in @('syna_wallet', 'syna_speech', 'syna_todo_checked', 'syna_todo_unchecked')) {
    & $python $lvglConverter --ofmt C --cf I1 --background 0xffffff --align 1 `
        --output $cAssetDir --name "ui_$synaAssetName" (Join-Path $generatedDir "$synaAssetName.png")
    if($LASTEXITCODE -ne 0) { throw "Could not convert $synaAssetName to an LVGL image." }
}
foreach($statusName in $statusDefinitions.Keys) {
    & $python $lvglConverter --ofmt C --cf I1 --background 0xffffff --align 1 `
        --output $cAssetDir --name "ui_$statusName" (Join-Path $generatedDir "$statusName.png")
    if($LASTEXITCODE -ne 0) { throw "Could not convert $statusName to an LVGL image." }
}
foreach($wifiStatusName in $wifiStatusDefinitions.Keys) {
    & $python $lvglConverter --ofmt C --cf I1 --background 0xffffff --align 1 `
        --output $cAssetDir --name "ui_$wifiStatusName" (Join-Path $generatedDir "$wifiStatusName.png")
    if($LASTEXITCODE -ne 0) { throw "Could not convert $wifiStatusName to an LVGL image." }
}
foreach($pcStatusName in $pcStatusDefinitions.Keys) {
    & $python $lvglConverter --ofmt C --cf I1 --background 0xffffff --align 1 `
        --output $cAssetDir --name "ui_$pcStatusName" (Join-Path $generatedDir "$pcStatusName.png")
    if($LASTEXITCODE -ne 0) { throw "Could not convert $pcStatusName to an LVGL image." }
}
Write-Host "Generated one-bit UI assets in $cAssetDir"
