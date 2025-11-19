param(
    [string]$OutputPath = "flatten_repo.txt"
)

# Anchor output to the script directory when a relative path is provided
$scriptRoot = if ($PSScriptRoot) { $PSScriptRoot } else { Split-Path -Parent $PSCommandPath }
$outFile = if ([IO.Path]::IsPathRooted($OutputPath)) {
    $OutputPath
} else {
    Join-Path $scriptRoot $OutputPath
}

# Paths that should be skipped when flattening
$excludePrefixes = @(
    ".git",
    ".venv",
    ".playwright-profile",
    ".playwright-browsers",
    "playwright-browsers",
    "logs",
    "outputs",
    "node_modules"
)

Remove-Item -LiteralPath $outFile -ErrorAction SilentlyContinue

Get-ChildItem -Recurse -File |
    Where-Object {
        $rel = Resolve-Path -LiteralPath $_.FullName -Relative
        # Skip excluded prefixes
        -not ($excludePrefixes | ForEach-Object { $rel -like "$_`*" })
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
