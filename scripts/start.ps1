param(
    [switch]$NoBrowser
)

$ErrorActionPreference = "Stop"
$root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$python = Join-Path $root ".venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $python)) {
    throw "Virtual environment not found. Run .\scripts\setup.ps1 first."
}

Set-Location $root
if (-not $NoBrowser) {
    Start-Process "http://127.0.0.1:8000/"
}
& $python -m news_alpha.webapp
