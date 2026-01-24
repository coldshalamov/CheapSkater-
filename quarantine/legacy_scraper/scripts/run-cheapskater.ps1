[CmdletBinding()]
param(
    [switch]$Continuous,
    [string]$Zips,
    [string]$Categories
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
if (-not $repoRoot) {
    $repoRoot = $PSScriptRoot
}

function Resolve-Python {
    $targets = @("3.12", "3.11", "3.10")
    foreach ($ver in $targets) {
        try {
            $candidate = & py -$ver -c "import sys; print(sys.executable)" 2>$null
            if ($LASTEXITCODE -eq 0 -and $candidate) {
                return $candidate.Trim()
            }
        } catch {
        }
    }

    try {
        $candidate = & py -3 -c "import sys; print(sys.executable)" 2>$null
        if ($LASTEXITCODE -eq 0 -and $candidate) {
            return $candidate.Trim()
        }
    } catch {
    }

    $pythonCmd = Get-Command python -ErrorAction SilentlyContinue
    if ($pythonCmd) {
        return $pythonCmd.Source
    }
    return $null
}

$pythonExe = Resolve-Python
if (-not $pythonExe) {
    throw "Unable to locate Python 3.10+ via the 'py' launcher or PATH. Install Python 3.12 from the Microsoft Store first."
}

$pyVersion = (& $pythonExe -c "import platform; print(platform.python_version())").Trim()
if (-not $pyVersion) {
    throw "Failed to read Python version from $pythonExe"
}

$parsedVersion = [version]$pyVersion
if ($parsedVersion.Major -gt 3 -or ($parsedVersion.Major -eq 3 -and $parsedVersion.Minor -gt 12)) {
    throw "CheapSkater currently supports up to Python 3.12. Detected $pyVersion at $pythonExe."
}

$venvPath = Join-Path $repoRoot ".venv"
$venvPython = Join-Path $venvPath "Scripts\python.exe"

if (-not (Test-Path $venvPython)) {
    Write-Host "Creating virtual environment at $venvPath with $pythonExe"
    & $pythonExe -m venv $venvPath
}

Write-Host "Installing/updating pip inside the virtual environment..."
& $venvPython -m pip install --upgrade pip

Write-Host "Installing project dependencies (this can take a minute)..."
& $venvPython -m pip install -r (Join-Path $repoRoot "requirements.txt")

Write-Host "Ensuring Playwright browsers are installed..."
& $venvPython -m playwright install

$cliArgs = @()
if (-not $Continuous) {
    $cliArgs += "--once"
}
if ($Zips) {
    $cliArgs += "--zips"
    $cliArgs += $Zips
}
if ($Categories) {
    $cliArgs += "--categories"
    $cliArgs += $Categories
}

Write-Host ""
Write-Host "Launching CheapSkater via app.main $($cliArgs -join ' ')"
Write-Host ""

& $venvPython -m app.main @cliArgs
