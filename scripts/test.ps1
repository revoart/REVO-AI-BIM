# Runs the .NET unit/integration tests and the Python test suites.

[CmdletBinding()]
param(
    [ValidateSet('2026', '2027')]
    [string]$RevitVersion = '2026',
    [switch]$SkipDotnet,
    [switch]$SkipPython
)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
Push-Location $root

try {
    if (-not $SkipDotnet) {
        Write-Host '=== .NET tests ===' -ForegroundColor Cyan
        dotnet test tests\RevoAI.Revit.Tests\RevoAI.Revit.Tests.csproj -c Debug -p:RevitVersion=$RevitVersion --nologo
        if ($LASTEXITCODE -ne 0) { throw '.NET tests failed.' }
    }

    if (-not $SkipPython) {
        $python = Join-Path $root '.venv\Scripts\python.exe'
        if (-not (Test-Path $python)) {
            throw 'Python environment missing. Run scripts\bootstrap.ps1 first.'
        }

        Write-Host '=== Python tests ===' -ForegroundColor Cyan
        & $python -m pytest
        if ($LASTEXITCODE -ne 0) { throw 'Python tests failed.' }
    }

    Write-Host 'All tests passed.' -ForegroundColor Green
}
finally {
    Pop-Location
}
