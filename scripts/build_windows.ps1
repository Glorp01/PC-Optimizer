$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

python -m pip install --upgrade pip
python -m pip install -r requirements-dev.txt

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
