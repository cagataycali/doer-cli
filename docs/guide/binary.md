# Standalone Binary

Build a single executable with no Python dependency.

## PyInstaller (default)

```bash
./build.sh
```

Produces `dist/doer-<platform>` (e.g. `doer-darwin-arm64`, `doer-linux-x86_64`).

### What it does

- Installs `pyinstaller`, `strands-agents`.
- Optional UPX compression if installed (`brew install upx` or `apt install upx-ucl`).
- Uses `--onefile` — single executable.
- Bundles `doer/__init__.py` as data so `_source()` works in frozen mode.
- Collects all of `strands` (hidden imports).

## Nuitka (native compile)

```bash
./build-nuitka.sh
```

Produces `dist/doer-nuitka-<platform>`. Native C compile — smaller, faster startup, longer build.

## Spec File

`doer-darwin-arm64.spec` — reference spec for customization. Edit it and run:

```bash
pyinstaller doer-darwin-arm64.spec
```

## Install Globally

```bash
sudo mv dist/doer-darwin-arm64 /usr/local/bin/doer
doer "hello"
```

## Pre-built Releases

CI builds binaries on tag push. Download from [Releases](https://github.com/cagataycali/doer/releases):

```bash
curl -sSL https://github.com/cagataycali/doer/releases/latest/download/doer-$(uname -s | tr A-Z a-z)-$(uname -m) -o /usr/local/bin/doer
chmod +x /usr/local/bin/doer
```

## Size

- PyInstaller + UPX: ~15-30 MB
- Nuitka: ~20-40 MB

Most of it is the strands-agents package + Python runtime.

## Self-Awareness in Frozen Binary

The spec bundles `doer/__init__.py` as data:

```python
datas = [('doer/__init__.py', 'doer')]
```

At runtime, `_source()` reads from `sys._MEIPASS` (PyInstaller's temp extract dir). The agent sees its own code even when frozen.
