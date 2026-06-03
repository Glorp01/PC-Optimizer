#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

python3 -m pip install --upgrade pip
python3 -m pip install -r requirements-dev.txt

python3 -m PyInstaller \
  --noconfirm \
  --clean \
  --windowed \
  --name PCOptimizer \
  --specpath build \
  main.py

cd dist
rm -f PCOptimizer-macOS.zip
ditto -c -k --sequesterRsrc --keepParent PCOptimizer.app PCOptimizer-macOS.zip

echo "Built dist/PCOptimizer.app"
echo "Built dist/PCOptimizer-macOS.zip"
