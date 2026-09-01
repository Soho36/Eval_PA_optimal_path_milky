$ErrorActionPreference = 'Stop'

$verifiedRunner = Join-Path $PSScriptRoot 'run_verified_tests.ps1'
& $verifiedRunner
exit $LASTEXITCODE
