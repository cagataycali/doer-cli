#!/bin/sh
# doer — one-line installer
#   curl -sSL https://raw.githubusercontent.com/cagataycali/doer-cli/main/install.sh | sh
#
# Drops prebuilt `do` (and `doer` symlink) into ~/.local/bin or /usr/local/bin.

set -e

REPO="cagataycali/doer-cli"
# default install dir; override with DOER_INSTALL_DIR=/path sh install.sh
INSTALL_DIR="${DOER_INSTALL_DIR:-$HOME/.local/bin}"

# detect OS/arch
OS=$(uname -s | tr '[:upper:]' '[:lower:]')
ARCH=$(uname -m)
case "$OS-$ARCH" in
  darwin-arm64)    ASSET="doer-darwin-arm64" ;;
  darwin-x86_64)   ASSET="doer-darwin-x86_64" ;;
  linux-x86_64)    ASSET="doer-linux-x86_64" ;;
  linux-aarch64)   echo "no prebuilt for linux-aarch64 yet; use: pipx install doer-cli" >&2; exit 1 ;;
  *) echo "unsupported platform: $OS-$ARCH" >&2
     echo "fallback: pipx install doer-cli" >&2
     exit 1 ;;
esac

URL="https://github.com/${REPO}/releases/latest/download/${ASSET}"

echo "→ downloading $ASSET"
mkdir -p "$INSTALL_DIR"
TMP=$(mktemp -t doer.XXXXXX)
trap 'rm -f "$TMP"' EXIT

if ! curl -fsSL "$URL" -o "$TMP"; then
  echo "download failed: $URL" >&2
  echo "fallback: pipx install doer-cli" >&2
  exit 1
fi

chmod +x "$TMP"
mv "$TMP" "$INSTALL_DIR/do"
# symlink the long name
ln -sf "$INSTALL_DIR/do" "$INSTALL_DIR/doer"

echo "✓ installed:"
echo "    $INSTALL_DIR/do"
echo "    $INSTALL_DIR/doer -> do"

# PATH hint
case ":$PATH:" in
  *":$INSTALL_DIR:"*) ;;
  *) echo
     echo "⚠  $INSTALL_DIR is not in your PATH"
     echo "   add this to your shell rc:"
     echo "     export PATH=\"$INSTALL_DIR:\$PATH\""
     ;;
esac

echo
echo "try:  do \"hello\""
