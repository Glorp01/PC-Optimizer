#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

python3 -m pip install --upgrade pip
python3 -m pip install -r requirements-dev.txt

VERSION="${APP_VERSION:-0.0.0-dev}"
SAFE_VERSION="$(printf "%s" "$VERSION" | tr -cd '0-9A-Za-z._-')"
if [ -z "$SAFE_VERSION" ]; then
  SAFE_VERSION="0.0.0-dev"
fi
printf "APP_VERSION = '%s'\n" "$SAFE_VERSION" > _build_info.py
echo "Embedding app version: $SAFE_VERSION"

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
