#!/usr/bin/env bash
# build.sh — create standalone `doer` binary via PyInstaller
set -euo pipefail

cd "$(dirname "$0")"

PLATFORM="$(uname -s | tr '[:upper:]' '[:lower:]')-$(uname -m)"
OUT="dist/doer-${PLATFORM}"

echo "🦆 building doer for ${PLATFORM}..."

# ensure deps
python3 -m pip install --quiet --upgrade pip pyinstaller strands-agents

# build
python3 -m PyInstaller \
  --onefile \
  --name "doer-${PLATFORM}" \
  --clean \
  --noconfirm \
  --strip \
  --add-data "doer/__init__.py:doer" \
  --hidden-import strands \
  --hidden-import strands.handlers.callback_handler \
  --hidden-import strands.agent.conversation_manager \
  --collect-all strands \
  doer/__init__.py

ls -lh "dist/doer-${PLATFORM}"
echo "✅ binary: $(pwd)/dist/doer-${PLATFORM}"
