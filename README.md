# doer

one-file pipe-native agent. `strands-agents` only. ~100 LOC.

```bash
pip install doer

doer "list files modified today"
echo "some text" | doer "summarize"
git log -5 | doer "tldr"
```

## python

```python
import doer
doer("fix this bug")
```

## hot-reload tools

drop a `@tool` fn in `./tools/*.py` — strands auto-loads it.

```python
# tools/greet.py
from strands import tool

@tool
def greet(name: str) -> str:
    """Say hi."""
    return f"hi {name}!"
```

Apache-2.0.

## install as binary (no python needed)

download from [releases](https://github.com/cagataycali/doer/releases):

```bash
# linux / macos (one-liner)
curl -sSL https://github.com/cagataycali/doer/releases/latest/download/doer-$(uname -s | tr A-Z a-z)-$(uname -m) -o /usr/local/bin/doer
chmod +x /usr/local/bin/doer
```

or build yourself:

```bash
./build.sh   # writes dist/doer-<platform>
```
