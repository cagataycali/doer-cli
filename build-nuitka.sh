#!/usr/bin/env bash
# build-nuitka.sh — native compile via Nuitka
set -euo pipefail

cd "$(dirname "$0")"

PLATFORM="$(uname -s | tr '[:upper:]' '[:lower:]')-$(uname -m)"
NAME="doer-nuitka-${PLATFORM}"

echo "🦆 nuitka compiling ${NAME}..."

python3 -m pip install --quiet --upgrade pip nuitka ordered-set strands-agents

# compile package with __main__ as entry
python3 -m nuitka \
  --onefile \
  --standalone \
  --follow-imports \
  --include-package=strands \
  --include-package-data=strands \
  --include-data-file=doer/__init__.py=doer/__init__.py \
  --output-dir=dist \
  --output-filename="${NAME}" \
  --assume-yes-for-downloads \
  --remove-output \
  --module-name-choice=runtime \
  doer
