$ErrorActionPreference = 'Stop'

$projectRoot = Split-Path -Parent $PSScriptRoot
$env:PYTHONPATH = Join-Path $projectRoot 'src'
$candidates = @(
    (Join-Path $projectRoot 'venv\Scripts\python.exe'),
    (Join-Path $projectRoot '.venv\Scripts\python.exe'),
    'C:\Program Files\Python312\python.exe'
)
$projectPython = $candidates |
    Where-Object { Test-Path -LiteralPath $_ } |
    Select-Object -First 1
if (-not $projectPython) {
    $command = Get-Command python -ErrorAction Stop
    $projectPython = $command.Source
}

& $projectPython -B -m unittest discover `
    -s (Join-Path $projectRoot 'tests') `
    -v
$testExitCode = $LASTEXITCODE
if ($testExitCode -ne 0) {
    Write-Error "Contract tests failed with exit code $testExitCode"
    exit $testExitCode
}

exit 0
