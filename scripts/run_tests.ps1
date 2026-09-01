$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$env:PYTHONPATH = Join-Path $projectRoot 'src'
$projectPython = Join-Path $projectRoot '.venv\Scripts\python.exe'

if (Test-Path -LiteralPath $projectPython) {
    & $projectPython -m unittest discover -s (Join-Path $projectRoot 'tests') -v
} elseif (Test-Path -LiteralPath 'C:\Program Files\Python312\python.exe') {
    & 'C:\Program Files\Python312\python.exe' -m unittest discover -s (Join-Path $projectRoot 'tests') -v
} else {
    & python -m unittest discover -s (Join-Path $projectRoot 'tests') -v
}
