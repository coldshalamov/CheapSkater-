$ErrorActionPreference = 'Stop'

param(
    [string]$Python = 'python'
)

$repoRoot = Resolve-Path (Join-Path $PSScriptRoot '..')
$venvDir = Join-Path $repoRoot '.venv'

if (-not (Test-Path $venvDir)) {
    Write-Host "Creating virtual environment at $venvDir"
    & $Python '-m' 'venv' $venvDir
}

$venvPython = Join-Path $venvDir 'Scripts\python.exe'
if (-not (Test-Path $venvPython)) {
    throw "Virtual environment python not found at $venvPython"
}

$venvPip = Join-Path $venvDir 'Scripts\pip.exe'

Write-Host 'Upgrading pip...'
& $venvPip 'install' '--upgrade' 'pip'

Write-Host 'Installing requirements...'
& $venvPip 'install' '-r' (Join-Path $repoRoot 'requirements.txt')

Write-Host 'Installing Playwright browsers...'
& $venvPython '-m' 'playwright' 'install'

Write-Host 'Running readiness verification...'
& $venvPython (Join-Path $repoRoot 'scripts\verify_readiness.py')

$exitCode = $LASTEXITCODE

if ($exitCode -eq 0) {
    Write-Host 'Self-check PASS'
} else {
    Write-Host 'Self-check FAIL'
}

exit $exitCode
