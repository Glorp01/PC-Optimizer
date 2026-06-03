$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

python -m pip install --upgrade pip
python -m pip install -r requirements-dev.txt

$Version = $env:APP_VERSION
if ([string]::IsNullOrWhiteSpace($Version)) {
    $Version = "0.0.0-dev"
}
$SafeVersion = $Version -replace "[^0-9A-Za-z._-]", ""
if ([string]::IsNullOrWhiteSpace($SafeVersion)) {
    $SafeVersion = "0.0.0-dev"
}
Set-Content -LiteralPath (Join-Path $Root "_build_info.py") -Value "APP_VERSION = '$SafeVersion'`n" -Encoding UTF8
Write-Host "Embedding app version: $SafeVersion"

python -m PyInstaller `
    --noconfirm `
    --clean `
    --onefile `
    --windowed `
    --name PCOptimizer `
    --specpath build `
    main.py

$PackageDir = Join-Path $Root "dist\PCOptimizer-Windows-Portable"
New-Item -ItemType Directory -Force -Path $PackageDir | Out-Null
Copy-Item -Path (Join-Path $Root "dist\PCOptimizer.exe") -Destination $PackageDir -Force
Copy-Item -Path (Join-Path $Root "README.md") -Destination $PackageDir -Force

$ZipPath = Join-Path $Root "dist\PCOptimizer-Windows-Portable.zip"
if (Test-Path -LiteralPath $ZipPath) {
    Remove-Item -LiteralPath $ZipPath -Force
}

Compress-Archive -Path (Join-Path $PackageDir "*") -DestinationPath $ZipPath

Write-Host "Built dist\PCOptimizer.exe"
Write-Host "Built dist\PCOptimizer-Windows-Portable.zip"
