param(
    [string]$OutputPath = "flatten_repo.txt"
)

# Always anchor to the script's directory
$scriptRoot = if ($PSScriptRoot) { $PSScriptRoot } else { Split-Path -Parent $PSCommandPath }
Set-Location -LiteralPath $scriptRoot

$outFile = if ([IO.Path]::IsPathRooted($OutputPath)) { $OutputPath } else { Join-Path $scriptRoot $OutputPath }

# Paths/files that should be skipped when flattening
$excludePrefixes = @(
    ".git",
    ".venv",
    ".playwright-profile",
    ".playwright-browsers",
    "playwright-browsers",
    "logs",
    "outputs",
    "node_modules",
    "dist",
    "build"
)
$excludeExtensions = @(".exe", ".dll", ".pyd", ".so", ".bin", ".dat", ".jpg", ".jpeg", ".png", ".gif", ".zip", ".tar", ".gz", ".7z")

Write-Host "Flattening repository from $scriptRoot to $outFile..."
Remove-Item -LiteralPath $outFile -ErrorAction SilentlyContinue

Get-ChildItem -Recurse -File -ErrorAction SilentlyContinue |
    Where-Object {
        $rel = Resolve-Path -LiteralPath $_.FullName -Relative
        $prefixHit = ($excludePrefixes | Where-Object { $rel -like "$_`*" }).Count -gt 0
        $extensionHit = ($excludeExtensions | Where-Object { $rel.ToLower().EndsWith($_) }).Count -gt 0
        -not $prefixHit -and -not $extensionHit
    } |
    Sort-Object FullName |
    ForEach-Object {
        $rel = Resolve-Path -LiteralPath $_.FullName -Relative
        Add-Content -LiteralPath $outFile -Value "===== $rel =====" -Encoding UTF8
        try {
            Get-Content -LiteralPath $_.FullName -ErrorAction Stop | Add-Content -LiteralPath $outFile -Encoding UTF8
        } catch {
            Add-Content -LiteralPath $outFile -Value "[[unreadable or binary content]]" -Encoding UTF8
        }
        Add-Content -LiteralPath $outFile -Value "" -Encoding UTF8
    }

Write-Host "Flattened repository content written to $outFile"
