# Builds the Revit add-in and its tests for one or both installed Revit versions.

[CmdletBinding()]
param(
    [ValidateSet('2025', '2026', '2027', 'all')]
    [string]$RevitVersion = '2026',
    [ValidateSet('Debug', 'Release')]
    [string]$Configuration = 'Debug'
)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
Push-Location $root

try {
    $versions = if ($RevitVersion -eq 'all') { @('2026', '2027') } else { @($RevitVersion) }

    foreach ($version in $versions) {
        Write-Host "=== Building Revit $version ($Configuration) ===" -ForegroundColor Cyan
        dotnet build RevoAI.slnx -c $Configuration -p:RevitVersion=$version --nologo
        if ($LASTEXITCODE -ne 0) { throw "Build failed for Revit $version." }
    }

    Write-Host 'Build complete.' -ForegroundColor Green
}
finally {
    Pop-Location
}
