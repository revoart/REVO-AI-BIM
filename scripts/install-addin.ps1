# Registers the Revo AI BIM add-in for one installed Revit version.
#
# Layout produced:
#   %APPDATA%\Autodesk\Revit\Addins\<version>\RevoAI.Revit.addin
#   %APPDATA%\Autodesk\Revit\Addins\<version>\RevoAI\RevoAI.Revit.dll
#
# This is a developer install. Phase 10 replaces it with a signed installer.

[CmdletBinding()]
param(
    [ValidateSet('2026', '2027')]
    [string]$RevitVersion = '2026',
    [ValidateSet('Debug', 'Release')]
    [string]$Configuration = 'Debug'
)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
Push-Location $root

try {
    $buildDir = Join-Path $root "src\RevoAI.Revit\bin\$Configuration\$RevitVersion"
    if (-not (Test-Path (Join-Path $buildDir 'RevoAI.Revit.dll'))) {
        throw "Build output not found at $buildDir. Run scripts\build.ps1 -RevitVersion $RevitVersion first."
    }

    $addinRoot = Join-Path $env:APPDATA "Autodesk\Revit\Addins\$RevitVersion"
    $installDir = Join-Path $addinRoot 'RevoAI'
    New-Item -ItemType Directory -Force -Path $installDir | Out-Null

    Copy-Item (Join-Path $buildDir 'RevoAI.Revit.dll') $installDir -Force
    Copy-Item (Join-Path $buildDir 'RevoAI.Contracts.dll') $installDir -Force

    $pdb = Join-Path $buildDir 'RevoAI.Revit.pdb'
    if (Test-Path $pdb) { Copy-Item $pdb $installDir -Force }

    $deps = Join-Path $buildDir 'RevoAI.Revit.deps.json'
    if (Test-Path $deps) { Copy-Item $deps $installDir -Force }

    $manifest = @"
<?xml version="1.0" encoding="utf-8"?>
<RevitAddIns>
  <AddIn Type="Application">
    <Name>Revo AI BIM</Name>
    <Assembly>RevoAI\RevoAI.Revit.dll</Assembly>
    <FullClassName>RevoAI.Revit.App</FullClassName>
    <ClientId>6bf9f9a2-2940-47bc-bd99-d14db67ecab8</ClientId>
    <VendorId>REVOSTUDIOZ</VendorId>
    <VendorDescription>RevoStudioz</VendorDescription>
  </AddIn>
</RevitAddIns>
"@

    $manifestPath = Join-Path $addinRoot 'RevoAI.Revit.addin'
    Set-Content -Path $manifestPath -Value $manifest -Encoding UTF8

    # Developer convenience: point the engine at this repository if no
    # machine configuration exists yet. Phase 10 replaces this with installer
    # defaults. Existing configuration is never overwritten.
    $configPath = Join-Path $env:APPDATA 'RevoAI\config.json'
    if (-not (Test-Path $configPath)) {
        New-Item -ItemType Directory -Force -Path (Split-Path $configPath) | Out-Null
        $venvPython = Join-Path $root '.venv\Scripts\python.exe'
        $config = [ordered]@{
            engineRoot = $root
            startupTimeoutSeconds = 60
            requestTimeoutSeconds = 120
        }
        if (Test-Path $venvPython) {
            $config.pythonExecutable = $venvPython
        }
        $config | ConvertTo-Json | Set-Content -Path $configPath -Encoding UTF8
        Write-Host "Wrote developer configuration: $configPath" -ForegroundColor Yellow
    }

    Write-Host "Installed Revo AI BIM for Revit $RevitVersion." -ForegroundColor Green
    Write-Host "  Manifest: $manifestPath"
    Write-Host "  Assemblies: $installDir"
    Write-Host ''
    Write-Host 'Start Revit and check the Revo AI BIM log at:' -ForegroundColor Yellow
    Write-Host "  $env:LOCALAPPDATA\RevoAI\logs\revoai-$(Get-Date -Format 'yyyyMMdd').log"
}
finally {
    Pop-Location
}
