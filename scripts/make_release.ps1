$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$Root = Split-Path -Parent $ScriptDir
$DistRoot = Join-Path $Root "dist"
$VersionFile = Join-Path $Root "src\version.py"
$VersionMatch = Select-String -Path $VersionFile -Pattern '^__version__\s*=\s*"([^"]+)"' | Select-Object -First 1
if (-not $VersionMatch) {
    throw "Cannot read version from src\version.py"
}
$Version = $VersionMatch.Matches[0].Groups[1].Value
$PackageName = "forza-painter-fh6-v$Version"
$PackageDir = Join-Path $DistRoot $PackageName
$ZipPath = Join-Path $DistRoot "$PackageName.zip"

$include = @(
    "README.md",
    "README.zh-CN.md",
    "requirements.txt",
    "requirements-preview.txt",
    "install_dependencies.bat",
    "check_environment.bat",
    "clean_runtime_data.bat",
    "LICENSE",
    ".gitignore",
    "1. drag_image_file_here.bat",
    "start_app.bat",
    "src",
    "bin",
    "config",
    "assets",
    "docs"
)

if (Test-Path $PackageDir) {
    Remove-Item -LiteralPath $PackageDir -Recurse -Force
}
New-Item -ItemType Directory -Path $PackageDir | Out-Null

foreach ($item in $include) {
    $source = Join-Path $Root $item
    if (!(Test-Path $source)) {
        Write-Warning "Skipping missing item: $item"
        continue
    }
    $destination = Join-Path $PackageDir $item
    if ((Get-Item $source).PSIsContainer) {
        Copy-Item -LiteralPath $source -Destination $destination -Recurse
    } else {
        New-Item -ItemType Directory -Path (Split-Path -Parent $destination) -Force | Out-Null
        Copy-Item -LiteralPath $source -Destination $destination
    }
}

Get-ChildItem -Path $PackageDir -Recurse -Directory -Include "__pycache__", ".pytest_cache" -ErrorAction SilentlyContinue |
    Remove-Item -Recurse -Force
Get-ChildItem -Path $PackageDir -Recurse -File -Include "*.pyc", "*.pyo", "*.log" -ErrorAction SilentlyContinue |
    Remove-Item -Force

if (Test-Path $ZipPath) {
    Remove-Item -LiteralPath $ZipPath -Force
}
Compress-Archive -Path (Join-Path $PackageDir "*") -DestinationPath $ZipPath
Write-Host "Release package written to $ZipPath"
