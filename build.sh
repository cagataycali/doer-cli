#!/usr/bin/env bash
# build.sh — create standalone `doer` binary via PyInstaller (+ optional UPX)
set -euo pipefail

cd "$(dirname "$0")"

PLATFORM="$(uname -s | tr '[:upper:]' '[:lower:]')-$(uname -m)"
NAME="doer-${PLATFORM}"

echo "🦆 building ${NAME}..."

python3 -m pip install --quiet --upgrade pip pyinstaller strands-agents

UPX_ARGS=()
if command -v upx >/dev/null 2>&1; then
  UPX_DIR="$(dirname "$(command -v upx)")"
  UPX_ARGS=(--upx-dir "${UPX_DIR}")
  echo "🗜  UPX: $(upx --version | head -1)"
else
  echo "⚠  upx not found — skipping compression"
fi

python3 -m PyInstaller \
  --onefile \
  --name "${NAME}" \
  --clean \
  --noconfirm \
  --strip \
  "${UPX_ARGS[@]}" \
  --add-data "doer/__init__.py:doer" \
  --hidden-import strands \
  --hidden-import strands.handlers.callback_handler \
  --hidden-import strands.agent.conversation_manager \
  --collect-all strands \
  doer/__init__.py

ls -lh "dist/${NAME}"
echo "✅ binary: $(pwd)/dist/${NAME}"
