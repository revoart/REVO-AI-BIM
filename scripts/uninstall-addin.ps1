# Removes the developer installation of Revo AI BIM for one Revit version.

[CmdletBinding()]
param(
    [ValidateSet('2026', '2027')]
    [string]$RevitVersion = '2026'
)

$ErrorActionPreference = 'Stop'

$addinRoot = Join-Path $env:APPDATA "Autodesk\Revit\Addins\$RevitVersion"
$manifest = Join-Path $addinRoot 'RevoAI.Revit.addin'
$installDir = Join-Path $addinRoot 'RevoAI'

if (Test-Path $manifest) { Remove-Item $manifest -Force }
if (Test-Path $installDir) { Remove-Item $installDir -Recurse -Force }

Write-Host "Removed Revo AI BIM from Revit $RevitVersion." -ForegroundColor Green
