# Sends initialize/ping/shutdown to the Python engine over stdio and prints the
# raw protocol transcript. Use this to diagnose engine startup problems without
# launching Revit.

[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$python = Join-Path $root '.venv\Scripts\python.exe'

if (-not (Test-Path $python)) {
    throw 'Python environment missing. Run scripts\bootstrap.ps1 first.'
}

$env:PYTHONPATH = @(
    (Join-Path $root 'src\RevoAI.Engine'),
    (Join-Path $root 'src\RevoAI.Geometry')
) -join [IO.Path]::PathSeparator
$env:PYTHONUTF8 = '1'

$requests = @(
    '{"jsonRpc":"2.0","id":"1","method":"initialize","params":{"clientName":"smoke-test","clientVersion":"0.5.1","protocolVersion":"1.0"}}',
    '{"jsonRpc":"2.0","id":"2","method":"ping","params":{"message":"hello"}}',
    '{"jsonRpc":"2.0","id":"3","method":"shutdown"}'
) -join "`n"

$requests | & $python -m revoai_engine.service
