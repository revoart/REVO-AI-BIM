# Generates the Revo AI BIM ribbon icons (32 px and 16 px PNGs).
# Re-run only when the visual language changes; outputs are committed.

$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Drawing

$root = Split-Path -Parent $PSScriptRoot
$outDir = Join-Path $root 'src\RevoAI.Revit\Resources\Icons'
New-Item -ItemType Directory -Force -Path $outDir | Out-Null

$blue = [System.Drawing.Color]::FromArgb(255, 47, 128, 237)
$green = [System.Drawing.Color]::FromArgb(255, 34, 160, 107)

function New-Icon {
    param(
        [string]$Name,
        [System.Drawing.Color]$Color,
        [scriptblock]$Draw
    )

    $size = 32
    $bmp = New-Object System.Drawing.Bitmap($size, $size, [System.Drawing.Imaging.PixelFormat]::Format32bppArgb)
    $g = [System.Drawing.Graphics]::FromImage($bmp)
    $g.SmoothingMode = [System.Drawing.Drawing2D.SmoothingMode]::AntiAlias
    $g.Clear([System.Drawing.Color]::Transparent)

    $pen = New-Object System.Drawing.Pen($Color, 2.2)
    $pen.StartCap = [System.Drawing.Drawing2D.LineCap]::Round
    $pen.EndCap = [System.Drawing.Drawing2D.LineCap]::Round
    $brush = New-Object System.Drawing.SolidBrush($Color)

    & $Draw $g $pen $brush

    $bmp.Save((Join-Path $outDir "$Name-32.png"), [System.Drawing.Imaging.ImageFormat]::Png)

    $small = New-Object System.Drawing.Bitmap(16, 16, [System.Drawing.Imaging.PixelFormat]::Format32bppArgb)
    $sg = [System.Drawing.Graphics]::FromImage($small)
    $sg.InterpolationMode = [System.Drawing.Drawing2D.InterpolationMode]::HighQualityBicubic
    $sg.SmoothingMode = [System.Drawing.Drawing2D.SmoothingMode]::AntiAlias
    $sg.DrawImage($bmp, 0, 0, 16, 16)
    $small.Save((Join-Path $outDir "$Name-16.png"), [System.Drawing.Imaging.ImageFormat]::Png)

    $sg.Dispose(); $small.Dispose(); $brush.Dispose(); $pen.Dispose(); $g.Dispose(); $bmp.Dispose()
}

New-Icon -Name 'workspace' -Color $blue -Draw {
    param($g, $pen, $brush)
    $g.DrawRectangle($pen, 7, 8, 18, 18)
    $g.DrawLine($pen, 7, 14, 25, 14)
    $g.DrawLine($pen, 16, 14, 16, 26)
    $g.DrawRectangle($pen, 10, 17, 3, 3)
}

New-Icon -Name 'import' -Color $blue -Draw {
    param($g, $pen, $brush)
    $g.DrawLine($pen, 7, 22, 25, 22)
    $g.DrawLine($pen, 16, 6, 16, 19)
    $g.DrawLine($pen, 11, 14, 16, 19)
    $g.DrawLine($pen, 21, 14, 16, 19)
}

New-Icon -Name 'analysis' -Color $blue -Draw {
    param($g, $pen, $brush)
    $g.DrawEllipse($pen, 6, 6, 14, 14)
    $g.DrawLine($pen, 18, 18, 26, 26)
}

New-Icon -Name 'generate' -Color $blue -Draw {
    param($g, $pen, $brush)
    $g.DrawLine($pen, 16, 5, 27, 11)
    $g.DrawLine($pen, 27, 11, 16, 17)
    $g.DrawLine($pen, 16, 17, 5, 11)
    $g.DrawLine($pen, 5, 11, 16, 5)
    $g.DrawLine($pen, 5, 11, 5, 22)
    $g.DrawLine($pen, 5, 22, 16, 28)
    $g.DrawLine($pen, 16, 28, 27, 22)
    $g.DrawLine($pen, 27, 22, 27, 11)
    $g.DrawLine($pen, 16, 17, 16, 28)
}

New-Icon -Name 'review' -Color $blue -Draw {
    param($g, $pen, $brush)
    $g.DrawEllipse($pen, 4, 10, 24, 12)
    $g.FillEllipse($brush, 13, 13, 6, 6)
}

New-Icon -Name 'quality' -Color $green -Draw {
    param($g, $pen, $brush)
    $g.DrawEllipse($pen, 5, 5, 22, 22)
    $g.DrawLine($pen, 10, 16, 14, 20)
    $g.DrawLine($pen, 14, 20, 22, 11)
}

New-Icon -Name 'settings' -Color $blue -Draw {
    param($g, $pen, $brush)
    $g.DrawLine($pen, 6, 10, 26, 10)
    $g.DrawLine($pen, 6, 16, 26, 16)
    $g.DrawLine($pen, 6, 22, 26, 22)
    $g.FillEllipse($brush, 10, 7.5, 5, 5)
    $g.FillEllipse($brush, 19, 13.5, 5, 5)
    $g.FillEllipse($brush, 13, 19.5, 5, 5)
}

New-Icon -Name 'about' -Color $blue -Draw {
    param($g, $pen, $brush)
    $g.DrawEllipse($pen, 5, 5, 22, 22)
    $g.FillEllipse($brush, 14.5, 9, 3, 3)
    $g.DrawLine($pen, 16, 14, 16, 22)
}

Get-ChildItem $outDir | Select-Object Name, Length | Format-Table -AutoSize
