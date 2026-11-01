# Revo AI BIM bootstrap
#
# Creates the Python virtual environment, installs pinned dependencies and
# builds the .NET solution. Safe to re-run.

[CmdletBinding()]
param(
    [ValidateSet('2026', '2027')]
    [string]$RevitVersion = '2026',
    [switch]$SkipBuild
)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
Push-Location $root

try {
    Write-Host '=== Revo AI BIM bootstrap ===' -ForegroundColor Cyan

    foreach ($tool in @('dotnet', 'git')) {
        if (-not (Get-Command $tool -ErrorAction SilentlyContinue)) {
            throw "Required tool '$tool' was not found on PATH."
        }
    }

    if (-not (Get-Command py -ErrorAction SilentlyContinue) -and -not (Get-Command python -ErrorAction SilentlyContinue)) {
        throw 'Python 3.11+ was not found. Install Python 3.14 and ensure the py launcher is on PATH.'
    }

    if (-not (Test-Path '.venv\Scripts\python.exe')) {
        Write-Host 'Creating .venv with Python 3.14...'
        py -3.14 -m venv .venv
    }

    $python = Join-Path $root '.venv\Scripts\python.exe'
    Write-Host "Python: $python"

    & $python -m pip install --upgrade pip --disable-pip-version-check
    & $python -m pip install -r requirements-dev.in --disable-pip-version-check
    & $python -m pip install -e src\RevoAI.Engine -e src\RevoAI.Geometry --disable-pip-version-check

    & $python -c "import revoai_engine, revoai_geometry, open3d, numpy, scipy, laspy, pye57; print('Python imports OK:', revoai_engine.__version__, revoai_geometry.__version__, 'open3d', open3d.__version__, 'pye57', pye57.__version__)"

    if (-not $SkipBuild) {
        Write-Host "Building .NET solution for Revit $RevitVersion..."
        dotnet build RevoAI.slnx -c Debug -p:RevitVersion=$RevitVersion --nologo
    }

    Write-Host 'Bootstrap complete.' -ForegroundColor Green
}
finally {
    Pop-Location
}
